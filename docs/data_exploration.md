## OpenAlex (sample: 100 random AI works, 2018+)

### Coverage
| Field | Present |
|---|---|
| DOI | 95% |
| Abstract | 100% |
| Authors | 100% |
| Institution | 75% |
| References (>=1) | 73% |
| Primary topic | 100% |
| Open access | 75% |
| PDF URL | 50% |
| Also on arXiv | 22% |

### Findings
- Duplicates in the sample: none (OpenAlex ID, DOI, title).
- Abstracts come as an inverted index and must be rebuilt into plain text.
- Types: article 31, conference-paper 31, preprint 21, and about 17 others (dataset, book, report, dissertation, software, ...).
- 91% English. 30% of papers are from 2026, so many are very recent with few citations.
- References per paper: mean 19, median 12.5, max 233. 27% have none.
- References pointing inside the sample: 0 (expected with a random sample).

### Fields we keep
id, doi, title, publication_year, publication_date, type, language, cited_by_count,
abstract (rebuilt), authorships (author id, name, institutions), primary_topic and topics,
referenced_works, open_access.is_oa, best_oa_location.pdf_url, locations (to find the arXiv ID).

### Fields we ignore
apc_list, apc_paid, awards, mesh, concepts (deprecated), counts_by_year, funders, biblio,
study_designs, sustainable_development_goals, fwci, relevance_score, and similar metadata.

## arXiv (sample: 100 latest cs.LG / cs.AI)
- Fields we get: id, title, abstract, published date, authors, categories, doi, journal_ref, pdf_url.
- With DOI: 2%. With journal_ref: 2%. With pdf_url: 100%.
- Authors have names only (no IDs, usually no institutions).
- Use: abstracts and open-access PDFs. arXiv gives a PDF for every paper, while OpenAlex has a PDF URL for only 50%.
- Matching arXiv to OpenAlex: arXiv's own DOI field is almost always empty, so DOI matching alone won't work.
  Match on the arXiv ID instead: OpenAlex lists it in locations (landing_page_url contains arxiv.org/abs/<id>),
  and the DOI of an arXiv paper is 10.48550/arXiv.<id>, which we can build ourselves.
  Fall back to normalized title only if both fail.

## Decisions for Day 3 (schema)
1. Keep only types: article, conference-paper, preprint.
2. Keep only papers with an abstract. Keep English first; other languages can be added later.
3. Required columns: title, abstract. All other columns are nullable (DOI, year, PDF URL, institution).
4. Store references as cited OpenAlex IDs even when the cited paper is not in our database
   (paper_references.cited_openalex_id; cited_paper_id is filled later when it exists).
5. Add papers.has_full_text and papers.pdf_url. Papers without a PDF are indexed by abstract only.
6. Unique keys for deduplication: doi, openalex_id, arxiv_id.
7. Authors and institutions are separate tables, linked through paper_authors.
8. The sample is too small for citation links. Day 5 loads 5,000 papers, ideally from a focused
   topic so papers cite each other.