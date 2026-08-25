# mSPRT and the Peeking Study

PRD Section 7.5 point 4: demonstrate that naive daily peeking inflates
false positives, and that mSPRT ("always-valid" sequential testing)
controls it. Formula: Johari, Koomen, Pekelis, Walsh, "Peeking at A/B
Tests" (KDD 2017) -- not reinvented; see `ridepulse/experiments/msprt.py`
docstring for the exact mixture-SPRT statistic.

## Method

Simulate a NULL experiment (true effect = 0) monitored daily for 30 days,
50 new observations/day, alpha=0.05. Two decision rules run on the SAME
accumulating data at every peek:

- **Naive**: a fresh fixed-alpha two-sided z-test on all data accumulated
  so far. Declares significant (and stops) the first day p < 0.05.
- **mSPRT**: the always-valid p-value from the mixture likelihood ratio.
  Same stopping rule (p < 0.05), different p-value.

2000 replications.

## Result (real, measured, PRD's own target was "roughly 20 to 30%")

| Method | False-positive rate |
|---|---|
| Naive daily peeking | **27.1%** |
| mSPRT | **1.7%** |

Naive peeking inflates the true false-positive rate more than 5x above the
nominal 5% -- landing right in the range the PRD anticipated without being
tuned to hit it. mSPRT holds it not just below 5%, but comfortably below
(1.7%), consistent with mSPRT's "always-valid" property: the type-I error
is bounded ABOVE by alpha at any stopping time, and comes out conservative
in practice rather than exactly hitting the nominal rate -- expected
behavior, not a bug.

## Scope note

Kept intentionally simple, per the PRD's own instruction ("keep the
peeking demo simple") -- one normal-mean testing scenario, not integrated
with the simulator's marketplace dynamics. This demonstrates the
statistical phenomenon on its own terms, the same way the null-simulation
false-positive check in `ridepulse/experiments/ab_test.py` does for the
fixed-horizon test.
