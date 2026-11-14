"""Find section headings in cleaned PDF pages and split the text into sections."""
import re
from dataclasses import dataclass, field

# Unnumbered headings we trust. Words like "Model", "Method" or "Results" are NOT here: alone on a
# line they are usually table or figure labels, so they only count when numbered ("3 Model").
KNOWN_HEADINGS = {
    "abstract", "introduction", "related work", "related works", "background", "preliminaries",
    "problem formulation", "problem statement", "methodology", "experimental setup",
    "experimental results", "results and discussion", "discussion", "ablation study",
    "ablation studies", "limitations", "conclusion", "conclusions", "conclusion and future work",
    "future work", "acknowledgments", "acknowledgements", "acknowledgment", "acknowledgement",
}
CAPTION_RE = re.compile(r"^(table|figure|fig\.?|algorithm|listing|equation)\s*\d", re.I)

ARABIC_RE = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,2})\.?\s+([A-Z][A-Za-z0-9 ,:;&'’/()\-–]{2,80})\.?$")
ROMAN_RE = re.compile(r"^([IVX]{1,4})\.\s+([A-Z][A-Z0-9 ,:;&'’/()\-–]{2,70})$")
NUMBER_ONLY_RE = re.compile(r"^\d{1,2}(?:\.\d{1,2}){0,2}\.?$")
APPENDIX_RE = re.compile(r"^appendix(?:\s+[A-Z0-9])?(?:\s*[:.\-–]\s*.{0,60})?$", re.I)


@dataclass
class Section:
    title: str
    lines: list = field(default_factory=list)  # list of (page_number, line_text)


def _clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip(" .:")
    return title.title() if title.isupper() else title


def _valid_title(title: str) -> bool:
    words = title.split()
    if not 1 <= len(words) <= 10:
        return False
    if any(w.isdigit() for w in words):  # "Llama 2 13B" is a table row, not a heading
        return False
    if CAPTION_RE.match(title):
        return False
    if title.rstrip().endswith((",", ";", ":")):
        return False
    return sum(c.isalpha() for c in title) >= 3


def heading_title(line: str) -> str | None:
    """Return the heading text if the line is a section heading, else None."""
    line = line.strip()
    if not line or len(line) > 90:
        return None
    if line[:1].isupper() and (line.strip(" .:").lower() in KNOWN_HEADINGS or APPENDIX_RE.match(line)):
        return _clean_title(line)
    m = ARABIC_RE.match(line) or ROMAN_RE.match(line)
    if m and _valid_title(m.group(2)):
        return _clean_title(m.group(2))
    return None


def _title_like(line: str) -> bool:
    return (len(line) <= 60 and line[:1].isupper() and ":" not in line and "." not in line
            and _valid_title(line))


def split_sections(pages: list[str]) -> list[Section]:
    """Split cleaned pages (page i is PDF page i+1) into sections.
    Text before the first heading is 'Front matter'; a paper with no headings is 'Full text'."""
    sections = [Section("Front matter")]
    n_headings = 0
    for page_no, text in enumerate(pages, start=1):
        lines = [l.strip() for l in text.split("\n")]
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line:
                i += 1
                continue
            title, step = heading_title(line), 1
            # some PDFs put the number and the title on two lines: "2" / "Architecture"
            if title is None and NUMBER_ONLY_RE.match(line) and i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if nxt and _title_like(nxt):
                    title, step = _clean_title(nxt), 2
            if title:
                sections.append(Section(title))
                n_headings += 1
            else:
                sections[-1].lines.append((page_no, line))
            i += step

    sections = [s for s in sections if s.lines]
    if n_headings == 0 and sections:
        sections[0].title = "Full text"
    return sections