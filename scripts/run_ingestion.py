"""Usage:
  python scripts/run_ingestion.py --plan                                  # show what would run
  python scripts/run_ingestion.py --source openalex --query rag --year 2024 --limit 100   # test
  python scripts/run_ingestion.py --source openalex                       # one source, all partitions
  python scripts/run_ingestion.py                                         # everything
"""
import argparse
import logging
import sys
from pathlib import Path

from open_intelligence.ingestion import runner


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=list(runner.SOURCES))
    parser.add_argument("--query")
    parser.add_argument("--year", type=int)
    parser.add_argument("--limit", type=int, help="test run: not used for incremental state")
    parser.add_argument("--plan", action="store_true", help="only list the partitions to run")
    args = parser.parse_args()

    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("logs/ingestion.log")],
    )

    todo = runner.plan(args.source, args.query, args.year)
    print(f"{len(todo)} partitions to run")
    if args.plan:
        for t in todo:
            print(t)
        return 0

    failures = []
    for t in todo:
        try:
            print(runner.run_partition(**t, limit=args.limit))
        except Exception as e:  # keep going: one failed partition must not stop the rest
            failures.append((t, e))

    print(f"\nfinished: {len(todo) - len(failures)} ok, {len(failures)} failed")
    for t, e in failures:
        print("FAILED", t, repr(e))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())