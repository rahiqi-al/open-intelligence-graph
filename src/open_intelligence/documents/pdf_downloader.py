"""Download the PDFs of good papers into MinIO, politely and in parallel."""
import hashlib
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import httpx

from open_intelligence import settings
from open_intelligence.database import minio_store, postgres
from open_intelligence.ingestion.common import retrying

logger = logging.getLogger(__name__)

USER_AGENT = "open-intelligence-graph/0.1 (research project)"

# arXiv papers first (reliable), then papers that are also in OpenAlex, then the most cited.
CANDIDATES_SQL = """
SELECT paper_id, pdf_url FROM papers
WHERE pdf_url IS NOT NULL
  AND (pdf_status = 'pending'
       OR (%(retry)s::boolean AND pdf_status = 'failed' AND pdf_attempts < 3))
ORDER BY (arxiv_id IS NOT NULL) DESC, (openalex_id IS NOT NULL) DESC,
         cited_by_count DESC, publication_year DESC NULLS LAST
LIMIT %(limit)s
"""


class PdfError(Exception):
    """A PDF problem that retrying will not fix."""


class HostLimiter:
    """At most one request every `interval` seconds per website, shared by all threads."""

    def __init__(self, intervals: dict, default: float):
        self._intervals = intervals
        self._default = default
        self._next: dict[str, float] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def wait(self, host: str) -> None:
        with self._guard:
            lock = self._locks.setdefault(host, threading.Lock())
        interval = self._intervals.get(host, self._default)
        with lock:
            now = time.monotonic()
            delay = self._next.get(host, 0.0) - now
            if delay > 0:
                time.sleep(delay)
                now = time.monotonic()
            self._next[host] = now + interval


@retrying(min_wait=5, max_wait=60, attempts=3, multiplier=5)
def _fetch(client: httpx.Client, limiter: HostLimiter, url: str, cfg: dict) -> bytes:
    limiter.wait((urlparse(url).hostname or "").lower())
    with client.stream("GET", url) as resp:
        resp.raise_for_status()
        parts, size = [], 0
        for chunk in resp.iter_bytes():
            size += len(chunk)
            if size > cfg["max_bytes"]:
                raise PdfError("too_large")
            parts.append(chunk)
    data = b"".join(parts)
    if len(data) < cfg["min_bytes"]:
        raise PdfError("too_small")
    if b"%PDF" not in data[:1024]:
        raise PdfError("not_a_pdf")
    return data


def _download_one(client, minio, bucket, limiter, cfg, paper_id: int, url: str):
    data = _fetch(client, limiter, url, cfg)
    key = f"papers/{paper_id}.pdf"
    minio_store.put_bytes(minio, bucket, key, data, "application/pdf")
    return key, len(data), hashlib.sha256(data).hexdigest()


def download_pdfs(limit: int | None = None, retry_failed: bool = False) -> dict:
    cfg = settings.load_config()["pdfs"]
    limit = limit or cfg["max_per_run"]
    bucket = os.getenv("MINIO_BUCKET_PDFS", "pdfs")
    minio = minio_store.get_client()
    minio_store.ensure_bucket(minio, bucket)
    limiter = HostLimiter(cfg["host_interval_s"], cfg["default_interval_s"])
    stats = {"selected": 0, "downloaded": 0, "failed": 0, "mb": 0.0}

    with postgres.connect() as conn:
        rows = conn.execute(CANDIDATES_SQL, {"retry": retry_failed, "limit": limit}).fetchall()
        stats["selected"] = len(rows)
        logger.info("%d PDFs to download", len(rows))

        headers = {"User-Agent": USER_AGENT}
        with httpx.Client(timeout=cfg["timeout_s"], follow_redirects=True, headers=headers) as client:
            pool = ThreadPoolExecutor(max_workers=cfg["workers"])
            futures = {
                pool.submit(_download_one, client, minio, bucket, limiter, cfg, pid, url): (pid, url)
                for pid, url in rows
            }
            try:
                for done, fut in enumerate(as_completed(futures), start=1):
                    pid, url = futures[fut]
                    try:
                        key, size, sha = fut.result()
                        conn.execute(
                            "UPDATE papers SET pdf_status = 'downloaded', pdf_key = %s, pdf_bytes = %s, "
                            "pdf_sha256 = %s, pdf_error = NULL, pdf_downloaded_at = now() WHERE paper_id = %s",
                            (key, size, sha, pid),
                        )
                        stats["downloaded"] += 1
                        stats["mb"] += size / 1e6
                    except Exception as e:  # record the failure, keep going
                        error = f"{type(e).__name__}: {e}"[:300]
                        logger.warning("paper %s failed (%s): %s", pid, url, error)
                        conn.execute(
                            "UPDATE papers SET pdf_status = 'failed', pdf_error = %s, "
                            "pdf_attempts = pdf_attempts + 1 WHERE paper_id = %s",
                            (error, pid),
                        )
                        stats["failed"] += 1
                    if done % 25 == 0:
                        logger.info("%d/%d done (%d ok, %d failed)", done, len(rows),
                                    stats["downloaded"], stats["failed"])
            except KeyboardInterrupt:
                pool.shutdown(wait=False, cancel_futures=True)
                raise
            finally:
                pool.shutdown(wait=True)

    stats["mb"] = round(stats["mb"], 1)
    return stats