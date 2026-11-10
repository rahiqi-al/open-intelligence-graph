"""Day 2: fetch 100 recent cs.LG / cs.AI papers from arXiv."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

URL = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}

params = {
    "search_query": "cat:cs.LG OR cat:cs.AI",
    "start": 0,
    "max_results": 100,
    "sortBy": "submittedDate",
    "sortOrder": "descending",
}

resp = httpx.get(URL, params=params, timeout=60, follow_redirects=True)
resp.raise_for_status()

Path("data/raw").mkdir(parents=True, exist_ok=True)
Path("data/raw/arxiv_sample.xml").write_text(resp.text)  # keep the raw response

root = ET.fromstring(resp.text)
papers = []
for e in root.findall("a:entry", NS):
    pdf = next(
        (l.get("href") for l in e.findall("a:link", NS) if l.get("title") == "pdf"), None
    )
    papers.append(
        {
            "arxiv_id": e.findtext("a:id", namespaces=NS),
            "title": " ".join((e.findtext("a:title", namespaces=NS) or "").split()),
            "abstract": " ".join((e.findtext("a:summary", namespaces=NS) or "").split()),
            "published": e.findtext("a:published", namespaces=NS),
            "authors": [a.findtext("a:name", namespaces=NS) for a in e.findall("a:author", NS)],
            "categories": [c.get("term") for c in e.findall("a:category", NS)],
            "doi": e.findtext("x:doi", namespaces=NS),
            "journal_ref": e.findtext("x:journal_ref", namespaces=NS),
            "pdf_url": pdf,
        }
    )

Path("data/raw/arxiv_sample.json").write_text(json.dumps(papers, indent=2))

print("papers:", len(papers))
print("with DOI:", sum(1 for p in papers if p["doi"]))
print("with journal_ref:", sum(1 for p in papers if p["journal_ref"]))
print("with pdf_url:", sum(1 for p in papers if p["pdf_url"]))
print("first title:", papers[0]["title"])