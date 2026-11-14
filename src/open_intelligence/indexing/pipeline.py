"""Indexing: paper -> chunks (in memory) -> BGE embeddings -> Qdrant. Nothing is stored in between."""
import logging
import os
import time

from open_intelligence import settings
from open_intelligence.database import minio_store, postgres
from open_intelligence.documents import chunker, paper_text
from open_intelligence.indexing import embedder, qdrant_store

logger = logging.getLogger(__name__)

# Papers with full text first, then the most cited. A paper that was indexed with its abstract only is
# picked again once its PDF text becomes available (unless full text already failed for it).
PAPERS_SQL = """
SELECT paper_id, title, abstract, publication_year, coalesce(access_level, 'public'), source,
       openalex_id, arxiv_id, text_status, pdf_key
FROM papers
WHERE embedded_at IS NULL
   OR (embed_level = 'abstract' AND text_status = 'extracted' AND embed_error IS NULL)
ORDER BY (text_status = 'extracted') DESC, cited_by_count DESC
LIMIT %s
"""


def build_chunks(row, minio, bucket: str, max_pages: int, chunker_cfg: dict | None):
    """Returns (chunks, level, error). Full text when possible, abstract only as a fallback."""
    paper_id, _title, abstract, _year, access_level, _source, _oa, _ax, text_status, pdf_key = row
    error = None
    if text_status == "extracted" and pdf_key:
        try:
            pages = paper_text.load_clean_pages(minio, bucket, pdf_key, max_pages)
            chunks = chunker.chunk_pages(paper_id, pages, access_level, chunker_cfg)
            if chunks:
                return chunks, "full", None
            error = "no_chunks_from_pdf"
        except Exception as e:
            error = f"{type(e).__name__}: {e}"[:300]
        logger.warning("paper %s: full text failed (%s), using the abstract", paper_id, error)
    return chunker.chunk_abstract(paper_id, abstract, access_level), "abstract", error


def index_papers(limit: int | None = None) -> dict:
    config = settings.load_config()
    icfg = config["indexing"]
    collection = icfg["collection"]
    bucket = os.getenv("MINIO_BUCKET_PDFS", "pdfs")
    max_pages = config["pdfs"]["max_pages"]
    minio = minio_store.get_client()
    client = qdrant_store.get_client()
    qdrant_store.ensure_collection(client, collection, embedder.dimension(icfg))

    stats = {"papers": 0, "full_text": 0, "abstract_only": 0, "chunks": 0}
    started = time.time()
    with postgres.connect() as conn:
        rows = conn.execute(PAPERS_SQL, (limit or icfg["max_papers_per_run"],)).fetchall()
        logger.info("%d papers to index", len(rows))

        size = icfg["papers_per_batch"]
        for i in range(0, len(rows), size):
            batch = [(row, *build_chunks(row, minio, bucket, max_pages, config.get("chunker")))
                     for row in rows[i:i + size]]

            texts = [embedder.passage_text(row[1], c.section, c.text)
                     for row, chunks, _lvl, _err in batch for c in chunks]
            vectors = embedder.embed_passages(texts, icfg) if texts else []

            pos = 0
            for row, chunks, level, error in batch:
                paper_id, title, _abs, year, _access, source, openalex_id, arxiv_id = row[:8]
                vecs = vectors[pos:pos + len(chunks)]
                pos += len(chunks)

                qdrant_store.delete_paper(client, collection, paper_id)  # replace old chunks, no duplicates
                if chunks:
                    payloads = [{
                        "paper_id": paper_id, "chunk_index": c.index, "section": c.section,
                        "page_start": c.page_start, "page_end": c.page_end, "text": c.text,
                        "access_level": c.access_level, "title": title, "year": year,
                        "source": source, "openalex_id": openalex_id, "arxiv_id": arxiv_id,
                        "level": level,
                    } for c in chunks]
                    qdrant_store.upsert_points(client, collection, [c.chunk_id for c in chunks], vecs, payloads)
                conn.execute(
                    "UPDATE papers SET embed_level = %s, chunk_count = %s, embedded_at = now(), "
                    "embed_error = %s WHERE paper_id = %s",
                    (level, len(chunks), error, paper_id),
                )
                stats["papers"] += 1
                stats["full_text" if level == "full" else "abstract_only"] += 1
                stats["chunks"] += len(chunks)

            elapsed = time.time() - started
            logger.info("%d/%d papers | %d chunks | %.1f chunks/s", min(i + size, len(rows)), len(rows),
                        stats["chunks"], stats["chunks"] / max(elapsed, 1e-9))

    stats["minutes"] = round((time.time() - started) / 60, 1)
    return stats