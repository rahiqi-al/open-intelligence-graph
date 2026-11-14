"""Split a paper into chunks (in memory). Each chunk keeps its section, pages and access level.

Chunk size is estimated in tokens from the word count (tokens ~ words * tokens_per_word),
so no tokenizer is needed here.
"""
import uuid
from dataclasses import dataclass

from open_intelligence.documents.section_detector import split_sections

NAMESPACE = uuid.UUID("6f1c2c52-8f1e-4a55-9d0b-5a3f4f0f6a11")

DEFAULTS = {
    "chunk_tokens": 512,
    "overlap_tokens": 64,
    "tokens_per_word": 1.4,
    "min_chunk_words": 40,
    "min_alpha_ratio": 0.5,
    "skip_sections": ["acknowledg"],
}


@dataclass
class Chunk:
    chunk_id: str          # deterministic: same paper + same index -> same id (safe to re-run)
    paper_id: int
    index: int
    section: str
    page_start: int | None
    page_end: int | None
    text: str
    n_words: int
    access_level: str


def make_chunk_id(paper_id: int, index: int) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{paper_id}:{index}"))


def _alpha_ratio(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    return sum(c.isalpha() for c in chars) / len(chars) if chars else 0.0


def _windows(words: list, max_words: int, overlap: int):
    """Yield (start, end) word windows; windows end at a sentence end when one is near the end."""
    n, start = len(words), 0
    while start < n:
        end = min(start + max_words, n)
        if end < n:
            for i in range(end - 1, start + int(0.7 * max_words) - 1, -1):
                if words[i][0].endswith((".", "?", "!")):
                    end = i + 1
                    break
        yield start, end
        if end >= n:
            break
        start = max(end - overlap, start + 1)


def chunk_pages(paper_id: int, pages: list[str], access_level: str = "public",
                cfg: dict | None = None) -> list[Chunk]:
    cfg = {**DEFAULTS, **(cfg or {})}
    max_words = int(cfg["chunk_tokens"] / cfg["tokens_per_word"])
    overlap = int(cfg["overlap_tokens"] / cfg["tokens_per_word"])
    skip = tuple(s.lower() for s in cfg["skip_sections"])

    sections = split_sections(pages)
    if any(s.title.lower() == "abstract" for s in sections):
        # title + authors + affiliations are not useful to search; the abstract has its own section
        sections = [s for s in sections if s.title != "Front matter"]

    chunks: list[Chunk] = []
    for section in sections:
        if section.title.lower().startswith(skip):
            continue
        words = [(w, page) for page, line in section.lines for w in line.split()]
        for start, end in _windows(words, max_words, overlap):
            piece = words[start:end]
            text = " ".join(w for w, _ in piece)
            if len(piece) < cfg["min_chunk_words"] or _alpha_ratio(text) < cfg["min_alpha_ratio"]:
                continue  # too short, or mostly numbers (tables)
            index = len(chunks)
            chunks.append(Chunk(
                chunk_id=make_chunk_id(paper_id, index), paper_id=paper_id, index=index,
                section=section.title, page_start=piece[0][1], page_end=piece[-1][1],
                text=text, n_words=len(piece), access_level=access_level,
            ))
    return chunks


def chunk_abstract(paper_id: int, abstract: str, access_level: str = "public") -> list[Chunk]:
    """Fallback for papers without a usable PDF: one chunk with the abstract."""
    text = " ".join((abstract or "").split())
    n_words = len(text.split())
    if n_words < 20:
        return []
    return [Chunk(chunk_id=make_chunk_id(paper_id, 0), paper_id=paper_id, index=0,
                  section="Abstract", page_start=None, page_end=None, text=text,
                  n_words=n_words, access_level=access_level)]