"""CUPED (Controlled-experiment Using Pre-Experiment Data): reduce variance
in a metric estimate using a pre-period covariate correlated with the
outcome, without needing new data collection.

theta = Cov(X, Y) / Var(X) is the standard CUPED estimator (Deng et al.,
"Improving the Sensitivity of Online Controlled Experiments by Utilizing
Pre-Experiment Data", 2013) -- the OLS slope of Y on X, not reinvented.
Y_cuped = Y - theta * (X - mean(X)) has the same expectation as Y (theta
doesn't bias the mean) but lower variance whenever X and Y are correlated.

FIRST ATTEMPT AT A COVARIATE FAILED, and that failure is the reason this
module looks the way it does -- documented rather than silently reworked.
The initial idea: within one continuous simulation run (warm-up hour +
measurement hour, same seed), use warm-up mean wait as X and measurement
mean wait as Y, hypothesizing the queue state carries over the boundary.
Measured correlation: 0.027 -- indistinguishable from zero. This makes
sense on reflection: Poisson arrivals have INDEPENDENT increments over
disjoint time windows by definition, and at zone 106's calibrated
n_drivers=12 (real slack over the ~90/hr arrival rate), the queue clears
well within an hour, so there's no meaningful state to carry over. Fully
i.i.d. replications have no persistent unit-level trait for CUPED to
exploit -- which is also the actual textbook mechanism for why CUPED works
in real experiments (persistent day- or user-level heterogeneity), not
just "any pre-period number helps."

WORKING COVARIATE: real ride-hailing demand genuinely varies day to day
(weather, events, etc.) -- so a day-level demand multiplier that affects
BOTH the warm-up and measurement hour of the same simulated day is a
faithful mechanism, not a convenient invention. Its magnitude is measured,
not assumed: zone 106's real Wednesday-18:00 trip count across all 13
Wednesdays in the pilot window (all three months, not just the calibration
weeks) has a coefficient of variation of 20.2% (mean 84.9, std 17.1 trips
-- see docs/cuped_analysis.md for the query). That measured 20.2% is what
DAY_EFFECT_CV is set to below.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ridepulse.simulation.engine import SimParams, run_simulation

WARMUP_MINUTES = 60
MEASURE_MINUTES = 60
DAY_EFFECT_CV = 0.202  # measured, see module docstring


@dataclass
class CupedResult:
    n_replications: int
    n_excluded_empty_warmup: int
    correlation: float
    theoretical_variance_reduction_pct: float  # corr^2 (fraction of variance explained)
    measured_variance_reduction_pct: float  # Var(Y_cuped) / Var(Y)
    implied_sample_size_savings_pct: float  # == measured_variance_reduction_pct, derived below
    raw_variance: float
    cuped_variance: float
    theta: float


def collect_pre_post_pairs(
    arrival_rate: float, n_drivers: int, mean_trip_minutes: float, mean_patience_minutes: float, n_reps: int
) -> tuple[np.ndarray, np.ndarray, int]:
    """Returns (X pre-period means, Y measurement-period means, n_excluded).

    Each replication = one simulated day, with its own day-level demand
    multiplier (lognormal, CV=DAY_EFFECT_CV) applied to the arrival rate for
    BOTH the warm-up and measurement hour -- see module docstring for why
    this, not same-run carryover, is the real covariate here.
    """
    rng = np.random.default_rng(0)
    xs, ys = [], []
    n_excluded = 0
    for seed in range(n_reps):
        day_multiplier = rng.lognormal(mean=0, sigma=DAY_EFFECT_CV)
        result = run_simulation(
            SimParams(
                arrival_rate_per_hour=arrival_rate * day_multiplier,
                n_drivers=n_drivers,
                duration_hours=(WARMUP_MINUTES + MEASURE_MINUTES) / 60,
                mean_trip_minutes=mean_trip_minutes,
                mean_patience_minutes=mean_patience_minutes,
                seed=seed,
            )
        )
        pre = [w for w, m in zip(result.wait_times_min, result.match_times_min) if m < WARMUP_MINUTES]
        post = [w for w, m in zip(result.wait_times_min, result.match_times_min) if m >= WARMUP_MINUTES]
        if not pre or not post:
            n_excluded += 1
            continue
        xs.append(float(np.mean(pre)))
        ys.append(float(np.mean(post)))
    return np.array(xs), np.array(ys), n_excluded


def apply_cuped(x: np.ndarray, y: np.ndarray) -> CupedResult:
    correlation = float(np.corrcoef(x, y)[0, 1])
    theta = float(np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1))
    y_cuped = y - theta * (x - x.mean())

    raw_var = float(np.var(y, ddof=1))
    cuped_var = float(np.var(y_cuped, ddof=1))
    measured_reduction_pct = (1 - cuped_var / raw_var) * 100

    # Var(Y_cuped) = Var(Y) * (1 - r^2) is an exact OLS identity -- the
    # REMAINING variance fraction is (1-r^2), so the REDUCTION fraction is
    # r^2, not (1-r^2). Caught by checking this against the measured value
    # directly: an earlier version of this line had it backwards
    # ((1-r^2)*100, i.e. computing the remaining fraction and calling it the
    # reduction) and the two numbers didn't match (73.7% vs. 26.3%) -- for
    # an exact algebraic identity, that gap meant a real bug, not noise.
    theoretical_reduction_pct = (correlation**2) * 100

    # Required sample size for a fixed power/alpha/MDE is proportional to the
    # metric's variance (see power.py: n ~ sigma^2 / mde^2) -- so a variance
    # reduction of V% implies the same V% reduction in required sample size
    # for a fixed target MDE. Not a separate empirical measurement, the same
    # number derived from the definition.
    implied_savings_pct = measured_reduction_pct

    return CupedResult(
        n_replications=len(x),
        n_excluded_empty_warmup=0,  # filled in by caller, which has that count
        correlation=correlation,
        theoretical_variance_reduction_pct=theoretical_reduction_pct,
        measured_variance_reduction_pct=measured_reduction_pct,
        implied_sample_size_savings_pct=implied_savings_pct,
        raw_variance=raw_var,
        cuped_variance=cuped_var,
        theta=theta,
    )


def run_cuped_study(
    arrival_rate: float, n_drivers: int, mean_trip_minutes: float, mean_patience_minutes: float, n_reps: int = 400
) -> CupedResult:
    x, y, n_excluded = collect_pre_post_pairs(arrival_rate, n_drivers, mean_trip_minutes, mean_patience_minutes, n_reps)
    result = apply_cuped(x, y)
    result.n_excluded_empty_warmup = n_excluded
    return result


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger(__name__)

    # zone 106 calibrated params, same as the interference study
    r = run_cuped_study(arrival_rate=89.7, n_drivers=12, mean_trip_minutes=16.55, mean_patience_minutes=5, n_reps=400)
    log.info("replications used: %d (excluded %d with empty warm-up or measurement)", r.n_replications, r.n_excluded_empty_warmup)
    log.info("pre/post correlation: %.3f", r.correlation)
    log.info("theoretical variance reduction (corr^2): %.1f%%", r.theoretical_variance_reduction_pct)
    log.info("measured variance reduction (raw CUPED calc): %.1f%%", r.measured_variance_reduction_pct)
    log.info("implied sample-size savings: %.1f%%", r.implied_sample_size_savings_pct)
