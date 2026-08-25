# Data Quality Notes

Findings from ingestion validation (`ridepulse/ingestion/tlc.py::validate_file`,
run via `uv run python -m ridepulse.ingestion.cli validate --pilot` /
`--full`). Original findings below were from the 3-month pilot window
(2024-01, 2024-06, 2024-09, ~59.0M rows); **re-verified against the full
2023-2025 window (30 months, 592,955,659 rows)** once it was built --
noted inline where the full-window numbers refine or confirm the original.

## `request_datetime` occasionally lands after `pickup_datetime` (~0.95%-1.0% of rows)

**Finding:** `request_datetime > pickup_datetime` for ~184-188K rows/month out
of ~19-20M (0.94-0.96%) in the original pilot-window check.
**Re-verified across the full 30-month window: 0.995% of all 592.96M rows**
(range 0.82%-1.20% across individual months) -- consistent with the pilot
finding, not a pilot-specific artifact. `pickup_datetime > dropoff_datetime`
never occurs -- the anomaly is isolated to the request leg.

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

## Duplicate rows: negligible (<0.001%)

38-44 exact-duplicate rows per month (same license/base/pickup/dropoff/zone
tuple) out of ~19-20M in the pilot-window check. **Re-verified across the
full window: 0.0009% of all 592.96M rows** -- still negligible, still
~100x below the 0.1% warn threshold. Filtered via `SELECT DISTINCT` at the
staging layer.

## Also found while widening to the full window: `PULocationID`/`DOLocationID` type drift (2023-01 only)

**Finding:** every month's `PULocationID`/`DOLocationID` columns are
`INTEGER` except 2023-01, which is `BIGINT`. Caught by the same schema
check that validates every other month, not assumed away.

**Verified harmless before relaxing the check:** confirmed directly that
DuckDB's `read_parquet()` auto-promotes to `BIGINT` across a glob spanning
both schemas without data loss -- a TLC-side type annotation change, not a
real incompatibility. Handled with a narrow, documented compatible-type
allowance (`INTEGER` -> `BIGINT` only) in
`ridepulse/ingestion/tlc.py::COMPATIBLE_TYPE_WIDENINGS`, not a blanket
loosening of schema validation -- an unrelated wrong type still fails (see
`tests/test_tlc_validation.py`).

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
