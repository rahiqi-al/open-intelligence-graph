"""Usage:
  python scripts/run_indexing.py --limit 50   # small test
  python scripts/run_indexing.py              # up to max_papers_per_run papers
  python scripts/run_indexing.py --limit 20000   # everything that is not indexed yet
It is safe to stop (Ctrl+C) and run again: finished papers are skipped.
"""
import argparse
import json
import logging
from pathlib import Path

from open_intelligence.indexing import pipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("logs/indexing.log")],
    )
    for noisy in ("httpx", "sentence_transformers", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    print(json.dumps(pipeline.index_papers(args.limit), indent=2))


if __name__ == "__main__":
    main()