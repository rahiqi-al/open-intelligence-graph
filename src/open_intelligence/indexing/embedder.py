"""BGE embeddings. They run in Python (CPU or GPU), not in Docker."""
from functools import lru_cache

from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def _model(name: str, max_seq_length: int) -> SentenceTransformer:
    model = SentenceTransformer(name)
    model.max_seq_length = max_seq_length
    return model


def dimension(cfg: dict) -> int:
    return _model(cfg["model"], cfg["max_seq_length"]).get_sentence_embedding_dimension()


def passage_text(title: str, section: str, text: str) -> str:
    """What we embed: the paper title and the section give each chunk its context."""
    return f"{title}\n{section}\n{text}"


def embed_passages(texts: list[str], cfg: dict) -> list[list[float]]:
    model = _model(cfg["model"], cfg["max_seq_length"])
    vectors = model.encode(
        texts, batch_size=cfg["batch_size"], normalize_embeddings=True, show_progress_bar=False
    )
    return vectors.tolist()


def embed_query(text: str, cfg: dict) -> list[float]:
    """BGE needs an instruction in front of search queries (not in front of passages)."""
    model = _model(cfg["model"], cfg["max_seq_length"])
    return model.encode(cfg["query_prefix"] + text, normalize_embeddings=True).tolist()