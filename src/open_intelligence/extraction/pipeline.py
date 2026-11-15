"""Extract entities and relations from paper abstracts with the local LLM; save them in Postgres."""
import logging
import time

import httpx
from psycopg.types.json import Jsonb

from open_intelligence import settings
from open_intelligence.database import postgres
from open_intelligence.extraction import llm, schema

logger = logging.getLogger(__name__)

# Most cited papers first (they connect to the most other papers).
PAPERS_SQL = """
SELECT p.paper_id, p.title, p.abstract
FROM papers p
LEFT JOIN paper_extractions e ON e.paper_id = p.paper_id
WHERE p.abstract IS NOT NULL AND length(p.abstract) >= 80
  AND (e.paper_id IS NULL OR (%(retry)s::boolean AND e.status = 'failed'))
ORDER BY p.cited_by_count DESC, p.paper_id
LIMIT %(limit)s
"""

UPSERT_SQL = """
INSERT INTO paper_extractions
    (paper_id, status, model, prompt_version, entities, relations, n_entities, n_relations, error, seconds)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (paper_id) DO UPDATE SET
    status = EXCLUDED.status, model = EXCLUDED.model, prompt_version = EXCLUDED.prompt_version,
    entities = EXCLUDED.entities, relations = EXCLUDED.relations, n_entities = EXCLUDED.n_entities,
    n_relations = EXCLUDED.n_relations, error = EXCLUDED.error, seconds = EXCLUDED.seconds,
    extracted_at = now()
"""


def extract_papers(limit: int | None = None, retry_failed: bool = False) -> dict:
    cfg = settings.load_config()["extraction"]
    llm.check_ready(cfg)
    stats = {"selected": 0, "done": 0, "failed": 0, "entities": 0, "relations": 0}
    started = time.time()

    with postgres.connect() as conn, httpx.Client(timeout=cfg["timeout_s"]) as client:
        rows = conn.execute(PAPERS_SQL, {"retry": retry_failed, "limit": limit or cfg["max_per_run"]}).fetchall()
        stats["selected"] = len(rows)
        logger.info("%d papers to extract with %s", len(rows), cfg["model"])

        for i, (paper_id, title, abstract) in enumerate(rows, start=1):
            t0 = time.time()
            text = llm.paper_text(title, abstract, cfg["max_abstract_chars"])
            try:
                result = schema.clean_extraction(llm.extract_raw(client, text, cfg), text)
                seconds = time.time() - t0
                conn.execute(UPSERT_SQL, (
                    paper_id, "done", cfg["model"], llm.PROMPT_VERSION, Jsonb(result["entities"]),
                    Jsonb(result["relations"]), len(result["entities"]), len(result["relations"]), None, seconds,
                ))
                stats["done"] += 1
                stats["entities"] += len(result["entities"])
                stats["relations"] += len(result["relations"])
                logger.info("%d/%d paper %s: %d entities, %d relations, %.1fs", i, len(rows), paper_id,
                            len(result["entities"]), len(result["relations"]), seconds)
            except Exception as e:
                error = f"{type(e).__name__}: {e}"[:300]
                logger.warning("%d/%d paper %s failed: %s", i, len(rows), paper_id, error)
                conn.execute(UPSERT_SQL, (paper_id, "failed", cfg["model"], llm.PROMPT_VERSION, None, None,
                                          None, None, error, time.time() - t0))
                stats["failed"] += 1

    stats["minutes"] = round((time.time() - started) / 60, 1)
    return stats