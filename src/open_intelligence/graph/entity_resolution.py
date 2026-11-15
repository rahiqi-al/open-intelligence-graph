"""Merge duplicate entities across papers: same thing, different spelling, plural or acronym.

Rules only (no guessing): spelling/case/hyphen variants, simple plurals, and acronyms that the
abstracts themselves define, like "Retrieval-Augmented Generation (RAG)". Versions stay separate
(GPT-4 and GPT-4o are different entities).
"""
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

ROLE_RANK = {"proposed": 0, "used": 1, "compared": 2}  # if a paper has several roles for one entity

ACRONYM_RE = re.compile(r"((?:[A-Za-z][A-Za-z'\-]*\s+){1,8}[A-Za-z][A-Za-z'\-]*)\s*\(([A-Za-z][A-Za-z0-9\-]{1,12})\)")

PAREN_RE = re.compile(r"^(.*\S)\s*\([^()]*\)?$")


def clean_name(name: str) -> str:
    """'large language models (LLMs)' and the broken 'large language models (LLMs' -> 'large language models'."""
    name = " ".join(name.split())
    m = PAREN_RE.match(name)
    return m.group(1) if m else name


def entity_key(name: str) -> str:
    """'GPT-4', 'gpt 4' -> 'gpt4'. 'Transformers' -> 'transformer', 'LLMs' -> 'llm'."""
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    if len(key) >= 4 and key.endswith("s") and not key.endswith(("ss", "us", "is")):
        key = key[:-1]
    return key


def find_acronyms(text: str) -> list[tuple[str, str]]:
    """Pairs (acronym, long form) defined in the text, e.g. ('RAG', 'Retrieval-Augmented Generation')."""
    pairs = []
    for m in ACRONYM_RE.finditer(text or ""):
        phrase, acronym = m.group(1), m.group(2)
        core = acronym[:-1] if len(acronym) > 2 and acronym.endswith("s") and acronym[:-1].isupper() else acronym
        letters = re.sub(r"[^A-Za-z]", "", core).upper()
        if not 2 <= len(letters) <= 8:
            continue
        words = list(re.finditer(r"[A-Za-z][A-Za-z']*", phrase))
        if len(words) < len(letters):
            continue
        tail = words[-len(letters):]
        if "".join(w.group(0)[0].upper() for w in tail) == letters:  # initials must match the acronym
            pairs.append((acronym, phrase[tail[0].start():].strip()))
    return pairs


def build_acronym_map(texts) -> dict[str, str]:
    """acronym key -> long form key. An acronym with two different meanings is left alone."""
    found: dict[str, set] = defaultdict(set)
    for text in texts:
        for acronym, long_form in find_acronyms(text):
            a, l = entity_key(acronym), entity_key(long_form)
            if a and l and a != l:
                found[a].add(l)
    return {a: next(iter(longs)) for a, longs in found.items() if len(longs) == 1}


@dataclass
class Resolved:
    entities: list = field(default_factory=list)   # {key, name, type, aliases, n_papers}
    mentions: list = field(default_factory=list)   # {paper_id, key, role}
    relations: list = field(default_factory=list)  # {source, relation, target, paper_ids}
    stats: dict = field(default_factory=dict)


def resolve_entities(rows, abstracts) -> Resolved:
    """rows: (paper_id, entities, relations) from paper_extractions; abstracts: {paper_id: text}."""
    acronyms = build_acronym_map(abstracts.values())

    def canon(name: str) -> str:
        key = entity_key(clean_name(name))
        return acronyms.get(key, key)

    surface: dict[str, Counter] = defaultdict(Counter)
    types: dict[str, Counter] = defaultdict(Counter)
    papers: dict[str, set] = defaultdict(set)
    roles: dict[tuple, str] = {}
    names_before = set()
    for paper_id, entities, _relations in rows:
        for e in entities or []:
            name = clean_name(e["name"])
            key = canon(name)
            if not key:
                continue
            names_before.add(name.lower())
            surface[key][name] += 1
            types[key][e["type"]] += 1
            papers[key].add(paper_id)
            current = roles.get((paper_id, key))
            if current is None or ROLE_RANK[e["role"]] < ROLE_RANK[current]:
                roles[(paper_id, key)] = e["role"]

    result = Resolved()
    for key in sorted(surface):
        # show the full name rather than the acronym when both exist
        candidates = [n for n in surface[key] if entity_key(n) == key] or list(surface[key])
        display = max(candidates, key=lambda n: (surface[key][n], len(n)))
        result.entities.append({
            "key": key, "name": display, "type": types[key].most_common(1)[0][0],
            "aliases": sorted(set(surface[key]) - {display}), "n_papers": len(papers[key]),
        })
    result.mentions = [{"paper_id": p, "key": k, "role": r} for (p, k), r in sorted(roles.items())]

    edges: dict[tuple, set] = defaultdict(set)
    for paper_id, _entities, relations in rows:
        for r in relations or []:
            source, target = canon(r["source"]), canon(r["target"])
            if source != target and source in surface and target in surface:
                edges[(source, r["relation"], target)].add(paper_id)
    result.relations = [{"source": s, "relation": rel, "target": t, "paper_ids": sorted(ids)}
                        for (s, rel, t), ids in sorted(edges.items())]

    result.stats = {
        "papers": len(rows),
        "distinct_names_before": len(names_before),
        "entities_after_merge": len(result.entities),
        "entities_in_2plus_papers": sum(1 for e in result.entities if e["n_papers"] >= 2),
        "acronyms_known": len(acronyms),
        "relations": len(result.relations),
    }
    return result