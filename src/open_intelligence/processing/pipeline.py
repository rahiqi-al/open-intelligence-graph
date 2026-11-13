"""Day 5 pipeline: raw files in MinIO -> parse -> clean -> validate -> deduplicate -> PostgreSQL."""
import logging
import os
from collections import Counter

from open_intelligence import settings
from open_intelligence.database import minio_store, postgres
from open_intelligence.processing import cleaning, deduplication, loader, parsers, validation

logger = logging.getLogger(__name__)

PARSERS = {"openalex": parsers.parse_openalex_page, "arxiv": parsers.parse_arxiv_page}


class QualityGateError(RuntimeError):
    pass


def new_files(client, bucket, conn, source=None, limit=None) -> list[tuple[str, str]]:
    """Raw files not processed yet, OpenAlex first (it is the preferred source when merging)."""
    done = {row[0] for row in conn.execute("SELECT object_key FROM processed_files")}
    files = []
    for src in [source] if source else ["openalex", "arxiv"]:
        keys = sorted(o.object_name for o in client.list_objects(bucket, prefix=f"source={src}/", recursive=True))
        files += [(src, key) for key in keys if key not in done]
    return files[:limit] if limit else files


def run(source=None, limit_files=None, dry_run=False, force=False) -> dict:
    cfg = settings.load_config()["processing"]
    bucket = os.getenv("MINIO_BUCKET_RAW", "raw-json")
    minio = minio_store.get_client()

    with postgres.connect() as conn:
        files = new_files(minio, bucket, conn, source, limit_files)
        logger.info("%d new raw files to process", len(files))

        accepted, rejects, file_stats = [], [], []
        reasons = Counter()
        total = 0

        for src, key in files:
            try:
                records, errors = PARSERS[src](minio_store.get_bytes(minio, bucket, key))
            except Exception as e:  # unreadable file: log it, skip it
                logger.error("cannot parse %s: %r", key, e)
                rejects.append((src, key, None, None, "unreadable_file", repr(e)))
                reasons["unreadable_file"] += 1
                file_stats.append((src, key, 1, 1))
                total += 1
                continue

            rejected = 0
            for err in errors:
                rejects.append((src, key, err["source_id"], err.get("title"), "parse_error", err["details"]))
                reasons["parse_error"] += 1
                rejected += 1

            for rec in records:
                cleaning.clean_record(rec)
                problems = validation.validate(rec, cfg)
                if problems:
                    logger.debug("rejected %s %s: %s", src, rec.source_id, problems)
                    reasons[problems[0][0]] += 1
                    details = "; ".join(f"{code}:{detail}" for code, detail in problems)
                    rejects.append((src, key, rec.source_id, (rec.title or "")[:300], problems[0][0], details))
                    rejected += 1
                else:
                    accepted.append(rec)

            n = len(records) + len(errors)
            total += n
            file_stats.append((src, key, n, rejected))
            logger.info("%s: %d records, %d rejected", key, n, rejected)

        rejected_total = sum(reasons.values())
        reject_rate = rejected_total / total if total else 0.0
        logger.info("parsed %d records, rejected %d (%.1f%%)", total, rejected_total, reject_rate * 100)
        if reject_rate > cfg["max_reject_rate"] and not force:
            raise QualityGateError(
                f"reject rate {reject_rate:.1%} is above {cfg['max_reject_rate']:.0%}: "
                f"{dict(reasons)}. Check logs/processing.log or use --force"
            )

        merged, duplicates = deduplication.deduplicate(accepted)
        logger.info("%d valid records -> %d papers after deduplication (%d duplicates)",
                    len(accepted), len(merged), duplicates)

        stats = {
            "files": len(files),
            "records_parsed": total,
            "rejected": rejected_total,
            "rejected_by_reason": dict(reasons),
            "duplicates_merged": duplicates,
            "papers_to_load": len(merged),
            "inserted": 0,
            "merged_into_existing": 0,
            "db_failed": 0,
            "references_linked": None,
        }
        if dry_run:
            return stats

        for rec in merged:
            try:
                outcome = loader.save_paper(conn, rec)
                stats["inserted" if outcome == "inserted" else "merged_into_existing"] += 1
            except Exception as e:  # e.g. a unique-key conflict: skip this paper, log it
                logger.warning("db error for %s %s: %s", rec.source_id, rec.title, e)
                rejects.append((rec.source, "-", rec.source_id, (rec.title or "")[:300], "db_error", str(e)[:500]))
                stats["db_failed"] += 1

        stats["references_linked"] = loader.link_references(conn)

        with conn.cursor() as cur:
            if rejects:
                cur.executemany(
                    "INSERT INTO rejected_records (source, object_key, source_id, title, reason, details) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    rejects,
                )
            cur.executemany(
                "INSERT INTO processed_files (object_key, source, records_total, records_rejected) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (object_key) DO UPDATE SET "
                "records_total = EXCLUDED.records_total, records_rejected = EXCLUDED.records_rejected, "
                "processed_at = now()",
                [(key, src, n, rej) for src, key, n, rej in file_stats],
            )
        return stats