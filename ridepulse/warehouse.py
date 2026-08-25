"""Build the DuckDB warehouse by running sql/01_staging -> 02_marts -> 03_metrics in order.

Usage: uv run python -m ridepulse.warehouse
"""

from __future__ import annotations

import logging
import os

import duckdb

from ridepulse.ingestion.config import REPO_ROOT, load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

SQL_LAYERS = ["01_staging", "02_marts", "03_metrics"]


def build(duckdb_path: str | None = None) -> None:
    duckdb_path = duckdb_path or load_config()["paths"]["duckdb_path"]
    # The SQL files use paths like 'data/raw/tlc/*.parquet' relative to the
    # repo root, so run from there regardless of the caller's cwd.
    os.chdir(REPO_ROOT)
    con = duckdb.connect(duckdb_path)
    # 16GB machine: cap DuckDB well below total RAM and force disk spilling
    # for anything that doesn't fit, rather than letting it OOM the process.
    con.execute("SET memory_limit = '8GB'")
    con.execute("SET temp_directory = 'data/duckdb_tmp'")

    for layer in SQL_LAYERS:
        layer_dir = REPO_ROOT / "sql" / layer
        for sql_file in sorted(layer_dir.glob("*.sql")):
            logger.info("running %s/%s", layer, sql_file.name)
            con.execute(sql_file.read_text())

    tables = con.execute("SHOW ALL TABLES").fetchdf()
    logger.info("warehouse built: %d relations\n%s", len(tables), tables[["name"]])
    con.close()


if __name__ == "__main__":
    build()
