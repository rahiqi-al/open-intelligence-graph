from open_intelligence.graph.entity_resolution import (
    entity_key, find_acronyms, resolve_entities,
)


def ent(name, type_="Method", role="used"):
    return {"name": name, "type": type_, "role": role}


def rel(s, r, t):
    return {"source": s, "relation": r, "target": t}


def test_entity_key():
    assert entity_key("GPT-4") == entity_key("gpt 4") == "gpt4"
    assert entity_key("Transformers") == entity_key("Transformer")
    assert entity_key("LLMs") == entity_key("LLM")
    assert entity_key("GPT-4o") != entity_key("GPT-4")  # versions stay separate
    assert entity_key("BERT") == "bert" and entity_key("analysis") == "analysis"


def test_find_acronyms():
    text = ("We use Retrieval-Augmented Generation (RAG) and Chain-of-Thought (CoT) with Large Language Models (LLMs). "
            "We propose the new system (ABC) and a tool (a prototype).")
    assert find_acronyms(text) == [
        ("RAG", "Retrieval-Augmented Generation"), ("CoT", "Chain-of-Thought"), ("LLMs", "Large Language Models")]


def test_spelling_variants_merge_and_count_papers():
    rows = [(1, [ent("GPT-4")], []), (2, [ent("gpt 4")], []), (3, [ent("GPT-4o")], [])]
    result = resolve_entities(rows, {})
    by_key = {e["key"]: e for e in result.entities}
    assert by_key["gpt4"]["n_papers"] == 2 and by_key["gpt4"]["aliases"] == ["gpt 4"]
    assert "gpt4o" in by_key


def test_acronym_from_abstract_merges_and_shows_long_name():
    abstracts = {1: "We study Retrieval-Augmented Generation (RAG) for question answering."}
    rows = [(1, [ent("Retrieval-Augmented Generation")], []), (2, [ent("RAG")], []), (3, [ent("RAG")], [])]
    result = resolve_entities(rows, abstracts)
    assert len(result.entities) == 1
    e = result.entities[0]
    assert e["name"] == "Retrieval-Augmented Generation" and e["aliases"] == ["RAG"] and e["n_papers"] == 3


def test_ambiguous_acronym_is_not_merged():
    abstracts = {1: "Fast Search Engine (FSE) is used.", 2: "We evaluate Fine Sample Estimation (FSE) here."}
    rows = [(1, [ent("FSE")], []), (2, [ent("Fast Search Engine")], [])]
    assert len(resolve_entities(rows, abstracts).entities) == 2


def test_role_priority_and_type_vote():
    rows = [(1, [ent("X1", "Method", "compared"), ent("X1", "Method", "proposed")], []),
            (2, [ent("X1", "Tool")], []), (3, [ent("X1", "Method")], [])]
    result = resolve_entities(rows, {})
    assert {(m["paper_id"], m["role"]) for m in result.mentions if m["key"] == "x1"} == {
        (1, "proposed"), (2, "used"), (3, "used")}
    assert result.entities[0]["type"] == "Method"


def test_relations_are_mapped_aggregated_and_filtered():
    abstracts = {1: "Retrieval-Augmented Generation (RAG) helps."}
    rows = [
        (1, [ent("RAG"), ent("BM25", role="compared")], [rel("RAG", "OUTPERFORMS", "BM25")]),
        (2, [ent("Retrieval-Augmented Generation"), ent("bm25", role="compared")],
         [rel("Retrieval-Augmented Generation", "OUTPERFORMS", "bm25"),
          rel("RAG", "BASED_ON", "Retrieval-Augmented Generation"),   # self loop after merge
          rel("RAG", "USED_FOR", "Unknown")]),                         # unknown endpoint
    ]
    result = resolve_entities(rows, abstracts)
    assert len(result.relations) == 1
    r = result.relations[0]
    assert (r["source"], r["relation"], r["target"], r["paper_ids"]) == (
        "retrievalaugmentedgeneration", "OUTPERFORMS", "bm25", [1, 2])
    assert result.stats["entities_after_merge"] == 2


def test_parenthesis_in_names_is_removed_and_merged():
    abstracts = {1: "We study Large Language Models (LLMs) and Chain-of-Thought (CoT) prompting."}
    rows = [(1, [ent("large language models (LLMs", "Dataset"), ent("Chain-of-Thought (CoT)")], []),
            (2, [ent("Large Language Models"), ent("CoT")], []),
            (3, [ent("LLMs")], [])]
    result = resolve_entities(rows, abstracts)
    by_name = {e["name"]: e for e in result.entities}
    assert set(by_name) == {"large language models", "Chain-of-Thought"}
    llm = next(e for e in result.entities if "language" in e["name"].lower())
    assert llm["n_papers"] == 3 and llm["type"] == "Method"
    assert next(e for e in result.entities if e["name"] == "Chain-of-Thought")["n_papers"] == 2