# RidePulse — Marketplace Experimentation & Demand Intelligence Platform

**Status: early build, in progress.** This README will be reordered to lead
with results once there are real charts to show (see `PRD.md` Section 15 for
the target structure: Problem → Why → Architecture → Data audit → Metrics →
Forecasting → Simulator calibration → Experiments → Optimization →
Limitations → Future work). Until then, it tracks what's actually built and
verified, with no placeholder numbers.

Full requirements and rationale: see [`PRD.md`](PRD.md).

## What this is

An end-to-end analytics build on real NYC TLC High Volume For-Hire Vehicle
(Uber + Lyft) trip records: a DuckDB warehouse with layered SQL, zone-hour
demand forecasting with rolling-origin backtests, a calibrated marketplace
simulator used to stress-test A/B testing methods under interference, and a
budget-constrained incentive optimizer.

## Data window (read this before trusting any number in this repo)

The PRD's target window is 2023-2025 (~150-250M rows/year). This build
currently runs on a **pilot window of 3 months from 2024** (January, June,
September — chosen to span low/medium/high season, and to fall entirely in
the pre-congestion-pricing period for a later diff-in-diff check), configured
in [`configs/data.yaml`](configs/data.yaml). ~59M trip rows currently
ingested. The full window is a config change away
(`full_months` in the same file) — widen it once the pipeline is proven end
to end. Every reported number in this repo should be read against whatever
window backed it at the time; this section will be updated when that
changes.

## Built so far

- **Ingestion** (`ridepulse/ingestion/`): downloads TLC HVFHS monthly
  parquet, NOAA daily weather (NYC Central Park station), and the TLC zone
  lookup table. Validates schema, required-field nulls, timestamp ordering,
  and duplicates on every file before it's trusted downstream — see
  [`docs/data_quality_notes.md`](docs/data_quality_notes.md) for what that
  validation actually found in the real data (a ~0.95% request-timestamp
  quirk, traced to its likely cause, not just flagged and ignored).
- **Warehouse** (`ridepulse/warehouse.py`, `sql/`): layered SQL —
  `01_staging` (typed trips/zones/weather), `02_marts`
  (`mart_zone_hour_demand`, the primary forecasting-target and KPI-source
  table), `03_metrics` (KPI views). Run via `make warehouse`.
- **Metrics**: 5 of 12 PRD KPIs have working SQL views; the rest are
  explicitly scoped (not silently dropped) in
  [`docs/metrics_definitions.md`](docs/metrics_definitions.md), which also
  documents *why* two of them (fulfillment proxy, imbalance index) don't yet
  have a definition — the HVFHS data has no request-level denominator, and
  picking a proxy without saying so plainly would violate this project's own
  anti-fabrication rule (PRD Section 4).

## Not yet built

Forecasting models/backtest harness, simulator, experimentation engine
(CUPED/mSPRT/switchback), incentive optimizer, FastAPI/Streamlit/Tableau
surfaces. See `PRD.md` Section 12 for the intended sequencing.

## Quickstart

```bash
make setup           # uv sync
make pull-pilot       # download the 3-month pilot window (~1.5GB)
make validate-pilot   # schema/null/timestamp/duplicate checks
make warehouse        # build the DuckDB warehouse (staging -> marts -> metrics)
```

Requires ~8GB free RAM for the warehouse build step on the current data
window; DuckDB is configured to cap itself at 8GB and spill to
`data/duckdb_tmp/` rather than exhausting system memory outright, but a
machine already under heavy memory pressure from other processes can still
starve it. If `make warehouse` gets killed (exit 137), check what else is
running before assuming the query itself is the problem.

## Limitations (living list, expand as they're found)

- **Fulfillment is unmeasurable, not just imperfectly measured.** HVFHS
  trip files contain only completed, matched trips. There is no
  public request-level record of cancellations. Any "demand" or
  "fulfillment" claim in this repo is built on a stated proxy, never a
  direct measurement — see `docs/metrics_definitions.md`.
- **Pilot data window.** Numbers here reflect 3 months of 2024, not the full
  2023-2025 range the PRD targets. Widen before treating any result as final.
