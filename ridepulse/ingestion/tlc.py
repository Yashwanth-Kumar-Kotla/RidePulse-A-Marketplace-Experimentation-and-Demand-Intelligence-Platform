"""Download and validate NYC TLC High Volume For-Hire Vehicle (HVFHS) monthly trip files.

Schema verified live against fhvhv_tripdata_2024-01.parquet on 2026-08-20
(24 columns, 19,663,930 rows). One combined file per month covers all
high-volume FHV bases (Uber=HV0003, Lyft=HV0005, Via=HV0004, Juno=HV0002),
distinguished by hvfhs_license_num -- there is no per-platform URL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb
import requests

from ridepulse.ingestion.config import REPO_ROOT, load_config

logger = logging.getLogger(__name__)

# column_name -> duckdb type, as observed on the live source. Ingestion fails
# loudly if a downloaded file's schema drifts from this rather than silently
# coercing, since a silent type change would corrupt every downstream layer.
EXPECTED_SCHEMA = {
    "hvfhs_license_num": "VARCHAR",
    "dispatching_base_num": "VARCHAR",
    "originating_base_num": "VARCHAR",
    "request_datetime": "TIMESTAMP",
    "on_scene_datetime": "TIMESTAMP",
    "pickup_datetime": "TIMESTAMP",
    "dropoff_datetime": "TIMESTAMP",
    "PULocationID": "INTEGER",
    "DOLocationID": "INTEGER",
    "trip_miles": "DOUBLE",
    "trip_time": "BIGINT",
    "base_passenger_fare": "DOUBLE",
    "tolls": "DOUBLE",
    "bcf": "DOUBLE",
    "sales_tax": "DOUBLE",
    "congestion_surcharge": "DOUBLE",
    "airport_fee": "DOUBLE",
    "tips": "DOUBLE",
    "driver_pay": "DOUBLE",
    "shared_request_flag": "VARCHAR",
    "shared_match_flag": "VARCHAR",
    "access_a_ride_flag": "VARCHAR",
    "wav_request_flag": "VARCHAR",
    "wav_match_flag": "VARCHAR",
}

# Columns that must never be null -- a request with no pickup location or no
# fare timestamp isn't a usable trip record.
NOT_NULL_COLUMNS = ["hvfhs_license_num", "pickup_datetime", "dropoff_datetime", "PULocationID", "DOLocationID"]


# request_datetime appears coarsened to the nearest 15 minutes for a subset
# of trips (~7% of all rows land exactly on a quarter-hour vs. an expected
# ~1/15, and that share jumps to ~51% among request>pickup violations) --
# most likely privacy-related timestamp bucketing on lower-volume dispatching
# bases. This produces request_datetime > pickup_datetime for ~1% of rows.
# It's a known, quantified TLC data quirk (see docs/data_quality_notes.md),
# not corruption, so it's a WARN below this rate, not a hard ingestion FAIL.
TIMESTAMP_VIOLATION_WARN_THRESHOLD = 0.02
DUPLICATE_WARN_THRESHOLD = 0.001


@dataclass
class ValidationResult:
    month: str
    row_count: int
    schema_ok: bool
    schema_diff: dict
    null_violations: dict
    timestamp_order_violations: int
    duplicate_rows: int

    @property
    def timestamp_violation_rate(self) -> float:
        return self.timestamp_order_violations / self.row_count if self.row_count else 0.0

    @property
    def duplicate_rate(self) -> float:
        return self.duplicate_rows / self.row_count if self.row_count else 0.0

    @property
    def ok(self) -> bool:
        """Hard-fail gate: schema drift or nulls in required columns block ingestion.

        Timestamp-order and duplicate issues below their warn thresholds are
        known, bounded data quirks -- flagged, filtered at the staging layer,
        but not a reason to block the whole pull.
        """
        return (
            self.schema_ok
            and self.row_count > 0
            and not self.null_violations
            and self.timestamp_violation_rate <= TIMESTAMP_VIOLATION_WARN_THRESHOLD
            and self.duplicate_rate <= DUPLICATE_WARN_THRESHOLD
        )


def month_url(month: str) -> str:
    cfg = load_config()["tlc"]
    return f"{cfg['base_url']}/{cfg['file_prefix']}_{month}.parquet"


def raw_path(month: str) -> Path:
    cfg = load_config()["paths"]
    raw_dir = REPO_ROOT / cfg["raw_dir"] / "tlc"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir / f"fhvhv_tripdata_{month}.parquet"


def download_month(month: str, force: bool = False) -> Path:
    """Stream one month's HVFHS parquet to data/raw/tlc/. Skips if already present."""
    dest = raw_path(month)
    if dest.exists() and not force:
        logger.info("tlc %s already downloaded (%s), skipping", month, dest)
        return dest

    url = month_url(month)
    logger.info("downloading tlc %s from %s", month, url)
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        tmp = dest.with_suffix(".parquet.part")
        with open(tmp, "wb") as f:
            f.writelines(resp.iter_content(chunk_size=1 << 20))
        tmp.rename(dest)
    logger.info("downloaded tlc %s -> %s (%.1f MB)", month, dest, dest.stat().st_size / 1e6)
    return dest


def validate_file(path: Path, month: str) -> ValidationResult:
    """Schema, null-threshold, timestamp-sanity, and duplicate checks per PRD 7.1."""
    con = duckdb.connect()
    actual = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchdf()
    actual_schema = dict(zip(actual["column_name"], actual["column_type"]))

    schema_diff = {}
    for col, expected_type in EXPECTED_SCHEMA.items():
        got = actual_schema.get(col)
        if got != expected_type:
            schema_diff[col] = {"expected": expected_type, "got": got}
    schema_ok = not schema_diff

    row_count = con.execute(f"SELECT count(*) FROM read_parquet('{path}')").fetchone()[0]

    null_violations = {}
    for col in NOT_NULL_COLUMNS:
        n_null = con.execute(
            f'SELECT count(*) FROM read_parquet(\'{path}\') WHERE "{col}" IS NULL'
        ).fetchone()[0]
        if n_null > 0:
            null_violations[col] = n_null

    # request <= pickup <= dropoff must hold whenever both sides are non-null.
    # on_scene_datetime is excluded: it is null for a meaningful share of
    # legitimate trips (e.g. some dispatch flows never log a scene arrival).
    ts_violations = con.execute(
        f"""
        SELECT count(*) FROM read_parquet('{path}')
        WHERE (request_datetime IS NOT NULL AND pickup_datetime IS NOT NULL
               AND request_datetime > pickup_datetime)
           OR (pickup_datetime IS NOT NULL AND dropoff_datetime IS NOT NULL
               AND pickup_datetime > dropoff_datetime)
        """
    ).fetchone()[0]

    dup_rows = con.execute(
        f"""
        SELECT count(*) - count(DISTINCT (hvfhs_license_num, dispatching_base_num,
               pickup_datetime, dropoff_datetime, "PULocationID", "DOLocationID"))
        FROM read_parquet('{path}')
        """
    ).fetchone()[0]

    return ValidationResult(
        month=month,
        row_count=row_count,
        schema_ok=schema_ok,
        schema_diff=schema_diff,
        null_violations=null_violations,
        timestamp_order_violations=ts_violations,
        duplicate_rows=dup_rows,
    )
