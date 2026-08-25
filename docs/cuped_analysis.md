# CUPED Analysis

PRD Section 7.5 point 3 / Section 11 #2: one of the three "wow" components.
`theta = Cov(X,Y)/Var(X)`, `Y_cuped = Y - theta*(X - mean(X))` -- the
standard CUPED estimator (Deng et al. 2013), not reinvented.

## The covariate that didn't work, and why (kept, not hidden)

First hypothesis: within one continuous simulation run (1hr warm-up + 1hr
measurement, same seed), use warm-up mean wait as the pre-period covariate
X and measurement mean wait as the outcome Y, on the theory that queue
state carries over the boundary. **Measured correlation: 0.027** --
indistinguishable from zero.

This makes sense on reflection rather than being a dead end: Poisson
arrivals have independent increments over disjoint time windows by
definition, and zone 106's calibrated `n_drivers=12` has real slack over
the ~90/hr arrival rate (see `docs/simulator_calibration.md`), so the
queue clears well within an hour -- there's no state left to carry over.
More fundamentally: fully i.i.d. replications have no persistent
unit-level trait for CUPED to exploit, which is also the actual textbook
reason CUPED works in real experiments (persistent day- or user-level
heterogeneity) -- not "any number from before the experiment helps."

## The covariate that worked, grounded in real data

Real ride-hailing demand genuinely varies day to day. Queried the
warehouse directly: zone 106's real Wednesday-18:00 trip count across all
13 Wednesdays in the pilot window (Jan/Jun/Sep 2024, not just the 4 weeks
used for calibration) has **mean 84.9 trips, std 17.1, coefficient of
variation 20.2%**. Used that measured 20.2% as a day-level demand
multiplier (lognormal) applied to the arrival rate for an entire simulated
day -- affecting both the warm-up and measurement hour together, which is
a faithful mechanism (real day-level demand shocks: weather, events),
not a convenience.

## Result (400 replications, zone 106 calibrated params)

| Metric | Value |
|---|---|
| Pre/post correlation | 0.513 |
| Theoretical variance reduction (r²) | 26.3% |
| Measured variance reduction (actual CUPED calc) | 26.3% |
| Implied sample-size savings | 26.3% |

Theoretical and measured agree almost exactly, as they should -- `Var(Y_cuped)
= Var(Y)(1-r²)` is an exact OLS identity, not an approximation, so a real
gap between the two numbers would mean a bug, not sampling noise (see
below).

**Implied sample-size savings = variance reduction, by derivation, not a
separate measurement**: required sample size for a fixed power/alpha/MDE
is proportional to the metric's variance (`ridepulse/experiments/power.py`:
`n ~ sigma^2 / mde^2`), so a 26.3% variance reduction directly implies a
26.3% smaller required sample size for the same target MDE.

## A real bug this caught, not just a design choice

The first version of `theoretical_variance_reduction_pct` computed
`(1 - r^2) * 100` -- backwards. `1-r^2` is the REMAINING variance
fraction after CUPED, not the reduction; the reduction fraction is `r^2`.
This surfaced as a real anomaly, not something assumed away: the first run
showed theoretical=73.7% vs. measured=26.3%, a huge gap for values that
are supposed to match by an exact algebraic identity. Verified the
"measured" side by hand (`Var(Y_cuped)/Var(Y)` computed directly) before
concluding the theoretical formula, not the measurement, was wrong. Fixed
and added `tests/test_cuped.py::test_cuped_matches_a_hand_computed_reduction`,
which constructs `Y = 0.8*X + noise` with a known-by-construction r=0.8
and reduction=64%, specifically so this class of sign error can't silently
reappear.

## Honest scope note

26.3% is a real, useful number for an interview conversation ("CUPED cut
my required sample size by over a quarter using a covariate I verified
mattered, after ruling out a naive covariate that measured at zero") -- it
is not the dramatic 90%+ reductions sometimes reported in production
systems with rich user-level historical data. This simulator has no
persistent user identities to draw a richer covariate from; the day-effect
mechanism used here is the most realistic covariate available in this
setup, and its magnitude (20.2% CV) is measured from real data, not tuned
to produce a nicer-looking result.
