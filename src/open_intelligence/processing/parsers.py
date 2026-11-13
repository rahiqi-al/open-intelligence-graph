"""Turn raw OpenAlex JSON pages and arXiv XML pages into PaperRecord objects."""
import json
import re
import xml.etree.ElementTree as ET

from open_intelligence.processing.models import PaperRecord

NS = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
ARXIV_URL_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})", re.I
)
ARXIV_ABS_RE = re.compile(r"arxiv\.org/abs/(.+?)(?:v\d+)?$")


def short_id(url):
    """https://openalex.org/W123 -> W123"""
    return url.rsplit("/", 1)[-1] if url else None


def rebuild_abstract(inverted_index):
    """OpenAlex stores abstracts as {word: [positions]}. Rebuild the plain text."""
    if not inverted_index:
        return None
    positions = {i: word for word, idxs in inverted_index.items() for i in idxs}
    return " ".join(positions[i] for i in sorted(positions))


def find_arxiv_id(work):
    for loc in work.get("locations") or []:
        for key in ("landing_page_url", "pdf_url"):
            m = ARXIV_URL_RE.search(loc.get(key) or "")
            if m:
                return m.group(1)
    return None


def _openalex_work(w) -> PaperRecord:
    authors, names = [], []
    for position, a in enumerate(w.get("authorships") or [], start=1):
        author = a.get("author") or {}
        if author.get("display_name"):
            names.append(author["display_name"])
        if not author.get("id"):
            continue
        authors.append(
            {
                "openalex_id": short_id(author["id"]),
                "name": author.get("display_name"),
                "orcid": author.get("orcid"),
                "position": position,
                "institutions": [
                    {
                        "openalex_id": short_id(i["id"]),
                        "name": i.get("display_name"),
                        "country_code": i.get("country_code"),
                        "type": i.get("type"),
                    }
                    for i in (a.get("institutions") or [])
                    if i.get("id")
                ],
            }
        )

    primary_id = (w.get("primary_topic") or {}).get("id")
    raw_topics = w.get("topics") or ([w["primary_topic"]] if w.get("primary_topic") else [])
    topics = [
        {
            "openalex_id": short_id(t["id"]),
            "name": t.get("display_name"),
            "subfield": (t.get("subfield") or {}).get("display_name"),
            "field": (t.get("field") or {}).get("display_name"),
            "domain": (t.get("domain") or {}).get("display_name"),
            "score": t.get("score"),
            "is_primary": t["id"] == primary_id,
        }
        for t in raw_topics
        if t.get("id")
    ]

    return PaperRecord(
        source="openalex",
        source_id=short_id(w["id"]),
        title=w.get("title") or w.get("display_name"),
        abstract=rebuild_abstract(w.get("abstract_inverted_index")),
        openalex_id=short_id(w["id"]),
        doi=w.get("doi"),
        arxiv_id=find_arxiv_id(w),
        publication_year=w.get("publication_year"),
        publication_date=w.get("publication_date"),
        type=w.get("type"),
        language=w.get("language"),
        cited_by_count=w.get("cited_by_count") or 0,
        is_open_access=(w.get("open_access") or {}).get("is_oa"),
        pdf_url=(w.get("best_oa_location") or {}).get("pdf_url"),
        author_names=names,
        authors=authors,
        topics=topics,
        references=[short_id(r) for r in (w.get("referenced_works") or [])],
    )


def parse_openalex_page(raw: bytes):
    """Returns (records, errors)."""
    records, errors = [], []
    for w in json.loads(raw).get("results", []):
        try:
            records.append(_openalex_work(w))
        except Exception as e:  # one bad work must not lose the page
            errors.append({"source_id": short_id(w.get("id")), "title": w.get("title"), "details": repr(e)})
    return records, errors


def _arxiv_entry(e) -> PaperRecord:
    abs_url = e.findtext("a:id", namespaces=NS) or ""
    m = ARXIV_ABS_RE.search(abs_url)
    arxiv_id = m.group(1) if m else None
    published = e.findtext("a:published", namespaces=NS)
    return PaperRecord(
        source="arxiv",
        source_id=arxiv_id or abs_url,
        title=e.findtext("a:title", namespaces=NS),
        abstract=e.findtext("a:summary", namespaces=NS),
        arxiv_id=arxiv_id,
        doi=e.findtext("x:doi", namespaces=NS),
        publication_year=int(published[:4]) if published else None,
        publication_date=published[:10] if published else None,
        type="preprint",
        is_open_access=True,
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None,
        author_names=[n for n in (a.findtext("a:name", namespaces=NS) for a in e.findall("a:author", NS)) if n],
    )


def parse_arxiv_page(raw: bytes):
    """Returns (records, errors)."""
    records, errors = [], []
    for e in ET.fromstring(raw).findall("a:entry", NS):
        if "api/errors" in (e.findtext("a:id", namespaces=NS) or ""):
            continue
        try:
            records.append(_arxiv_entry(e))
        except Exception as ex:
            errors.append({"source_id": e.findtext("a:id", namespaces=NS), "title": None, "details": repr(ex)})
    return records, errors