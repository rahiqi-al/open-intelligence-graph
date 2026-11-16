"""Ask the local LLM (Ollama) for the entities and relations of one paper."""
import json

import httpx

from open_intelligence.extraction.schema import JSON_SCHEMA
from open_intelligence.ingestion.common import retrying


import os
from open_intelligence import settings


def get_config() -> dict:
    """The extraction settings; OLLAMA_URL (set in Docker for Airflow) overrides the URL in settings.yaml."""
    cfg = dict(settings.load_config()["extraction"])
    cfg["ollama_url"] = os.getenv("OLLAMA_URL", cfg["ollama_url"])
    return cfg

PROMPT_VERSION = "v2"

SYSTEM_PROMPT = """You extract a knowledge graph from a research paper's title and abstract. Answer with JSON only.

Entity types:
- Method: algorithms, models, architectures, techniques
- Dataset: datasets and benchmarks
- Task: problems or applications
- Metric: evaluation measures
- Tool: software, libraries, systems

Entity roles: proposed (introduced by this paper), used (used or built on), compared (baseline or compared against).
Relations between entities: BASED_ON, IMPROVES_ON, OUTPERFORMS, USED_FOR, EVALUATED_ON, PART_OF.

Rules:
- Only named things that appear in the text. Copy names exactly as written (keep versions: LLaMA-13B, GPT-3).
- Never list descriptions or groups of things, such as "publicly available datasets" or "state-of-the-art models".
- When the abstract says one model beats another, add an OUTPERFORMS relation.
- At most 8 entities and 6 relations.
- Relations must connect two entities from your entity list."""

EXAMPLE_INPUT = """Title: FastRetriever: Efficient Dense Retrieval with Distilled Encoders
Abstract: We present FastRetriever, a dense retrieval method that distills a cross-encoder into a small bi-encoder. On MS MARCO and Natural Questions, FastRetriever improves MRR@10 over DPR while running 5x faster. We release the code as a PyTorch library."""

EXAMPLE_OUTPUT = {
    "entities": [
        {"name": "FastRetriever", "type": "Method", "role": "proposed"},
        {"name": "cross-encoder", "type": "Method", "role": "used"},
        {"name": "bi-encoder", "type": "Method", "role": "used"},
        {"name": "DPR", "type": "Method", "role": "compared"},
        {"name": "MS MARCO", "type": "Dataset", "role": "used"},
        {"name": "Natural Questions", "type": "Dataset", "role": "used"},
        {"name": "MRR@10", "type": "Metric", "role": "used"},
        {"name": "PyTorch", "type": "Tool", "role": "used"},
        {"name": "dense retrieval", "type": "Task", "role": "used"},
    ],
    "relations": [
        {"source": "FastRetriever", "relation": "BASED_ON", "target": "cross-encoder"},
        {"source": "FastRetriever", "relation": "OUTPERFORMS", "target": "DPR"},
        {"source": "FastRetriever", "relation": "EVALUATED_ON", "target": "MS MARCO"},
        {"source": "FastRetriever", "relation": "EVALUATED_ON", "target": "Natural Questions"},
    ],
}


def paper_text(title: str, abstract: str, max_chars: int) -> str:
    return f"Title: {title}\nAbstract: {' '.join(abstract.split())[:max_chars]}"


def check_ready(cfg: dict) -> None:
    """Fail early with a clear message if Ollama or the model is missing."""
    try:
        tags = httpx.get(f"{cfg['ollama_url']}/api/tags", timeout=10).json()
    except (httpx.HTTPError, ValueError):
        raise RuntimeError(
            f"Ollama is not reachable at {cfg['ollama_url']}. Start it: docker compose --profile llm up -d ollama"
        )
    names = {m["name"] for m in tags.get("models", [])}
    if cfg["model"] not in names and f"{cfg['model']}:latest" not in names:
        raise RuntimeError(
            f"model {cfg['model']} is not downloaded. Run: docker compose --profile llm exec ollama ollama pull {cfg['model']}"
        )


@retrying(min_wait=5, max_wait=30, attempts=3, multiplier=3)
def extract_raw(client: httpx.Client, text: str, cfg: dict) -> dict:
    """One LLM call. Returns the raw JSON (validated later by schema.clean_extraction)."""
    response = client.post(f"{cfg['ollama_url']}/api/chat", json={
        "model": cfg["model"],
        "stream": False,
        "format": JSON_SCHEMA,
        "keep_alive": "30m",
        "options": {"temperature": 0, "seed": 0, "num_ctx": 4096, "num_predict": 900},
        "messages": [  # the fixed start of the prompt is cached by Ollama between papers
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": EXAMPLE_INPUT},
            {"role": "assistant", "content": json.dumps(EXAMPLE_OUTPUT)},
            {"role": "user", "content": text},
        ],
    })
    response.raise_for_status()
    return json.loads(response.json()["message"]["content"])