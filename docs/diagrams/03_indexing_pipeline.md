# 03 — Indexing Pipeline (offline)

How stored papers become searchable vectors and a knowledge graph.

```mermaid
flowchart TB
    PG[("1. PostgreSQL papers")] --> DL["2. Download open-access PDFs"]
    DL --> MN[("MinIO<br/>PDFs")]
    MN --> EX["3. Extract text<br/>PyMuPDF"]
    EX --> SD["4. Detect sections<br/>abstract, intro, methods, results"]
    SD --> CH["5. Chunk<br/>keep paper_id, section, page, access level"]

    CH --> EM["6a. Embed chunks<br/>BGE / E5"]
    EM --> QD[("7a. Qdrant")]

    CH --> EN["6b. Extract entities + relations<br/>methods, topics, concepts"]
    EN --> ER["7b. Entity resolution<br/>merge duplicates"]
    ER --> N4[("8b. Neo4j")]
    PG --> N4
```

## Steps

1. **Papers** — metadata, abstract and PDF URL come from PostgreSQL.
2. **Download** — only open-access PDFs, stored in MinIO; papers without a PDF stay indexed by abstract.
3. **Extract** — PyMuPDF text extraction, cleaned of headers, footers and references.
4. **Sections** — split by heading so retrieval can work at document → section → chunk level.
5. **Chunk** — fixed size with overlap; each chunk keeps `paper_id`, `section`, `page` and an access level for RBAC filtering.
6a. **Embed** — one vector per chunk.
7a. **Qdrant** — one point per chunk with its payload.
6b. **Extract** — LLM-based extraction of methods, concepts and relations from chunks.
7b. **Resolve** — merge variants of the same entity ("GraphRAG", "Graph RAG").
8b. **Neo4j** — Paper, Author, Institution, Topic, Method nodes with their relationships; paper–paper links come from PostgreSQL citations.
