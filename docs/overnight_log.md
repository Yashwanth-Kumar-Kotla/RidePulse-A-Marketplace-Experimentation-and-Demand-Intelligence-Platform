# Overnight Build Log

Running log of the self-paced overnight build session. Newest entries on top.
See PRD.md for full spec, README.md for current status summary.

## Resume bullets (running draft, real numbers only, Google XYZ format)

1. Reduced demand-forecast error by 19% (WAPE 12.3% vs. 15.2% seasonal-naive
   baseline), as measured by a 12-fold rolling-origin backtest, by
   engineering a LightGBM pipeline with lag/calendar/weather features over
   59M real NYC rideshare trips.
2. Uncovered a -103% measurement bias in naive A/B testing under marketplace
   interference, as measured by comparing naive rider-randomized and
   switchback estimators against known simulator ground truth, by building
   a calibrated discrete-event marketplace simulator and an interference
   study from scratch.
3. Cut required experiment sample size by 26.3%, as measured by CUPED
   variance reduction using a real day-level demand covariate (20.2% CV),
   by implementing the CUPED estimator and rejecting an initial covariate
   that failed validation at near-zero correlation.
4. Improved incentive-budget efficiency by up to 8% over a greedy heuristic
   and 45% over uniform allocation, as measured by unfulfilled-demand
   reduction in a calibrated marketplace simulator, by building a PuLP
   budget allocator over simulation-measured uplift curves, verified
   against brute-force search.

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

### Milestone: decision layer -- third and final "wow" component done (01:15)

Full methodology in `docs/decision_layer.md` (new) and
`docs/decision_layer.png` (new) -- summary here. All 3 PRD Section 11
"wow" components are now done.

Calibrated a THIRD zone (251, Staten Island, low-volume) the same way as
zones 79/106 -- n_drivers=3, patience=7min, arrival=23.7/hr -- giving 3
real anchors spanning different demand/supply regimes. Built
`ridepulse/optimization/uplift.py` (simulation-measured uplift curves,
reusing the interference study's treatment_speedup mechanism -- spend ->
treatment_prob via an assumed $5/treated-trip cost, stated as assumed not
measured) and `allocator.py` (PuLP MILP: multi-choice knapsack, one spend
level per zone, maximize total unfulfilled-demand reduction under budget).

**Uplift curves came back genuinely different shapes, not textbook
concave across the board -- reported as found:** zone 251 saturates hard
at $200 (spending more is pure waste, confirmed directly); zone 106 shows
*increasing* marginal returns instead of decreasing (plausibly the same
shared-pool compounding effect from the interference study -- more
treated trips free more capacity for everyone -- noted as a hypothesis,
not confirmed further).

**Result at $700 budget: optimizer +27.1 trips/hr vs. greedy +25.9
(-4.3%) vs. uniform +18.7 (-44.8%).** Tested across 5 budget levels
($300-$900), not just this one point: optimizer beats greedy at $300
(+5.1%), $600 (+7.6%), $700 (+4-8%), ties exactly at $500 and $900 (no
room left for a smarter trade-off there) -- reported honestly rather than
cherry-picking the best-looking budget.

**Correctness verified against brute force, not just trusted**: the PuLP
solver matches exhaustive search exactly across 8 budget levels on a
synthetic curve set with a known dominated option, and correctly avoids
that dominated option.

**Fairness note (PRD asks for this explicitly)**: greedy excludes Staten
Island at every budget tested. The optimizer isn't fundamentally fairer by
design -- it happened to favor Brooklyn (worst baseline fulfillment,
52.7%) over already-well-served Manhattan (83.1%) because that's where
the marginal returns were, not because of any equity objective. Stated
plainly: this optimizer has no fairness constraint, and a real deployment
would need one if equitable coverage matters.

9 new tests (budget respected, brute-force match across 8 budgets,
avoids dominated options, both baselines respect budget, optimizer never
worse than either baseline). All 43 repo tests + ruff pass. Committed as
"Add decision layer -- optimizer beats greedy 4-8% depending on budget,
uniform by ~45%, verified against brute force" once pushed.

**All three PRD Section 11 "wow" components are now done**: interference
bias chart, CUPED savings, prediction-to-decision optimizer.

Next: mSPRT + peeking study if time remains, then Streamlit readout app.

### Milestone: README rewritten with real numbers, all links verified (01:23)

Full rewrite in the PRD's target order (Problem/Why implicit in the intro,
Architecture, Data window, Data audit, Metrics, Forecasting, Simulator
calibration, Experiments, Optimization, Limitations, Future work), leading
with the three protected "wow" results in the first screen as PRD Section
10.2 asks for. Every number is real and traceable to tonight's actual runs
-- no placeholders, and every honest caveat kept in (partial simulator
calibration, the naive A/B sign flip, CUPED's failed first covariate, the
decision layer's budget-dependent margin). Resume-ready bullets (Google
XYZ format) added to both the README and the top of this log.

Verified rather than assumed: every doc link in the new README
(PRD.md, docs/overnight_log.md, docs/interference_study.md,
docs/cuped_analysis.md, docs/decision_layer.md, docs/data_quality_notes.md,
docs/metrics_definitions.md, docs/simulator_calibration.md,
configs/data.yaml) checked to actually exist with `[ -f ... ]` before
committing -- all 9 present. Full test suite re-run to confirm doc-only
changes didn't break anything (43 passed).

Committed as "Rewrite README with real measured numbers and resume-ready
bullets" once pushed.

Next: Streamlit readout app.

### Milestone: Streamlit experiment readout page, verified running (01:29)

Built `dashboard/app.py`: one page (PRD Section 7.8 explicitly wants
productionization "deliberately light" -- no auth, no multi-page nav)
displaying the three flagship results (interference bias chart, CUPED
numbers, decision-layer chart) plus the forecasting backtest and simulator
calibration honesty note, so a reviewer gets the full real story --
caveats included -- in one place. Displays already-computed results from
tonight's docs/*.md rather than re-running simulations on page load
(explicit design choice, stated in the module docstring: single source of
truth is the docs, this page mirrors them).

**Caught one real issue before it shipped**: the first draft used
Markdown links like `[Full methodology](docs/interference_study.md)`,
which look clickable but wouldn't actually work -- Streamlit doesn't serve
arbitrary repo files as static content, so clicking would 404. Replaced
with plain-text file references instead of a broken affordance.

**Verified running, not just written**: `uv add streamlit`, launched with
`streamlit run dashboard/app.py --server.headless true` on a background
port, confirmed `HTTP 200` on the root page and `ok` on `/_stcore/health`,
checked the server log for a traceback (would appear there if the script
threw during render) -- none. Killed the test server cleanly afterward.
`make dashboard` added as the run command.

All 43 repo tests + ruff pass (no code logic changed, just the new
dashboard page). Committed as "Add Streamlit experiment readout page,
verified running" once pushed.

---

## Session summary (final)

Ten-plus real, tested, pushed commits covering the full PRD critical path
in one overnight session:

1. Repo scaffold + TLC/NOAA ingestion with real validation
2. Layered SQL warehouse + metrics definitions + data-quality findings
3. Unit tests + CI
4. Fixed a real OOM bug in the warehouse build (bucketed histogram vs.
   approx_quantile at high group cardinality)
5. Seasonal-naive forecasting baseline (15.2% WAPE) + 12-fold backtest
6. LightGBM demand model (12.3% WAPE, beats naive on 10/12 folds)
7. Discrete-event marketplace simulator core engine, verified on toy
   scenarios
8. Simulator calibration against real data -- honest partial match, plus
   a real modeling bug found and fixed (continuous-queue instability ->
   warm-up/measure design)
9. Power/MDE calculator + fixed-horizon A/B with SRM check, null
   false-positive rate verified against alpha
10. **The interference study** (flagship result): naive A/B -103% bias
    (wrong sign), switchback +3% bias
11. **CUPED**: 26.3% variance reduction, after documenting a failed first
    covariate attempt and catching a real sign bug via a mismatch that
    shouldn't have existed
12. **Decision layer**: PuLP optimizer beats greedy by 4-8% (budget-
    dependent) and uniform by ~45%, verified against brute force
13. README rewritten with all real numbers, resume bullets, verified links
14. Streamlit readout page, verified actually running

**What's NOT built, honestly**: mSPRT/peeking study (PRD's own
first-thing-to-cut, deprioritized behind the three protected "wow"
results by design); FastAPI + Docker (lowest priority, PRD calls
productionization "deliberately light"); Tableau Public (structurally
out of scope, GUI-only publish flow); the full 2023-2025 data window
(deliberately still the 3-month pilot, disclosed everywhere); DiD
congestion-pricing analysis and Chicago generalization (need a wider
data window).

**Real bugs found and fixed tonight, not hidden**: the warehouse OOM,
the simulator's unstable continuous-queue model, a broken chart-label
overflow, a CUPED sign error, and a non-functional Streamlit link -- all
caught by checking real output against expectations, not by trusting
code that merely ran without an exception. This pattern is the actual
throughline of the night, and worth saying so directly rather than just
listing the wins.

This is a clean, honest stopping point. Ending the loop here rather than
forcing mSPRT or FastAPI/Docker into the remaining time.

---

## Session resumed (user awake, asked to complete the whole project)

User reviewed the repo, confirmed it's presentable, and asked to continue
past the PRD's own "never cut" scoping and build everything except
Tableau (which they'll finish themselves -- GUI-only, can't be automated).

### Milestone: README image embeds (quick fix)

Found during the audit: zero charts were actually embedded in README.md --
the three flagship results were tables/text only, even though the PNGs
existed and were linked from the individual docs/*.md files. Directly
undercut the PRD's own goal of landing the visual results in the first
screen. Embedded all three (interference_bias.png, decision_layer.png,
simulator_calibration_overlay.png) inline.

### Milestone: mSPRT + peeking study

`ridepulse/experiments/msprt.py`: always-valid mixture-SPRT p-value
(Johari et al. KDD 2017). Null-simulation peeking study, 2000 reps: naive
daily peeking inflates false positives to **27.1%** (the PRD's own
anticipated ~20-30%, not tuned to hit it), mSPRT holds it at **1.7%**.
6 new tests. Full writeup: `docs/msprt_peeking_study.md`.

### Milestone: FastAPI serving layer -- found and fixed a real 100%-missing feature

`api/main.py`: `/forecast/{zone}` (lazy-trained LightGBM) and
`/experiments/{interference,cuped,decision-layer}` (same verified numbers
as the docs and Streamlit page). Testing every endpoint with real
requests -- not just checking the process booted -- surfaced a genuine
bug: every zone 404'd. Root cause: `temp_avg_c` is 0/272 rows populated in
the raw NOAA feed for this station (confirmed at the source). LightGBM's
training path tolerated it silently (zero information gain, never split
on); a stricter `dropna()` in the new serving code exposed it. Removed
the dead feature from `FEATURE_COLUMNS` rather than working around it at
the API layer; re-ran the backtest to confirm it was genuinely
unaffected -- pooled WAPE unchanged at 12.3%, exactly as expected. 4 new
API tests.

### Milestone: CI break and fix, confirmed via the GitHub Actions API, not guessed

The FastAPI commit broke CI -- confirmed by fetching the actual run/job
status via the public GitHub API (not assumed from a passing local run).
Root cause: a new API test hit the live DuckDB warehouse, which is
gitignored and never built in a fresh CI checkout. Fixed with a
`skipif` gated on the warehouse file existing, verified by actually
hiding `data/ridepulse.duckdb` locally and confirming the two
DB-dependent tests skip cleanly rather than fail. Re-checked the CI API
after pushing the fix: green.

### Milestone: surge proxy + WoW anomaly KPIs (7/12 built)

`kpi_surge_proxy.sql` (fare vs. median $/mile for comparable trips) and
`kpi_wow_anomaly.sql` (robust z-score via MAD). Caught and fixed a real
SQL bug before it ran: an early draft nested a window function inside
another window function's argument (invalid), split into staged CTEs.

### Milestone: Docker -- genuinely blocked by the local environment, documented honestly

Docker Desktop hung on every `docker pull`/`docker build` attempt across
multiple restarts. Diagnosed rather than assumed: confirmed general
network was fine (`curl` reached Docker Hub's registry and auth endpoints
successfully) while the daemon's own VM network path hung -- a local
Docker Desktop issue, not a code problem. `docker/Dockerfile` and
`.dockerignore` are written (multi-stage-free, `uv sync --frozen`, no
data baked in, volume-mount pattern for `data/`) but NOT verified to
build. Stated as genuinely unverified in the README rather than assumed
to work.

### Milestone: widened to the full 2023-2025 window -- 593M rows, two real bugs found and fixed

Downloaded and validated all 30 months (`configs/data.yaml full_months`).
NOAA weather needed an explicit `force=True` refresh -- the first attempt
silently kept the old 3-month-window file since `download_weather()` only
checks file existence, not date coverage.

Validation caught a real schema variant: 2023-01's `PULocationID`/
`DOLocationID` are `BIGINT` while every other month is `INTEGER`. Verified
directly (not assumed) that DuckDB's `read_parquet()` auto-promotes across
a glob spanning both schemas without loss, then added a narrow, documented
compatible-widening allowance rather than loosening validation generally.
2 new tests using real parquet fixtures.

**Warehouse rebuild hit a real OOM at 10x scale**, fixed by root-causing
rather than guessing: `stg_trips`'s `SELECT DISTINCT` across 593M rows hit
DuckDB's own memory cap twice (graceful DuckDB exceptions, not OS kills).
Disabling insertion-order preservation alone wasn't enough. Root cause:
10 CPU cores means DuckDB parallelizes the hash-based DISTINCT into
per-thread partitions, multiplying peak memory roughly by thread count.
Fixed with `threads=4` + `memory_limit=11GB` (real headroom measured
before the change, not guessed) -- less parallelism, more time, less
peak memory. Full build now succeeds in ~7.5 minutes.

**Verified, not assumed**: `stg_trips` row count exactly matches
`mart_zone_hour_demand`'s summed `trip_count` (592,951,618 both), correct
Jan 2023-Jun 2025 date range, monthly volumes all realistic (18-20M/month).

**Re-ran forecasting at full scale (120 folds: 4/month x 30 months,
superseding the 12-fold pilot result)**: naive baseline **18.2%** WAPE
(worse than the pilot's 15.2% -- reported honestly; the original 3-month
pilot was plausibly an unusually calm sample). LightGBM **12.4%** WAPE,
beating naive on **all 120/120 folds** (vs. 10/12 at pilot scale) --
LightGBM's relative edge grew from ~19% to ~32% with more training
history, consistent with a trained model benefiting from data in a way a
fixed rule can't.

**Re-verified the two new KPIs against the full window** (they're views,
so they auto-recomputed against the new data): surge proxy p10-p90 spread
0.83-1.24 (was 0.85-1.23); WoW anomaly rate dropped from 3.9% to 2.2%,
consistent with more weeks per group producing a more stable MAD estimate.

**Deliberately NOT re-run against the full window**: the calibrated
simulator and the three flagship experiment results (interference, CUPED,
decision layer) -- still on the 3-month pilot subset. Documented as a
deliberate scoping choice in the README, not an inconsistency: those are
simulator-internal methodology results that don't need more real-world
row volume to be valid, only accurate calibration inputs, which the pilot
window already provided. Re-running them is listed as future work.

README fully updated to reflect all of the above: three main results
section leads with real embedded charts, data window section explains the
warehouse/experiments split precisely, forecasting section shows both the
full-window (authoritative) and pilot-window (superseded) numbers side by
side, limitations/future-work sections rewritten to match current reality
rather than left stale. All internal doc/image links re-verified to
resolve. 55 tests passing throughout every step of this phase.
