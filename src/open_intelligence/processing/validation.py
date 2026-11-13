"""Quality checks. A record that fails is skipped and logged, never loaded."""
from open_intelligence.ingestion.common import utc_today
from open_intelligence.processing.models import PaperRecord


def validate(rec: PaperRecord, cfg: dict) -> list[tuple[str, str]]:
    """Returns a list of (reason_code, details). Empty list = the record is good."""
    problems = []

    if not rec.title:
        problems.append(("missing_title", ""))
    elif len(rec.title) < cfg["min_title_chars"]:
        problems.append(("title_too_short", rec.title))

    if not rec.abstract:
        problems.append(("missing_abstract", ""))
    elif len(rec.abstract) < cfg["min_abstract_chars"]:
        problems.append(("abstract_too_short", f"{len(rec.abstract)} chars"))

    max_year = utc_today().year + 1
    if rec.publication_year is None or not (cfg["year_min"] <= rec.publication_year <= max_year):
        problems.append(("invalid_year", str(rec.publication_year)))

    if rec.type not in cfg["allowed_types"]:
        problems.append(("type_not_allowed", str(rec.type)))

    if rec.language is not None and rec.language not in cfg["allowed_languages"]:
        problems.append(("language_not_english", rec.language))

    if not (rec.openalex_id or rec.arxiv_id or rec.doi):
        problems.append(("no_identifier", ""))

    return problems