"""Usage:
  python scripts/run_pdfs.py --limit 20       # small test: download 20 PDFs, then check their text
  python scripts/run_pdfs.py                  # download up to max_per_run PDFs, then check text
  python scripts/run_pdfs.py --retry-failed   # also retry failed downloads (max 3 attempts each)
  python scripts/run_pdfs.py --skip-download  # only check text of PDFs already downloaded
"""
import argparse
import json
import logging
from pathlib import Path

from open_intelligence.documents import pdf_downloader, text_check


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-check", action="store_true")
    args = parser.parse_args()

    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("logs/pdfs.log")],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    result = {}
    if not args.skip_download:
        result["download"] = pdf_downloader.download_pdfs(args.limit, args.retry_failed)
    if not args.skip_check:
        result["text_check"] = text_check.check_texts(args.limit)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()