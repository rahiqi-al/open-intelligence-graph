"""Check that the text of downloaded PDFs can be extracted. Nothing is stored except status in Postgres."""
import logging
import os

from open_intelligence import settings
from open_intelligence.database import minio_store, postgres
from open_intelligence.documents import pdf_extractor, text_cleaner

logger = logging.getLogger(__name__)


def check_texts(limit: int | None = None) -> dict:
    cfg = settings.load_config()["pdfs"]
    bucket = os.getenv("MINIO_BUCKET_PDFS", "pdfs")
    minio = minio_store.get_client()
    stats = {"selected": 0, "extracted": 0, "failed": 0, "references_removed": 0}

    with postgres.connect() as conn:
        rows = conn.execute(
            "SELECT paper_id, pdf_key FROM papers WHERE pdf_status = 'downloaded' "
            "AND text_status = 'pending' ORDER BY paper_id LIMIT %s",
            (limit or 1_000_000,),
        ).fetchall()
        stats["selected"] = len(rows)
        logger.info("%d PDFs to check", len(rows))

        for done, (paper_id, pdf_key) in enumerate(rows, start=1):
            try:
                pdf = minio_store.get_bytes(minio, bucket, pdf_key)
                pages = pdf_extractor.extract_pages(pdf, cfg["max_pages"])
                clean, refs_removed = text_cleaner.clean_pages(pages)
                n_chars = sum(len(p) for p in clean)
                if n_chars < cfg["min_text_chars"]:
                    raise ValueError(f"too_little_text:{n_chars}")  # probably a scanned PDF
                conn.execute(
                    "UPDATE papers SET text_status = 'extracted', page_count = %s, text_chars = %s, "
                    "text_error = NULL, has_full_text = TRUE WHERE paper_id = %s",
                    (len(pages), n_chars, paper_id),
                )
                stats["extracted"] += 1
                stats["references_removed"] += int(refs_removed)
            except Exception as e:
                error = f"{type(e).__name__}: {e}"[:300]
                logger.warning("paper %s text check failed: %s", paper_id, error)
                conn.execute(
                    "UPDATE papers SET text_status = 'failed', text_error = %s WHERE paper_id = %s",
                    (error, paper_id),
                )
                stats["failed"] += 1
            if done % 50 == 0:
                logger.info("%d/%d checked", done, len(rows))
    return stats