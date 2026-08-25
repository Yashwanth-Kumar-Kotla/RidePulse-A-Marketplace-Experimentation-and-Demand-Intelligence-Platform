"""Fixed-horizon A/B/N analysis: two-sample test, confidence interval, and a
sample ratio mismatch (SRM) check.

Welch's t-test (unequal-variance two-sample t-test) is used rather than a
pooled-variance t-test -- it's the standard default for A/B analysis since
treatment and control often do have different variances (e.g. an
intervention that shifts the mean can also change the spread), and Welch's
test doesn't assume otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import chisquare, ttest_ind
from scipy.stats import t as t_dist

# SRM alert threshold is deliberately much stricter than a normal alpha=0.05
# significance test: a chi-square goodness-of-fit test has real statistical
# power to detect even tiny, practically-irrelevant allocation imbalances at
# large N, so alpha=0.05 would flag constantly on benign random variation.
# p < 0.001 is standard practice (e.g. Kohavi et al.) specifically because an
# imbalance real enough to hit that threshold is very rarely just noise --
# it's almost always a bug in the randomization or logging.
SRM_ALPHA = 0.001


@dataclass
class ABTestResult:
    control_n: int
    treatment_n: int
    control_mean: float
    treatment_mean: float
    effect: float  # treatment_mean - control_mean
    ci_95: tuple[float, float]
    p_value: float
    significant: bool  # at alpha=0.05


def analyze(control: np.ndarray, treatment: np.ndarray, alpha: float = 0.05) -> ABTestResult:
    control, treatment = np.asarray(control, dtype=float), np.asarray(treatment, dtype=float)
    t_result = ttest_ind(treatment, control, equal_var=False)
    effect = treatment.mean() - control.mean()

    # Welch-Satterthwaite CI on the mean difference, consistent with the
    # unequal-variance t-test above.
    se = np.sqrt(treatment.var(ddof=1) / len(treatment) + control.var(ddof=1) / len(control))
    t_crit = t_dist.ppf(1 - alpha / 2, t_result.df)
    ci = (effect - t_crit * se, effect + t_crit * se)

    return ABTestResult(
        control_n=len(control),
        treatment_n=len(treatment),
        control_mean=float(control.mean()),
        treatment_mean=float(treatment.mean()),
        effect=float(effect),
        ci_95=(float(ci[0]), float(ci[1])),
        p_value=float(t_result.pvalue),
        significant=bool(t_result.pvalue < alpha),
    )


@dataclass
class SRMResult:
    observed: dict[str, int]
    expected_ratios: dict[str, float]
    p_value: float
    srm_detected: bool  # True = allocation looks broken, don't trust the A/B result


def check_srm(observed_counts: dict[str, int], expected_ratios: dict[str, float]) -> SRMResult:
    """expected_ratios must sum to 1 (e.g. {"control": 0.5, "treatment": 0.5})."""
    if abs(sum(expected_ratios.values()) - 1.0) > 1e-9:
        raise ValueError("expected_ratios must sum to 1")
    total = sum(observed_counts.values())
    arms = list(observed_counts.keys())
    observed = [observed_counts[a] for a in arms]
    expected = [expected_ratios[a] * total for a in arms]
    chi2_result = chisquare(f_obs=observed, f_exp=expected)
    return SRMResult(
        observed=observed_counts,
        expected_ratios=expected_ratios,
        p_value=float(chi2_result.pvalue),
        srm_detected=bool(chi2_result.pvalue < SRM_ALPHA),
    )
