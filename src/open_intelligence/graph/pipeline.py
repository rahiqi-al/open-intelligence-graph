"""Build the Neo4j graph: metadata from Postgres + resolved entities from the LLM extractions."""
import logging

from open_intelligence.database import postgres
from open_intelligence.graph import entity_resolution, neo4j_store

logger = logging.getLogger(__name__)

QUERIES = {
    "papers": """SELECT paper_id, title, publication_year AS year, cited_by_count, doi, openalex_id, arxiv_id,
                        source, coalesce(access_level, 'public') AS access_level,
                        coalesce(has_full_text, FALSE) AS has_full_text FROM papers""",
    "authors": "SELECT author_id, display_name AS name, openalex_id, orcid FROM authors",
    "institutions": "SELECT institution_id, name, openalex_id, country_code, type FROM institutions",
    "topics": "SELECT topic_id, name, openalex_id, field FROM topics",
    "authored": "SELECT paper_id, author_id, author_position AS position FROM paper_authors",
    "affiliations": "SELECT author_id, institution_id FROM author_institutions",
    "paper_topics": "SELECT paper_id, topic_id, score FROM paper_topics",
    "citations": ("SELECT citing_paper_id AS citing, cited_paper_id AS cited FROM paper_references "
                  "WHERE cited_paper_id IS NOT NULL"),
}

EXTRACTIONS_SQL = """
SELECT e.paper_id, e.entities, e.relations, p.abstract
FROM paper_extractions e JOIN papers p ON p.paper_id = e.paper_id
WHERE e.status = 'done'
"""


def _fetch_dicts(conn, sql: str) -> list[dict]:
    cursor = conn.execute(sql)
    columns = [c.name for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def load_from_postgres() -> tuple[dict, list, dict]:
    with postgres.connect() as conn:
        tables = {name: _fetch_dicts(conn, sql) for name, sql in QUERIES.items()}
        extractions = conn.execute(EXTRACTIONS_SQL).fetchall()
    rows = [(paper_id, entities, relations) for paper_id, entities, relations, _ in extractions]
    abstracts = {paper_id: abstract or "" for paper_id, _e, _r, abstract in extractions}
    return tables, rows, abstracts


def build_graph(reset: bool = False, dry_run: bool = False) -> dict:
    tables, rows, abstracts = load_from_postgres()
    resolved = entity_resolution.resolve_entities(rows, abstracts)
    logger.info("entities: %s", resolved.stats)

    if dry_run:  # show what the resolution does, write nothing
        merged = sorted((e for e in resolved.entities if e["aliases"]), key=lambda e: -e["n_papers"])[:20]
        top = sorted(resolved.entities, key=lambda e: -e["n_papers"])[:15]
        return {"resolution": resolved.stats, "merged_examples": merged,
                "most_common": [(e["name"], e["type"], e["n_papers"]) for e in top]}

    driver = neo4j_store.get_driver()
    with driver.session() as session:
        if reset:
            neo4j_store.reset(session)
        neo4j_store.ensure_constraints(session)
        # nodes first, then relationships
        for name, writer in [("papers", neo4j_store.write_papers), ("authors", neo4j_store.write_authors),
                             ("institutions", neo4j_store.write_institutions), ("topics", neo4j_store.write_topics)]:
            logger.info("%s: %d", name, writer(session, tables[name]))
        logger.info("entities: %d", neo4j_store.write_entities(session, resolved.entities))
        for name, writer in [("authored", neo4j_store.write_authored), ("affiliations", neo4j_store.write_affiliations),
                             ("paper_topics", neo4j_store.write_paper_topics), ("citations", neo4j_store.write_citations)]:
            logger.info("%s: %d", name, writer(session, tables[name]))
        logger.info("paper-entity links: %d", neo4j_store.write_mentions(session, resolved.mentions))
        logger.info("entity relations: %d", neo4j_store.write_entity_relations(session, resolved.relations))
        result = neo4j_store.counts(session)
    driver.close()
    result["resolution"] = resolved.stats
    return result