"""Load the cleaned text pages of one paper, straight from its PDF in MinIO (nothing is stored)."""
from open_intelligence.database import minio_store
from open_intelligence.documents import pdf_extractor, text_cleaner


def load_clean_pages(minio, bucket: str, pdf_key: str, max_pages: int) -> list[str]:
    pdf = minio_store.get_bytes(minio, bucket, pdf_key)
    pages = pdf_extractor.extract_pages(pdf, max_pages)
    clean, _refs_removed = text_cleaner.clean_pages(pages)
    return clean