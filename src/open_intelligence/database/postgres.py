import os

import psycopg

from open_intelligence import settings  # noqa: F401  (loads .env)


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        autocommit=True,
    )


def has_success(conn, source: str, query_name: str, window_start) -> bool:
    """True if this partition was already loaded successfully."""
    row = conn.execute(
        "SELECT 1 FROM ingestion_runs WHERE source = %s AND query_name = %s "
        "AND window_start = %s AND status = 'success' LIMIT 1",
        (source, query_name, window_start),
    ).fetchone()
    return row is not None


def last_max_publication_date(conn, source: str, query_name: str, window_start):
    """Incremental marker: newest publication date seen in this partition (None if never loaded)."""
    row = conn.execute(
        "SELECT max(max_publication_date) FROM ingestion_runs WHERE source = %s "
        "AND query_name = %s AND window_start = %s AND status = 'success'",
        (source, query_name, window_start),
    ).fetchone()
    return row[0]


def start_run(conn, source, query_name, search, api_filter, window_start, window_end) -> int:
    return conn.execute(
        "INSERT INTO ingestion_runs (source, query_name, search, api_filter, window_start, window_end) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING run_id",
        (source, query_name, search, api_filter, window_start, window_end),
    ).fetchone()[0]


def finish_run(conn, run_id, status, pages, works, max_date, error=None) -> None:
    conn.execute(
        "UPDATE ingestion_runs SET finished_at = now(), status = %s, pages = %s, "
        "works_fetched = %s, max_publication_date = %s, error = %s WHERE run_id = %s",
        (status, pages, works, max_date, error, run_id),
    )