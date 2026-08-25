"""LightGBM demand model, backtested on the exact same 12-fold harness as the
seasonal-naive baseline (ridepulse/forecasting/backtest.py) so the WAPE
numbers are directly comparable.

Per-fold training data = every panel row strictly before that fold's test
day, across ALL pilot months that came chronologically first -- not just the
current month. E.g. a September fold trains on the full January + June data
plus September up to the test day. This falls out naturally from filtering
on `pickup_hour < day_start` (timestamps compare correctly across months),
no month-by-month special-casing needed. One real consequence, disclosed
here rather than hidden: the January folds have far less training data
(<=27 days) than the September folds (Jan + Jun + up to 26 days of Sep),
since January is the first pilot month.
"""

from __future__ import annotations

import duckdb
import lightgbm as lgb
import mlflow
import pandas as pd

from ridepulse.forecasting.backtest import FoldResult, make_folds, wape
from ridepulse.forecasting.data import load_dense_zone_hour_panel
from ridepulse.forecasting.features import FEATURE_COLUMNS, build_feature_panel
from ridepulse.ingestion.config import REPO_ROOT, load_config

LGBM_PARAMS = {
    "objective": "regression",
    "n_estimators": 200,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 20,
    "verbosity": -1,
}


def backtest_lightgbm(
    panel: pd.DataFrame | None = None, con: duckdb.DuckDBPyConnection | None = None
) -> tuple[list[FoldResult], float]:
    close_when_done = con is None
    if con is None:
        duckdb_path = REPO_ROOT / load_config()["paths"]["duckdb_path"]
        con = duckdb.connect(str(duckdb_path), read_only=True)
    if panel is None:
        panel = load_dense_zone_hour_panel(con)
    panel = build_feature_panel(panel, con)
    if close_when_done:
        con.close()

    folds = make_folds(panel)
    results = []
    all_actual, all_pred = [], []

    # MLflow's filesystem store ('./mlruns') is in maintenance mode as of
    # mlflow 3.x and refuses to run; sqlite is the currently recommended
    # lightweight local backend.
    mlflow.set_tracking_uri(f"sqlite:///{REPO_ROOT / 'data' / 'mlflow.db'}")
    mlflow.set_experiment("ridepulse-forecasting")

    for fold_id, month, day_start, day_end in folds:
        train = panel[panel["pickup_hour"] < day_start]
        test = panel[(panel["pickup_hour"] >= day_start) & (panel["pickup_hour"] < day_end)]

        model = lgb.LGBMRegressor(**LGBM_PARAMS)
        model.fit(train[FEATURE_COLUMNS], train["trip_count"])
        pred = pd.Series(model.predict(test[FEATURE_COLUMNS]), index=test.index).clip(lower=0)
        fold_wape = wape(test["trip_count"], pred)

        with mlflow.start_run(run_name=f"lgbm_{fold_id}"):
            mlflow.log_param("fold_id", fold_id)
            mlflow.log_param("train_rows", len(train))
            mlflow.log_params(LGBM_PARAMS)
            mlflow.log_metric("wape", fold_wape)

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
        all_pred.append(pred)

    pooled_wape = wape(pd.concat(all_actual), pd.concat(all_pred))
    return results, pooled_wape


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger(__name__)

    fold_results, pooled = backtest_lightgbm()
    log.info("%-12s %-10s %8s %10s", "fold", "test_date", "n_rows", "wape")
    for r in fold_results:
        log.info("%-12s %-10s %8d %9.1f%%", r.fold_id, r.test_date.date(), r.n_rows, r.wape * 100)
    log.info("-" * 45)
    log.info("pooled LightGBM WAPE across all %d folds: %.1f%%", len(fold_results), pooled * 100)
