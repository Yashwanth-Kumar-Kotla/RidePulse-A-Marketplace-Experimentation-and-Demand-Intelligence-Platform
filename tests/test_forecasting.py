import pandas as pd

from ridepulse.forecasting.backtest import make_folds, wape
from ridepulse.forecasting.baseline import add_seasonal_naive


def make_panel(month: str, n_days: int, zone: int = 1) -> pd.DataFrame:
    hours = pd.date_range(f"{month}-01", periods=n_days * 24, freq="h")
    return pd.DataFrame(
        {
            "pu_location_id": zone,
            "pickup_hour": hours,
            "month": pd.Timestamp(f"{month}-01"),
            "trip_count": range(len(hours)),
        }
    )


def test_seasonal_naive_lag_is_168_hours():
    panel = make_panel("2024-01", n_days=10)
    result = add_seasonal_naive(panel)
    row = result[result["pickup_hour"] == pd.Timestamp("2024-01-08 00:00:00")].iloc[0]
    expected = result[result["pickup_hour"] == pd.Timestamp("2024-01-01 00:00:00")].iloc[0]["trip_count"]
    assert row["pred_seasonal_naive"] == expected


def test_seasonal_naive_does_not_leak_across_month_gap():
    jan = make_panel("2024-01", n_days=31)
    jun = make_panel("2024-06", n_days=30)
    combined = pd.concat([jan, jun], ignore_index=True)
    result = add_seasonal_naive(combined)
    first_jun_row = result[result["month"] == pd.Timestamp("2024-06-01")].sort_values("pickup_hour").iloc[0]
    assert pd.isna(first_jun_row["pred_seasonal_naive"])


def test_wape_matches_hand_computed_value():
    actual = pd.Series([10.0, 20.0, 0.0])
    pred = pd.Series([8.0, 25.0, 1.0])
    # |10-8| + |20-25| + |0-1| = 8; sum(actual) = 30
    assert wape(actual, pred) == 8.0 / 30.0


def test_make_folds_gives_four_per_month():
    panel = pd.concat([make_panel("2024-01", n_days=31), make_panel("2024-06", n_days=30)], ignore_index=True)
    folds = make_folds(panel)
    assert len(folds) == 8  # 4 folds x 2 months
    jan_folds = [f for f in folds if f[1] == pd.Timestamp("2024-01-01")]
    assert len(jan_folds) == 4
