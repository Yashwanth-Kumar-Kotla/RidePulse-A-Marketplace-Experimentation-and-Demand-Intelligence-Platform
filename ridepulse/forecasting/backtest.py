"""12-fold rolling-origin backtest harness (PRD Section 7.3).

The 3 pilot months are non-contiguous (see data.py), so "12 folds" can't mean
one continuous rolling window across Jan->Jun->Sep. Instead: 4 folds per
month x 3 months = 12 folds, each fold = one held-out day from that month's
last 4 days, walked forward day by day. Every test day has >=21 days of
same-month history before it, well past the 7-day seasonal-naive warmup.

WAPE, not MAPE: MAPE is undefined/explodes when true demand is near zero,
which is common at hourly zone grain (many outer-zone hours have 0-2 trips).
WAPE = sum(|error|) / sum(|actual|) aggregates numerator and denominator
separately across the whole fold before dividing, so it stays well-behaved
even when many individual zone-hours are near zero.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ridepulse.forecasting.baseline import add_seasonal_naive
from ridepulse.forecasting.data import load_dense_zone_hour_panel

FOLDS_PER_MONTH = 4


@dataclass
class FoldResult:
    fold_id: str
    month: pd.Timestamp
    test_date: pd.Timestamp
    n_rows: int
    wape: float
    actual_sum: float


def make_folds(panel: pd.DataFrame) -> list[tuple[str, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """Returns (fold_id, month, test_day_start, test_day_end_exclusive) tuples."""
    folds = []
    for month, month_df in panel.groupby("month"):
        last_days = sorted(month_df["pickup_hour"].dt.normalize().unique())[-FOLDS_PER_MONTH:]
        for day in last_days:
            fold_id = f"{pd.Timestamp(month).strftime('%Y-%m')}_{pd.Timestamp(day).strftime('%d')}"
            folds.append((fold_id, month, pd.Timestamp(day), pd.Timestamp(day) + pd.Timedelta(days=1)))
    return folds


def wape(actual: pd.Series, pred: pd.Series) -> float:
    return (actual - pred).abs().sum() / actual.abs().sum()


def backtest_seasonal_naive(panel: pd.DataFrame | None = None) -> tuple[list[FoldResult], float]:
    """Returns (per-fold results, pooled WAPE across all fold rows)."""
    if panel is None:
        panel = load_dense_zone_hour_panel()
    panel = add_seasonal_naive(panel)

    folds = make_folds(panel)
    results = []
    all_actual, all_pred = [], []

    for fold_id, month, day_start, day_end in folds:
        test = panel[(panel["pickup_hour"] >= day_start) & (panel["pickup_hour"] < day_end)]
        missing_pred = test["pred_seasonal_naive"].isna().sum()
        if missing_pred > 0:
            raise ValueError(
                f"fold {fold_id}: {missing_pred} rows have no seasonal-naive prediction -- "
                "test day is too close to the start of its month for the 7-day lag"
            )
        fold_wape = wape(test["trip_count"], test["pred_seasonal_naive"])
        results.append(
            FoldResult(
                fold_id=fold_id,
                month=month,
                test_date=day_start,
                n_rows=len(test),
                wape=fold_wape,
                actual_sum=test["trip_count"].sum(),
            )
        )
        all_actual.append(test["trip_count"])
        all_pred.append(test["pred_seasonal_naive"])

    pooled_wape = wape(pd.concat(all_actual), pd.concat(all_pred))
    return results, pooled_wape


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger(__name__)

    fold_results, pooled = backtest_seasonal_naive()
    log.info("%-12s %-10s %8s %10s", "fold", "test_date", "n_rows", "wape")
    for r in fold_results:
        log.info("%-12s %-10s %8d %9.1f%%", r.fold_id, r.test_date.date(), r.n_rows, r.wape * 100)
    log.info("-" * 45)
    log.info("pooled WAPE across all %d folds: %.1f%%", len(fold_results), pooled * 100)
