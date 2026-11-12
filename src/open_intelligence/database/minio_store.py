import io
import json
import os

from minio import Minio

from open_intelligence import settings  # noqa: F401  (loads .env)


def get_client() -> Minio:
    return Minio(
        os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.getenv("MINIO_ROOT_USER"),
        secret_key=os.getenv("MINIO_ROOT_PASSWORD"),
        secure=False,
    )


def put_bytes(client: Minio, bucket: str, key: str, data: bytes, content_type: str) -> None:
    client.put_object(bucket, key, io.BytesIO(data), length=len(data), content_type=content_type)


def get_bytes(client: Minio, bucket: str, key: str) -> bytes:
    resp = client.get_object(bucket, key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def get_json(client: Minio, bucket: str, key: str):
    return json.loads(get_bytes(client, bucket, key))