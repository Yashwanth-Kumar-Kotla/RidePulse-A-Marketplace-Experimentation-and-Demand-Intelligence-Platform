"""mSPRT (mixture sequential probability ratio test) and a peeking study
demonstrating why naive daily significance checks inflate false positives
under continuous monitoring, while mSPRT's "always-valid" p-value doesn't.

mSPRT formula: Johari, Koomen, Pekelis, Walsh, "Peeking at A/B Tests:
Why it matters, and what to do about it" (KDD 2017). For testing H0:
delta=0 vs H1: delta!=0 on a normal-mean difference with known per-
observation variance V and a N(0, tau^2) mixing prior on the true effect:

    Lambda_n = sqrt(V / (V + n*tau^2)) * exp(n^2 * tau^2 * mean_n^2 / (2*V*(V+n*tau^2)))

p_n = min(1/Lambda_n, 1) is a valid p-value at ANY stopping time n (not
just a fixed pre-registered n) -- that's the property a naive fixed-alpha
test checked repeatedly does not have.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def mixture_sprt_lambda(cumulative_mean: np.ndarray, n: np.ndarray, variance: float, tau: float) -> np.ndarray:
    """cumulative_mean[i] = mean of the first n[i] observations."""
    return np.sqrt(variance / (variance + n * tau**2)) * np.exp(
        (n**2) * (tau**2) * (cumulative_mean**2) / (2 * variance * (variance + n * tau**2))
    )


def always_valid_p_value(lambda_n: np.ndarray) -> np.ndarray:
    return np.minimum(1.0 / lambda_n, 1.0)


@dataclass
class PeekingStudyResult:
    n_reps: int
    n_days: int
    alpha: float
    naive_false_positive_rate: float  # fraction of null reps that trigger at ANY day under naive peeking
    msprt_false_positive_rate: float  # same, under mSPRT's always-valid p-value


def run_peeking_study(
    n_days: int = 30, daily_n: int = 50, true_std: float = 1.0, alpha: float = 0.05, tau: float = 0.3,
    n_reps: int = 2000, seed: int = 0,
) -> PeekingStudyResult:
    """Simulates a NULL experiment (no true effect, mean=0) monitored daily.

    'naive': runs a fresh fixed-alpha two-sided z-test on ALL data accumulated
    so far, every day, and stops (falsely) the first day p < alpha.
    'mSPRT': same daily monitoring, but using the always-valid p-value instead.
    Both track whether the null was ever falsely rejected across the n_days
    window -- the ONLY difference is which decision rule is used at each peek.
    """
    rng = np.random.default_rng(seed)
    naive_triggers = 0
    msprt_triggers = 0

    for _ in range(n_reps):
        daily_samples = rng.normal(0, true_std, size=(n_days, daily_n))
        cumulative_sum = np.cumsum(daily_samples.sum(axis=1))
        cumulative_n = daily_n * np.arange(1, n_days + 1)
        cumulative_mean = cumulative_sum / cumulative_n
        # variance of a single observation's contribution to the mean, so
        # cumulative_mean has variance true_std^2 / cumulative_n -- matches
        # mixture_sprt_lambda's convention (per-observation variance V).
        variance = true_std**2

        naive_se = np.sqrt(variance / cumulative_n)
        naive_z = cumulative_mean / naive_se
        naive_p = 2 * (1 - _standard_normal_cdf(np.abs(naive_z)))
        if np.any(naive_p < alpha):
            naive_triggers += 1

        lambda_n = mixture_sprt_lambda(cumulative_mean, cumulative_n, variance, tau)
        msprt_p = always_valid_p_value(lambda_n)
        if np.any(msprt_p < alpha):
            msprt_triggers += 1

    return PeekingStudyResult(
        n_reps=n_reps,
        n_days=n_days,
        alpha=alpha,
        naive_false_positive_rate=naive_triggers / n_reps,
        msprt_false_positive_rate=msprt_triggers / n_reps,
    )


def _standard_normal_cdf(z: np.ndarray) -> np.ndarray:
    from scipy.stats import norm

    return norm.cdf(z)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger(__name__)

    result = run_peeking_study()
    log.info(
        "null simulation, %d reps, %d days of daily peeking, alpha=%.2f:", result.n_reps, result.n_days, result.alpha
    )
    log.info("  naive fixed-alpha peeking false-positive rate: %.1f%%", result.naive_false_positive_rate * 100)
    log.info("  mSPRT always-valid false-positive rate: %.1f%%", result.msprt_false_positive_rate * 100)
