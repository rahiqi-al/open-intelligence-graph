"""OpenAlex source: page-number pagination over one partition (query x date range).

Basic paging allows up to 10,000 results per query, far above our per-partition cap.
"""
import os
import time
from datetime import date

import httpx

from open_intelligence import settings
from open_intelligence.ingestion.common import Page, retrying

URL = "https://api.openalex.org/works"


def _filter(start: date, end: date) -> str:
    base = settings.load_config()["ingestion"]["openalex"]["base_filter"]
    return f"{base},from_publication_date:{start},to_publication_date:{end}"


def _sort(mode: str) -> str:
    # backfill: most cited first. incremental: newest first.
    return "publication_date:desc" if mode == "incremental" else "cited_by_count:desc"


def describe(search: str, start: date, end: date, mode: str) -> str:
    return f"search={search}; filter={_filter(start, end)}; sort={_sort(mode)}"


@retrying(min_wait=2)
def _get(client: httpx.Client, params: dict) -> httpx.Response:
    resp = client.get(URL, params=params)
    resp.raise_for_status()
    return resp


def fetch_pages(search: str, start: date, end: date, mode: str):
    per_page = settings.load_config()["ingestion"]["openalex"]["per_page"]
    params = {
        "search": search,
        "filter": _filter(start, end),
        "sort": _sort(mode),
        "per-page": per_page,
    }
    if os.getenv("OPENALEX_EMAIL"):
        params["mailto"] = os.getenv("OPENALEX_EMAIL")
    if os.getenv("OPENALEX_API_KEY"):
        params["api_key"] = os.getenv("OPENALEX_API_KEY")

    page_no = 1
    with httpx.Client(timeout=60) as client:
        while True:
            params["page"] = page_no
            resp = _get(client, params)
            results = resp.json().get("results", [])
            if not results:
                return
            dates = [w["publication_date"] for w in results if w.get("publication_date")]
            yield Page(
                raw=resp.content,
                ext="json",
                content_type="application/json",
                n_works=len(results),
                newest_date=max(dates) if dates else None,
            )
            if len(results) < per_page:  # last page
                return
            page_no += 1
            time.sleep(0.1)