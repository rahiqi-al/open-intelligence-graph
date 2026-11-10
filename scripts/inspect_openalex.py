"""Day 2: inspect fields, missing values, duplicates and relationships."""
import json
import re
from pathlib import Path

import pandas as pd

works = json.loads(Path("data/raw/openalex_sample.json").read_text())
print("works:", len(works))
print("\nTop-level fields:\n", sorted(works[0].keys()))


def rebuild_abstract(inv):
    """OpenAlex stores abstracts as {word: [positions]}. Rebuild plain text."""
    if not inv:
        return None
    pos = {i: w for w, idxs in inv.items() for i in idxs}
    return " ".join(pos[i] for i in sorted(pos))


def norm_title(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


ids = {w["id"] for w in works}
rows = []
for w in works:
    refs = w.get("referenced_works") or []
    auths = w.get("authorships") or []
    rows.append(
        {
            "id": w["id"],
            "doi": w.get("doi"),
            "title": w.get("title"),
            "year": w.get("publication_year"),
            "type": w.get("type"),
            "language": w.get("language"),
            "cited_by": w.get("cited_by_count"),
            "has_abstract": bool(w.get("abstract_inverted_index")),
            "n_authors": len(auths),
            "has_institution": any(a.get("institutions") for a in auths),
            "n_refs": len(refs),
            "refs_in_sample": sum(1 for r in refs if r in ids),
            "has_topic": bool(w.get("primary_topic")),
            "is_oa": (w.get("open_access") or {}).get("is_oa"),
            "pdf_url": (w.get("best_oa_location") or {}).get("pdf_url"),
            "on_arxiv": any(
                "arxiv.org" in ((l.get("landing_page_url") or "") + (l.get("pdf_url") or ""))
                for l in (w.get("locations") or [])
            ),
        }
    )
df = pd.DataFrame(rows)

print("\n--- Coverage (share of papers that have the field) ---")
cov = {
    "doi": df.doi.notna().mean(),
    "abstract": df.has_abstract.mean(),
    "authors (>=1)": (df.n_authors > 0).mean(),
    "institution": df.has_institution.mean(),
    "references (>=1)": (df.n_refs > 0).mean(),
    "primary topic": df.has_topic.mean(),
    "open access": df.is_oa.fillna(False).mean(),
    "pdf url": df.pdf_url.notna().mean(),
    "on arXiv": df.on_arxiv.mean(),
}
for k, v in cov.items():
    print(f"{k:20} {v:6.0%}")

print("\n--- Duplicates ---")
print("duplicate OpenAlex ids:", df.id.duplicated().sum())
print("duplicate DOIs:        ", df.doi.dropna().duplicated().sum())
print("duplicate titles:      ", df.title.map(norm_title).duplicated().sum())

print("\n--- Distributions ---")
print("years:\n", df.year.value_counts().sort_index().to_string())
print("\ntypes:\n", df.type.value_counts().to_string())
print("\nlanguages:\n", df.language.value_counts(dropna=False).to_string())
print("\nreferences per paper:\n", df.n_refs.describe().round(1).to_string())

print("\n--- Relationships ---")
print("total references listed:      ", df.n_refs.sum())
print("references pointing INSIDE sample:", df.refs_in_sample.sum())

w0 = works[0]
print("\n--- Example paper ---")
print("title:   ", w0["title"])
print("abstract:", (rebuild_abstract(w0.get("abstract_inverted_index")) or "")[:300])
print("authors: ", [a["author"]["display_name"] for a in w0["authorships"][:3]])
print("institutions:", [
    i["display_name"] for a in w0["authorships"][:2] for i in a.get("institutions", [])
])
print("topic:   ", (w0.get("primary_topic") or {}).get("display_name"))