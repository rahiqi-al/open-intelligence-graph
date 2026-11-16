FROM apache/airflow:2.9.3-python3.11

# model cache for sentence-transformers (volume hf_cache is mounted here)
RUN mkdir -p /opt/airflow/hf_cache

# CPU-only torch first, otherwise sentence-transformers pulls the huge CUDA build
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir \
    -c https://raw.githubusercontent.com/apache/airflow/constraints-2.9.3/constraints-3.11.txt \
    "psycopg[binary]" httpx minio pymupdf qdrant-client neo4j pyyaml python-dotenv tenacity sentence-transformers