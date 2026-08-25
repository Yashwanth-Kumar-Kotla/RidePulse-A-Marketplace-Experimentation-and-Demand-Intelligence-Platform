import pandas as pd

from ridepulse.forecasting.features import add_calendar_features, add_lag_features


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


def test_lag_1h_and_24h_match_hand_computed_values():
    panel = make_panel("2024-01", n_days=10)
    result = add_lag_features(panel)
    row = result[result["pickup_hour"] == pd.Timestamp("2024-01-03 05:00:00")].iloc[0]
    assert row["lag_1h"] == result[result["pickup_hour"] == pd.Timestamp("2024-01-03 04:00:00")].iloc[0]["trip_count"]
    assert row["lag_24h"] == result[result["pickup_hour"] == pd.Timestamp("2024-01-02 05:00:00")].iloc[0]["trip_count"]


def test_lags_do_not_leak_across_month_gap():
    jan = make_panel("2024-01", n_days=31)
    jun = make_panel("2024-06", n_days=30)
    combined = pd.concat([jan, jun], ignore_index=True)
    result = add_lag_features(combined)
    first_jun_row = result[result["month"] == pd.Timestamp("2024-06-01")].sort_values("pickup_hour").iloc[0]
    assert pd.isna(first_jun_row["lag_1h"])
    assert pd.isna(first_jun_row["lag_168h"])


def test_calendar_features_are_correct_for_a_known_date():
    panel = make_panel("2024-01", n_days=8)  # 2024-01-01 is a Monday
    result = add_calendar_features(panel)
    monday = result[result["pickup_hour"] == pd.Timestamp("2024-01-01 09:00:00")].iloc[0]
    assert monday["hour_of_day"] == 9
    assert monday["day_of_week"] == 0  # Monday
    assert monday["is_weekend"] == 0

    saturday = result[result["pickup_hour"] == pd.Timestamp("2024-01-06 09:00:00")].iloc[0]
    assert saturday["is_weekend"] == 1
