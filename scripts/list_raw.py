import os
from collections import defaultdict

from open_intelligence.database import minio_store

client = minio_store.get_client()
bucket = os.getenv("MINIO_BUCKET_RAW", "raw-json")

parts = defaultdict(lambda: [0, 0])  # partition -> [files, bytes]
for obj in client.list_objects(bucket, recursive=True):
    partition = "/".join(obj.object_name.split("/")[:4])  # source/query/window/ingest_date
    parts[partition][0] += 1
    parts[partition][1] += obj.size

for partition, (files, size) in sorted(parts.items()):
    print(f"{partition:70} {files:3} files {size / 1e6:6.1f} MB")
print("total:", sum(f for f, _ in parts.values()), "files,",
      round(sum(s for _, s in parts.values()) / 1e6, 1), "MB")