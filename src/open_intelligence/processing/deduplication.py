"""Deduplicate records inside one batch and merge the OpenAlex and arXiv versions of a paper."""
from collections import defaultdict

from open_intelligence.processing.models import PaperRecord


def identity_keys(rec: PaperRecord) -> list[tuple]:
    keys = []
    if rec.openalex_id:
        keys.append(("openalex", rec.openalex_id))
    if rec.arxiv_id:
        keys.append(("arxiv", rec.arxiv_id))
    if rec.doi:
        keys.append(("doi", rec.doi))
    if len(rec.title_norm) >= 25 and rec.publication_year:
        keys.append(("title", rec.title_norm, rec.publication_year))
    return keys


def merge_pair(a: PaperRecord, b: PaperRecord) -> PaperRecord:
    """Merge b into a. a is the preferred record (OpenAlex), b fills the gaps."""
    if len(b.abstract or "") > len(a.abstract or ""):
        a.abstract = b.abstract
    for name in ("openalex_id", "doi", "arxiv_id", "publication_year", "publication_date",
                 "type", "language", "pdf_url"):
        if getattr(a, name) is None:
            setattr(a, name, getattr(b, name))
    if a.is_open_access is None or b.is_open_access:
        a.is_open_access = b.is_open_access or a.is_open_access
    a.cited_by_count = max(a.cited_by_count, b.cited_by_count)
    if len(b.author_names) > len(a.author_names):
        a.author_names = b.author_names
    if not a.authors:
        a.authors = b.authors
    if not a.topics:
        a.topics = b.topics
    a.references = sorted(set(a.references) | set(b.references))
    a.sources = sorted(set(a.sources) | set(b.sources))
    if a.arxiv_id:
        a.pdf_url = f"https://arxiv.org/pdf/{a.arxiv_id}"
    return a


def deduplicate(records: list[PaperRecord]) -> tuple[list[PaperRecord], int]:
    """Returns (merged_records, number_of_duplicates_removed)."""
    parent = list(range(len(records)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first_seen = {}
    for i, rec in enumerate(records):
        for key in identity_keys(rec):
            if key in first_seen:
                parent[find(i)] = find(first_seen[key])
            else:
                first_seen[key] = i

    groups = defaultdict(list)
    for i, rec in enumerate(records):
        groups[find(i)].append(rec)

    merged = []
    for group in groups.values():
        group.sort(key=lambda r: 0 if "openalex" in r.sources else 1)  # OpenAlex first
        out = group[0]
        for other in group[1:]:
            out = merge_pair(out, other)
        merged.append(out)
    return merged, len(records) - len(merged)