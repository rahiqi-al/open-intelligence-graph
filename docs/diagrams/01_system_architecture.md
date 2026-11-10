# 01 — System Architecture

Overall view of the platform. Every service runs in Docker Compose.

```mermaid
flowchart TB
    subgraph L1["1. Data sources"]
        OA[OpenAlex API]
        AX[arXiv API]
    end

    subgraph L2["2. Data engineering"]
        AF[Airflow]
        ING[Python ingestion<br/>pagination + incremental]
        CLN[Cleaning + deduplication<br/>+ quality checks]
    end

    subgraph L3["3. Storage"]
        MN[(MinIO<br/>raw JSON + PDFs)]
        PG[(PostgreSQL<br/>metadata + users + roles)]
        QD[(Qdrant<br/>chunk embeddings)]
        N4[(Neo4j<br/>knowledge graph)]
    end

    subgraph L4["4. Document processing"]
        PDF[PDF extraction]
        CHK[Section detection + chunking]
        EMB[Embeddings BGE / E5]
        ENT[Entity + relationship extraction]
    end

    subgraph L5["5. Security"]
        RB[RBAC + document access]
        IG[Prompt-injection guard]
        TB[Trust boundary]
        OG[Output guard]
    end

    subgraph L6["6. Hybrid retrieval"]
        VR[Vector RAG]
        GR[GraphRAG]
        FUS[Fusion + dedup]
        RR[Reranker]
        CTX[Context builder]
    end

    subgraph L7["7. Generation + agents"]
        LG[LangGraph workflow]
        LLM[LLM]
        CV[Citation verification]
    end

    subgraph L8["8. Evaluation + observability"]
        EV[RAGAS + retrieval metrics + ablation + security tests]
        LF[Langfuse tracing]
    end

    AF --> ING
    OA & AX --> ING --> MN
    MN --> CLN --> PG
    PG --> PDF
    MN --> PDF --> CHK
    CHK --> EMB --> QD
    CHK --> ENT --> N4
    PG --> N4

    LG --> RB --> IG --> VR & GR
    VR --> QD
    GR --> N4
    VR & GR --> FUS --> RR --> TB --> CTX --> LLM --> OG --> CV
    CV --> LG

    EV -. measures .-> L6
    EV -. measures .-> L5
    LF -. traces .-> LG
```

## Layers

1. **Data sources** — OpenAlex (papers, authors, institutions, topics, citations) and arXiv (abstracts, open-access full text).
2. **Data engineering** — Airflow schedules Python extractors that clean, deduplicate (DOI + source IDs) and validate.
3. **Storage** — MinIO keeps raw JSON and PDFs, PostgreSQL is the source of truth for metadata, users and roles, Qdrant stores chunk vectors, Neo4j stores relationships. `paper_id` links them.
4. **Document processing** — PDFs are extracted, split into sections and chunks, then embedded (Qdrant) and mined for entities (Neo4j).
5. **Security** — RBAC with document-level access, prompt-injection guard, trust boundary for retrieved text, output guard.
6. **Hybrid retrieval** — Vector RAG and GraphRAG run in parallel; results are fused, deduplicated, reranked and turned into a context.
7. **Generation + agents** — LangGraph orchestrates; the LLM answers; every claim is checked against retrieved evidence.
8. **Evaluation + observability** — retrieval metrics, RAGAS, ablation and security tests; Langfuse traces every run.
