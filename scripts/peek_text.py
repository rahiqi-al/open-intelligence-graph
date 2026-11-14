"""Print the cleaned text of one paper, extracted from its PDF in memory.
Usage: python scripts/peek_text.py [paper_id]   (random downloaded paper if no id)
"""
import os
import sys

from open_intelligence import settings
from open_intelligence.database import minio_store, postgres
from open_intelligence.documents import pdf_extractor, text_cleaner

cfg = settings.load_config()["pdfs"]

with postgres.connect() as conn:
    if len(sys.argv) > 1:
        row = conn.execute(
            "SELECT paper_id, title, pdf_key FROM papers WHERE paper_id = %s", (int(sys.argv[1]),)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT paper_id, title, pdf_key FROM papers WHERE pdf_status = 'downloaded' "
            "ORDER BY random() LIMIT 1"
        ).fetchone()

if not row or not row[2]:
    sys.exit("no downloaded paper found")

paper_id, title, key = row
pdf = minio_store.get_bytes(minio_store.get_client(), os.getenv("MINIO_BUCKET_PDFS", "pdfs"), key)
pages = pdf_extractor.extract_pages(pdf, cfg["max_pages"])
clean, refs_removed = text_cleaner.clean_pages(pages)
n_chars = sum(len(p) for p in clean)

print(f"paper {paper_id}: {title}")
print(f"{len(pages)} pages | {n_chars} chars | references removed: {refs_removed}")
print("\n--- start of page 1 ---")
print(clean[0][:1000])
print("\n--- end of the last page kept ---")
print(clean[-1][-600:])