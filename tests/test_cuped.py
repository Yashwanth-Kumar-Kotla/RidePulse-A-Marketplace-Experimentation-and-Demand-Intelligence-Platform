import numpy as np

from ridepulse.experiments.cuped import apply_cuped


def test_cuped_matches_a_hand_computed_reduction():
    # Construct Y = 0.8*X + noise with X ~ N(0,1) and noise ~ N(0, 0.36) so
    # Var(Y) = 0.8^2*Var(X) + Var(noise) = 0.64 + 0.36 = 1.0 and the true
    # correlation is Cov(X,Y)/(sigma_X*sigma_Y) = 0.8/(1*1) = 0.8 -- so the
    # expected variance reduction is r^2 = 0.64 (64%), known by construction,
    # not just trusted from the simulator's own noisy output.
    rng = np.random.default_rng(0)
    n = 200_000  # large N so the sample statistics converge tightly to the
    # true 0.8/0.64 values -- this is a correctness check on the linear
    # algebra, not a test of sampling noise.
    x = rng.normal(0, 1, n)
    y = 0.8 * x + rng.normal(0, 0.6, n)

    result = apply_cuped(x, y)
    assert abs(result.correlation - 0.8) < 0.01
    assert abs(result.theoretical_variance_reduction_pct - 64.0) < 1.0
    assert abs(result.measured_variance_reduction_pct - 64.0) < 1.0
    # the exact OLS identity: theoretical and measured must agree closely
    # with each other regardless of the specific data (not just both be
    # near 64 separately) -- this is what actually caught the sign bug.
    assert abs(result.theoretical_variance_reduction_pct - result.measured_variance_reduction_pct) < 1.0


def test_cuped_never_increases_variance_for_correlated_data():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 1, 5000)
    y = 0.5 * x + rng.normal(0, 1, 5000)
    result = apply_cuped(x, y)
    assert result.cuped_variance <= result.raw_variance


def test_zero_correlation_gives_near_zero_reduction():
    rng = np.random.default_rng(2)
    x = rng.normal(0, 1, 50_000)
    y = rng.normal(0, 1, 50_000)  # independent of x by construction
    result = apply_cuped(x, y)
    assert abs(result.correlation) < 0.02
    assert result.measured_variance_reduction_pct < 1.0


def test_implied_sample_size_savings_equals_measured_variance_reduction():
    rng = np.random.default_rng(3)
    x = rng.normal(0, 1, 10_000)
    y = 0.6 * x + rng.normal(0, 1, 10_000)
    result = apply_cuped(x, y)
    assert result.implied_sample_size_savings_pct == result.measured_variance_reduction_pct
