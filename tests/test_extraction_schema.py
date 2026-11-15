from open_intelligence.extraction.schema import clean_extraction

TEXT = ("Title: Mistral 7B\nAbstract: We introduce Mistral 7B, which outperforms Llama 2 13B using "
        "grouped-query attention and sliding window attention. RL agents are not covered. It was said to be fast.")


def ent(name, type_="Method", role="used"):
    return {"name": name, "type": type_, "role": role}


def rel(s, r, t):
    return {"source": s, "relation": r, "target": t}


def test_keeps_grounded_drops_invented_and_generic():
    raw = {"entities": [ent("Mistral 7B", role="proposed"), ent("GPT-5"), ent("model"), ent("Llama 2 13B", role="compared")],
           "relations": []}
    names = [e["name"] for e in clean_extraction(raw, TEXT)["entities"]]
    assert names == ["Mistral 7B", "Llama 2 13B"]


def test_dedupes_spelling_variants():
    raw = {"entities": [ent("grouped-query attention"), ent("Grouped Query Attention"), ent("grouped query attention.")],
           "relations": []}
    assert len(clean_extraction(raw, TEXT)["entities"]) == 1


def test_short_acronyms_need_the_exact_word():
    raw = {"entities": [ent("RL"), ent("AI"), ent("ai")], "relations": []}
    assert [e["name"] for e in clean_extraction(raw, TEXT)["entities"]] == ["RL"]  # "AI" is inside "said"


def test_invalid_type_or_role_dropped():
    raw = {"entities": [ent("Mistral 7B", type_="Person"), ent("Llama 2 13B", role="boss")], "relations": []}
    assert clean_extraction(raw, TEXT)["entities"] == []


def test_relations_only_between_kept_entities():
    raw = {"entities": [ent("Mistral 7B", role="proposed"), ent("Llama 2 13B", role="compared"), ent("GPT-5")],
           "relations": [rel("Mistral 7B", "OUTPERFORMS", "Llama 2 13B"),
                         rel("Mistral 7B", "OUTPERFORMS", "GPT-5"),          # GPT-5 was dropped
                         rel("Mistral 7B", "OUTPERFORMS", "Llama 2 13B"),    # duplicate
                         rel("Mistral 7B", "LOVES", "Llama 2 13B"),          # unknown relation
                         rel("Mistral 7B", "BASED_ON", "Mistral 7B")]}       # self loop
    result = clean_extraction(raw, TEXT)
    assert result["relations"] == [rel("Mistral 7B", "OUTPERFORMS", "Llama 2 13B")]


def test_caps_and_bad_input():
    many = {"entities": [ent(f"Method{i}") for i in range(30)], "relations": []}
    text = " ".join(f"Method{i}" for i in range(30))
    assert len(clean_extraction(many, text)["entities"]) == 12
    assert clean_extraction({}, TEXT) == {"entities": [], "relations": []}
    assert clean_extraction({"entities": None, "relations": None}, TEXT)["entities"] == []




LLAMA = ("Title: LLaMA: Open and Efficient Foundation Language Models\nAbstract: We introduce LLaMA, a collection of "
         "foundation language models. We show that it is possible to train state-of-the-art models using publicly "
         "available datasets exclusively, without resorting to proprietary and inaccessible datasets. In particular, "
         "LLaMA-13B outperforms GPT-3 (175B) on most benchmarks, and LLaMA-65B is competitive with the best models, "
         "Chinchilla-70B and PaLM-540B.")


def test_llama_case_junk_dropped_and_relation_kept():
    raw = {"entities": [ent("LLaMA", role="proposed"), ent("GPT-3", role="compared"),
                        ent("Chinchilla-70B", role="compared"), ent("PaLM-540B", role="compared"),
                        ent("proprietary and inaccessible datasets", "Dataset"),
                        ent("publicly available datasets", "Dataset"),
                        ent("state-of-the-art models", "Task")],
           "relations": [rel("LLaMA-13B", "OUTPERFORMS", "GPT-3"),          # LLaMA-13B -> LLaMA
                         rel("LLaMA-65B", "OUTPERFORMS", "Unknown Thing")]}  # target unknown: dropped
    result = clean_extraction(raw, LLAMA)
    assert [e["name"] for e in result["entities"]] == ["LLaMA", "GPT-3", "Chinchilla-70B", "PaLM-540B"]
    assert result["relations"] == [rel("LLaMA", "OUTPERFORMS", "GPT-3")]


def test_resolve_needs_a_single_match():
    raw = {"entities": [ent("Mistral 7B", role="proposed"), ent("Llama 2 13B", role="compared")],
           "relations": [rel("Mistral", "OUTPERFORMS", "Llama 2")]}
    assert clean_extraction(raw, TEXT)["relations"] == [rel("Mistral 7B", "OUTPERFORMS", "Llama 2 13B")]


def test_lowercase_dataset_or_tool_is_dropped():
    raw = {"entities": [ent("grouped-query attention", "Dataset"), ent("Mistral 7B", "Dataset")], "relations": []}
    assert [e["name"] for e in clean_extraction(raw, TEXT)["entities"]] == ["Mistral 7B"]