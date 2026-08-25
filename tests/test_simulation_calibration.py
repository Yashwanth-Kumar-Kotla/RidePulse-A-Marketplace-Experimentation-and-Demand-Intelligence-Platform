from ridepulse.simulation.calibration import RealSample, grid_search, simulate_avg


def test_simulate_avg_pools_waits_across_replications():
    single = simulate_avg(arrival_rate=30, n_drivers=10, mean_trip_minutes=15, mean_patience_minutes=5, n_reps=1)
    many = simulate_avg(arrival_rate=30, n_drivers=10, mean_trip_minutes=15, mean_patience_minutes=5, n_reps=20)
    # both should produce a valid (non-nan) percentile once there's at least one match
    assert single["wait_p50_min"] == single["wait_p50_min"]  # not NaN
    assert many["wait_p50_min"] == many["wait_p50_min"]


def test_grid_search_returns_the_actual_minimum_of_the_grid():
    # Correctness of the argmin itself: with a fixed seed range the search is
    # deterministic, so the returned combo's error must be <= every other
    # grid cell's error when re-simulated independently. This deliberately
    # doesn't assume any particular direction (more drivers != always lower
    # wait once warm-up + patience-driven cancellation interact) -- it tests
    # that grid_search finds the best of what it evaluated, not a guess
    # about simulator dynamics.
    fit = RealSample(
        zone=1, label="fit", n_observations=100, arrival_rate_per_hour=30, avg_trip_minutes=10,
        wait_p50_min=2.0, wait_p90_min=5.0,
    )
    n_drivers_grid, patience_grid = [5, 10, 20, 40], [2, 5]
    best = grid_search(fit, n_drivers_grid, patience_grid, search_reps=10)

    for n_drivers in n_drivers_grid:
        for patience in patience_grid:
            sim = simulate_avg(fit.arrival_rate_per_hour, n_drivers, fit.avg_trip_minutes, patience, n_reps=10)
            err = (sim["wait_p50_min"] - fit.wait_p50_min) ** 2 + (sim["wait_p90_min"] - fit.wait_p90_min) ** 2
            assert err >= best["err"] - 1e-9
