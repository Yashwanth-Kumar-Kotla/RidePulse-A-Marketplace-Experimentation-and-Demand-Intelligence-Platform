# Data Quality Notes

Findings from ingestion validation (`ridepulse/ingestion/tlc.py::validate_file`,
run via `uv run python -m ridepulse.ingestion.cli validate --pilot`) against
the pilot window (2024-01, 2024-06, 2024-09, ~59.0M rows combined).

## `request_datetime` occasionally lands after `pickup_datetime` (~0.95% of rows)

**Finding:** `request_datetime > pickup_datetime` for ~184-188K rows/month out
of ~19-20M (0.94-0.96%). `pickup_datetime > dropoff_datetime` never occurs (0
rows in every pilot month) -- the anomaly is isolated to the request leg.

**Root cause (inferred, not officially confirmed by TLC docs):** among the
violating rows, 51% have `request_datetime` falling exactly on a 15-minute
mark (:00/:15/:30/:45), versus a 7.3% base rate for on-quarter-hour timestamps
across all rows. That's a ~7x over-representation, consistent with TLC
applying coarser temporal bucketing to `request_datetime` for a subset of
trips -- plausibly a privacy measure on lower-volume dispatching bases where
finer timestamps could aid re-identification. This is an inference from the
data's own fingerprint, not a claim sourced from TLC's data dictionary.

**Handling:** these rows are excluded from `request_datetime`-based wait-time
calculations (KPI #2, `p50/p90 request-to-pickup wait time`) at the marts
layer via `WHERE request_datetime <= pickup_datetime`, rather than dropped
from the dataset entirely -- `pickup_datetime` and `dropoff_datetime` remain
reliable for every other metric on these rows. Ingestion validation treats
this as a WARN (rate reported, logged) below a 2% threshold, not a hard FAIL,
since it's a bounded, understood, and filterable quirk rather than corruption.

## Duplicate rows: negligible (<0.0003%)

38-44 exact-duplicate rows per month (same license/base/pickup/dropoff/zone
tuple) out of ~19-20M. Filtered via `SELECT DISTINCT` at the staging layer.
Warn threshold: 0.1% of rows; actual rate is ~50x below that.

## No violations found

- Schema: exact match to the 24-column schema verified live against
  `fhvhv_tripdata_2024-01.parquet` on 2026-08-20 (see `tlc.py::EXPECTED_SCHEMA`).
- Required-field nulls (`hvfhs_license_num`, `pickup_datetime`,
  `dropoff_datetime`, `PULocationID`, `DOLocationID`): zero, every pilot month.

## NOAA `TAVG` (average temperature) is 0% populated for this station/period

**Finding:** `TAVG` is empty in 0 of 272 rows of the raw NOAA daily-summary
CSV (`data/raw/noaa/nyc_weather_daily.csv`) -- not a handful of gaps, every
single row. `TMAX`, `TMIN`, `PRCP`, `SNOW`, `SNWD`, `AWND` are populated
normally (a handful of nulls, not systematic). This is a known pattern for
some GHCN stations: they report daily max/min temperature directly but
don't compute/report a daily average.

**How it was found:** not caught during ingestion validation (which checks
completeness of TLC trip fields, not NOAA weather fields) or during the
LightGBM backtest (`ridepulse/forecasting/lgbm_model.py`, 12.3% pooled
WAPE) -- LightGBM tolerates an all-missing feature natively (zero
information gain, so it's simply never split on), which silently masked
the gap for weeks of use. It surfaced when the FastAPI forecast endpoint
(`api/main.py`) used a stricter `dropna(subset=FEATURE_COLUMNS)` for
inference-time row selection, which made every single zone return 404.

**Fix:** removed `temp_avg_c` from `FEATURE_COLUMNS`
(`ridepulse/forecasting/features.py`) rather than working around it at the
serving layer -- it never carried any information for the model to use.
Verified directly, not assumed: re-ran the LightGBM backtest after removing
it, pooled WAPE unchanged at 12.3%, exactly as expected for a feature that
was 100% missing the whole time.

## Fulfillment proxy: an open limitation, not yet resolved

TLC HVFHS trip files contain only *completed, matched* trips -- there is no
public request-level record of cancellations or unmatched requests. This
means KPI #3 (`fulfillment proxy rate`) and KPI #10 (`supply-demand imbalance
index`) cannot be computed as `completed / requested`, because the
denominator doesn't exist in this data. Candidate proxies to evaluate at the
metrics layer (Section 7.2): (a) wait-time inflation/dispersion by zone-hour
as an indirect undersupply signal, (b) `on_scene_datetime` gaps as a driver
availability proxy. Whichever is chosen, the README and metrics-definitions
doc must state plainly that it is a proxy for fulfillment, not a measurement
of it -- there is no ground truth for demand that went unfulfilled in this
dataset.
