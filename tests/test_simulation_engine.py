from ridepulse.simulation.engine import SimParams, run_simulation


def test_no_drivers_means_everyone_cancels():
    result = run_simulation(SimParams(arrival_rate_per_hour=20, n_drivers=0, duration_hours=10, seed=1))
    assert result.completed_trips == 0
    assert result.cancelled_trips > 0
    assert result.fulfillment_rate == 0.0


def test_heavy_oversupply_means_no_cancellations_and_zero_wait():
    result = run_simulation(
        SimParams(arrival_rate_per_hour=5, n_drivers=50, duration_hours=24, mean_trip_minutes=10, seed=1)
    )
    assert result.cancelled_trips == 0
    assert result.fulfillment_rate == 1.0
    assert all(w == 0.0 for w in result.wait_times_min)


def test_undersupply_produces_more_cancellations_than_oversupply():
    params_kwargs = {"arrival_rate_per_hour": 30, "duration_hours": 24, "mean_trip_minutes": 15, "seed": 7}
    scarce = run_simulation(SimParams(n_drivers=3, **params_kwargs))
    plentiful = run_simulation(SimParams(n_drivers=30, **params_kwargs))
    assert scarce.fulfillment_rate < plentiful.fulfillment_rate
    assert scarce.utilization > plentiful.utilization


def test_wait_times_are_never_negative():
    result = run_simulation(SimParams(arrival_rate_per_hour=25, n_drivers=8, duration_hours=48, seed=3))
    assert all(w >= 0 for w in result.wait_times_min)


def test_same_seed_is_deterministic():
    params = SimParams(arrival_rate_per_hour=15, n_drivers=6, duration_hours=24, seed=42)
    a = run_simulation(params)
    b = run_simulation(params)
    assert a.completed_trips == b.completed_trips
    assert a.cancelled_trips == b.cancelled_trips
    assert a.wait_times_min == b.wait_times_min


def test_completed_plus_cancelled_accounts_for_every_arrival():
    result = run_simulation(SimParams(arrival_rate_per_hour=40, n_drivers=6, duration_hours=24, seed=9))
    assert result.completed_trips + result.cancelled_trips == result.total_arrivals
    assert result.completed_trips > 0
    assert result.cancelled_trips > 0
