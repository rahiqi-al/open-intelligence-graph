"""Day 3: load data/raw/openalex_sample.json into PostgreSQL (schema test)."""
import json
import os
import re
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

ALLOWED_TYPES = {"article", "conference-paper", "preprint"}
ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}|[a-z\-]+/\d{7})", re.I)


def short_id(url):
    """https://openalex.org/W123 -> W123"""
    return url.rsplit("/", 1)[-1] if url else None


def clean_doi(doi):
    if not doi:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi).lower()


def rebuild_abstract(inv):
    if not inv:
        return None
    pos = {i: w for w, idxs in inv.items() for i in idxs}
    return " ".join(pos[i] for i in sorted(pos))


def find_arxiv_id(work):
    for loc in work.get("locations") or []:
        for key in ("landing_page_url", "pdf_url"):
            m = ARXIV_RE.search(loc.get(key) or "")
            if m:
                return m.group(1)
    return None


def upsert_one(cur, sql, params):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def load_work(cur, w):
    pdf_url = (w.get("best_oa_location") or {}).get("pdf_url")
    paper_id = upsert_one(
        cur,
        """
        INSERT INTO papers (openalex_id, doi, arxiv_id, title, abstract, publication_year,
                            publication_date, type, language, cited_by_count, is_open_access, pdf_url)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (openalex_id) DO UPDATE SET
            cited_by_count = EXCLUDED.cited_by_count,
            pdf_url = EXCLUDED.pdf_url
        RETURNING paper_id
        """,
        (
            short_id(w["id"]),
            clean_doi(w.get("doi")),
            find_arxiv_id(w),
            w["title"].strip(),
            rebuild_abstract(w.get("abstract_inverted_index")),
            w.get("publication_year"),
            w.get("publication_date"),
            w.get("type"),
            w.get("language"),
            w.get("cited_by_count") or 0,
            (w.get("open_access") or {}).get("is_oa"),
            pdf_url,
        ),
    )

    # authors + institutions
    for pos, a in enumerate(w.get("authorships") or [], start=1):
        author = a.get("author") or {}
        if not author.get("id"):
            continue
        author_id = upsert_one(
            cur,
            """
            INSERT INTO authors (openalex_id, orcid, display_name) VALUES (%s,%s,%s)
            ON CONFLICT (openalex_id) DO UPDATE SET display_name = EXCLUDED.display_name
            RETURNING author_id
            """,
            (short_id(author["id"]), author.get("orcid"), author.get("display_name") or "Unknown"),
        )
        cur.execute(
            "INSERT INTO paper_authors (paper_id, author_id, author_position) VALUES (%s,%s,%s) "
            "ON CONFLICT DO NOTHING",
            (paper_id, author_id, pos),
        )
        for inst in a.get("institutions") or []:
            if not inst.get("id"):
                continue
            inst_id = upsert_one(
                cur,
                """
                INSERT INTO institutions (openalex_id, name, country_code, type) VALUES (%s,%s,%s,%s)
                ON CONFLICT (openalex_id) DO UPDATE SET name = EXCLUDED.name
                RETURNING institution_id
                """,
                (short_id(inst["id"]), inst.get("display_name") or "Unknown",
                 inst.get("country_code"), inst.get("type")),
            )
            cur.execute(
                "INSERT INTO author_institutions (author_id, institution_id) VALUES (%s,%s) "
                "ON CONFLICT DO NOTHING",
                (author_id, inst_id),
            )

    # topics
    primary_id = (w.get("primary_topic") or {}).get("id")
    topics = w.get("topics") or ([w["primary_topic"]] if w.get("primary_topic") else [])
    for t in topics:
        if not t.get("id"):
            continue
        topic_id = upsert_one(
            cur,
            """
            INSERT INTO topics (openalex_id, name, subfield, field, domain) VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (openalex_id) DO UPDATE SET name = EXCLUDED.name
            RETURNING topic_id
            """,
            (short_id(t["id"]), t.get("display_name"),
             (t.get("subfield") or {}).get("display_name"),
             (t.get("field") or {}).get("display_name"),
             (t.get("domain") or {}).get("display_name")),
        )
        cur.execute(
            "INSERT INTO paper_topics (paper_id, topic_id, score, is_primary) VALUES (%s,%s,%s,%s) "
            "ON CONFLICT DO NOTHING",
            (paper_id, topic_id, t.get("score"), t["id"] == primary_id),
        )

    # references
    for ref in w.get("referenced_works") or []:
        cur.execute(
            "INSERT INTO paper_references (citing_paper_id, cited_openalex_id) VALUES (%s,%s) "
            "ON CONFLICT DO NOTHING",
            (paper_id, short_id(ref)),
        )


def main():
    works = json.loads(Path("data/raw/openalex_sample.json").read_text())
    loaded = skipped = failed = 0

    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    ) as conn:
        with conn.cursor() as cur:
            for w in works:
                if (
                    w.get("type") not in ALLOWED_TYPES
                    or not w.get("title")
                    or not w.get("abstract_inverted_index")
                ):
                    skipped += 1
                    continue
                try:
                    with conn.transaction():  # one savepoint per paper
                        load_work(cur, w)
                    loaded += 1
                except Exception as e:
                    failed += 1
                    print("FAILED:", w.get("id"), e)

    print(f"loaded={loaded} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()