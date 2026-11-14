from open_intelligence.documents.chunker import chunk_abstract, chunk_pages, make_chunk_id
from open_intelligence.documents.section_detector import heading_title, split_sections


def sentence(i: int) -> str:
    return f"Sentence number {i} explains how the retrieval model works in practice."


def body(n_sentences: int, start: int = 0) -> str:
    return " ".join(sentence(i) for i in range(start, start + n_sentences))


def test_heading_detection():
    assert heading_title("Abstract") == "Abstract"
    assert heading_title("1 Introduction") == "Introduction"
    assert heading_title("2.1 Experimental Setup") == "Experimental Setup"
    assert heading_title("I. RELATED WORK") == "Related Work"
    assert heading_title("Appendix A: Extra results") == "Appendix A: Extra results"
    assert heading_title("3 Llama 2 13B") is None  # table row
    assert heading_title("We train the model for 3 epochs on the data.") is None
    assert heading_title("Table 1: Results on the benchmark.") is None


def test_sections_and_number_on_separate_line():
    pages = [
        "My Paper\nAuthor One\nAbstract\nWe study things.\n1 Introduction\nText of intro.",
        "2\nArchitecture\nText of architecture.\n3 Conclusion\nDone.",
    ]
    sections = split_sections(pages)
    assert [s.title for s in sections] == [
        "Front matter", "Abstract", "Introduction", "Architecture", "Conclusion"]
    assert sections[3].lines[0][0] == 2  # page number is kept


def test_no_headings_is_full_text():
    sections = split_sections([body(5)])
    assert [s.title for s in sections] == ["Full text"]


def test_chunks_size_pages_and_overlap():
    pages = ["1 Introduction\n" + body(40), body(40, 40), body(40, 80)]
    cfg = {"chunk_tokens": 140, "overlap_tokens": 28, "tokens_per_word": 1.4}  # 100 words, 20 overlap
    chunks = chunk_pages(7, pages, "internal", cfg)
    assert len(chunks) > 3
    assert all(c.n_words <= 100 for c in chunks)
    assert all(c.section == "Introduction" and c.access_level == "internal" for c in chunks)
    assert chunks[0].page_start == 1 and chunks[-1].page_end == 3
    assert [c.index for c in chunks] == list(range(len(chunks)))
    # overlap: the start of a chunk repeats the end of the previous one
    assert " ".join(chunks[1].text.split()[:5]) in chunks[0].text


def test_chunks_end_at_sentence_end():
    pages = ["1 Introduction\n" + body(60)]
    chunks = chunk_pages(1, pages, cfg={"chunk_tokens": 140, "overlap_tokens": 14, "tokens_per_word": 1.4})
    assert all(c.text.endswith(".") for c in chunks[:-1])


def test_deterministic_ids_and_skips():
    pages = ["1 Introduction\n" + body(10) + "\nAcknowledgments\n" + body(10) + "\n2 Method\n12 34 56 78 " * 20]
    a = chunk_pages(5, pages)
    b = chunk_pages(5, pages)
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]
    assert a[0].chunk_id == make_chunk_id(5, 0)
    assert all(c.section != "Acknowledgments" for c in a)  # skipped section
    assert all(c.section != "Method" for c in a)           # numbers only (table) is dropped


def test_abstract_fallback():
    assert chunk_abstract(1, "too short") == []
    chunks = chunk_abstract(1, body(5), "public")
    assert len(chunks) == 1 and chunks[0].section == "Abstract" and chunks[0].page_start is None


def test_ambiguous_words_need_a_number():
    assert heading_title("model") is None
    assert heading_title("Model") is None
    assert heading_title("Results") is None
    assert heading_title("3 Model") == "Model"
    assert heading_title("4 Results") == "Results"
    assert heading_title("Related Work") == "Related Work"


def test_caption_after_page_number_is_not_a_heading():
    pages = ["Abstract\nSome abstract text here.\n6\nTable 3: Comparison of Chat models. Mistral 7B –\nrow text"]
    titles = [s.title for s in split_sections(pages)]
    assert not any(t.startswith("Table") for t in titles)


def test_front_matter_dropped_only_when_abstract_exists():
    with_abstract = ["Paper Title\n" + body(8) + "\nAbstract\n" + body(8)]
    assert all(c.section != "Front matter" for c in chunk_pages(1, with_abstract))
    without_abstract = [body(8) + "\n1 Introduction\n" + body(8)]
    assert any(c.section == "Front matter" for c in chunk_pages(1, without_abstract))