"""Vector search test.
Usage: python scripts/search_vectors.py "your question" [--k 5] [--access public,internal]
"""
import argparse

from open_intelligence import settings
from open_intelligence.indexing import embedder, qdrant_store

parser = argparse.ArgumentParser()
parser.add_argument("query")
parser.add_argument("--k", type=int, default=5)
parser.add_argument("--access", help="comma-separated access levels allowed, e.g. public")
args = parser.parse_args()

cfg = settings.load_config()["indexing"]
client = qdrant_store.get_client()
print(f"{client.count(cfg['collection']).count} chunks in Qdrant\n")

vector = embedder.embed_query(args.query, cfg)
levels = args.access.split(",") if args.access else None
for hit in qdrant_store.search(client, cfg["collection"], vector, args.k, levels):
    p = hit.payload
    pages = f"p.{p['page_start']}-{p['page_end']}" if p["page_start"] else "abstract"
    print(f"{hit.score:.3f} | {p['title'][:70]} ({p['year']}) | {p['section']} | {pages} | {p['access_level']}")
    print(f"        {p['text'][:220]}...\n")