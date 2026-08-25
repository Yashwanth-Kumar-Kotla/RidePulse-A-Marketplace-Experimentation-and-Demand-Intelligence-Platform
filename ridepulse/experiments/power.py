"""Power / minimum detectable effect (MDE) calculators.

Standard textbook formulas (e.g. Kohavi, Tang & Xu, "Trustworthy Online
Controlled Experiments", ch. 3), not reinvented -- these compute the
per-arm sample size needed to detect a given effect at a given
significance level (alpha) and power (1 - beta), for a fixed two-arm
design with equal allocation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.stats import norm


@dataclass
class PowerResult:
    required_n_per_arm: int
    baseline: float
    mde: float
    alpha: float
    power: float


def _z_scores(alpha: float, power: float) -> tuple[float, float]:
    z_alpha = norm.ppf(1 - alpha / 2)  # two-sided
    z_beta = norm.ppf(power)
    return z_alpha, z_beta


def sample_size_for_proportions(baseline_rate: float, mde_absolute: float, alpha: float = 0.05, power: float = 0.8) -> PowerResult:
    """MDE is an ABSOLUTE difference in proportion (e.g. 0.02 = 2 percentage points),
    not relative -- callers comparing e.g. fulfillment rate should pass it that way.

    n = (z_alpha/2 + z_beta)^2 * [p1(1-p1) + p2(1-p2)] / (p1 - p2)^2, per arm.
    """
    if not 0 < baseline_rate < 1:
        raise ValueError("baseline_rate must be in (0, 1)")
    p1 = baseline_rate
    p2 = baseline_rate + mde_absolute
    z_alpha, z_beta = _z_scores(alpha, power)
    n = ((z_alpha + z_beta) ** 2) * (p1 * (1 - p1) + p2 * (1 - p2)) / (mde_absolute**2)
    return PowerResult(required_n_per_arm=math.ceil(n), baseline=baseline_rate, mde=mde_absolute, alpha=alpha, power=power)


def sample_size_for_means(baseline_std: float, mde_absolute: float, alpha: float = 0.05, power: float = 0.8) -> PowerResult:
    """For a continuous metric (e.g. wait-time minutes). Assumes equal variance
    in both arms (a standard simplifying assumption for a planning-stage
    calculator -- Welch's t-test used at analysis time doesn't require it).

    n = 2 * (z_alpha/2 + z_beta)^2 * sigma^2 / mde^2, per arm.
    """
    if baseline_std <= 0:
        raise ValueError("baseline_std must be positive")
    z_alpha, z_beta = _z_scores(alpha, power)
    n = 2 * ((z_alpha + z_beta) ** 2) * (baseline_std**2) / (mde_absolute**2)
    return PowerResult(required_n_per_arm=math.ceil(n), baseline=baseline_std, mde=mde_absolute, alpha=alpha, power=power)
