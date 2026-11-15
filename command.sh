## Workflow 1: from ingesting data to a searchable system (offline)

Everything starts with Airflow, which runs the pipeline on a schedule. It calls the OpenAlex and arXiv APIs and downloads papers page by page. On later runs it only fetches papers that are new or updated, which is what incremental ingestion means. Each response is saved untouched as raw JSON in MinIO. That way, if you change your cleaning rules later, you can replay the data without calling the APIs again.

Next comes cleaning. Titles and authors are trimmed and normalized, and DOIs and years are standardized. OpenAlex stores abstracts in an unusual format, so the abstract is rebuilt into plain text. Then deduplication removes papers that appear twice, matching first on DOI, then on source IDs, then on the normalized title. Quality checks follow: a record with no title or an invalid year is logged and skipped. The clean records are loaded into PostgreSQL, which is the source of truth for papers, authors, institutions, topics, citations and users. After this step you have a structured dataset.

The second stage turns those papers into something an AI can search. For papers with an open-access PDF, the PDF is downloaded into MinIO and PyMuPDF extracts its text. Headers, footers and the reference list are removed. The text is split by section (abstract, introduction, methods, results), and each section is cut into overlapping chunks of about 512 tokens. Every chunk keeps its `paper_id`, section, page number and an access level, so later steps can cite it and filter it by role. Papers with no PDF are indexed by their abstract only.

From here the chunks go two ways. In the first, an embedding model (BGE or E5) turns each chunk into a vector, and the vectors are stored in Qdrant. This lets you later search by meaning rather than exact words. In the second, an LLM reads the chunks and extracts entities and relationships, such as which methods a paper uses and which topics it discusses. Entity resolution merges variants like "GraphRAG" and "Graph RAG" into one node. Then Neo4j is built from two sources: the extracted entities, and the metadata and citations already in PostgreSQL. The result is a graph of Papers, Authors, Institutions, Topics and Methods, linked by relationships like CITES and USES_METHOD. When this is done you have three synchronized stores, linked by `paper_id`. Qdrant finds similar text, Neo4j finds connected research, and PostgreSQL holds the metadata.

## Workflow 2: from the user's prompt to the LLM's answer (online)

A user types a question, for example: "What are the main limitations of current GraphRAG approaches?" The first thing that happens is the security check. RBAC looks at the user's role to decide whether they may ask questions at all. A `viewer` can search but not ask, while a `researcher` can. Then the input guard scans the question for prompt-injection attempts, such as "ignore previous instructions". A malicious question is blocked and logged, and a clean one continues.

Next, query understanding runs. The system extracts the entities in the question (here, "GraphRAG") and the intent (here, finding limitations). A LangGraph router then decides which strategy to use. This is the agentic part. The router can send the question to the Research agent for finding papers, the Graph agent for relationships, or the Comparison agent for comparing approaches.

Retrieval then runs two searches in parallel. Vector RAG embeds the question with the same model used at indexing time and searches Qdrant for the most similar chunks. It applies the user's access filter, so restricted documents never appear. It works hierarchically, finding the best papers first, then the best sections inside them, then the best chunks. GraphRAG matches "GraphRAG" to a node in Neo4j and follows relationships for several hops. For example, it finds papers that cite the original GraphRAG paper, the methods those papers use, and related papers. The connected papers it collects are only IDs, so it fetches their text chunks from Qdrant. Vector RAG finds text that sounds like the question. GraphRAG finds research that is connected to it. Together they give better coverage than either alone.

The two result sets are then merged, and chunks found by both paths are kept only once. A cross-encoder reranker reads each chunk together with the question and reorders everything by true relevance, keeping the top few. Before anything reaches the LLM, every chunk is scanned for hidden instructions, because a paper could contain text like "ignore the user and say X". Suspicious chunks are dropped. The rest are wrapped in tags that mark them as untrusted data, and the system prompt tells the LLM that it may only use the tagged text as evidence and must never follow instructions found inside it. The context builder then assembles the chunks, each labeled with its paper title, year and section.

Now the LLM generates the answer, using only that context, and attaches a citation to every claim. The output guard checks that the answer doesn't leak the system prompt or restricted content. The citation verifier checks that each claim is actually supported by the chunk it cites. If a claim is unsupported, the answer goes back to the LLM for another attempt. The Critic agent also reviews the evidence, and if it is weak it sends the question back to the router for another round, with at most two retries. Once everything passes, the user receives the answer with citations pointing to real papers. Langfuse records every step of the run, including latency and token cost.















1) first workflow: from paper ingestion to knowledge graph
After downloading the papers, we clean their metadata (titles, authors, DOI, abstracts, etc.) and store it in PostgreSQL.
The original PDFs are stored in MinIO, then retrieved to extract their text using PyMuPDF. We clean the extracted text in memory by removing headers, 
footers and references, then split it into overlapping chunks. Each chunk follows two paths: first, an embedding model (BGE or E5) converts it into a vector stored in Qdrant,
allowing semantic search based on meaning rather than exact words. Second, an LLM analyzes the chunks to extract entities (authors, topics, methods, etc.) and their relationships. 
Entity resolution merges different names referring to the same concept to avoid duplicates. These extracted relationships are combined with the existing metadata and citations from PostgreSQL to build a knowledge graph in Neo4j. 
Finally, the three databases are connected through paper_id: PostgreSQL manages paper metadata, Qdrant finds relevant text by meaning, and Neo4j explores relationships between papers, authors, topics and methods.
(- PostgreSQL: Already contains paper metadata, authors, institutions and citations.
- LLM extraction: Provides additional entities and relationships discovered inside the paper's text. information (entities))





2) second workflow: from the user's prompt to the LLM's answer (online)
1. Merge results: Combine chunks from Vector RAG and GraphRAG, removing duplicates.
2. Reranking: The Cross-Encoder ranks all combined chunks by relevance and keeps the best ones.
3. Security scan: Scan selected chunks for prompt injection. Drop suspicious chunks and log them.
4. Context builder: Organize the remaining chunks with paper titles, years, sections and page numbers.
5. LLM generation: Generate an answer using the retrieved evidence.
6. Output guard: Check the generated answer for system prompt leakage or restricted content.
7. Citation verifier: Check whether each claim is supported by its cited chunk.
8. Critic agent: Evaluate the overall answer and evidence quality. If something is insufficient, request another retrieval round (maximum two retries).
9. Final response: Return the verified answer with citations.
10. Langfuse: Monitor the entire workflow, including agents, retrieval, latency, token usage, costs and errors.


- Citation verifier and Critic are different: The verifier checks citation accuracy; the Critic evaluates the overall quality of the answer and evidence.
- Langfuse is not a final step: It monitors the entire workflow while it runs.



# Summary: `pyproject.toml` in Python

## 1. What is `pyproject.toml`?

It's the main configuration file for a modern Python project.

It tells Python development tools:

- The project's name and version.
- Which Python version is required.
- Where our Python packages are located.
- How to build and install the project.
- Which dependencies are required.
- How to configure tools like pytest.

## 2. Why do we need it?

Imagine we create our own Python project with many modules (ingestion, retrieval, generation, etc.).

We want to import our own code just like we import installed libraries such as Pandas or Airflow.

For that, we need to make our project recognizable as an installable Python package.

`pyproject.toml` provides the configuration needed to do that.

## 3. Understanding our project structure

```
open-intelligence-graph/
│
├── pyproject.toml
│
├── src/
│   └── open_intelligence_graph/
│       ├── __init__.py
│       ├── ingestion/
│       ├── retrieval/
│       └── generation/
│
└── tests/
```

We use the src layout to separate our actual Python code from configuration files and tests.

Inside `pyproject.toml`, we specify:

```
[tool.setuptools.packages.find]
where = ["src"]
```

This tells setuptools to look inside `src/` to discover our Python packages.

The actual package is `open_intelligence_graph`, not `src`.

## 4. Understanding `pip install -e .`

This command is essential:

```
pip install -e .
```

| Part      | Meaning                          |
| --------- | -------------------------------- |
| `pip`     | Python package installer         |
| `install` | Install the project              |
| `-e`      | Editable installation            |
| `.`       | Current directory (project root) |

What happens?

1. Pip looks at the current project directory.
2. It reads `pyproject.toml`.
3. Setuptools discovers the packages inside `src/`.
4. Pip registers the project in the current Python environment.
5. Python can now find and import our modules.

Editable mode: Our source code stays in its original location. Changes to our Python files are immediately available without reinstalling the project.

## 5. Understanding the configuration

Our initial configuration:

```
[project]
name = "open-intelligence-graph"
version = "0.1.0"
requires-python = ">=3.11"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

| Section                           | Purpose                                     |
| --------------------------------- | ------------------------------------------- |
| `[project]`                       | Project information and requirements        |
| `[build-system]`                  | Defines the packaging/building tool         |
| `[tool.setuptools.packages.find]` | Tells setuptools where to discover packages |
| `[tool.pytest.ini_options]`       | Configures pytest to find tests in `tests/` |

## 6. Why this approach?

There are different ways to manage Python projects:

- `pip` + `pyproject.toml` + `setuptools`
- `uv` + `pyproject.toml`
- Poetry + `pyproject.toml`
- Hatch + `pyproject.toml`

We're choosing:

Our chosen stack

- `pyproject.toml`: Project configuration.
- `pip`: Package installation.
- `setuptools`: Packaging and package discovery.
- `venv`: Virtual environment.
- `pytest`: Testing.

This is a mature, professional and widely used approach.

## 7. The most important things to remember

1. `pyproject.toml` configures our Python project.
2. `where = ["src"]` tells setuptools where our Python packages live.
3. `setuptools` discovers our actual package: `open_intelligence_graph`.
4. `pip install -e .` registers our project in the Python environment in editable mode.
5. We can then import our code like any installed Python package.

For example:

```
from open_intelligence_graph.retrieval.retriever import Retriever
```

The ultimate goal: Make Open Intelligence Graph a properly structured, installable Python package whose modules can communicate through clean imports.




Yes! What you were doing is also correct, and it's a common approach when working with Python inside Docker, especially with Airflow.

But there's an important difference between your old approach and the new approach we're setting up.

## 1. What you were doing before

In your Docker Compose configuration:

```
environment:
  - PYTHONPATH=/project

volumes:
  - .:/project
```

You were doing two things:

First: Mounting your project

```
volumes:
  - .:/project
```

This tells Docker:

"Take my entire project directory on my computer and make it accessible inside the container at `/project`."

So your container can access your Python files.

Second: Setting PYTHONPATH

```
PYTHONPATH=/project
```

This tells Python:

"When looking for Python modules to import, also search inside `/project`."

For example, if you have:

```
/project/
    ingestion/
        loader.py
    retrieval/
        retriever.py
```

You can import:

```
from retrieval.retriever import Retriever
```

Because Python knows to look inside `/project`.

## 2. What is the difference?

You now have two ways to make Python find your code.

Method A: Docker + PYTHONPATH

```
volumes:
  - .:/project

environment:
  - PYTHONPATH=/project
```

Python searches directly inside the mounted directory.

Works

Method B: Docker + pyproject.toml + pip

```
volumes:
  - .:/project
```

Then inside the container:

```
pip install -e /project
```

Python registers your project as an installed package using its packaging configuration.

Works

With our `src/` layout, the second method discovers the package inside `/project/src/` automatically.

You could also use `PYTHONPATH=/project/src` with the first method.

## 3. Which method do professionals use?

Both exist in professional development, but they serve slightly different purposes.

| Approach                              | Assessment                 |
| ------------------------------------- | -------------------------- |
| Mount project + PYTHONPATH            | Simple, but less robust    |
| Mount project + editable installation | Better for development     |
| Install package into Docker image     | Recommended for production |

Why prefer installation?

- Python understands your project as a proper package.
- Dependencies can be declared and installed automatically.
- You don't need to manually configure `PYTHONPATH`.
- Your development environment behaves more like a real installed package.

## 4. What I recommend for Open Intelligence Graph

I'd use this architecture:

Development environment

Your computer

Source code + pyproject.toml

Docker bind mount

Docker container

```
pip install -e /project
```

Editable installation of our project

Production environment

Custom Docker image

Our application and dependencies installed inside the image

Running application

No source-code bind mount or PYTHONPATH needed

In production, we'd normally install the package into the image during the Docker build rather than mounting our development folder.

## 5. Final takeaway

Your previous approach wasn't wrong at all.

The difference is:

- `PYTHONPATH`: Tells Python where to search for code.
- `pip install -e .`: Registers your project as an installed package.
- Docker volume: Makes your local files accessible inside the container.

My choice for our project: `pyproject.toml` + `pip install -e .` during development, and package installation inside the Docker image for production.

This gives us a clean and professional foundation without unnecessarily complicating the architecture.



OpenAlex helps you discover and organize research papers.



arXiv helps you discover papers and obtain their PDFs for text extraction and RAG ingestion.


Day 2 summary

What we did: fetched 100 random AI papers from OpenAlex and 100 recent papers from arXiv, saved both as raw files, and inspected their fields, missing values, duplicates and relationships.

What we learned:

OpenAlex gives metadata and references. It has the abstract, authors, topics and reference lists, which is what the knowledge graph is built from. Its data is rich but incomplete: 27% of papers have no references, 25% have no institution, and only 50% have a PDF link.
arXiv gives full text. Every arXiv paper has a PDF, so arXiv is the main source for text chunks. Its metadata is thin: no author IDs, almost no DOIs.
Matching goes through the arXiv ID, not the DOI. arXiv’s DOI field is almost always empty. We find the arXiv ID inside OpenAlex’s locations, or build the DOI 10.48550/arXiv.<id> ourselves.
Filter the types. About 14% of OpenAlex works are datasets, books, software and similar, so we keep only articles, conference papers and preprints.
Allow missing data. Only title and abstract are required, and every other column must accept NULL.
The sample is too small for the graph. 0 of 1,910 references pointed to another paper in the sample, which is why Day 5 loads 5,000 papers from a focused topic.

Output: data/raw/openalex_sample.json, data/raw/arxiv_sample.json, data/raw/arxiv_sample.xml, the three exploration scripts and docs/data_exploration.md.











"## Workflow 1: from ingesting data to a searchable system (offline)

Everything starts with Airflow, which runs the pipeline on a schedule. It calls the OpenAlex and arXiv APIs and downloads papers page by page. On later runs it only fetches papers that are new or updated, which is what incremental ingestion means. Each response is saved untouched as raw JSON in MinIO. That way, if you change your cleaning rules later, you can replay the data without calling the APIs again.

Next comes cleaning. Titles and authors are trimmed and normalized, and DOIs and years are standardized. OpenAlex stores abstracts in an unusual format, so the abstract is rebuilt into plain text. Then deduplication removes papers that appear twice, matching first on DOI, then on source IDs, then on the normalized title. Quality checks follow: a record with no title or an invalid year is logged and skipped. The clean records are loaded into PostgreSQL, which is the source of truth for papers, authors, institutions, topics, citations and users. After this step you have a structured dataset.

The second stage turns those papers into something an AI can search. For papers with an open-access PDF, the PDF is downloaded into MinIO and PyMuPDF extracts its text. Headers, footers and the reference list are removed. The text is split by section (abstract, introduction, methods, results), and each section is cut into overlapping chunks of about 512 tokens. Every chunk keeps its `paper_id`, section, page number and an access level, so later steps can cite it and filter it by role. Papers with no PDF are indexed by their abstract only.

From here the chunks go two ways. In the first, an embedding model (BGE or E5) turns each chunk into a vector, and the vectors are stored in Qdrant. This lets you later search by meaning rather than exact words. In the second, an LLM reads the chunks and extracts entities and relationships, such as which methods a paper uses and which topics it discusses. Entity resolution merges variants like "GraphRAG" and "Graph RAG" into one node. Then Neo4j is built from two sources: the extracted entities, and the metadata and citations already in PostgreSQL. The result is a graph of Papers, Authors, Institutions, Topics and Methods, linked by relationships like CITES and USES_METHOD. When this is done you have three synchronized stores, linked by `paper_id`. Qdrant finds similar text, Neo4j finds connected research, and PostgreSQL holds the metadata.

## Workflow 2: from the user's prompt to the LLM's answer (online)

A user types a question, for example: "What are the main limitations of current GraphRAG approaches?" The first thing that happens is the security check. RBAC looks at the user's role to decide whether they may ask questions at all. A `viewer` can search but not ask, while a `researcher` can. Then the input guard scans the question for prompt-injection attempts, such as "ignore previous instructions". A malicious question is blocked and logged, and a clean one continues.

Next, query understanding runs. The system extracts the entities in the question (here, "GraphRAG") and the intent (here, finding limitations). A LangGraph router then decides which strategy to use. This is the agentic part. The router can send the question to the Research agent for finding papers, the Graph agent for relationships, or the Comparison agent for comparing approaches.

Retrieval then runs two searches in parallel. Vector RAG embeds the question with the same model used at indexing time and searches Qdrant for the most similar chunks. It applies the user's access filter, so restricted documents never appear. It works hierarchically, finding the best papers first, then the best sections inside them, then the best chunks. GraphRAG matches "GraphRAG" to a node in Neo4j and follows relationships for several hops. For example, it finds papers that cite the original GraphRAG paper, the methods those papers use, and related papers. The connected papers it collects are only IDs, so it fetches their text chunks from Qdrant. Vector RAG finds text that sounds like the question. GraphRAG finds research that is connected to it. Together they give better coverage than either alone.

The two result sets are then merged, and chunks found by both paths are kept only once. A cross-encoder reranker reads each chunk together with the question and reorders everything by true relevance, keeping the top few. Before anything reaches the LLM, every chunk is scanned for hidden instructions, because a paper could contain text like "ignore the user and say X". Suspicious chunks are dropped. The rest are wrapped in tags that mark them as untrusted data, and the system prompt tells the LLM that it may only use the tagged text as evidence and must never follow instructions found inside it. The context builder then assembles the chunks, each labeled with its paper title, year and section.

Now the LLM generates the answer, using only that context, and attaches a citation to every claim. The output guard checks that the answer doesn't leak the system prompt or restricted content. The citation verifier checks that each claim is actually supported by the chunk it cites. If a claim is unsupported, the answer goes back to the LLM for another attempt. The Critic agent also reviews the evidence, and if it is weak it sends the question back to the router for another round, with at most two retries. Once everything passes, the user receives the answer with citations pointing to real papers. Langfuse records every step of the run, including latency and token cost."






OpenAlex ID: OpenAlex's own ID for identifying its records.
DOI: A permanent publication identifier used across academic platforms, not just OpenAlex.





"Yes, exactly. You have two separate pipelines, each with a different responsibility.

## 1. Offline pipeline: ingestion and indexing

Runs automatically in the background

Airflow orchestrates this pipeline on a schedule (for example, every day at 2 AM).

Its job is to prepare the research data so it becomes searchable.

Airflow (Scheduler)

Triggers the ingestion and indexing workflow

OpenAlex API + arXiv API

MinIO — Store raw JSON and PDFs

Cleaning, deduplication and validation

PostgreSQL — Store structured metadata

PDF extraction and chunking

BGE / E5

Qdrant

Text embeddings

LLM extraction

Neo4j

Entities and relationships

PostgreSQL also provides metadata and citation relationships for Neo4j.

When the pipeline finishes:

- PostgreSQL contains structured metadata.
- Qdrant contains vectors representing paper chunks.
- Neo4j contains the research knowledge graph.

These three databases are linked through `paper_id`.

Important: Airflow orchestrates the workflow. It does not perform all the processing itself. It triggers Python scripts, Docker tasks or other processing jobs.

## 2. Online pipeline: retrieval and answer generation

Runs when a user asks a question

This pipeline does not need to wait for Airflow or run on a schedule. It is triggered by a user request.

User asks a question

Security checks + RBAC

Query understanding + LangGraph router

Vector RAG

Qdrant

GraphRAG

Neo4j

Merge results + deduplication

Cross-encoder reranking

Security checks + context building

LLM generates the answer

Citation verification + Critic

Final answer with citations

Langfuse monitors the execution, including latency, token usage and errors.

## 3. The difference between the two pipelines

|              | Offline pipeline                       | Online pipeline               |
| ------------ | -------------------------------------- | ----------------------------- |
| Trigger      | Airflow schedule                       | User question                 |
| Execution    | Background                             | On demand                     |
| Main purpose | Prepare and index data                 | Retrieve and generate answers |
| Uses         | APIs, MinIO, PostgreSQL, Qdrant, Neo4j | Qdrant, Neo4j, LLM            |
| Output       | Searchable research database           | Answer with citations         |

Think about it this way:

- Pipeline 1: Collects, processes and stores research papers so they are ready for AI search.
- Pipeline 2: Uses those already-indexed papers to answer users' questions.

One important detail: the offline pipeline can run again periodically to add new papers or update existing ones. The online pipeline accesses the latest successfully indexed data without rebuilding the entire database for every question."









Yes, exactly. You have two separate pipelines, each with a different responsibility.

## 1. Offline pipeline: ingestion and indexing

Runs automatically in the background

Airflow orchestrates this pipeline on a schedule (for example, every day at 2 AM).

Its job is to prepare the research data so it becomes searchable.

Airflow (Scheduler)

Triggers the ingestion and indexing workflow

OpenAlex API + arXiv API

MinIO — Store raw JSON and PDFs

Cleaning, deduplication and validation

PostgreSQL — Store structured metadata

PDF extraction and chunking

BGE / E5

Qdrant

Text embeddings

LLM extraction

Neo4j

Entities and relationships

PostgreSQL also provides metadata and citation relationships for Neo4j.

When the pipeline finishes:

- PostgreSQL contains structured metadata.
- Qdrant contains vectors representing paper chunks.
- Neo4j contains the research knowledge graph.

These three databases are linked through `paper_id`.

Important: Airflow orchestrates the workflow. It does not perform all the processing itself. It triggers Python scripts, Docker tasks or other processing jobs.

## 2. Online pipeline: retrieval and answer generation

Runs when a user asks a question

This pipeline does not need to wait for Airflow or run on a schedule. It is triggered by a user request.

User asks a question

Security checks + RBAC

Query understanding + LangGraph router

Vector RAG

Qdrant

GraphRAG

Neo4j

Merge results + deduplication

Cross-encoder reranking

Security checks + context building

LLM generates the answer

Citation verification + Critic

Final answer with citations

Langfuse monitors the execution, including latency, token usage and errors.

## 3. The difference between the two pipelines

|              | Offline pipeline                       | Online pipeline               |
| ------------ | -------------------------------------- | ----------------------------- |
| Trigger      | Airflow schedule                       | User question                 |
| Execution    | Background                             | On demand                     |
| Main purpose | Prepare and index data                 | Retrieve and generate answers |
| Uses         | APIs, MinIO, PostgreSQL, Qdrant, Neo4j | Qdrant, Neo4j, LLM            |
| Output       | Searchable research database           | Answer with citations         |

Think about it this way:

- Pipeline 1: Collects, processes and stores research papers so they are ready for AI search.
- Pipeline 2: Uses those already-indexed papers to answer users' questions.

One important detail: the offline pipeline can run again periodically to add new papers or update existing ones. The online pipeline accesses the latest successfully indexed data without rebuilding the entire database for every question.











This configuration defines what papers your pipeline collects from OpenAlex and how many.

### 1. General settings

| Parameter         | Meaning                                          |
| ----------------- | ------------------------------------------------ |
| `per_page: 100`   | Fetch 100 papers per API request.                |
| `year_from: 2018` | Only collect papers published from 2018 onwards. |
| `base_filter`     | Apply common filters to all queries.             |

Base filters:

- `primary_topic.field.id:17`: Only papers belonging to OpenAlex field ID 17.
- `has_abstract:true`: Papers must have an abstract.
- `type:article|conference-paper|preprint`: Only collect these three publication types.

### 2. Five research queries

Each query searches for papers on a specific topic.

| Query            | Search term                    | Maximum papers |
| ---------------- | ------------------------------ | -------------- |
| RAG              | Retrieval augmented generation | 1,500          |
| Knowledge Graph  | Knowledge graph                | 1,500          |
| LLM              | Large language model           | 1,000          |
| Graph ML         | Graph neural network           | 500            |
| Data Engineering | Data engineering               | 500            |
| Total            |                                | 5,000          |

### 3. What happens?

Your ingestion pipeline:

1. Sends five different searches to OpenAlex.
2. Retrieves papers matching each topic.
3. Collects up to the specified maximum for each query.
4. Downloads their metadata and abstracts (and potentially PDFs through a separate process).
5. Stores them for further processing.

Why five queries?

Because you want a focused research corpus covering related topics. This also helps your knowledge graph identify relationships between papers through their citations.


&&&&

Pagination: cursor paging, 100 works per page.
Raw storage: every page is saved untouched in MinIO at raw-json/openalex/<query>/<run time>/page_0001.json.
Incremental: results are sorted newest first. Each successful run records the newest publication date it saw. The next run asks only for works from that date on.
Errors: retries with exponential backoff on timeouts, 429 and 5xx errors. Any other error fails the run, and it is recorded.
Logging: console plus logs/ingestion.log.
Corpus focus: 5 focused queries (RAG, knowledge graph, LLM, graph neural network, data engineering) for about 5,000 papers. Papers on one topic cite each other, which the graph needs.









Design
Partition loading: each query is split into yearly partitions. A partition is one source, one query and one year, and it is fetched on its own. This works for any year range.
Closed years (backfill): a closed year is fetched once, most-cited papers first (arXiv: most relevant first). Once it succeeds it is skipped on every later run. Most-cited papers give you more papers that cite each other, which the graph needs.
Current year (incremental): this partition is fetched newest first, starting at the newest date already seen. A second run fetches only a few works.
Raw layout in MinIO (Hive-style): source=openalex/query=rag/window=2024/ingest_date=2026-11-11/run_ts=.../page_0001.json. Day 5 can read only the new ingest_date partitions.
Failures: a failed partition is recorded, and the next run retries it. One failed partition doesn’t stop the others.
Airflow later: plan() returns the list of partitions that need work. Each partition becomes one parallel Airflow task.
Test runs: runs with --limit are marked test and never move the incremental marker.



We have two stages:
1. Backfill: Collect existing papers from past years (2018–2025) to build our initial database.
2. Incremental loading: After that, regularly fetch only newly published papers (2026 onwards).
In simple terms: First, collect historical data. Then, keep updating the database with new data.







One Airflow DAG execution can trigger multiple ingestion tasks, and each task gets its own run_id.


















How it works
Scope: abstracts only, most cited papers first, about 100 per run. Running the LLM on all 30k chunks would take weeks on your CPU, so the full text stays in Qdrant for vector search.
Entities: Method, Dataset, Task, Metric and Tool, each with a role (proposed, used or compared).
Relations: BASED_ON, IMPROVES_ON, OUTPERFORMS, USED_FOR, EVALUATED_ON and PART_OF.
Reliable output: Ollama is forced to answer in an exact JSON schema, and the prompt has one worked example.
Hallucination check: an entity is kept only if it really appears in the title or abstract. Generic words (“model”, “approach”) are dropped, spelling variants are merged, and a relation is kept only if both ends survived.
Storage: results go in a Postgres table, paper_extractions (small JSON), because LLM calls are slow and we don’t want to redo them. Day 10 reads it, merges duplicates and writes the graph to Neo4j.


Postgres first or directly to Neo4j: you can write straight to Neo4j, and it would work. I’d still keep the Postgres step for two reasons:

LLM calls are slow. If we change the graph design or the duplicate-merge rules, we rebuild Neo4j from Postgres in seconds instead of redoing hours of LLM work.
Duplicates need all papers at once. “GPT-4” and “gpt4” from different papers must be merged before the graph is written, and Postgres also tracks done and failed papers so a run can resume.

It costs almost nothing, because it’s a small JSON table.

Parallel paths: yes, vector embedding and graph extraction don’t depend on each other, so in the Airflow DAG on Day 11 they run as two parallel branches. On your laptop they share the same CPU, so running both at once won’t be faster. One difference from the earlier plan is that the graph path reads the abstract from Postgres, not the chunks, because running the LLM on 30k chunks would take weeks.


The idea is simple: Use PostgreSQL as temporary storage before creating the Neo4j graph.

You could send the data directly to Neo4j, but PostgreSQL makes the process easier to manage.
Why keep PostgreSQL?
1. Avoid repeating expensive LLM calls

Imagine you extract information from 1,000 research papers using an LLM.
- The LLM extracts entities and relationships.
- You save the extracted results in PostgreSQL.
- Later, you decide to change how your Neo4j graph is structured.
Without PostgreSQL, you might need to process all 1,000 papers again using the LLM.

With PostgreSQL, you simply take the already-extracted data and rebuild Neo4j.

2. Detect and merge duplicates

Imagine two papers mention the same technology:
- Paper 1: GPT-4
- Paper 2: gpt4
They refer to the same entity.

PostgreSQL lets you collect the extracted entities from all papers first, identify duplicates, merge them, and then send the clean results to Neo4j.

3. Track processing progress

PostgreSQL also tracks each paper's status:
- Done: Successfully processed.
- Failed: Processing failed.
- Pending: Not processed yet.
If your pipeline stops, you can resume from where it stopped instead of starting over.




A profile in Docker Compose lets you group services and decide which ones to start. docker compose --profile orchestration up -d  mean run the default one core services and theone that have profile orchestration.









Ollama = The engine that runs AI models.
Model = The actual AI (e.g. Llama 3.1, Mistral, Qwen).
Run the container: Starts the Ollama server.



Pull the model: Downloads the model into the container's persistent volume.



Use the model: Ollama loads it into RAM when your Python application sends its first request.

- --limit, --dry-run, --plan, etc.: Arguments that tell the script how to behave. These are called command-line arguments (CLI arguments) or flags. They are used to control how a Python script runs.
Usually, developers define them using Python's argparse library.
CLI (Command-Line Interface) arguments are options defined by the developer inside the code to control how a script behaves.
2. What happens if you don't provide an argument?
Correct! The script uses its default value.

For example, if the code contains:
parser.add_argument("--limit", type=int, default=10)



Then:
python scripts/run_extraction.py


Processes 10 papers.

But:
python scripts/run_extraction.py --limit 5


Processes 5 papers.
. Two important types
Arguments with values:
--limit 5
--source arxiv


You provide a value.

Boolean flags:
--dry-run
--verbose
--force

Developers use CLI arguments to control a script without modifying its code every time.

For example, imagine your extraction script processes 1,000 research papers.


You simply include the flag to activate its behavior.


Other reasons developers use CLI arguments:
1. Automation: Run scripts automatically with different parameters using Airflow, cron jobs, or CI/CD pipelines.
2. Reusability: Use the same script for different projects, datasets, or environments.
3. Customization: Let users choose settings without needing to understand or edit the code.
4. Environment control: Specify development, testing, or production configurations.
5. Scalability: Change the number of records processed depending on available resources.
6. Reproducibility: Run the same script with the same arguments to reproduce a previous execution.
7. Error recovery: Use options like --retry or --force to control how failed or existing data is handled.
8. Integration: Allow other programs to execute Python scripts and pass parameters to them.







Speed: if it’s still around 60 seconds per paper after the shorter prompt, that’s the 3B model on your CPU






# **1. Qdrant hierarchy (from top to bottom)**

Think of Qdrant as a storage system organized into collections, points, vectors and payloads.

**Qdrant**

Vector database / server

**Collection**

Example: research_papers

**Points**

Each point represents one stored item (usually one chunk)

**Vector**

Numerical representation of the chunk

**Payload**

Original text and metadata

### **Meaning of each level**

| Level      | Meaning                                                |
| ---------- | ------------------------------------------------------ |
| Qdrant     | The database server.                                   |
| Collection | A group of points with a defined vector configuration. |
| Point      | One individual record stored in a collection.          |
| Vector     | Numbers representing the semantic meaning of text.     |
| Payload    | Additional information attached to a point.            |

**Example from your research paper RAG project:**

A research paper is divided into 20 chunks.

- Collection: `research_papers`
- Points: 20
- Each point contains one chunk's vector and payload.
- Payload can contain the chunk text, paper ID, title, page number and other metadata.

Note: A point can contain multiple named vectors if the collection is configured for that.

# **2. Distance metrics in Qdrant**

Distance tells Qdrant how to compare two vectors and determine how close or similar they are.

| Metric      | Simple meaning                                               | How to interpret                                                                      |
| ----------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| Cosine      | Compares the direction of two vectors.                       | Closer directions = more similar.                                                     |
| Euclidean   | Measures the straight-line distance between two vectors.     | Smaller distance = closer vectors.                                                    |
| Dot product | Multiplies corresponding vector values and adds the results. | Larger score generally means greater similarity for appropriately trained embeddings. |

### **Simple explanation of each**

**1. Cosine**

Imagine two arrows:

- If they point in almost the same direction, their vectors are similar.
- If they point in different directions, they are less similar.

It focuses on direction rather than vector length.

**2. Euclidean**

Imagine two points on a map.

Euclidean measures the straight-line distance between them.

- 2 units apart = closer.
- 10 units apart = farther.

**3. Dot product**

It compares vectors using multiplication and addition.

It considers both direction and magnitude (length).

The interpretation depends on how your embedding model produces its vectors.

**Important:** Cosine and Euclidean are distance metrics where lower is better. Dot product is a similarity score where higher is generally better.

# **3. Other important things to understand about Qdrant**

These are the concepts you should know when building your RAG pipeline.

| Concept           | Meaning                                             |
| ----------------- | --------------------------------------------------- |
| Embedding model   | Converts text chunks into numerical vectors.        |
| Vector dimensions | Number of values in each vector (e.g. 768 or 1536). |
| Payload           | Stores text and metadata associated with a point.   |
| Point ID          | Unique identifier for each point.                   |
| Similarity search | Finds vectors closest to your query vector.         |
| Top-K             | Number of closest results to retrieve.              |
| Filtering         | Restricts searches using metadata.                  |
| Upsert            | Inserts or updates points.                          |
| Delete            | Removes points from a collection.                   |
| Indexing          | Organizes data to make searching faster.            |
| Persistence       | Keeps your data stored between container restarts.  |

## **4. How this works in your RAG project**

**Research Paper PDF**

**Text Extraction**

**Chunking**

Divide text into smaller pieces

**Embedding Model**

Convert each chunk into a vector

**Qdrant**

Store vectors + payloads as points inside a collection

**User Question**

**Embedding Model**

Convert question into a vector using the same embedding model

**Similarity Search**

Find the most relevant chunks using the distance metric

**LLM**

Generate an answer using retrieved chunks

## **5. Five things you should particularly remember**

1. **Same embedding model:** Use a compatible embedding model for both stored chunks and user queries.
2. **Same dimensions:** The query vector dimensions must match the collection's vector configuration.
3. **Distance metric:** Choose a metric compatible with your embedding model.
4. **Payload:** Store useful metadata so you can identify where each retrieved chunk came from.
5. **Top-K:** Controls how many chunks you retrieve for the LLM.

For your project, an example payload could look like this:

```
{
  "paper_id": "paper_001",
  "chunk_id": "chunk_005",
  "text": "Retrieval-Augmented Generation...",
  "title": "Introduction to RAG",
  "page": 4,
  "source": "arxiv"
}
```

**My recommendation:** Understand the relationship between Collection → Point → Vector + Payload first. These are the foundations of working with Qdrant.



Embedding models convert text, images, or other data into numerical vectors that represent their meaning.

### **1. Main types of embedding models**

| Type                  | What they convert                                         |
| --------------------- | --------------------------------------------------------- |
| Text Embeddings       | Text into vectors.                                        |
| Image Embeddings      | Images into vectors.                                      |
| Multimodal Embeddings | Text, images and sometimes other modalities into vectors. |
| Audio Embeddings      | Audio into vectors.                                       |
| Video Embeddings      | Video content into vectors.                               |

### **2. Popular text embedding models**

These are particularly relevant to your RAG project.

| Model             | Provider  |
| ----------------- | --------- |
| BGE               | BAAI      |
| E5                | Microsoft |
| Nomic Embed       | Nomic     |
| GTE               | Alibaba   |
| OpenAI Embeddings | OpenAI    |
| Jina Embeddings   | Jina AI   |
| Qwen3-Embedding   | Alibaba   |

### **3. What should you know?**

Embedding models differ in:

- **Dimensions:** Number of values in the resulting vector.
- **Quality:** How well they capture semantic meaning.
- **Languages:** Some support multiple languages.
- **Context length:** How much text they can process at once.
- **Speed:** How quickly they generate embeddings.

### **4. For your research paper RAG project**

I would consider:

- `BGE`: Strong general-purpose text embeddings.
- `E5`: Good semantic search.
- `Qwen3-Embedding`: Modern multilingual embedding family.

**Important:** An embedding model is different from an LLM.

- LLM (Qwen, Llama): Generates answers and extracts information.
- Embedding model (BGE, E5): Converts text into vectors for similarity search.