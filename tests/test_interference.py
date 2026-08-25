from ridepulse.experiments.interference import run_interference_study

PARAMS = {"arrival_rate": 89.7, "n_drivers": 12, "mean_trip_minutes": 16.55, "mean_patience_minutes": 5}


def test_true_effect_is_negative_and_meaningfully_nonzero():
    # treatment_speedup < 1 makes treated trips faster -> drivers free up sooner
    # -> the all-treatment world should show LOWER wait than the all-control world.
    result = run_interference_study(**PARAMS, treatment_speedup=0.7, n_reps=50)
    assert result.true_effect_min < -0.1  # negative and not just noise-sized


def test_naive_estimate_is_biased_toward_zero_relative_to_true_effect():
    # the whole point of the study: naive should understate the magnitude of
    # the true effect because control riders indirectly benefit from
    # capacity freed up by treatment-matched trips finishing faster.
    result = run_interference_study(**PARAMS, treatment_speedup=0.7, n_reps=50)
    assert abs(result.naive_estimate_min) < abs(result.true_effect_min)


def test_switchback_estimate_is_closer_to_true_effect_than_naive():
    result = run_interference_study(**PARAMS, treatment_speedup=0.7, n_reps=50)
    assert abs(result.switchback_bias_pct) < abs(result.naive_bias_pct)


def test_no_treatment_effect_means_all_estimates_are_near_zero():
    # sanity check at the other extreme: speedup=1.0 means no real effect at
    # all, so true/naive/switchback should all land near zero, not just
    # switchback "winning" by coincidence of a specific effect size.
    result = run_interference_study(**PARAMS, treatment_speedup=1.0, n_reps=50)
    assert abs(result.true_effect_min) < 0.5
    assert abs(result.naive_estimate_min) < 0.5
    assert abs(result.switchback_estimate_min) < 0.5


def test_same_seed_range_is_deterministic():
    a = run_interference_study(**PARAMS, treatment_speedup=0.7, n_reps=30)
    b = run_interference_study(**PARAMS, treatment_speedup=0.7, n_reps=30)
    assert a == b
