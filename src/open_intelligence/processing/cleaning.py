"""Cleaning and normalization of PaperRecord fields."""
import re
import unicodedata
from datetime import date

from open_intelligence.processing.models import PaperRecord

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
ARXIV_DOI_RE = re.compile(r"^10\.48550/arxiv\.(.+)$", re.I)
MARKUP_RE = re.compile(
    r"</?(?:jats:)?(?:p|italic|bold|sub|sup|title|sec|abstract|ext-link|monospace|sc)\b[^<>]*>", re.I
)
ABSTRACT_PREFIX_RE = re.compile(r"^abstract\s*[:.\-–—]\s*", re.I)


def clean_text(text: str | None) -> str | None:
    if not text:
        return None
    text = unicodedata.normalize("NFKC", text)
    text = MARKUP_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi.strip(), flags=re.I).lower()
    return doi if DOI_RE.match(doi) else None


def title_key(title: str | None) -> str:
    """Lowercase letters and digits only, used to spot the same title written differently."""
    return re.sub(r"[\W_]+", "", (title or "").lower())


def _valid_date(value: str | None) -> str | None:
    try:
        return date.fromisoformat(value[:10]).isoformat() if value else None
    except ValueError:
        return None


def clean_record(rec: PaperRecord) -> PaperRecord:
    rec.title = clean_text(rec.title)
    abstract = clean_text(rec.abstract)
    rec.abstract = ABSTRACT_PREFIX_RE.sub("", abstract) if abstract else None

    rec.doi = normalize_doi(rec.doi)
    if not rec.arxiv_id and rec.doi:  # arXiv papers have the DOI 10.48550/arXiv.<id>
        m = ARXIV_DOI_RE.match(rec.doi)
        if m:
            rec.arxiv_id = re.sub(r"v\d+$", "", m.group(1))

    rec.language = rec.language.lower() if rec.language else None
    rec.author_names = [n for n in (clean_text(n) for n in rec.author_names) if n]

    rec.publication_date = _valid_date(rec.publication_date)
    if rec.publication_year is None and rec.publication_date:
        rec.publication_year = int(rec.publication_date[:4])
    rec.cited_by_count = max(int(rec.cited_by_count or 0), 0)

    rec.title_norm = title_key(rec.title)
    if rec.arxiv_id:  # the arXiv PDF is the most reliable full-text source
        rec.pdf_url = f"https://arxiv.org/pdf/{rec.arxiv_id}"
    return rec