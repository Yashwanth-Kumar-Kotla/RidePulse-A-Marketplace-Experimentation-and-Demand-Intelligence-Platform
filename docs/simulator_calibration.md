# Simulator Calibration

Calibrating `ridepulse/simulation/engine.py` against real held-out wait-time
data, per PRD Section 13's non-negotiable requirement: an unvalidated
simulator is explicitly named as the project's top risk, and no experiment
result should be reported on an uncalibrated simulator.

## Scope: what's calibrated, what isn't

Per PRD Section 7.4 ("calibrate on some quantities, hold out others, and say
which"):
- **Calibrated: wait-time distribution (p50/p90).** Real ground truth exists
  (`stg_trips.wait_time_seconds`, pooled per zone-hour).
- **NOT independently validated: utilization.** HVFHS has no driver on/off-
  duty timestamps -- there is no ground truth to compare against (same
  reason `docs/metrics_definitions.md` marks KPI #4, driver utilization, as
  "Planned, no ground truth"). Reported below as a simulator output only.

Arrival rate = real completed `trip_count`/hour. This inherits the
fulfillment-proxy limitation already documented in
`docs/data_quality_notes.md`: completed trips likely understate true demand
in supply-constrained zone-hours, since cancelled/unmatched requests aren't
observed in HVFHS data.

## Method

1. Two zones spanning different demand levels: Zone 79 (Manhattan,
   ~270K January trips) and Zone 106 (Brooklyn/Gowanus, ~39K January trips).
2. Target: Wednesday 18:00 (a real recurring rush-hour slice). **Fit** sample
   = pooled raw wait times from three Wednesdays (Jan 3, 10, 17). **Holdout**
   sample = a fourth Wednesday (Jan 24), not used for fitting.
3. Grid search over `n_drivers` and `mean_patience_minutes` (trip duration
   fixed from the real `avg_trip_time_seconds` for that zone) to minimize
   squared error between simulated and real fit-sample p50/p90.
4. **Out-of-sample validation**: run the fitted `n_drivers` /
   `mean_patience_minutes` against the HOLDOUT week's own real arrival rate
   (demand genuinely varies week to week) and compare simulated vs. real
   holdout p50/p90. A fit that isn't checked out-of-sample is a curve-fit,
   not a calibration.

### A real modeling bug found and fixed along the way

The first version simulated many continuous hours at a constant arrival
rate. That models an unstable queue that builds up without bound whenever
demand is even slightly above capacity (an M/M/c queue at rho>=1 never
reaches steady state) -- verified directly: simulated utilization pinned at
~1.0 and wait times were inflated far above real values at every driver
count tried, because the queue never got a chance to reset. A real rush
hour is a demand burst that resets daily, not a continuous multi-hour
overload.

The fix (standard discrete-event-simulation practice: discard the initial
transient) simulates a 1-hour warm-up at the same arrival rate, then
measures wait times only from the following 1-hour window -- letting driver
occupancy reach a realistic level before measuring, rather than starting
from either "fully idle" (which artificially produces near-zero wait) or
"already infinitely backlogged" (which artificially inflates it without
bound).

## Result

| Zone | Fitted n_drivers | Fitted patience (min) | Real p50 (holdout) | Sim p50 | Real p90 (holdout) | Sim p90 | Sim utilization (unvalidated) |
|---|---|---|---|---|---|---|---|
| 79 (Manhattan) | 85 | 10 | 2.85 min | 4.94 min | 4.90 min | 6.82 min | 1.13 |
| 106 (Brooklyn) | 12 | 5 | 3.28 min | 3.23 min | 5.33 min | 7.02 min | 1.13 |

See `docs/simulator_calibration_overlay.png` for the chart.

**Honest read: partial calibration, not a clean match.** Zone 106's p50
matches almost exactly (1.5% off). Everything else is systematically
*overestimated* by the simulator: Zone 79's p50 by 73%, Zone 79's p90 by
39%, Zone 106's p90 by 32%. Right order of magnitude and right direction
(busier zone -> more wait), wrong precision.

**Most likely cause, and it's a limitation this project already
disclosed before calibration even started:** `engine.py`'s docstring names
"no cross-zone driver repositioning" as a deliberate simplification -- a
driver stays in-zone after a trip instead of following real drop-off
patterns. A real marketplace has drivers reposition INTO a surging zone
from neighboring zones, effectively making real supply more elastic than
this closed single-zone model allows. That's exactly consistent with the
error direction observed here: the simulator, unable to draw on outside
supply, predicts more strain (higher wait) than the real -- more elastic --
system actually shows. This is a hypothesis consistent with the evidence,
not independently confirmed; confirming it would mean building the
cross-zone flow model, which is out of scope tonight.

Also worth noting: `utilization` > 1.0 in both zones (1.13), which
`engine.py`'s own docstring already flags as a real boundary effect (a trip
matched near the end of the measurement window still runs its full
duration past the window edge) -- not a new bug, an expected consequence of
measuring a bounded window, and part of why utilization isn't claimed as
independently validated.

## What this means for using the simulator downstream

The simulator is usable for what it's explicitly meant to validate --
**relative, within-simulator comparisons** like the interference study
(naive A/B vs. switchback bias, both measured against the same simulator's
own ground truth) -- because that comparison doesn't depend on the
simulator's absolute wait-time level matching reality, only on the
simulator behaving like a coherent marketplace. It is NOT validated well
enough to make absolute claims like "real riders in zone 79 wait N minutes"
-- that would overstate what was actually confirmed here. This distinction
is stated explicitly in the README /docs, per the project's standing rule
against overselling a result.
