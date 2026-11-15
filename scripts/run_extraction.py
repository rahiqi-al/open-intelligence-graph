"""Usage:
  python scripts/run_extraction.py --limit 5       # timing test
  python scripts/run_extraction.py                 # up to max_per_run papers (most cited first)
  python scripts/run_extraction.py --retry-failed  # try the failed papers again
It is safe to stop (Ctrl+C) and run again: finished papers are skipped.
"""
import argparse
import json
import logging
from pathlib import Path

from open_intelligence.extraction import pipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()

    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("logs/extraction.log")],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    print(json.dumps(pipeline.extract_papers(args.limit, args.retry_failed), indent=2))


if __name__ == "__main__":
    main()