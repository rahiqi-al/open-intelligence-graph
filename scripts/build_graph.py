"""Usage:
  python scripts/build_graph.py --dry-run   # show the entity merging, write nothing
  python scripts/build_graph.py             # build / update the Neo4j graph (safe to run again)
  python scripts/build_graph.py --reset     # delete the whole graph first, then rebuild
"""
import argparse
import json
import logging
from pathlib import Path

from open_intelligence.graph import pipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("logs/graph.log")],
    )
    logging.getLogger("neo4j").setLevel(logging.WARNING)

    print(json.dumps(pipeline.build_graph(args.reset, args.dry_run), indent=2, default=str))


if __name__ == "__main__":
    main()