"""Clean extracted PDF text: remove headers/footers, fix hyphenation, cut the reference list."""
import re
from collections import Counter

REFERENCES_RE = re.compile(r"^\s*(?:\d+\.?\s*|[IVX]+\.?\s*)?(references|bibliography)\s*$", re.I)
ARXIV_STAMP_RE = re.compile(r"^arXiv:\d{4}\.\d{4,5}v\d+\s*\[[\w.\-]+\].*$", re.M)


def _norm(line: str) -> str:
    return re.sub(r"\d+", "#", line.strip().lower())


def remove_headers_footers(pages: list[str]) -> list[str]:
    """Drop lines that repeat at the top or bottom of many pages (running titles, page numbers)."""
    if len(pages) < 4:
        return pages
    split = [p.split("\n") for p in pages]
    counts = Counter()
    for lines in split:
        counts.update({_norm(l) for l in lines[:3] + lines[-3:] if l.strip()})
    threshold = max(3, int(0.4 * len(pages)))
    repeated = {line for line, c in counts.items() if c >= threshold}

    cleaned = []
    for lines in split:
        n = len(lines)
        kept = [l for i, l in enumerate(lines)
                if not (_norm(l) in repeated and (i < 3 or i >= n - 3))]
        cleaned.append("\n".join(kept))
    return cleaned


def fix_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"([a-z])-\n([a-z])", r"\1\2", text)  # re-join words hyphenated at line ends
    text = ARXIV_STAMP_RE.sub("", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def cut_references(pages: list[str]) -> tuple[list[str], bool]:
    """Remove everything from the last 'References' heading on (only after 30% of the text)."""
    total = sum(len(p) for p in pages) or 1
    seen, cut = 0, None
    for page_index, page in enumerate(pages):
        for line_index, line in enumerate(page.split("\n")):
            if seen >= 0.3 * total and REFERENCES_RE.match(line):
                cut = (page_index, line_index)
            seen += len(line) + 1
    if cut is None:
        return pages, False
    page_index, line_index = cut
    last = "\n".join(pages[page_index].split("\n")[:line_index])
    return pages[:page_index] + [last], True


def clean_pages(pages: list[str]) -> tuple[list[str], bool]:
    """Returns (clean pages, references_removed). Page i of the result is page i+1 of the PDF."""
    pages = remove_headers_footers(pages)
    pages = [fix_text(p) for p in pages]
    return cut_references(pages)