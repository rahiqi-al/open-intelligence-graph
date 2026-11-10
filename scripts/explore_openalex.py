"""Day 2: fetch 100 random AI works from OpenAlex and save the raw JSON."""
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

URL = "https://api.openalex.org/works"
OUT = Path("data/raw/openalex_sample.json")

params = {
    "filter": ",".join(
        [
            "primary_topic.subfield.id:1702",  # Artificial Intelligence
            "has_abstract:true",
            "from_publication_date:2018-01-01",
        ]
    ),
    "sample": 100,  # random sample, so we see real-world messy data
    "seed": 42,  # same seed = same sample every run
    "per-page": 100,
}
if os.getenv("OPENALEX_EMAIL"):
    params["mailto"] = os.getenv("OPENALEX_EMAIL")
if os.getenv("OPENALEX_API_KEY"):  # optional: only if the API asks for a key
    params["api_key"] = os.getenv("OPENALEX_API_KEY")

resp = httpx.get(URL, params=params, timeout=60)
resp.raise_for_status()
data = resp.json()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(data["results"], indent=2))

print("status:", resp.status_code)
print("works saved:", len(data["results"]))
print("total matching in OpenAlex:", data["meta"]["count"])
print("saved to:", OUT)