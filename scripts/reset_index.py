"""Delete the Qdrant collection and mark all papers as not indexed (use after changing the model).
Usage: python scripts/reset_index.py --yes
"""
import sys

from open_intelligence import settings
from open_intelligence.database import postgres
from open_intelligence.indexing import qdrant_store

if "--yes" not in sys.argv:
    sys.exit("This deletes all vectors. Run again with --yes")

name = settings.load_config()["indexing"]["collection"]
client = qdrant_store.get_client()
if client.collection_exists(name):
    client.delete_collection(name)
with postgres.connect() as conn:
    conn.execute("UPDATE papers SET embedded_at = NULL, embed_level = NULL, chunk_count = NULL, embed_error = NULL")
print("index reset")