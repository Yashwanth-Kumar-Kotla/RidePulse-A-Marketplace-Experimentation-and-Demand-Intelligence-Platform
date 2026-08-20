"""Ingestion CLI. Usage:

    uv run python -m ridepulse.ingestion.cli pull --pilot
    uv run python -m ridepulse.ingestion.cli pull --full
    uv run python -m ridepulse.ingestion.cli validate --pilot
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict

from ridepulse.ingestion import noaa, tlc, zones
from ridepulse.ingestion.config import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def months_for(scope: str) -> list[str]:
    cfg = load_config()["tlc"]
    return cfg["pilot_months"] if scope == "pilot" else cfg["full_months"]


def cmd_pull(args: argparse.Namespace) -> None:
    scope = "pilot" if args.pilot else "full"
    months = months_for(scope)
    logger.info("pulling %d months (%s): %s", len(months), scope, months)

    for month in months:
        tlc.download_month(month, force=args.force)

    start, end = f"{months[0]}-01", f"{sorted(months)[-1]}-28"
    noaa.download_weather(start, end, force=args.force)
    zones.download_zone_lookup(force=args.force)
    logger.info("pull complete")


def cmd_validate(args: argparse.Namespace) -> None:
    scope = "pilot" if args.pilot else "full"
    months = months_for(scope)
    all_ok = True
    results = []
    for month in months:
        path = tlc.raw_path(month)
        if not path.exists():
            logger.error("month %s not downloaded yet -- run `pull` first", month)
            all_ok = False
            continue
        result = tlc.validate_file(path, month)
        results.append(asdict(result))
        status = "OK" if result.ok else "FAILED"
        logger.info(
            "%s: %s -- rows=%d schema_ok=%s null_violations=%s ts_violations=%d dup_rows=%d",
            month,
            status,
            result.row_count,
            result.schema_ok,
            result.null_violations,
            result.timestamp_order_violations,
            result.duplicate_rows,
        )
        all_ok = all_ok and result.ok

    print(json.dumps(results, indent=2, default=str))
    if not all_ok:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="RidePulse ingestion CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, fn in [("pull", cmd_pull), ("validate", cmd_validate)]:
        p = sub.add_parser(name)
        scope = p.add_mutually_exclusive_group(required=True)
        scope.add_argument("--pilot", action="store_true", help="use configs/data.yaml pilot_months")
        scope.add_argument("--full", action="store_true", help="use configs/data.yaml full_months")
        if name == "pull":
            p.add_argument("--force", action="store_true", help="re-download even if file exists")
        p.set_defaults(func=fn)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
