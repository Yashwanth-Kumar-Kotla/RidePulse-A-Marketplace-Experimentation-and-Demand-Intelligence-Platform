"""Simulation-measured uplift curves: how much does spending $X on a
driver incentive in a given zone-hour reduce unfulfilled demand?

Deliberately NOT a fitted ML uplift model (T-learner etc., as the PRD
mentions as an option) -- measuring the effect directly via the calibrated
simulator is more honest and grounded for this scope: no synthetic-label
fitting step to introduce its own error on top of an already-imperfect
simulator (see docs/simulator_calibration.md).

Spend -> treatment_prob mapping: a fixed cost_per_treated_trip (assumed,
documented, not measured -- there's no real incentive-program cost data in
this dataset) buys the incentive for that fraction of the zone-hour's
expected riders: treatment_prob = min(1, spend / (cost_per_treated_trip *
arrival_rate)). This makes "$ per zone" and "% of riders treated" the same
knob, expressed in a real currency the optimizer can budget against.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ridepulse.simulation.engine import SimParams, run_simulation

WARMUP_MINUTES = 60
MEASURE_MINUTES = 60
COST_PER_TREATED_TRIP = 5.0  # assumed driver bonus per incentivized completed trip, in dollars
TREATMENT_SPEEDUP = 0.7  # same mechanism/magnitude as the interference study


@dataclass
class ZoneParams:
    zone: int
    label: str
    borough: str
    n_drivers: int
    mean_patience_minutes: float
    arrival_rate: float
    mean_trip_minutes: float
    real_trip_count: float  # real Jan trip volume, used only for the "greedy by demand" baseline


@dataclass
class UpliftPoint:
    zone: int
    spend: float
    treatment_prob: float
    fulfillment_rate: float
    unfulfilled_reduction: float  # vs. spend=0 baseline for this zone, in expected completed trips/hour
    p90_wait_min: float


def _measured(result, treatment_only=None):
    out = []
    for w, m, t in zip(result.wait_times_min, result.match_times_min, result.treatment_flags):
        if m < WARMUP_MINUTES:
            continue
        if treatment_only is not None and t != treatment_only:
            continue
        out.append(w)
    return out


def _run_zone(zone: ZoneParams, treatment_prob: float, seed: int):
    return run_simulation(
        SimParams(
            arrival_rate_per_hour=zone.arrival_rate,
            n_drivers=zone.n_drivers,
            duration_hours=(WARMUP_MINUTES + MEASURE_MINUTES) / 60,
            mean_trip_minutes=zone.mean_trip_minutes,
            mean_patience_minutes=zone.mean_patience_minutes,
            treatment_prob=treatment_prob,
            treatment_speedup=TREATMENT_SPEEDUP,
            seed=seed,
        )
    )


def build_uplift_curve(zone: ZoneParams, spend_levels: list[float], n_reps: int = 100) -> list[UpliftPoint]:
    baseline_completed = None
    points = []
    for spend in spend_levels:
        treatment_prob = min(1.0, spend / (COST_PER_TREATED_TRIP * zone.arrival_rate)) if spend > 0 else 0.0
        completed_counts, cancelled_counts, p90s = [], [], []
        for seed in range(n_reps):
            result = _run_zone(zone, treatment_prob, seed)
            measured_waits = _measured(result)
            # count only matches/cancellations in the measurement window
            n_completed_measured = len(measured_waits)
            n_cancelled_total = result.cancelled_trips  # cancellations aren't windowed by match time
            # (they have no match); use the full-run rate as a reasonable per-hour proxy since
            # warm-up and measurement have the same underlying arrival_rate/treatment_prob.
            completed_counts.append(n_completed_measured)
            cancelled_counts.append(n_cancelled_total / 2)  # split evenly across the 2 simulated hours
            if measured_waits:
                p90s.append(np.percentile(measured_waits, 90))

        mean_completed = float(np.mean(completed_counts))
        mean_cancelled = float(np.mean(cancelled_counts))
        fulfillment_rate = mean_completed / (mean_completed + mean_cancelled) if (mean_completed + mean_cancelled) else 0.0

        if baseline_completed is None:
            baseline_completed = mean_completed
        unfulfilled_reduction = mean_completed - baseline_completed

        points.append(
            UpliftPoint(
                zone=zone.zone,
                spend=spend,
                treatment_prob=treatment_prob,
                fulfillment_rate=fulfillment_rate,
                unfulfilled_reduction=unfulfilled_reduction,
                p90_wait_min=float(np.mean(p90s)) if p90s else float("nan"),
            )
        )
    return points
