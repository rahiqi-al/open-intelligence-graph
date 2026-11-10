# Open Intelligence Graph

AI-powered research intelligence platform that connects scientific literature into a searchable knowledge graph.

Turn fragmented scientific literature into connected, searchable and actionable knowledge.

## Table of contents

1. [The problem](#1-the-problem)
2. [The solution](#2-the-solution)
3. [MVP features](#3-mvp-features)
4. [Architecture and diagrams](#4-architecture-and-diagrams)
5. [Tools and technology stack](#5-tools-and-technology-stack)
6. [Concepts](#6-concepts)
7. [Data sources](#7-data-sources)
8. [Data model](#8-data-model)
9. [Security](#9-security)
10. [Evaluation](#10-evaluation)
11. [Repository structure](#11-repository-structure)
12. [20-day plan](#12-20-day-plan)
13. [Getting started](#13-getting-started)

## 1. The problem

Researching a technical subject often means going through hundreds or thousands of papers to understand existing approaches, compare findings, identify limitations and discover connections between studies.

1. **Too much information** — thousands of papers exist on the same subject; finding the relevant ones takes time.
2. **Fragmented knowledge** — papers are connected through citations, authors, methods and findings, but these connections are hard to explore manually.
3. **Difficult comparisons** — understanding contradictory results, comparing methodologies and finding what is unexplored requires reading many papers.

Traditional search finds documents. Synthesizing knowledge across a large collection is still manual work.

## 2. The solution

A platform that:

- Finds relevant research with semantic search.
- Discovers connections between papers, authors, institutions, topics and methods.
- Compares methodologies and findings across studies.
- Traces how a research topic has evolved.
- Generates evidence-backed answers and literature reviews with citations.


## 3. MVP features

1. Search and filter papers.
2. View paper details and references.
3. Explore relationships between papers.
4. Ask questions and receive cited answers.

The focus is data engineering, retrieval and LLM security. The UI is a simple Streamlit app added at the end.

## 4. Architecture and diagrams

Each diagram has its own file in [`docs/diagrams/`](docs/diagrams).

| # | Diagram | What it shows |
|---|---|---|
| 01 | [System architecture](docs/diagrams/01_system_architecture.md) | All layers end to end |
| 02 | [Data pipeline](docs/diagrams/02_data_pipeline.md) | APIs → raw JSON → cleaning → deduplication → PostgreSQL |
| 03 | [Indexing pipeline](docs/diagrams/03_indexing_pipeline.md) | PDFs → chunks → Qdrant, entities → Neo4j |
| 04 | [Hybrid retrieval workflow](docs/diagrams/04_hybrid_retrieval_workflow.md) | Vector RAG + GraphRAG → fusion → rerank → answer → citation check |
| 05 | [Knowledge graph model](docs/diagrams/05_knowledge_graph_model.md) | Neo4j nodes and relationships |
| 06 | [Agent workflow](docs/diagrams/06_agent_workflow.md) | LangGraph router, specialist agents, critic |
| 07 | [Evaluation workflow](docs/diagrams/07_evaluation_workflow.md) | Vector vs Graph vs Hybrid measurement |
| 08 | [Security workflow](docs/diagrams/08_security_workflow.md) | RBAC, prompt-injection defence, trust boundary, output guard |

Storage roles:

- **MinIO** — raw API JSON and PDFs.
- **PostgreSQL** — source of truth for paper metadata, users and roles.
- **Qdrant** — vector representations of text chunks.
- **Neo4j** — research relationships.
- `paper_id` links the stores; every chunk keeps its paper ID, location and access level for citations and RBAC.

## 5. Tools and technology stack

Everything runs in **Docker Compose**.

| Layer | Tools |
|---|---|
| Package manager | **pip** |
| Language | Python 3.11+ |
| Data pipelines | Python, Pandas, httpx, Airflow |
| Object storage | MinIO |
| Relational database | PostgreSQL |
| Vector database | Qdrant |
| Knowledge graph | Neo4j |
| PDF processing | PyMuPDF |
| Embeddings | BGE or E5 (sentence-transformers) |
| Reranking | BGE reranker (cross-encoder) |
| LLM | Qwen / Llama via Ollama, or an API-based model |
| Orchestration | LangGraph |
| Security | RBAC, prompt-injection detection, trust boundary, output guard |
| Evaluation | RAGAS + custom retrieval metrics + pytest |
| Tracing | Langfuse |
| UI (last) | Streamlit |

Docker Compose services: `postgres`, `minio`, `qdrant`, `neo4j`, `airflow`, `langfuse`, `ollama`, `app`.

## 6. Concepts

| Concept | What you build |
|---|---|
| API ingestion | Paginated, incremental extraction |
| Data quality | Validation, deduplication, logging |
| Chunking | Section-aware chunks with paper ID, section, page |
| Embeddings | BGE / E5 vectors per chunk |
| Vector RAG | Semantic retrieval from Qdrant |
| Reranking | Cross-encoder reordering of candidates |
| Hierarchical RAG | Document → section → chunk retrieval |
| Entity and relationship extraction | Methods, topics, concepts from text |
| Entity resolution | Merging duplicate entities |
| Knowledge graph | Neo4j research graph |
| GraphRAG | Relationship-based retrieval linked back to chunks |
| Multi-hop retrieval | Following several relationships |
| Hybrid retrieval | Vector RAG + GraphRAG, fused |
| Evidence fusion | Merge and deduplicate both result sets |
| Context construction | Compact, source-tagged LLM context |
| Citation verification | Every claim checked against retrieved evidence |
| Summaries | Per-paper and cross-paper summaries |
| Query routing | Choose the retrieval strategy per question |
| Agentic RAG | Research, Graph, Comparison, Report, Critic agents |
| RBAC | Roles with document-level access filtering |
| Prompt-injection defence | Direct (question) and indirect (retrieved chunks) |
| Trust boundary | Retrieved text treated as untrusted data |
| Output guard | Leakage and citation checks on answers |
| Evaluation | Recall@K, MRR, nDCG, RAGAS, ablation study, security tests |
| Observability | Latency, token cost, failures |

## 7. Data sources

| Source | Data |
|---|---|
| [OpenAlex](https://docs.openalex.org/) | Works, titles, abstracts, authors, institutions, topics, citations |
| [arXiv](https://info.arxiv.org/help/api/index.html) | Metadata, abstracts, open-access full text |

Scope: AI, Machine Learning and Data Engineering. Start with 100 papers, then 5,000; scale to 20,000+ later.
Papers without an accessible PDF are indexed by metadata and abstract only.

## 8. Data model

**PostgreSQL:** `papers`, `authors`, `institutions`, `topics`, `paper_authors`, `paper_references`, `paper_topics`, `users` (with `role`).

**MinIO buckets:** `raw-json`, `pdfs`.

**Qdrant:** one point per chunk — `chunk_id`, `paper_id`, `section`, `page`, `access_level`, `text`, `embedding`.

**Neo4j:**

```
(Paper)-[:AUTHORED_BY]->(Author)
(Author)-[:AFFILIATED_WITH]->(Institution)
(Paper)-[:CITES]->(Paper)
(Paper)-[:DISCUSSES]->(Topic)
(Paper)-[:USES_METHOD]->(Method)
(Paper)-[:RELATED_TO]->(Paper)
```

## 9. Security

| Area | Implementation |
|---|---|
| RBAC | Roles `admin`, `researcher`, `viewer`; each role has allowed actions |
| Document-level access | Chunks carry an `access_level`; Qdrant filters and Neo4j queries respect the user's role |
| Prompt-injection defence | Input guard on the question; scan of retrieved chunks for hidden instructions |
| Trust boundary | Retrieved text wrapped as untrusted data, never treated as instructions |
| System-prompt hardening | Only the system prompt and the user question can give instructions |
| Output guard | Citation required for every claim; no system-prompt or restricted-content leakage |
| Security tests | Injection payloads and RBAC leak cases in `data/evaluation/security_cases.json` |

Workflow: [diagram 08](docs/diagrams/08_security_workflow.md).

## 10. Evaluation

| What | How |
|---|---|
| Retrieval quality | Recall@K, MRR, nDCG (implemented from scratch) |
| Answer quality | RAGAS: faithfulness, answer relevancy, context precision, context recall |
| Citation correctness | Share of claims supported by the cited chunk |
| Ablation | Vector only vs Graph only vs Hybrid on the same question set |
| Security | Injection block rate; RBAC leak rate (must be 0) |
| Observability | Langfuse traces: latency, token cost, failures |
| Regression | pytest suite on key questions and security cases |

## 11. Repository structure

```
open-intelligence-graph/
├── README.md
├── .gitignore
├── .env.example
├── Dockerfile
├── requirements*.txt
├── pyproject.toml
├── docker-compose.yml
├── config/
│   └── settings.yaml
├── infrastructure/
│   ├── postgres/schema.sql
│   └── neo4j/constraints.cypher
├── airflow/dags/
│   ├── ingestion_dag.py
│   └── indexing_dag.py
├── src/open_intelligence/
│   ├── ingestion/          # openalex.py, arxiv.py
│   ├── processing/         # cleaning.py, deduplication.py, validation.py
│   ├── database/           # postgres.py, minio_store.py
│   ├── documents/          # pdf_extractor.py, section_detector.py, chunker.py
│   ├── embeddings/         # embedder.py
│   ├── vector_store/       # qdrant_store.py
│   ├── knowledge_graph/    # entity_extractor.py, entity_resolution.py, graph_builder.py, neo4j_store.py
│   ├── retrieval/          # vector_retriever.py, graph_retriever.py, hierarchical.py, multi_hop.py,
│   │                       # fusion.py, reranker.py, hybrid_retriever.py, context_builder.py
│   ├── security/           # rbac.py, injection_guard.py, trust_boundary.py, output_guard.py
│   ├── generation/         # llm.py, prompts.py, citation_verifier.py
│   ├── agents/             # router.py, research_agent.py, graph_agent.py, comparison_agent.py,
│   │                       # report_agent.py, critic_agent.py, workflow.py
│   └── evaluation/         # metrics.py, ragas_eval.py, ablation.py
├── scripts/                # run_ingestion.py, build_vector_index.py, build_graph.py
├── app/
│   └── streamlit_app.py    # added at the end
├── data/
│   └── evaluation/         # questions.json, security_cases.json
├── notebooks/              # data exploration
├── tests/                  # test_cleaning.py, test_chunker.py, test_retrieval.py, test_citations.py,
│                           # test_rbac.py, test_injection.py, test_output_guard.py
└── docs/diagrams/          # 01 to 08, one file per diagram
```

## 12. 20-day plan

### Phase A — Data foundation (Days 1–5)

| Day | Goal | Output |
|---|---|---|
| 1 | Create the repo, reate the venv, add requirements files, write `docker-compose.yml` (PostgreSQL, MinIO, Qdrant, Neo4j), define scope | Services start with `docker compose up` |
| 2 | Explore OpenAlex and arXiv APIs; fetch 100 sample papers; inspect the raw JSON | Sample JSON + exploration notebook |
| 3 | Inspect missing values, duplicates and relationships; design `schema.sql` (including `users` and roles); load the sample into PostgreSQL | Schema + 100 papers in PostgreSQL |
| 4 | Reusable OpenAlex ingestion: pagination, incremental runs, raw JSON stored in MinIO, logging, error handling | `ingestion/openalex.py` working |
| 5 | Cleaning, deduplication (DOI + source IDs), quality checks; load 5,000 papers | 5,000 clean papers in PostgreSQL |

### Phase B — Vector RAG (Days 6–10)

| Day | Goal | Output |
|---|---|---|
| 6 | Download open-access PDFs into MinIO; extract text with PyMuPDF | Text for papers with PDFs |
| 7 | Section detection and chunking with metadata (`paper_id`, section, page, access level) | Chunks ready to embed |
| 8 | Generate embeddings (BGE/E5); create the Qdrant collection; index all chunks | Searchable Qdrant collection |
| 9 | Vector retriever + LLM answer with citations (first end-to-end RAG) | Question → cited answer |
| 10 | Reranker + hierarchical retrieval (document → section → chunk) | Improved retrieval quality |

### Phase C — Knowledge graph and GraphRAG (Days 11–14)

| Day | Goal | Output |
|---|---|---|
| 11 | Extract entities and relationships (methods, topics, concepts) from chunks | Structured entities |
| 12 | Entity resolution; build the Neo4j graph from PostgreSQL and extracted entities | Populated knowledge graph |
| 13 | Graph retriever with Cypher traversal; multi-hop retrieval; link results back to Qdrant chunks | GraphRAG working |
| 14 | Hybrid retrieval: parallel Vector + Graph, fusion, deduplication, rerank, context builder | Hybrid retriever |

### Phase D — Generation, security and agents (Days 15–17)

| Day | Goal | Output |
|---|---|---|
| 15 | Prompts, cited answer generation, citation verification, per-paper and cross-paper summaries | Verified cited answers |
| 16 | Security: RBAC with document-level filters, prompt-injection detection, chunk scan, trust boundary, output guard | Secured RAG pipeline |
| 17 | LangGraph: router, Research, Graph, Comparison, Report and Critic agents | Full agentic workflow |

### Phase E — Evaluation and delivery (Days 18–20)

| Day | Goal | Output |
|---|---|---|
| 18 | Golden question set (50+); implement Recall@K, MRR, nDCG; run RAGAS | Evaluation scores |
| 19 | Ablation (Vector vs Graph vs Hybrid); Langfuse tracing; security test cases; pytest regression suite | Comparison report |
| 20 | Airflow DAGs for ingestion and indexing; Streamlit UI; add `app` to Docker Compose; final README and results | Finished project |

Do not start a day until the previous one works.

## 13. Getting started

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .

cp .env.example .env
docker compose up -d

python scripts/check_services.py
pytest
```

| Service | URL |
|---|---|
| MinIO console | http://localhost:9001 |
| Qdrant | http://localhost:6333/dashboard |
| Neo4j browser | http://localhost:7474 |
| PostgreSQL | localhost:5432 |
| Airflow | http://localhost:8080 |
| Langfuse | http://localhost:3000 |
| Ollama | http://localhost:11434 |
| Streamlit app | http://localhost:8501 |
