"""Write the graph to Neo4j. Everything uses MERGE, so running it again never creates duplicates."""
import os

from neo4j import GraphDatabase

BATCH = 1000
# Labels and relationship types come from these fixed lists only (never from the data).
ENTITY_LABELS = ["Method", "Dataset", "Task", "Metric", "Tool"]
MENTION_RELS = {"proposed": "PROPOSES", "used": "USES", "compared": "COMPARED_WITH"}
ENTITY_RELS = ["BASED_ON", "IMPROVES_ON", "OUTPERFORMS", "USED_FOR", "EVALUATED_ON", "PART_OF"]

CONSTRAINTS = [
    "CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (n:Paper) REQUIRE n.paper_id IS UNIQUE",
    "CREATE CONSTRAINT author_id IF NOT EXISTS FOR (n:Author) REQUIRE n.author_id IS UNIQUE",
    "CREATE CONSTRAINT institution_id IF NOT EXISTS FOR (n:Institution) REQUIRE n.institution_id IS UNIQUE",
    "CREATE CONSTRAINT topic_id IF NOT EXISTS FOR (n:Topic) REQUIRE n.topic_id IS UNIQUE",
    "CREATE CONSTRAINT entity_key IF NOT EXISTS FOR (n:Entity) REQUIRE n.key IS UNIQUE",
]


def get_driver():
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "oig_password")),
    )


def _run(session, query: str, rows: list) -> int:
    for i in range(0, len(rows), BATCH):
        session.run(query, rows=rows[i:i + BATCH]).consume()
    return len(rows)


def ensure_constraints(session) -> None:
    for statement in CONSTRAINTS:
        session.run(statement).consume()


def reset(session) -> None:
    session.run("MATCH (n) CALL { WITH n DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS").consume()


def write_papers(session, rows: list) -> int:
    return _run(session, """
        UNWIND $rows AS row
        MERGE (p:Paper {paper_id: row.paper_id})
        SET p.title = row.title, p.year = row.year, p.cited_by_count = row.cited_by_count,
            p.doi = row.doi, p.openalex_id = row.openalex_id, p.arxiv_id = row.arxiv_id,
            p.source = row.source, p.access_level = row.access_level, p.has_full_text = row.has_full_text
        """, rows)


def write_authors(session, rows: list) -> int:
    return _run(session, """
        UNWIND $rows AS row
        MERGE (a:Author {author_id: row.author_id})
        SET a.name = row.name, a.openalex_id = row.openalex_id, a.orcid = row.orcid
        """, rows)


def write_institutions(session, rows: list) -> int:
    return _run(session, """
        UNWIND $rows AS row
        MERGE (i:Institution {institution_id: row.institution_id})
        SET i.name = row.name, i.openalex_id = row.openalex_id, i.country_code = row.country_code, i.type = row.type
        """, rows)


def write_topics(session, rows: list) -> int:
    return _run(session, """
        UNWIND $rows AS row
        MERGE (t:Topic {topic_id: row.topic_id})
        SET t.name = row.name, t.openalex_id = row.openalex_id, t.field = row.field
        """, rows)


def write_authored(session, rows: list) -> int:
    return _run(session, """
        UNWIND $rows AS row
        MATCH (a:Author {author_id: row.author_id})
        MATCH (p:Paper {paper_id: row.paper_id})
        MERGE (a)-[r:AUTHORED]->(p)
        SET r.position = row.position
        """, rows)


def write_affiliations(session, rows: list) -> int:
    return _run(session, """
        UNWIND $rows AS row
        MATCH (a:Author {author_id: row.author_id})
        MATCH (i:Institution {institution_id: row.institution_id})
        MERGE (a)-[:AFFILIATED_WITH]->(i)
        """, rows)


def write_paper_topics(session, rows: list) -> int:
    return _run(session, """
        UNWIND $rows AS row
        MATCH (p:Paper {paper_id: row.paper_id})
        MATCH (t:Topic {topic_id: row.topic_id})
        MERGE (p)-[r:HAS_TOPIC]->(t)
        SET r.score = row.score
        """, rows)


def write_citations(session, rows: list) -> int:
    return _run(session, """
        UNWIND $rows AS row
        MATCH (a:Paper {paper_id: row.citing})
        MATCH (b:Paper {paper_id: row.cited})
        MERGE (a)-[:CITES]->(b)
        """, rows)


def write_entities(session, entities: list) -> int:
    total = 0
    for label in ENTITY_LABELS:  # one query per label (labels cannot be parameters)
        rows = [e for e in entities if e["type"] == label]
        total += _run(session, f"""
            UNWIND $rows AS row
            MERGE (e:Entity {{key: row.key}})
            SET e:{label}, e.name = row.name, e.type = row.type, e.aliases = row.aliases, e.n_papers = row.n_papers
            """, rows)
    return total


def write_mentions(session, mentions: list) -> int:
    total = 0
    for role, rel_type in MENTION_RELS.items():
        rows = [m for m in mentions if m["role"] == role]
        total += _run(session, f"""
            UNWIND $rows AS row
            MATCH (p:Paper {{paper_id: row.paper_id}})
            MATCH (e:Entity {{key: row.key}})
            MERGE (p)-[:{rel_type}]->(e)
            """, rows)
    return total


def write_entity_relations(session, relations: list) -> int:
    total = 0
    for rel_type in ENTITY_RELS:
        rows = [r for r in relations if r["relation"] == rel_type]
        total += _run(session, f"""
            UNWIND $rows AS row
            MATCH (a:Entity {{key: row.source}})
            MATCH (b:Entity {{key: row.target}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET r.paper_ids = row.paper_ids, r.n_papers = size(row.paper_ids)
            """, rows)
    return total


def counts(session) -> dict:
    nodes = session.run("MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS n ORDER BY n DESC").data()
    rels = session.run("MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n ORDER BY n DESC").data()
    return {"nodes": {r["label"]: r["n"] for r in nodes}, "relationships": {r["type"]: r["n"] for r in rels}}