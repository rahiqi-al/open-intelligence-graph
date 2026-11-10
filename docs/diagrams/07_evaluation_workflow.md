# 07 — Evaluation Workflow

```mermaid
flowchart LR
    GS["1. Golden question set<br/>questions + expected papers"] --> RUN["2. Run 3 configurations"]
    RUN --> C1["Vector only"]
    RUN --> C2["Graph only"]
    RUN --> C3["Hybrid"]
    C1 & C2 & C3 --> M1["3a. Retrieval metrics<br/>Recall@K, MRR, nDCG"]
    C1 & C2 & C3 --> M2["3b. Answer metrics<br/>RAGAS: faithfulness, answer relevancy,<br/>context precision, context recall"]
    C1 & C2 & C3 --> M3["3c. Citation correctness"]
    C3 --> M5["3d. Security tests<br/>injection, RBAC leaks"]
    C1 & C2 & C3 --> TR["3e. Langfuse traces<br/>latency, tokens, failures"]
    M1 & M2 & M3 & M5 & TR --> REP["4. Comparison report"]
    REP --> IMP["5. Improve chunking, retrieval, prompts"]
    IMP --> RUN
```

## Steps

1. **Golden set** — 50+ questions with the papers that should be retrieved.
2. **Run** — the same questions through Vector-only, Graph-only and Hybrid.
3. **Measure**
   - **Retrieval metrics (custom)** — Recall@K, MRR, nDCG. Implement these yourself.
   - **RAGAS** — faithfulness, answer relevancy, context precision, context recall.
   - **Citation correctness** — share of cited claims supported by the cited chunk.
   - **Security tests** — injection payloads must be blocked; a `viewer` must never receive restricted documents.
   - **Langfuse** — latency, token cost, failures, per-step inputs and outputs.
4. **Report** — table comparing the three configurations.
5. **Improve** — adjust chunk size, top-K, reranker, prompts; run again.
6. **Regression** — a `pytest` suite keeps key questions and security cases from degrading.
