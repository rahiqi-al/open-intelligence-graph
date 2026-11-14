"""Qdrant collection for the paper chunks."""
import os

from qdrant_client import QdrantClient, models


def get_client() -> QdrantClient:
    return QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"), check_compatibility=False)


def ensure_collection(client: QdrantClient, name: str, dim: int) -> None:
    if client.collection_exists(name):
        size = client.get_collection(name).config.params.vectors.size
        if size != dim:
            raise RuntimeError(
                f"collection '{name}' has vector size {size} but the model gives {dim}. "
                "Run scripts/reset_index.py after changing the embedding model."
            )
        return
    client.create_collection(
        collection_name=name,
        vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
    )
    # indexes on the fields we filter by (security filter on access_level, paper, year, section)
    for field, schema in [
        ("paper_id", models.PayloadSchemaType.INTEGER),
        ("access_level", models.PayloadSchemaType.KEYWORD),
        ("year", models.PayloadSchemaType.INTEGER),
        ("section", models.PayloadSchemaType.KEYWORD),
    ]:
        client.create_payload_index(name, field_name=field, field_schema=schema)


def delete_paper(client: QdrantClient, name: str, paper_id: int) -> None:
    client.delete(
        collection_name=name,
        points_selector=models.FilterSelector(filter=models.Filter(must=[
            models.FieldCondition(key="paper_id", match=models.MatchValue(value=paper_id))
        ])),
    )


def upsert_points(client: QdrantClient, name: str, ids: list, vectors: list, payloads: list) -> None:
    client.upsert(
        collection_name=name,
        points=models.Batch(ids=ids, vectors=vectors, payloads=payloads),
    )


def search(client: QdrantClient, name: str, vector: list, k: int = 5, access_levels: list | None = None):
    query_filter = None
    if access_levels:
        query_filter = models.Filter(must=[
            models.FieldCondition(key="access_level", match=models.MatchAny(any=access_levels))
        ])
    return client.query_points(
        collection_name=name, query=vector, limit=k, query_filter=query_filter, with_payload=True
    ).points