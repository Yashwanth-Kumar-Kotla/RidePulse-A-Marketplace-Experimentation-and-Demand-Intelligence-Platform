"""Build the dense zone-hour demand panel used for forecasting.

Forecasting target: total trips per (zone, hour), summed across platform
(Uber + Lyft) -- a rider/driver-facing demand forecast doesn't care which
app the trip came through, and splitting by platform would roughly halve an
already-thin pilot-window sample per cell.

The panel must be DENSE (a row for every zone x hour, including zero-trip
cells) rather than sparse (only rows that had >=1 trip): mart_zone_hour_demand
is built via GROUP BY on stg_trips, so a zone-hour with zero trips simply has
no row. Checked directly: only ~93.7% of the theoretical (zone x hour x
platform) cells in the January pilot month have a row -- the missing ~6.3%
are real zero-demand cells (mostly outer zones overnight), not a data gap.
Treating "no row" as "no data" instead of "zero trips" would silently bias
every downstream forecast upward.

The three pilot months (Jan/Jun/Sep 2024, configs/data.yaml pilot_months) are
NOT contiguous -- there's a multi-week gap between them. Any time-based lag
(e.g. "same hour last week") must never be computed across that gap, so the
panel is built and lagged per-month, never as one 3-month-long series.
"""

from __future__ import annotations

import duckdb
import pandas as pd

from ridepulse.ingestion.config import REPO_ROOT, load_config


def load_dense_zone_hour_panel(con: duckdb.DuckDBPyConnection | None = None) -> pd.DataFrame:
    """Returns columns: pu_location_id, pickup_hour, month, trip_count (dense, 0-filled)."""
    close_when_done = con is None
    if con is None:
        duckdb_path = REPO_ROOT / load_config()["paths"]["duckdb_path"]
        con = duckdb.connect(str(duckdb_path), read_only=True)

    panel = con.execute(
        """
        WITH zone_hour_totals AS (
            SELECT pu_location_id, pickup_hour, sum(trip_count) AS trip_count
            FROM mart_zone_hour_demand
            GROUP BY 1, 2
        ),
        month_bounds AS (
            SELECT
                date_trunc('month', pickup_hour) AS month,
                min(pickup_hour) AS start_hr,
                max(pickup_hour) AS end_hr
            FROM zone_hour_totals
            GROUP BY 1
        ),
        hours AS (
            SELECT month, unnest(generate_series(start_hr, end_hr, INTERVAL 1 HOUR)) AS pickup_hour
            FROM month_bounds
        ),
        zones AS (SELECT DISTINCT pu_location_id FROM zone_hour_totals)
        SELECT z.pu_location_id, h.pickup_hour, h.month, coalesce(t.trip_count, 0) AS trip_count
        FROM hours h
        CROSS JOIN zones z
        LEFT JOIN zone_hour_totals t
            ON t.pu_location_id = z.pu_location_id AND t.pickup_hour = h.pickup_hour
        ORDER BY z.pu_location_id, h.pickup_hour
        """
    ).fetchdf()

    if close_when_done:
        con.close()
    return panel
