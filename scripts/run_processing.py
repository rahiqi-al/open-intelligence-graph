"""Usage:
  python scripts/run_processing.py --dry-run                  # parse, clean, validate, deduplicate. No database writes.
  python scripts/run_processing.py --source openalex --limit-files 5
  python scripts/run_processing.py                            # process all new raw files
  python scripts/run_processing.py --force                    # ignore the quality gate
"""
import argparse
import json
import logging
import sys
from pathlib import Path

from open_intelligence.processing import pipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["openalex", "arxiv"])
    parser.add_argument("--limit-files", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    Path("logs").mkdir(exist_ok=True)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logfile = logging.FileHandler("logs/processing.log")
    logfile.setLevel(logging.DEBUG)  # every rejected record is written here
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[console, logfile],
    )
    logging.getLogger("open_intelligence").setLevel(logging.DEBUG)

    try:
        stats = pipeline.run(args.source, args.limit_files, args.dry_run, args.force)
    except pipeline.QualityGateError as e:
        print("QUALITY GATE FAILED:", e)
        return 1
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())