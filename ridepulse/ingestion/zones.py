"""Download the TLC taxi zone lookup table (zone ID -> borough/zone name)."""

from __future__ import annotations

import logging
from pathlib import Path

import requests

from ridepulse.ingestion.config import REPO_ROOT, load_config

logger = logging.getLogger(__name__)


def raw_path() -> Path:
    cfg = load_config()["paths"]
    raw_dir = REPO_ROOT / cfg["raw_dir"] / "zones"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir / "taxi_zone_lookup.csv"


def download_zone_lookup(force: bool = False) -> Path:
    dest = raw_path()
    if dest.exists() and not force:
        logger.info("zone lookup already downloaded, skipping")
        return dest

    url = load_config()["taxi_zones"]["lookup_csv_url"]
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    logger.info("downloaded zone lookup -> %s", dest)
    return dest
