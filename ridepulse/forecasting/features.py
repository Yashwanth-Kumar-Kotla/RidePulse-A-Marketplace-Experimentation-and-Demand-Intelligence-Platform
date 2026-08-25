"""Feature engineering for the LightGBM demand model.

Lag features (t-1h, t-24h, t-168h) are computed within (zone, month) groups,
same reasoning as the seasonal-naive baseline in baseline.py: the pilot
months are non-contiguous, so a lag must never reach across the gap between
them. NaN near the start of each month (not enough history yet) is left as
NaN rather than filled -- LightGBM splits on missingness natively, so this
doesn't need imputation, and filling it with e.g. 0 would misrepresent
"unknown" as "no demand."
"""

from __future__ import annotations

import duckdb
import pandas as pd

LAG_HOURS = [1, 24, 24 * 7]


def add_lag_features(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.sort_values(["pu_location_id", "month", "pickup_hour"]).copy()
    grouped = panel.groupby(["pu_location_id", "month"])["trip_count"]
    for lag in LAG_HOURS:
        panel[f"lag_{lag}h"] = grouped.shift(lag)
    return panel


def add_calendar_features(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.copy()
    panel["hour_of_day"] = panel["pickup_hour"].dt.hour
    panel["day_of_week"] = panel["pickup_hour"].dt.dayofweek
    panel["is_weekend"] = panel["day_of_week"].isin([5, 6]).astype(int)
    return panel


def add_weather_features(panel: pd.DataFrame, con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    weather = con.execute(
        "SELECT weather_date, precip_mm, temp_avg_c, temp_max_c, temp_min_c, wind_avg_ms FROM stg_weather"
    ).fetchdf()
    panel = panel.copy()
    panel["weather_date"] = panel["pickup_hour"].dt.normalize()
    weather["weather_date"] = pd.to_datetime(weather["weather_date"])
    return panel.merge(weather, on="weather_date", how="left").drop(columns=["weather_date"])


FEATURE_COLUMNS = [
    "lag_1h",
    "lag_24h",
    "lag_168h",
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "precip_mm",
    "temp_max_c",
    "temp_min_c",
    "wind_avg_ms",
    # temp_avg_c deliberately excluded: confirmed 0/272 rows populated in the
    # raw NOAA feed for this station (this GHCN station reports TMAX/TMIN but
    # not TAVG directly, a common pattern -- not a join bug). Found via the
    # API's forecast endpoint failing for every zone with an all-NaN feature
    # after a stricter dropna(); LightGBM's training path had silently
    # tolerated it (100% missing carries zero information gain, so it never
    # affected any split) -- see docs/data_quality_notes.md.
]


def build_feature_panel(panel: pd.DataFrame, con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    panel = add_lag_features(panel)
    panel = add_calendar_features(panel)
    panel = add_weather_features(panel, con)
    return panel
