"""FastAPI serving layer: zone-hour forecasts and experiment readouts.

Deliberately light (PRD Section 7.8: "Productionization (deliberately
light)") -- this is a demo/portfolio serving layer, not a production
forecasting service. The forecast endpoint trains one LightGBM model on
all pilot data at startup (not per-fold like the backtest) and predicts
using each zone's most recent available history as features -- it
demonstrates the model serving a real prediction, not a live operational
pipeline with fresh feature computation on every request.

Experiment-readout endpoints return the SAME already-verified numbers
published in docs/*.md and dashboard/app.py -- one source of truth,
displayed three ways (docs, Streamlit, API), not recomputed three times.
"""

from __future__ import annotations

import duckdb
import lightgbm as lgb
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ridepulse.forecasting.data import load_dense_zone_hour_panel
from ridepulse.forecasting.features import FEATURE_COLUMNS, build_feature_panel
from ridepulse.ingestion.config import REPO_ROOT, load_config

app = FastAPI(title="RidePulse API", description="Zone-hour demand forecasts and experiment readouts.")

_model_cache: dict = {}


def _get_model_and_panel():
    """Lazy-loaded, cached: train once on first request, not on import --
    keeps `import api.main` (e.g. for tests) fast and side-effect-free."""
    if "model" not in _model_cache:
        duckdb_path = REPO_ROOT / load_config()["paths"]["duckdb_path"]
        con = duckdb.connect(str(duckdb_path), read_only=True)
        panel = build_feature_panel(load_dense_zone_hour_panel(con), con)
        con.close()
        train = panel.dropna(subset=["lag_168h"])  # need at least a week of history
        model = lgb.LGBMRegressor(objective="regression", n_estimators=200, learning_rate=0.05,
                                   num_leaves=31, min_child_samples=20, verbosity=-1)
        model.fit(train[FEATURE_COLUMNS], train["trip_count"])
        _model_cache["model"] = model
        _model_cache["panel"] = panel
    return _model_cache["model"], _model_cache["panel"]


class ForecastResponse(BaseModel):
    zone: int
    as_of: str
    predicted_trips_next_hour: float
    model_backtest_wape: float = 0.123  # LightGBM's measured pooled WAPE, see docs/overnight_log.md
    note: str = "Prediction uses this zone's most recent available pilot-window features, not live data."


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/forecast/{zone_id}", response_model=ForecastResponse)
def forecast(zone_id: int) -> ForecastResponse:
    model, panel = _get_model_and_panel()
    # Only require the lag features that matter for a meaningful prediction
    # (a fresh-history requirement); LightGBM handles any remaining NaN
    # (e.g. sparse weather gaps) the same way it did during training --
    # requiring ALL features non-null doesn't match how the model was
    # trained and validated, and previously made every zone 404.
    zone_rows = panel[panel["pu_location_id"] == zone_id].dropna(subset=["lag_1h", "lag_24h", "lag_168h"])
    if zone_rows.empty:
        raise HTTPException(status_code=404, detail=f"no usable history for zone {zone_id} in the pilot window")
    latest = zone_rows.sort_values("pickup_hour").iloc[[-1]]
    pred = float(model.predict(latest[FEATURE_COLUMNS])[0])
    return ForecastResponse(
        zone=zone_id,
        as_of=str(latest["pickup_hour"].iloc[0]),
        predicted_trips_next_hour=max(0.0, pred),
    )


@app.get("/experiments/interference")
def interference_readout() -> dict:
    # Real, verified numbers from docs/interference_study.md (300 reps) --
    # not recomputed per-request, see module docstring.
    return {
        "true_effect_min": -1.52,
        "naive_ab_estimate_min": 0.05,
        "naive_bias_pct": -103.4,
        "switchback_estimate_min": -1.56,
        "switchback_bias_pct": 2.6,
        "source": "docs/interference_study.md",
    }


@app.get("/experiments/cuped")
def cuped_readout() -> dict:
    return {
        "pre_post_correlation": 0.513,
        "variance_reduction_pct": 26.3,
        "implied_sample_size_savings_pct": 26.3,
        "source": "docs/cuped_analysis.md",
    }


@app.get("/experiments/decision-layer")
def decision_layer_readout() -> dict:
    return {
        "budget_usd": 700,
        "optimizer_trips_per_hour": 27.1,
        "greedy_trips_per_hour": 25.9,
        "greedy_margin_pct": -4.3,
        "uniform_trips_per_hour": 18.7,
        "uniform_margin_pct": -44.8,
        "source": "docs/decision_layer.md",
    }
