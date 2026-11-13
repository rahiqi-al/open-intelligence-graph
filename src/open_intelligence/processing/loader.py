"""Write cleaned PaperRecords to PostgreSQL. Merges into an existing paper when an identity key matches."""
from open_intelligence.processing.models import PaperRecord

INSERT_PAPER = """
INSERT INTO papers (openalex_id, doi, arxiv_id, title, title_norm, abstract, publication_year,
    publication_date, type, language, cited_by_count, is_open_access, pdf_url, author_names, source)
VALUES (%(openalex_id)s, %(doi)s, %(arxiv_id)s, %(title)s, %(title_norm)s, %(abstract)s,
    %(publication_year)s, %(publication_date)s, %(type)s, %(language)s, %(cited_by_count)s,
    %(is_open_access)s, %(pdf_url)s, %(author_names)s, %(source)s)
RETURNING paper_id
"""

UPDATE_PAPER = """
UPDATE papers SET
    openalex_id      = COALESCE(openalex_id, %(openalex_id)s),
    doi              = COALESCE(doi, %(doi)s),
    arxiv_id         = COALESCE(arxiv_id, %(arxiv_id)s),
    title_norm       = COALESCE(title_norm, %(title_norm)s),
    abstract         = CASE WHEN length(%(abstract)s::text) > length(abstract)
                            THEN %(abstract)s::text ELSE abstract END,
    publication_year = COALESCE(publication_year, %(publication_year)s::int),
    publication_date = COALESCE(publication_date, %(publication_date)s::date),
    type             = COALESCE(type, %(type)s),
    language         = COALESCE(language, %(language)s),
    cited_by_count   = GREATEST(cited_by_count, %(cited_by_count)s::int),
    is_open_access   = COALESCE(is_open_access, %(is_open_access)s::boolean),
    pdf_url          = CASE WHEN starts_with(COALESCE(pdf_url, ''), 'https://arxiv.org/pdf/')
                            THEN pdf_url ELSE COALESCE(%(pdf_url)s::text, pdf_url) END,
    author_names     = CASE WHEN COALESCE(cardinality(%(author_names)s::text[]), 0)
                                 > COALESCE(cardinality(author_names), 0)
                            THEN %(author_names)s::text[] ELSE author_names END,
    source           = (SELECT string_agg(DISTINCT s, '+' ORDER BY s)
                        FROM unnest(string_to_array(source, '+') || %(sources)s::text[]) AS s)
WHERE paper_id = %(paper_id)s
"""


def _params(rec: PaperRecord) -> dict:
    return {
        "openalex_id": rec.openalex_id,
        "doi": rec.doi,
        "arxiv_id": rec.arxiv_id,
        "title": rec.title,
        "title_norm": rec.title_norm,
        "abstract": rec.abstract,
        "publication_year": rec.publication_year,
        "publication_date": rec.publication_date,
        "type": rec.type,
        "language": rec.language,
        "cited_by_count": rec.cited_by_count,
        "is_open_access": rec.is_open_access,
        "pdf_url": rec.pdf_url,
        "author_names": rec.author_names,
        "source": "+".join(sorted(rec.sources)),
        "sources": sorted(rec.sources),
    }


def find_paper_id(cur, rec: PaperRecord):
    """Find an existing paper by OpenAlex ID, arXiv ID, DOI, then by title + year (+/- 1)."""
    for column in ("openalex_id", "arxiv_id", "doi"):
        value = getattr(rec, column)
        if value:
            row = cur.execute(f"SELECT paper_id FROM papers WHERE {column} = %s", (value,)).fetchone()
            if row:
                return row[0]
    if len(rec.title_norm) >= 25 and rec.publication_year:
        row = cur.execute(
            "SELECT paper_id FROM papers WHERE title_norm = %s AND publication_year BETWEEN %s AND %s LIMIT 1",
            (rec.title_norm, rec.publication_year - 1, rec.publication_year + 1),
        ).fetchone()
        if row:
            return row[0]
    return None


def _save_authors(cur, paper_id: int, rec: PaperRecord) -> None:
    for a in rec.authors:
        author_id = cur.execute(
            """
            INSERT INTO authors (openalex_id, orcid, display_name) VALUES (%s, %s, %s)
            ON CONFLICT (openalex_id) DO UPDATE SET display_name = EXCLUDED.display_name
            RETURNING author_id
            """,
            (a["openalex_id"], a.get("orcid"), a.get("name") or "Unknown"),
        ).fetchone()[0]
        cur.execute(
            "INSERT INTO paper_authors (paper_id, author_id, author_position) VALUES (%s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            (paper_id, author_id, a.get("position")),
        )
        for inst in a["institutions"]:
            inst_id = cur.execute(
                """
                INSERT INTO institutions (openalex_id, name, country_code, type) VALUES (%s, %s, %s, %s)
                ON CONFLICT (openalex_id) DO UPDATE SET name = EXCLUDED.name
                RETURNING institution_id
                """,
                (inst["openalex_id"], inst.get("name") or "Unknown", inst.get("country_code"), inst.get("type")),
            ).fetchone()[0]
            cur.execute(
                "INSERT INTO author_institutions (author_id, institution_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (author_id, inst_id),
            )


def _save_topics(cur, paper_id: int, rec: PaperRecord) -> None:
    for t in rec.topics:
        topic_id = cur.execute(
            """
            INSERT INTO topics (openalex_id, name, subfield, field, domain) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (openalex_id) DO UPDATE SET name = EXCLUDED.name
            RETURNING topic_id
            """,
            (t["openalex_id"], t.get("name") or "Unknown", t.get("subfield"), t.get("field"), t.get("domain")),
        ).fetchone()[0]
        cur.execute(
            "INSERT INTO paper_topics (paper_id, topic_id, score, is_primary) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            (paper_id, topic_id, t.get("score"), t.get("is_primary", False)),
        )


def _save_references(cur, paper_id: int, rec: PaperRecord) -> None:
    if rec.references:
        cur.executemany(
            "INSERT INTO paper_references (citing_paper_id, cited_openalex_id) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            [(paper_id, ref) for ref in rec.references if ref],
        )


def save_paper(conn, rec: PaperRecord) -> str:
    """Insert or merge one paper with its authors, topics and references. Returns 'inserted' or 'merged'."""
    with conn.transaction():  # one transaction per paper: a failure only affects this paper
        with conn.cursor() as cur:
            paper_id = find_paper_id(cur, rec)
            if paper_id is None:
                paper_id = cur.execute(INSERT_PAPER, _params(rec)).fetchone()[0]
                outcome = "inserted"
            else:
                cur.execute(UPDATE_PAPER, {**_params(rec), "paper_id": paper_id})
                outcome = "merged"
            _save_authors(cur, paper_id, rec)
            _save_topics(cur, paper_id, rec)
            _save_references(cur, paper_id, rec)
    return outcome


def link_references(conn) -> int:
    """Point references at papers we have loaded. Returns how many are linked in total."""
    conn.execute(
        """
        UPDATE paper_references r SET cited_paper_id = p.paper_id
        FROM papers p
        WHERE r.cited_openalex_id = p.openalex_id AND r.cited_paper_id IS NULL
        """
    )
    return conn.execute("SELECT count(*) FROM paper_references WHERE cited_paper_id IS NOT NULL").fetchone()[0]