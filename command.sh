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