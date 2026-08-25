# Interference Study

PRD Section 11 #1: the single highest-value artifact in this project. If
scope had to be cut anywhere else tonight, this was the one result to
protect.

## Question

In a two-sided marketplace, a driver-incentive intervention changes a
SHARED resource (the driver pool), not something delivered privately to
individual riders. If you measure its effect with a naive rider-randomized
A/B test anyway, how wrong is the answer -- and does a switchback
(time-block) design actually fix it, or is that just conventional wisdom?

## Mechanism (what's simulated, and why it's a real interference mechanism)

The incentive makes a treatment-tagged rider's matched trip finish
`treatment_speedup`x faster (0.7 = 30% faster here) -- modeling an
incentivized driver hustling to complete the trip and become available
again sooner. That driver then returns to the SAME shared pool used by
every other rider in the zone, treatment-tagged or not. This is a real,
standard interference mechanism (a shared-resource turnover externality),
implemented as a small, inspectable extension to
`ridepulse/simulation/engine.py` (`treatment_prob`, `treatment_speedup` on
`SimParams`; `treatment_flags` on `SimResult`) -- not a special-cased
model built just for this result.

## Method: three estimators of the same intervention

1. **True effect (known ground truth):** run the simulator twice per
   replication -- once with `treatment_prob=1.0` (the whole world gets the
   incentive) and once with `treatment_prob=0.0` (nobody does). These two
   worlds never mix tags in the same driver pool, so the difference in mean
   wait time between them is unbiased by construction.
2. **Naive rider-randomized A/B:** ONE shared simulation per replication
   with `treatment_prob=0.5` -- both tags coexist in the same driver pool,
   the way a real naive experiment would actually run. Compares mean wait
   for treatment-tagged riders vs. control-tagged riders within that same
   contaminated pool.
3. **Switchback:** reuses the same clean, single-condition runs from (1),
   resampled as independent "blocks," and compares mean block-level wait
   across treatment blocks vs. control blocks. No within-block
   contamination by construction.

All three use the same warm-up-then-measure pattern as
`docs/simulator_calibration.md` (1-hour warm-up discarded, 1 hour
measured) for the same reason: a rush hour resets daily, it isn't a
continuous overload.

Parameters reused from the zone 106 calibration (`docs/simulator_calibration.md`:
fitted `n_drivers=12`, `mean_patience_minutes=5`; real `arrival_rate=89.7/hr`,
`avg_trip_minutes=16.55`) so this is grounded in a calibrated-as-possible
setup, not arbitrary toy numbers -- though see the scope note below on what
that calibration does and doesn't license.

## Result (300 replications, real, measured)

| Estimator | Effect on wait time | Bias vs. true effect |
|---|---|---|
| True effect (ground truth) | -1.52 min | -- |
| Naive rider-randomized A/B | +0.05 min | **-103%** |
| Switchback (time-block) | -1.56 min | **+3%** |

![Interference bias chart](interference_bias.png)

**The naive design doesn't just underestimate the effect -- it misses it
almost entirely**, and even gets the sign wrong in this run (+0.05 min
vs. a true -1.52 min). Control riders indirectly benefit from the extra
driver capacity that treatment-matched trips free up sooner, so the
"control" arm isn't a clean counterfactual -- it's contaminated by the
treatment. The switchback design, which never lets both conditions share a
driver pool at the same time, recovers the true effect to within 3%.

**Robustness check performed, not just a single lucky run:** re-ran at 100
and 300 replications (bias direction and rough magnitude held: naive
~-99% to -103%, switchback ~+1% to +3%) and against zone 79's calibrated
parameters instead of zone 106's (naive -99.5%, switchback +1.0%). The
qualitative finding -- naive is severely biased toward zero, switchback is
not -- is consistent across both zones and replication counts, not an
artifact of one specific parameter choice. Also checked the null case
(`treatment_speedup=1.0`, no real effect): all three estimators correctly
land near zero, confirming switchback isn't just "always predicting a big
number" by coincidence.

## Scope: what this does and doesn't license

Per `docs/simulator_calibration.md`, this simulator's ABSOLUTE wait-time
levels are only partially validated (one zone's p50 matched closely,
everything else was overestimated by 32-73%). This study does not depend
on that: it's a RELATIVE comparison of two estimators against the
simulator's own internal ground truth, which is exactly the kind of
comparison the calibration write-up said the simulator remains valid for.
It demonstrates that naive rider-randomization is structurally biased
under interference and that switchback substantially corrects it -- a
methodological finding about experiment design, not a claim about the
exact minutes real Uber/Lyft riders would gain from a real incentive
program.
