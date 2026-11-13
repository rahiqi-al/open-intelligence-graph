from dataclasses import dataclass, field


@dataclass
class PaperRecord:
    """One paper in a common format, whatever the source."""

    source: str  # "openalex" | "arxiv"
    source_id: str
    title: str | None = None
    abstract: str | None = None
    openalex_id: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    publication_year: int | None = None
    publication_date: str | None = None
    type: str | None = None
    language: str | None = None
    cited_by_count: int = 0
    is_open_access: bool | None = None
    pdf_url: str | None = None
    author_names: list[str] = field(default_factory=list)
    authors: list[dict] = field(default_factory=list)  # OpenAlex authors with IDs and institutions
    topics: list[dict] = field(default_factory=list)
    references: list[str] = field(default_factory=list)  # OpenAlex IDs of cited works
    title_norm: str = ""
    sources: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.sources:
            self.sources = [self.source]