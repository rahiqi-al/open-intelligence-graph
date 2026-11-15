"""What the LLM must return, and the checks that clean its answer (small LLMs make mistakes)."""
import re

ENTITY_TYPES = ["Method", "Dataset", "Task", "Metric", "Tool"]
ROLES = ["proposed", "used", "compared"]
RELATIONS = ["BASED_ON", "IMPROVES_ON", "OUTPERFORMS", "USED_FOR", "EVALUATED_ON", "PART_OF"]

# Ollama forces the model to answer in exactly this JSON shape
JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "type": {"type": "string", "enum": ENTITY_TYPES},
                "role": {"type": "string", "enum": ROLES},
            },
            "required": ["name", "type", "role"],
        }},
        "relations": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "relation": {"type": "string", "enum": RELATIONS},
                "target": {"type": "string"},
            },
            "required": ["source", "relation", "target"],
        }},
    },
    "required": ["entities", "relations"],
}


def _key(text: str) -> str:
    """'GPT-4' and 'gpt 4' give the same key."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


GENERIC_KEYS = {_key(w) for w in [
    "model", "models", "method", "methods", "approach", "approaches", "task", "tasks", "dataset",
    "datasets", "framework", "frameworks", "system", "systems", "algorithm", "algorithms",
    "technique", "techniques", "performance", "results", "data", "code", "paper", "work", "metric",
    "metrics", "tool", "tools", "benchmark", "benchmarks", "baseline", "baselines", "accuracy",
    "language model", "neural network", "deep learning", "machine learning",
]}


# words that show a description ("publicly available datasets"), not a name
DESCRIPTION_RE = re.compile(
    r"state-of-the-art|publicly|available|proprietary|inaccessible|existing|novel|proposed|various|"
    r"several|different|previous|prior work|recent|our |the best|baselines?\b", re.I)


def _resolve(key: str, entities: dict) -> str | None:
    """Find the kept entity a relation endpoint points to ('LLaMA-13B' -> 'LLaMA')."""
    if key in entities:
        return key
    close = [k for k in entities if len(k) >= 3 and len(key) >= 3 and (k in key or key in k)]
    return close[0] if len(close) == 1 else None


def _grounded(name: str, key: str, text: str, text_key: str) -> bool:
    """The entity must really appear in the title/abstract (the LLM sometimes invents names)."""
    if len(key) < 4:  # short acronyms (RL, GPT): the exact word must appear
        return re.search(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])", text) is not None
    return key in text_key


def clean_extraction(raw: dict, source_text: str, max_entities: int = 12, max_relations: int = 10) -> dict:
    text_key = _key(source_text)
    entities: dict[str, dict] = {}
    for e in raw.get("entities") or []:
        name = " ".join(str(e.get("name", "")).split()).strip(" .,;:()\"'")
        key = _key(name)
        if (not 2 <= len(name) <= 60 or key in GENERIC_KEYS or len(key) < 2
                or e.get("type") not in ENTITY_TYPES or e.get("role") not in ROLES
                or DESCRIPTION_RE.search(name)
                or (e.get("type") in ("Dataset", "Tool") and not re.search(r"[A-Z0-9]", name))
                or not _grounded(name, key, source_text, text_key)):
            continue
        entities.setdefault(key, {"name": name, "type": e["type"], "role": e["role"]})
        if len(entities) >= max_entities:
            break

    relations, seen = [], set()
    for r in raw.get("relations") or []:
        source = _resolve(_key(str(r.get("source", ""))), entities)
        target = _resolve(_key(str(r.get("target", ""))), entities)
        relation = r.get("relation")
        if relation not in RELATIONS or source is None or target is None or source == target:
            continue  # relations may only connect entities we kept
        if (source, relation, target) in seen:
            continue
        seen.add((source, relation, target))
        relations.append({"source": entities[source]["name"], "relation": relation,
                          "target": entities[target]["name"]})
        if len(relations) >= max_relations:
            break
    return {"entities": list(entities.values()), "relations": relations}