"""Show the sections and chunks of one paper.
Usage: python scripts/peek_chunks.py [paper_id]   (random extracted paper if no id)
"""
import os
import sys
from collections import Counter

from open_intelligence import settings
from open_intelligence.database import minio_store, postgres
from open_intelligence.documents import chunker, paper_text

config = settings.load_config()

with postgres.connect() as conn:
    if len(sys.argv) > 1:
        row = conn.execute(
            "SELECT paper_id, title, pdf_key, access_level FROM papers WHERE paper_id = %s",
            (int(sys.argv[1]),),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT paper_id, title, pdf_key, access_level FROM papers "
            "WHERE text_status = 'extracted' ORDER BY random() LIMIT 1"
        ).fetchone()

if not row or not row[2]:
    sys.exit("no downloaded paper found")

paper_id, title, pdf_key, access_level = row
pages = paper_text.load_clean_pages(
    minio_store.get_client(), os.getenv("MINIO_BUCKET_PDFS", "pdfs"), pdf_key, config["pdfs"]["max_pages"]
)
chunks = chunker.chunk_pages(paper_id, pages, access_level, config.get("chunker"))

print(f"paper {paper_id}: {title}")
print(f"{len(pages)} pages -> {len(chunks)} chunks\n")
print("chunks per section:")
for section, n in Counter(c.section for c in chunks).items():
    print(f"  {n:3d}  {section}")
for c in chunks[:3] + chunks[-1:]:
    print(f"\n--- chunk {c.index} | {c.section} | pages {c.page_start}-{c.page_end} | {c.n_words} words ---")
    print(c.text[:400])