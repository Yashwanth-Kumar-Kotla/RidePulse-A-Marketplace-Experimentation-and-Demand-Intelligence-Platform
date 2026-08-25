"""Seasonal-naive baseline: predict trips(zone, hour) = trips(zone, hour - 7 days).

Mandatory baseline per PRD Section 7.3 -- every other model must beat this or
the result is reported honestly, not hidden.
"""

from __future__ import annotations

import pandas as pd

LAG_HOURS = 24 * 7  # one week, in hours


def add_seasonal_naive(panel: pd.DataFrame) -> pd.DataFrame:
    """Adds a `pred_seasonal_naive` column. NaN wherever fewer than 7 days of
    same-month history exist yet (the first 7 days of each pilot month).

    Shifts by row position within each (zone, month) group, not by matching
    timestamps -- safe here because load_dense_zone_hour_panel already
    guarantees one row per hour with no gaps within a month, and grouping by
    month prevents the shift from reaching across the gap between pilot
    months (Jan rows and Jun rows are never adjacent within a group).
    """
    panel = panel.sort_values(["pu_location_id", "month", "pickup_hour"]).copy()
    panel["pred_seasonal_naive"] = panel.groupby(["pu_location_id", "month"])["trip_count"].shift(LAG_HOURS)
    return panel
