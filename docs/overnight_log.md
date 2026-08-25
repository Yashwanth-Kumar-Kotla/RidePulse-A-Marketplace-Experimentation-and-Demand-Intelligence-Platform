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

### Milestone: LightGBM demand model, backtested on the same harness (00:01)

Built `ridepulse/forecasting/features.py` (lag features at t-1h/t-24h/t-168h,
computed within (zone, month) groups so they can't leak across the
non-contiguous pilot-month gap -- same reasoning as the seasonal-naive
baseline, tested the same way; calendar features; weather joined from
`stg_weather`) and `ridepulse/forecasting/lgbm_model.py`, which reuses
`make_folds`/`wape` from `backtest.py` directly rather than reimplementing
the fold logic, so the WAPE numbers are apples-to-apples comparable.

Per-fold training uses every row strictly before that fold's test day,
across ALL earlier pilot months (falls out naturally from filtering on
`pickup_hour < day_start`, since month timestamps compare correctly) --
disclosed consequence: January folds train on much less data (<=27 days)
than September folds (Jan + Jun + up to 26 days of Sep), since January is
the first pilot month.

**Result (real, measured): pooled WAPE = 12.3%**, vs. the seasonal-naive
baseline's 15.2% -- a ~19% relative improvement. Being precise rather than
overselling this: LightGBM beats naive on 10 of 12 folds, ties on 1
(2024-01-30, both 12.6%), and is narrowly WORSE on 1 (2024-01-29: LightGBM
13.9% vs. naive 12.9%) -- plausibly the fold with the least training history
(only 28 days available). Full per-fold numbers in git history / rerun
`uv run python -m ridepulse.forecasting.lgbm_model`.

Hit one real snag along the way: MLflow 3.x's filesystem tracking store
(`./mlruns`) is now in "maintenance mode" and refuses to initialize --
switched to the sqlite backend it recommends (`sqlite:///data/mlflow.db`,
gitignored). Runs are logged (fold_id, train_rows, hyperparams, wape) under
experiment "ridepulse-forecasting".

Verified: 3 new unit tests (lag values match hand-computed shifts, lags
don't leak across the month gap, calendar features correct for a known
Monday/Saturday). All 14 repo tests + ruff pass, no warnings. Committed as
"Add LightGBM demand model, beats seasonal-naive 12.3% vs 15.2% WAPE" once
pushed.

Next: marketplace simulator (the foundation for the flagship interference
study) -- this is the biggest, riskiest piece left. Calibration is
non-negotiable per PRD Section 13.

### Milestone: simulator core engine, verified on toy scenarios (00:07)

Built `ridepulse/simulation/engine.py`: a hand-rolled heapq event loop
(3 event types: arrival, patience expiry, trip complete), not a DES
framework (simpy etc.) -- with only 3 event types, a framework would add a
coroutine control-flow paradigm to learn without saving meaningful code.
One zone = one queueing system (n drivers, Poisson arrivals, FIFO matching,
patience-based cancellation, exponential trip durations).

Two modeling simplifications made explicitly, documented in the module
docstring rather than silently assumed: (1) no cross-zone driver
repositioning -- a driver stays in-zone after a trip instead of following
the real drop-off zone; that needs an origin-destination flow matrix per
zone-hour, which is a real feature for later, not a one-liner; (2) matching
is "any idle driver in zone," not geospatial "nearest," since there's no
sub-zone position at this grain.

**This unit deliberately does NOT calibrate against real data yet** (that's
the next unit, non-negotiable per PRD Section 13 before any experiment
result gets reported) -- it only proves the engine itself behaves correctly.
Verified with two toy scenarios plus 6 pytest tests:
- Oversubscribed (30 riders/hr, 5 drivers, 15-min mean trips): 61%
  fulfillment, 92% utilization, 1.7min mean wait -- correctly shows real
  strain.
- Undersubscribed (10 riders/hr, 20 drivers): 100% fulfillment, 12%
  utilization, 0min mean wait -- correctly shows slack capacity.
- Tests cover: zero drivers -> 100% cancellation; heavy oversupply -> zero
  cancellation and zero wait; scarce vs. plentiful drivers -> fulfillment
  and utilization move in the correct direction; no negative wait times;
  same seed is fully reproducible; completed+cancelled accounts for every
  single arrival (no silent drops in the event loop).

Also noted directly in the `utilization` property: it isn't strictly
bounded at 1.0 -- a trip matched near the end of the simulation window
still runs its full duration past the window edge, a real boundary effect
in any windowed measurement, not a bug. Left visible rather than clamped.

All 20 repo tests + ruff pass. Committed as "Add discrete-event simulator
core engine, verified on toy scenarios" once pushed.

Next: calibrate against real held-out data (arrival rate from actual
zone-hour demand, driver count / trip duration / patience tuned so
simulated wait-time and utilization distributions match real ones) --
required before any experiment can use this simulator.

### Milestone: simulator calibration -- honest partial match, real bug found and fixed (00:24)

Full methodology and result in `docs/simulator_calibration.md` (new) and
`docs/simulator_calibration_overlay.png` (new) -- summary here.

Calibrated `n_drivers` / `mean_patience_minutes` against real pooled
wait-time p50/p90 for two zones (79 = Manhattan high-volume, 106 =
Brooklyn/Gowanus medium-volume) at a real recurring rush-hour slice
(Wednesday 18:00), fit on 3 weeks of January, validated out-of-sample on a
4th held-out week. Utilization is NOT independently validated (no ground
truth exists in HVFHS data -- same reason KPI #4 in metrics_definitions.md
is marked "Planned"), reported as simulator output only, per PRD Section
7.4's explicit allowance to "calibrate on some quantities, hold out
others, and say which."

**Found and fixed a real modeling bug along the way**, not just tuned
parameters: the first version simulated many continuous hours at a
constant rate, which models an unstable queue that builds up without bound
whenever demand is even slightly above capacity -- verified directly
(simulated utilization pinned at ~1.0, wait inflated far above real at
every driver count tried). A real rush hour resets daily; it isn't a
continuous overload. Fixed with standard DES practice: 1-hour warm-up,
then measure only matches in the following hour -- required adding
`match_times_min` to `SimResult` (engine.py) so wait times could be
filtered to the measurement window.

**Result (real, measured, reported honestly -- this is a partial match,
not a clean one):**

| Zone | Real p50 (holdout) | Sim p50 | Real p90 (holdout) | Sim p90 |
|---|---|---|---|---|
| 79 | 2.85 min | 4.94 min (+73%) | 4.90 min | 6.82 min (+39%) |
| 106 | 3.28 min | 3.23 min (-1.5%) | 5.33 min | 7.02 min (+32%) |

Zone 106's p50 is a near-exact match. Everything else is systematically
*overestimated* by 32-73%. Right order of magnitude and right direction
(busier zone -> more wait), wrong precision. Most likely cause, and it's a
limitation already disclosed in engine.py's docstring BEFORE calibration
started: no cross-zone driver repositioning -- the simulator can't draw on
drivers flowing in from neighboring zones during a surge, so it predicts
more strain than the real (more elastic) system shows. This is a
hypothesis consistent with the error's direction, not independently
confirmed.

**What this does and doesn't license**: usable for relative,
within-simulator comparisons (e.g. the interference study -- naive A/B vs.
switchback, both measured against the same simulator's own ground truth)
since that doesn't depend on matching reality's absolute wait level. NOT
validated well enough to claim "real riders wait N minutes" -- stated
explicitly rather than overselling a 30-70%-off number as calibrated truth.

Verified: 2 new calibration tests (pooling across replications behaves
sanely; grid_search's argmin is verified correct by independently
re-simulating every grid cell and confirming none beats the returned
error) + 1 new engine test (match_times_min aligns with wait_times_min).
All 23 repo tests + ruff pass. Committed as "Calibrate simulator against
real data -- partial match, systematic wait overestimation" once pushed.

Next: experimentation engine, starting with power/MDE and fixed-horizon
A/B, building toward the interference/switchback flagship result.

### Milestone: power/MDE calculator + fixed-horizon A/B with SRM check (00:31)

Built `ridepulse/experiments/power.py` (standard textbook sample-size
formulas for proportions and means, cited not reinvented) and
`ab_test.py` (Welch's t-test -- unequal-variance default, doesn't assume
control/treatment have the same spread -- plus a Welch-Satterthwaite 95%
CI, and a chi-square sample-ratio-mismatch check at a strict p<0.001
threshold, standard practice since SRM tests have enough power to flag
tiny benign imbalances at large N).

**The one that actually matters most here (PRD Section 7.5 point 6):**
verified the A/B pipeline's false-positive rate under a null simulation
(no true effect, 2000 reps, alpha=0.05) lands inside a 99.9% binomial CI
around 0.05 -- i.e. the test is correctly calibrated, not silently
miscalibrated in a way that would invalidate every experiment result built
on top of it later tonight. Used a CI rather than a tight hardcoded bound
specifically so the test doesn't flake on normal sampling variance.

6 new tests total (power monotonicity in both directions, AB test recovers
a known synthetic effect, SRM correctly flags a broken allocation and
correctly clears a balanced one, plus the null false-positive-rate check).
All 29 repo tests + ruff pass. Committed as "Add power/MDE calculator and
fixed-horizon A/B test with SRM check" once pushed.

Next: the interference study -- naive rider-randomized A/B vs. switchback
on the same simulated driver-incentive intervention, bias measured against
known simulator ground truth. The single most important deliverable in
the project (PRD Section 11 #1).

### Milestone: THE INTERFERENCE STUDY -- flagship result done (00:44)

Full methodology and result in `docs/interference_study.md` (new) and
`docs/interference_bias.png` (new) -- summary here. This was the single
most important deliverable in the whole project (PRD Section 11 #1) and
the result came out clean and striking, not forced.

Extended `ridepulse/simulation/engine.py` with a small, real interference
mechanism: a treatment-tagged rider's matched trip runs faster
(`treatment_speedup < 1`, modeling an incentivized driver hustling), which
returns that driver to the SHARED pool sooner -- benefiting whichever
rider is matched next regardless of their own tag. Built
`ridepulse/experiments/interference.py` with three estimators: true effect
(clean all-treatment vs. all-control worlds, unbiased by construction),
naive rider-randomized A/B (one shared, contaminated pool), switchback
(independent all-or-nothing blocks). Reused the zone 106 calibration
params (`n_drivers=12`, `patience=5min`, real `arrival_rate=89.7/hr`,
`avg_trip=16.55min`) so this is grounded, not arbitrary.

**Result (300 reps, real, measured):**

| Estimator | Effect | Bias |
|---|---|---|
| True effect | -1.52 min | -- |
| Naive A/B | +0.05 min | **-103%** |
| Switchback | -1.56 min | **+3%** |

The naive design doesn't just understate the effect, it misses it almost
entirely (and gets the sign wrong in this run). Switchback recovers it to
within 3%. Sanity-checked before trusting this: (1) true effect is
non-zero and in the expected direction by construction, verified directly;
(2) result holds at 100 and 300 reps and against zone 79's params too, not
a one-off; (3) the null case (`treatment_speedup=1.0`, no real effect) --
all three estimators correctly land near zero, confirming switchback isn't
just "always guessing big."

Also fixed a real plotting bug along the way (not a data problem): initial
bar-chart annotation offsets were fixed constants that didn't scale to
this data's range (one bar ~0.05, others ~-1.5), pushing text completely
outside the visible axes. Fixed by scaling label offsets to the actual
data range instead of a hardcoded number -- verified by rendering and
looking at the actual image before calling it done, not just checking the
script ran without error.

5 new tests (true effect direction/magnitude, naive biased toward zero,
switchback closer than naive, null case near-zero for all three,
determinism). All 34 repo tests + ruff pass. Committed as "Add the
interference study -- naive A/B misses a real effect almost entirely,
switchback recovers it" once pushed.

Next: CUPED (pre-period covariates, measured variance reduction).

### Milestone: CUPED -- 26.3% variance reduction, real covariate found after a real dead end (00:56)

Full methodology in `docs/cuped_analysis.md` (new) -- summary here.

**First covariate hypothesis failed, kept in the writeup rather than
silently swapped out**: same-run warm-up-vs-measurement wait time as pre/
post, hypothesizing queue-state carryover. Measured correlation: 0.027,
indistinguishable from zero -- makes sense in hindsight (Poisson arrivals
have independent increments across disjoint windows; zone 106's calibrated
n_drivers=12 has enough slack that the queue clears within an hour; i.i.d.
replications have no persistent trait to exploit, which is also *why*
CUPED normally works in real systems -- persistent day/user heterogeneity).

**Working covariate, grounded in real data, not assumed**: queried the
warehouse for zone 106's real Wednesday-18:00 trip count across all 13
Wednesdays in the pilot window -- CV=20.2% (mean 84.9, std 17.1). Used that
measured 20.2% as a day-level demand multiplier affecting both periods of
a simulated day (a faithful real-world mechanism: weather/events cause
real day-to-day demand swings).

**Result (400 reps): correlation 0.513, variance reduction 26.3% (measured
and theoretical agree almost exactly, as they should for an exact OLS
identity), implied sample-size savings 26.3%** (same number by direct
derivation from power.py's n~sigma^2/mde^2, not a separate measurement).

**Caught a real bug via the theoretical/measured mismatch, not by luck**:
first version of the theoretical formula was `(1-r^2)*100` -- backwards.
`1-r^2` is the REMAINING variance fraction, the reduction is `r^2`. The
first run showed theoretical=73.7% vs measured=26.3%, and since these two
numbers are supposed to match by an exact algebraic identity (not
approximately, exactly), that gap meant a bug, not noise -- verified the
measured side by hand before concluding the theoretical formula was wrong,
fixed it, and added a synthetic test with a hand-computable known
reduction (Y=0.8X+noise, r=0.8, expected reduction=64%) specifically so
this sign error can't silently reappear.

4 new tests (hand-computed synthetic reduction, never-increases-variance,
near-zero-correlation-gives-near-zero-reduction, sample-size-savings
equals variance-reduction by construction). All 38 repo tests + ruff pass.
Committed as "Add CUPED analysis -- 26.3% variance reduction, real
covariate found after a documented dead end" once pushed.

Honest framing kept in the doc: 26.3% is a real, useful number, not the
90%+ sometimes seen in production systems with rich user-level history --
this simulator has no persistent user identities for a richer covariate.

Next: mSPRT + peeking study if time remains (simplify freely, it's the
PRD's own first-thing-to-cut), then decision layer, then Streamlit.
