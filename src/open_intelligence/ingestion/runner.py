"""Plans and runs ingestion partitions (source x query x year)."""
import logging
import os
from datetime import datetime, timezone

from open_intelligence import settings
from open_intelligence.database import minio_store, postgres
from open_intelligence.ingestion import arxiv, openalex
from open_intelligence.ingestion.common import raw_key, utc_today, year_windows

logger = logging.getLogger(__name__)

SOURCES = {"openalex": openalex, "arxiv": arxiv}


def _queries(name: str | None = None) -> list[dict]:
    queries = settings.load_config()["ingestion"]["queries"]
    if name:
        queries = [q for q in queries if q["name"] == name]
        if not queries:
            raise ValueError(f"unknown query: {name}")
    return queries


def plan(source: str | None = None, query: str | None = None, year: int | None = None) -> list[dict]:
    """Partitions that still need work. Closed years already loaded are skipped."""
    today = utc_today()
    todo = []
    with postgres.connect() as conn:
        for src in [source] if source else list(SOURCES):
            for q in _queries(query):
                for w in year_windows(q["year_from"], today):
                    if year and w.start.year != year:
                        continue
                    if not w.is_open and postgres.has_success(conn, src, q["name"], w.start):
                        continue
                    todo.append({"source": src, "query": q["name"], "year": w.start.year})
    return todo


def run_partition(source: str, query: str, year: int, limit: int | None = None) -> dict:
    """Fetch one partition and store every raw page in MinIO.

    limit = test run: stops after about `limit` works and does not move the incremental marker.
    """
    q = _queries(query)[0]
    windows = {w.start.year: w for w in year_windows(q["year_from"])}
    if year not in windows:
        raise ValueError(f"{year} is outside the range of query {query}")
    window = windows[year]
    module = SOURCES[source]
    search = q[f"{source}_search"]
    max_works = limit or q["max_per_window"]
    bucket = os.getenv("MINIO_BUCKET_RAW", "raw-json")
    tag = f"{source}:{query}:{year}"

    now = datetime.now(timezone.utc)
    run_ts, ingest_date = now.strftime("%Y%m%dT%H%M%SZ"), now.date().isoformat()
    minio = minio_store.get_client()

    with postgres.connect() as conn:
        if window.is_open:  # incremental: continue from the newest date already loaded
            since = postgres.last_max_publication_date(conn, source, query, window.start)
            start, mode = since or window.start, "incremental"
        else:  # backfill: the whole year, loaded once
            start, mode = window.start, "backfill"

        run_id = postgres.start_run(
            conn, source, query, search, module.describe(search, start, window.end, mode),
            window.start, window.end,
        )
        logger.info("[%s] run %s started (%s, from %s to %s)", tag, run_id, mode, start, window.end)

        pages = works = 0
        newest = None
        try:
            for page in module.fetch_pages(search, start, window.end, mode):
                pages += 1
                key = raw_key(source, query, window.label, ingest_date, run_ts, pages, page.ext)
                minio_store.put_bytes(minio, bucket, key, page.raw, page.content_type)
                works += page.n_works
                if page.newest_date:
                    newest = page.newest_date if newest is None else max(newest, page.newest_date)
                logger.info("[%s] page %d saved (%d works) -> %s", tag, pages, works, key)
                if works >= max_works:
                    break
            status = "test" if limit else "success"
            postgres.finish_run(conn, run_id, status, pages, works, newest)
        except BaseException as e:
            logger.exception("[%s] run %s failed", tag, run_id)
            postgres.finish_run(conn, run_id, "failed", pages, works, None, error=str(e))
            raise

    stats = {"source": source, "query": query, "year": year, "mode": mode, "status": status,
             "pages": pages, "works": works, "newest": newest}
    logger.info("[%s] done: %s", tag, stats)
    return stats