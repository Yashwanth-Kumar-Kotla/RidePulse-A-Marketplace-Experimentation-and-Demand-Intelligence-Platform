"""Download NOAA GHCN daily weather for the NYC Central Park station.

Uses NCEI's public Access Data Service (no API token required), verified
live on 2026-08-20.
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests

from ridepulse.ingestion.config import REPO_ROOT, load_config

logger = logging.getLogger(__name__)

NCEI_URL = "https://www.ncei.noaa.gov/access/services/data/v1"

# Subset of GHCN daily-summary fields relevant to demand modeling.
FIELDS = ["PRCP", "SNOW", "SNWD", "TMAX", "TMIN", "TAVG", "AWND"]


def raw_path() -> Path:
    cfg = load_config()["paths"]
    raw_dir = REPO_ROOT / cfg["raw_dir"] / "noaa"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir / "nyc_weather_daily.csv"


def download_weather(start_date: str, end_date: str, force: bool = False) -> Path:
    """start_date/end_date as 'YYYY-MM-DD'."""
    dest = raw_path()
    if dest.exists() and not force:
        logger.info("noaa weather already downloaded, skipping")
        return dest

    cfg = load_config()["noaa"]
    params = {
        "dataset": "daily-summaries",
        "stations": cfg["station_id"].removeprefix("GHCND:"),
        "startDate": start_date,
        "endDate": end_date,
        "format": "csv",
        "units": "metric",
        "dataTypes": ",".join(FIELDS),
    }
    resp = requests.get(NCEI_URL, params=params, timeout=60)
    resp.raise_for_status()
    dest.write_text(resp.text)
    logger.info("downloaded noaa weather -> %s (%d bytes)", dest, len(resp.text))
    return dest
