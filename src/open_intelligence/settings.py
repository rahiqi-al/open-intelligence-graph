"""Loads .env and config/settings.yaml."""
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]  # repo root
load_dotenv(ROOT / ".env")


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config" / "settings.yaml").read_text())