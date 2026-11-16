"""Health checks and result checks used by the Airflow DAG.

Plain Python (no Airflow import): each function returns a small dict, or raises CheckFailed.
"""
import os

from open_intelligence import settings
from open_intelligence.database import minio_store, postgres
from open_intelligence.extraction import llm
from open_intelligence.graph import neo4j_store
from open_intelligence.indexing import qdrant_store

REQUIRED_ENV = ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD",
                "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD", "NEO4J_PASSWORD"]
REQUIRED_CONFIG = ["ingestion", "processing", "pdfs", "indexing", "extraction"]
REQUIRED_TABLES = {
    "papers", "authors", "institutions", "topics", "paper_authors", "paper_references", "paper_topics",
    "author_institutions", "ingestion_runs", "processed_files", "rejected_records", "paper_extractions",
}


class CheckFailed(RuntimeError):
    """A check did not pass."""


# ---------------------------------------------------------------- health checks (before the pipeline)
def check_config() -> dict:
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        raise CheckFailed(f"missing environment variables: {missing}")
    try:
        config = settings.load_config()
    except Exception as e:
        raise CheckFailed(f"cannot read config/settings.yaml: {e!r}")
    absent = [key for key in REQUIRED_CONFIG if key not in config]
    if absent:
        raise CheckFailed(f"config/settings.yaml has no block(s): {absent}")
    warnings = [] if os.getenv("OPENALEX_EMAIL") else ["OPENALEX_EMAIL is not set (OpenAlex polite pool)"]
    return {"config_blocks": sorted(config), "warnings": warnings}


def check_postgres() -> dict:
    try:
        with postgres.connect() as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
            papers = conn.execute("SELECT count(*) FROM papers").fetchone()[0]
    except Exception as e:
        raise CheckFailed(f"postgres is not reachable: {e!r}")
    missing = sorted(REQUIRED_TABLES - tables)
    if missing:
        raise CheckFailed(f"postgres is missing tables: {missing}")
    return {"tables": len(tables), "papers": papers}


def check_minio() -> dict:
    buckets = [os.getenv("MINIO_BUCKET_RAW", "raw-json"), os.getenv("MINIO_BUCKET_PDFS", "pdfs")]
    try:
        client = minio_store.get_client()
        for bucket in buckets:
            minio_store.ensure_bucket(client, bucket)  # created if missing
    except Exception as e:
        raise CheckFailed(f"minio is not reachable: {e!r}")
    return {"buckets": buckets}


def check_qdrant() -> dict:
    try:
        names = [c.name for c in qdrant_store.get_client().get_collections().collections]
    except Exception as e:
        raise CheckFailed(f"qdrant is not reachable: {e!r}")
    return {"collections": names}


def check_neo4j() -> dict:
    try:
        driver = neo4j_store.get_driver()
        driver.verify_connectivity()
        driver.close()
    except Exception as e:
        raise CheckFailed(f"neo4j is not reachable: {e!r}")
    return {"neo4j": "ok"}


def check_ollama() -> dict:
    cfg = llm.get_config()
    try:
        llm.check_ready(cfg)
    except Exception as e:
        raise CheckFailed(str(e))
    return {"model": cfg["model"], "url": cfg["ollama_url"]}


# ---------------------------------------------------------------- result checks (after each stage)
def verify_ingestion(since) -> dict:
    """Partitions that ran since the DAG run started. Some failures are tolerated, all failing is not."""
    with postgres.connect() as conn:
        rows = conn.execute(
            "SELECT status, count(*), coalesce(sum(works_fetched), 0) FROM ingestion_runs "
            "WHERE started_at >= %s GROUP BY status", (since,)).fetchall()
    by_status = {status: {"partitions": n, "works": int(works)} for status, n, works in rows}
    ok = sum(v["partitions"] for s, v in by_status.items() if s in ("success", "test"))
    failed = by_status.get("failed", {}).get("partitions", 0)
    if failed and not ok:
        raise CheckFailed(f"every ingestion partition failed: {by_status}")
    return {"by_status": by_status, "warnings": [f"{failed} partition(s) failed"] if failed else []}


def verify_postgres() -> dict:
    with postgres.connect() as conn:
        papers = conn.execute("SELECT count(*) FROM papers").fetchone()[0]
        rejected = conn.execute("SELECT count(*) FROM rejected_records").fetchone()[0]
        pending_pdfs = conn.execute(
            "SELECT count(*) FROM papers WHERE pdf_url IS NOT NULL AND pdf_status = 'pending'").fetchone()[0]
    if papers == 0:
        raise CheckFailed("the papers table is empty")
    return {"papers": papers, "rejected_records": rejected, "pdfs_pending": pending_pdfs}


def verify_qdrant() -> dict:
    collection = settings.load_config()["indexing"]["collection"]
    with postgres.connect() as conn:
        papers, chunks = conn.execute(
            "SELECT count(*) FILTER (WHERE embedded_at IS NOT NULL), coalesce(sum(chunk_count), 0) FROM papers"
        ).fetchone()
    points = qdrant_store.get_client().count(collection, exact=True).count
    if points != int(chunks):
        raise CheckFailed(f"Qdrant has {points} points but Postgres says {int(chunks)} chunks "
                          "(an interrupted run heals itself on the next run)")
    return {"papers_indexed": papers, "chunks": points}


def verify_neo4j() -> dict:
    with postgres.connect() as conn:
        papers = conn.execute("SELECT count(*) FROM papers").fetchone()[0]
        citations = conn.execute(
            "SELECT count(*) FROM paper_references WHERE cited_paper_id IS NOT NULL").fetchone()[0]
    driver = neo4j_store.get_driver()
    try:
        with driver.session() as session:
            n_papers = session.run("MATCH (p:Paper) RETURN count(p) AS n").single()["n"]
            n_cites = session.run("MATCH ()-[r:CITES]->() RETURN count(r) AS n").single()["n"]
            n_entities = session.run("MATCH (e:Entity) RETURN count(e) AS n").single()["n"]
    finally:
        driver.close()
    if (n_papers, n_cites) != (papers, citations):
        raise CheckFailed(f"Neo4j has {n_papers} papers / {n_cites} citations, "
                          f"Postgres has {papers} / {citations}")
    return {"papers": n_papers, "citations": n_cites, "entities": n_entities}