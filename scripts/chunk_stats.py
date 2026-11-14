"""Chunk a random sample of papers and print quality numbers.
Usage: python scripts/chunk_stats.py [n_papers]   (default 50)
"""
import os
import statistics
import sys
import time
from collections import Counter

from open_intelligence import settings
from open_intelligence.database import minio_store, postgres
from open_intelligence.documents import chunker, paper_text

n_papers = int(sys.argv[1]) if len(sys.argv) > 1 else 50
config = settings.load_config()
bucket = os.getenv("MINIO_BUCKET_PDFS", "pdfs")
minio = minio_store.get_client()

with postgres.connect() as conn:
    rows = conn.execute(
        "SELECT paper_id, pdf_key, access_level FROM papers WHERE text_status = 'extracted' "
        "ORDER BY random() LIMIT %s", (n_papers,),
    ).fetchall()

words, per_paper, sections = [], [], Counter()
no_sections = empty = 0
start = time.time()
for paper_id, pdf_key, access_level in rows:
    pages = paper_text.load_clean_pages(minio, bucket, pdf_key, config["pdfs"]["max_pages"])
    chunks = chunker.chunk_pages(paper_id, pages, access_level, config.get("chunker"))
    per_paper.append(len(chunks))
    empty += int(not chunks)
    no_sections += int(bool(chunks) and all(c.section in ("Full text", "Front matter") for c in chunks))
    for c in chunks:
        words.append(c.n_words)
        sections[c.section] += 1

print(f"{len(rows)} papers in {time.time() - start:.1f}s")
print(f"chunks: {len(words)} total | per paper avg {statistics.mean(per_paper):.1f}, "
      f"min {min(per_paper)}, max {max(per_paper)}")
print(f"words per chunk: avg {statistics.mean(words):.0f}, min {min(words)}, max {max(words)}")
print(f"papers with no chunks: {empty} | papers with no sections detected: {no_sections}")
print("top sections:", sections.most_common(15))