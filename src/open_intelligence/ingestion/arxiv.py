"""arXiv source: offset pagination over one partition (query x date range)."""
import time
import xml.etree.ElementTree as ET
from datetime import date

import httpx

from open_intelligence import settings
from open_intelligence.ingestion.common import Page, retrying

URL = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom"}

# arXiv asks for at most 1 request every 3 seconds, across ALL requests (not only within a partition).
_MIN_INTERVAL = 3.5
_last_request = 0.0


def _query(search: str, start: date, end: date) -> str:
    return f"({search}) AND submittedDate:[{start:%Y%m%d}0000 TO {end:%Y%m%d}2359]"


def _sort(mode: str) -> str:
    # backfill: most relevant first. incremental: newest first.
    return "submittedDate" if mode == "incremental" else "relevance"


def describe(search: str, start: date, end: date, mode: str) -> str:
    return f"search_query={_query(search, start, end)}; sortBy={_sort(mode)}"


@retrying(min_wait=15, max_wait=180, attempts=6, multiplier=10)  # long backoff for 429
def _get(client: httpx.Client, params: dict) -> httpx.Response:
    global _last_request
    wait = _MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()
    resp = client.get(URL, params=params)
    resp.raise_for_status()
    return resp


def fetch_pages(search: str, start: date, end: date, mode: str):
    page_size = settings.load_config()["ingestion"]["arxiv"]["page_size"]
    offset = 0
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        while True:
            params = {
                "search_query": _query(search, start, end),
                "start": offset,
                "max_results": page_size,
                "sortBy": _sort(mode),
                "sortOrder": "descending",
            }
            resp = _get(client, params)
            entries = ET.fromstring(resp.content).findall("a:entry", NS)
            if not entries:
                return
            dates = [
                e.findtext("a:published", namespaces=NS)[:10]
                for e in entries
                if e.findtext("a:published", namespaces=NS)
            ]
            yield Page(
                raw=resp.content,
                ext="xml",
                content_type="application/xml",
                n_works=len(entries),
                newest_date=max(dates) if dates else None,
            )
            if len(entries) < page_size:
                return
            offset += page_size