import numpy as np
from scipy.stats import binomtest

from ridepulse.experiments.ab_test import analyze, check_srm
from ridepulse.experiments.power import (
    sample_size_for_means,
    sample_size_for_proportions,
)


def test_larger_mde_needs_fewer_samples():
    small_effect = sample_size_for_proportions(baseline_rate=0.5, mde_absolute=0.01)
    large_effect = sample_size_for_proportions(baseline_rate=0.5, mde_absolute=0.05)
    assert large_effect.required_n_per_arm < small_effect.required_n_per_arm


def test_higher_power_needs_more_samples():
    low_power = sample_size_for_means(baseline_std=10, mde_absolute=2, power=0.7)
    high_power = sample_size_for_means(baseline_std=10, mde_absolute=2, power=0.95)
    assert high_power.required_n_per_arm > low_power.required_n_per_arm


def test_ab_analyze_detects_a_real_difference():
    rng = np.random.default_rng(0)
    control = rng.normal(loc=10, scale=2, size=2000)
    treatment = rng.normal(loc=11, scale=2, size=2000)  # real +1 effect, large N -> should detect
    result = analyze(control, treatment)
    assert result.significant
    assert 0.5 < result.effect < 1.5  # recovers the true effect roughly
    assert result.ci_95[0] < result.effect < result.ci_95[1]


def test_srm_flags_a_broken_allocation():
    # expected 50/50 but observed wildly skewed
    result = check_srm({"control": 6000, "treatment": 4000}, {"control": 0.5, "treatment": 0.5})
    assert result.srm_detected


def test_srm_does_not_flag_a_balanced_allocation():
    result = check_srm({"control": 5010, "treatment": 4990}, {"control": 0.5, "treatment": 0.5})
    assert not result.srm_detected


def test_null_simulation_false_positive_rate_matches_alpha():
    """PRD Section 7.5 point 6: under a null simulation (no true effect), the
    A/B pipeline's false-positive rate should be ~alpha. Uses a binomial
    confidence interval around the expected rate rather than a tight
    hardcoded bound -- this is a statistical test over random draws, so it
    will never land on exactly 0.05, and a tight bound would flake."""
    rng = np.random.default_rng(1)
    alpha = 0.05
    n_reps = 2000
    n_per_arm = 200
    false_positives = 0
    for _ in range(n_reps):
        control = rng.normal(loc=0, scale=1, size=n_per_arm)
        treatment = rng.normal(loc=0, scale=1, size=n_per_arm)  # same distribution -- no true effect
        if analyze(control, treatment, alpha=alpha).significant:
            false_positives += 1

    # binomtest gives the CI on the true false-positive rate implied by this
    # sample; assert the nominal alpha falls inside a wide, non-flaky 99.9% CI.
    ci = binomtest(false_positives, n_reps).proportion_ci(confidence_level=0.999)
    assert ci.low <= alpha <= ci.high, (
        f"observed FP rate {false_positives / n_reps:.4f} 99.9% CI [{ci.low:.4f}, {ci.high:.4f}] "
        f"does not contain alpha={alpha}"
    )
