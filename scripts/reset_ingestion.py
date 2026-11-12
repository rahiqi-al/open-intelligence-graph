"""Delete raw files and run history. Dev use only.

  python scripts/reset_ingestion.py --source openalex --yes   # one source
  python scripts/reset_ingestion.py --yes                     # everything
"""
import argparse
import os

from minio.deleteobjects import DeleteObject

from open_intelligence.database import minio_store, postgres

parser = argparse.ArgumentParser()
parser.add_argument("--source", choices=["openalex", "arxiv"])
parser.add_argument("--yes", action="store_true")
args = parser.parse_args()
if not args.yes:
    raise SystemExit("This deletes raw data and run history. Add --yes to confirm.")

client = minio_store.get_client()
bucket = os.getenv("MINIO_BUCKET_RAW", "raw-json")
prefix = f"source={args.source}/" if args.source else ""

to_delete = [DeleteObject(o.object_name) for o in client.list_objects(bucket, prefix=prefix, recursive=True)]
errors = list(client.remove_objects(bucket, to_delete))

with postgres.connect() as conn:
    if args.source:
        conn.execute("DELETE FROM ingestion_runs WHERE source = %s", (args.source,))
    else:
        conn.execute("TRUNCATE ingestion_runs RESTART IDENTITY")

print(f"deleted {len(to_delete)} objects (errors: {len(errors)}), run history cleared")