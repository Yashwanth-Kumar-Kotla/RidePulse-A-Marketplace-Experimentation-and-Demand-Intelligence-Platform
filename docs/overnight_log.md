# Overnight Build Log

Running log of the self-paced overnight build session. Newest entries on top.
See PRD.md for full spec, README.md for current status summary.

---

## 2026-08-24 (session start)

Starting point: ingestion layer done, SQL staging/marts/metrics files written
but never successfully executed (warehouse build was OOM-killed earlier by a
competing background process). Verified before starting: `caffeinate -s` is
running (pid 2620, confirmed via `pmset -g assertions`), no competing
processes, memory is clear.

Plan for tonight, in priority order: finish warehouse build -> forecasting
baseline + backtest -> calibrated simulator -> experimentation engine
(interference/switchback first, it's the flagship result) -> CUPED -> decision
layer if time allows -> Streamlit readout. Full scope and explicit
out-of-scope items in the /loop prompt that kicked this off.

### Milestone: warehouse build fixed and verified (23:50)

The mart build (`sql/02_marts/mart_zone_hour_demand.sql`) was getting
OOM-killed (exit 137) even with DuckDB's memory_limit capped at 6-8GB and
temp_directory spilling enabled, and even with the machine otherwise idle.
Debugged by isolating the cause rather than blindly retrying:
- Cheap aggregates alone (count/sum/avg) over the same ~1.1M (zone, hour,
  platform) groups: 1.3s, no issue.
- `approx_quantile(...) FILTER (...)` over the same groups: still OOM/multi-minute
  even at 6GB, even with plain WHERE instead of FILTER.
- Same `approx_quantile` at ~262 groups (zone only, no hour/platform): 0.7s.
- Conclusion: the cost is the per-group t-digest sketch DuckDB allocates for
  `approx_quantile`, multiplied across ~1.1M groups -- not the 59M-row scan.

Fix: replaced the inline `approx_quantile` calls with a manual bucketed
histogram (15-second buckets, cheap COUNT aggregates) + a window-function
cumulative distribution to read off p50/p90 -- see
`sql/02_marts/mart_wait_time_percentiles.sql` for the full explanation and
`mart_zone_hour_demand.sql` for how it's joined in.

**Verified after the fix:**
- Full warehouse build (staging -> marts -> metrics, 9 relations) runs in
  ~19s clean, no OOM.
- Row-count integrity: `sum(trip_count)` in `mart_zone_hour_demand` ==
  `count(*)` in `stg_trips` == 58,996,944 -- the join lost/duplicated nothing.
- Sanity check: NYC HVFHS trips on 2024-01-01 summed across boroughs =
  638,384 (Staten Island 8,319 / Brooklyn 187,089 / Manhattan 220,688 /
  Bronx 81,748 / Queens 140,540) -- consistent with publicly reported
  citywide HVFHS daily volume.
- Sanity check: median zone-hour wait time p50 = 225s (Uber) / 255s (Lyft),
  p90 = 405s (Uber) / 450s (Lyft) -- 3.75-4.25 min / 6.75-7.5 min, a
  realistic range for rideshare wait times.

Committed as "Fix wait-time percentile OOM with a bucketed histogram
approach" once pushed.

### Milestone: seasonal-naive forecasting baseline + backtest harness (23:57)

Built `ridepulse/forecasting/`: `data.py` (dense zone-hour demand panel,
platform-summed, zero-filled -- checked directly that only ~93.7% of
theoretical zone-hour-platform cells have a row in the mart, so the missing
~6.3% are real zero-demand cells that must be filled, not left as gaps),
`baseline.py` (seasonal-naive: predict = same hour 7 days prior), and
`backtest.py` (12-fold rolling-origin: 4 folds/month x 3 pilot months, since
the months are non-contiguous and can't form one continuous rolling window --
documented in the module docstring).

**Result (real, measured, not fabricated): pooled WAPE = 15.2% across all 12
folds** (per-fold range 11.7%-19.7%; September is the worst month, June
second-worst -- plausibly more schedule variability in summer than the
seasonal-naive model's fixed 7-day-lag assumption captures, not yet
investigated further). This is the number to beat with a real model next.

Verified: 4 unit tests covering the correctness-critical logic (the 7-day
lag doesn't leak across the Jan/Jun gap -- this was the one genuine
correctness risk in this design, tested directly; WAPE formula matches a
hand-computed example; fold counts are right). All 11 repo tests + ruff
pass. Committed as "Add seasonal-naive forecasting baseline and 12-fold
backtest harness" once pushed.

Next: one real model (LightGBM) against this same harness, honestly
reported whether it beats 15.2% WAPE or not.
