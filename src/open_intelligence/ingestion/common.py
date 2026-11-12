"""Shared ingestion helpers: retry policy, yearly partitions, raw-storage paths."""
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def is_retryable(exc: BaseException) -> bool:
    """Retry on timeouts, connection errors, 429 and 5xx. Fail fast on other 4xx."""
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return False


def retrying(min_wait: int, max_wait: int = 90, attempts: int = 5, multiplier: int = 2):
    return retry(
        retry=retry_if_exception(is_retryable),
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=multiplier, min=min_wait, max=max_wait),
        before_sleep=lambda rs: logger.warning("retrying after: %r", rs.outcome.exception()),
        reraise=True,
    )


@dataclass(frozen=True)
class Window:
    """One yearly partition. is_open = the year is still running (receives new papers)."""

    start: date
    end: date
    is_open: bool

    @property
    def label(self) -> str:
        return str(self.start.year)


def year_windows(year_from: int, today: date | None = None) -> list[Window]:
    today = today or utc_today()
    windows = []
    for year in range(year_from, today.year + 1):
        start, end = date(year, 1, 1), date(year, 12, 31)
        if end >= today:
            windows.append(Window(start, today, True))
        else:
            windows.append(Window(start, end, False))
    return windows


@dataclass
class Page:
    """One raw API response, normalized for the runner."""

    raw: bytes  # byte-exact response body, stored untouched
    ext: str
    content_type: str
    n_works: int
    newest_date: str | None  # newest publication date on the page (YYYY-MM-DD)


def raw_key(source, query, window_label, ingest_date, run_ts, page_no, ext) -> str:
    """Hive-style partition path inside the raw bucket."""
    return (
        f"source={source}/query={query}/window={window_label}/"
        f"ingest_date={ingest_date}/run_ts={run_ts}/page_{page_no:04d}.{ext}"
    )