import numpy as np

from ridepulse.experiments.msprt import (
    always_valid_p_value,
    mixture_sprt_lambda,
    run_peeking_study,
)


def test_lambda_is_below_one_with_no_evidence():
    # mean=0 (no observed effect) should never look like evidence for H1.
    lam = mixture_sprt_lambda(cumulative_mean=np.array([0.0]), n=np.array([100.0]), variance=1.0, tau=0.3)
    assert lam[0] < 1.0


def test_lambda_grows_with_a_larger_observed_effect():
    lam_small = mixture_sprt_lambda(np.array([0.05]), np.array([100.0]), 1.0, 0.3)
    lam_large = mixture_sprt_lambda(np.array([0.5]), np.array([100.0]), 1.0, 0.3)
    assert lam_large[0] > lam_small[0]


def test_always_valid_p_value_bounded_in_unit_interval():
    lam = mixture_sprt_lambda(np.array([0.0, 0.1, 1.0]), np.array([50.0, 50.0, 50.0]), 1.0, 0.3)
    p = always_valid_p_value(lam)
    assert np.all((p >= 0) & (p <= 1))


def test_naive_peeking_inflates_false_positives_well_above_alpha():
    result = run_peeking_study(n_days=30, daily_n=50, alpha=0.05, n_reps=500, seed=1)
    assert result.naive_false_positive_rate > 0.10  # well above the nominal 5%


def test_msprt_false_positive_rate_stays_near_or_under_alpha():
    result = run_peeking_study(n_days=30, daily_n=50, alpha=0.05, n_reps=500, seed=1)
    # "always valid" means bounded ABOVE by alpha at any stopping time -- allow
    # some Monte Carlo slack rather than asserting exact equality to 0.05.
    assert result.msprt_false_positive_rate < 0.08


def test_msprt_is_far_less_inflated_than_naive():
    result = run_peeking_study(n_days=30, daily_n=50, alpha=0.05, n_reps=500, seed=1)
    assert result.msprt_false_positive_rate < result.naive_false_positive_rate / 2
