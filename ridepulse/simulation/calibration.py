"""Calibrate the simulator engine against real wait-time data.

What's calibrated and what isn't (PRD Section 7.4 explicitly allows this --
"calibrate on some quantities, hold out others, and say which"):
- CALIBRATED: wait-time distribution (p50/p90). Real ground truth exists
  (mart_wait_time_percentiles / raw wait_time_seconds in stg_trips).
- NOT independently validated: utilization. HVFHS has no driver on/off-duty
  timestamps, so there is no ground truth to compare against -- reported as
  a simulator output, not a calibrated-and-confirmed number. (This mirrors
  metrics_definitions.md KPI #4, already marked "Planned, no ground truth.")

Arrival rate = real completed trip_count/hour. This inherits the same
fulfillment-proxy limitation documented in data_quality_notes.md: completed
trips likely understate true demand in supply-constrained zone-hours, since
cancelled/unmatched requests aren't observed in HVFHS data. Stated once
here, not re-litigated per zone.

Methodology: fit (n_drivers, mean_patience_minutes) on one set of weeks by
grid search against real wait p50/p90, then VALIDATE OUT-OF-SAMPLE on a
held-out week not used for fitting -- using that week's own real arrival
rate (demand genuinely varies week to week) but the SAME fitted supply/
patience parameters (those are meant to be structural, not re-fit per week).
A fit that isn't checked out-of-sample is a curve-fit, not a calibration.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd

from ridepulse.simulation.engine import SimParams, run_simulation

WARMUP_HOURS = 1  # discard matches in this initial window, standard DES practice
MEASURE_HOURS = 1  # then measure wait times over this window
SIM_DURATION_HOURS = WARMUP_HOURS + MEASURE_HOURS
# Two earlier versions of this were tried and rejected on real evidence, not just intuition:
# (1) many continuous hours at a constant rate -- models an unstable queue that builds up
#     without bound whenever demand is even slightly above capacity (an M/M/c queue at rho>=1
#     never reaches steady state). Verified directly: pinned simulated utilization at ~1.0 and
#     inflated wait far above real values at every driver count tried, because the queue never
#     got to reset.
# (2) a single 1-hour run starting from a fully idle driver pool every time -- the opposite
#     problem. Verified directly: pooled median wait came out near 0 (many riders at the start
#     of the hour get matched instantly because every driver starts idle), which understates
#     real median wait, since a real 6pm rush hour is not preceded by an empty road network --
#     some drivers are already mid-trip from 5pm's demand.
# Fix: warm up for WARMUP_HOURS at the same arrival rate (drivers reach a realistic occupancy
# level), THEN measure only matches that occur in the following MEASURE_HOURS -- standard
# discard-the-initial-transient DES practice, not a new invented technique.


@dataclass
class RealSample:
    zone: int
    label: str
    n_observations: int
    arrival_rate_per_hour: float
    avg_trip_minutes: float
    wait_p50_min: float
    wait_p90_min: float


def real_hour_sample(
    con: duckdb.DuckDBPyConnection, zone: int, hour_of_day: int, dates: list[str], label: str
) -> RealSample:
    date_list = ", ".join(f"'{d}'" for d in dates)
    waits = con.execute(
        f"""
        SELECT wait_time_seconds, trip_time
        FROM stg_trips
        WHERE pu_location_id = {zone}
          AND date_part('hour', pickup_datetime) = {hour_of_day}
          AND date_trunc('day', pickup_datetime) IN ({date_list})
          AND request_ts_valid
        """
    ).fetchdf()
    n_arrivals = con.execute(
        f"""
        SELECT count(*) FROM stg_trips
        WHERE pu_location_id = {zone}
          AND date_part('hour', pickup_datetime) = {hour_of_day}
          AND date_trunc('day', pickup_datetime) IN ({date_list})
        """
    ).fetchone()[0]

    return RealSample(
        zone=zone,
        label=label,
        n_observations=len(waits),
        arrival_rate_per_hour=n_arrivals / len(dates),
        avg_trip_minutes=waits["trip_time"].mean() / 60.0,
        wait_p50_min=waits["wait_time_seconds"].median() / 60.0,
        wait_p90_min=np.percentile(waits["wait_time_seconds"], 90) / 60.0,
    )


def simulate_avg(
    arrival_rate: float, n_drivers: int, mean_trip_minutes: float, mean_patience_minutes: float, n_reps: int
) -> dict:
    pooled_waits: list[float] = []
    utils = []
    for seed in range(n_reps):
        result = run_simulation(
            SimParams(
                arrival_rate_per_hour=arrival_rate,
                n_drivers=n_drivers,
                duration_hours=SIM_DURATION_HOURS,
                mean_trip_minutes=mean_trip_minutes,
                mean_patience_minutes=mean_patience_minutes,
                seed=seed,
            )
        )
        measured = [
            w for w, m in zip(result.wait_times_min, result.match_times_min) if m >= WARMUP_HOURS * 60
        ]
        pooled_waits.extend(measured)
        utils.append(result.utilization)
    return {
        "wait_p50_min": float(np.median(pooled_waits)) if pooled_waits else float("nan"),
        "wait_p90_min": float(np.percentile(pooled_waits, 90)) if pooled_waits else float("nan"),
        "utilization": float(np.mean(utils)),
    }


def grid_search(
    fit_sample: RealSample, n_drivers_grid: list[int], patience_grid: list[float], search_reps: int = 25
) -> dict:
    best = None
    for n_drivers in n_drivers_grid:
        for patience in patience_grid:
            sim = simulate_avg(
                fit_sample.arrival_rate_per_hour, n_drivers, fit_sample.avg_trip_minutes, patience, search_reps
            )
            err = (sim["wait_p50_min"] - fit_sample.wait_p50_min) ** 2 + (
                sim["wait_p90_min"] - fit_sample.wait_p90_min
            ) ** 2
            if best is None or err < best["err"]:
                best = {"n_drivers": n_drivers, "mean_patience_minutes": patience, "err": err, **sim}
    return best


def calibrate_zone(
    con: duckdb.DuckDBPyConnection,
    zone: int,
    hour_of_day: int,
    fit_dates: list[str],
    holdout_dates: list[str],
    n_drivers_grid: list[int],
    patience_grid: list[float],
) -> dict:
    fit = real_hour_sample(con, zone, hour_of_day, fit_dates, "fit")
    holdout = real_hour_sample(con, zone, hour_of_day, holdout_dates, "holdout")

    best = grid_search(fit, n_drivers_grid, patience_grid)
    validation_sim = simulate_avg(
        holdout.arrival_rate_per_hour,
        best["n_drivers"],
        holdout.avg_trip_minutes,
        best["mean_patience_minutes"],
        n_reps=30,
    )

    return {
        "zone": zone,
        "fit": fit,
        "holdout": holdout,
        "fitted_params": {"n_drivers": best["n_drivers"], "mean_patience_minutes": best["mean_patience_minutes"]},
        "fit_sim_result": {k: best[k] for k in ("wait_p50_min", "wait_p90_min", "utilization")},
        "validation_sim_result": validation_sim,
    }


def summary_table(calibration_results: list[dict]) -> pd.DataFrame:
    rows = []
    for r in calibration_results:
        rows.append(
            {
                "zone": r["zone"],
                "n_drivers": r["fitted_params"]["n_drivers"],
                "mean_patience_min": r["fitted_params"]["mean_patience_minutes"],
                "real_holdout_p50_min": round(r["holdout"].wait_p50_min, 2),
                "sim_holdout_p50_min": round(r["validation_sim_result"]["wait_p50_min"], 2),
                "real_holdout_p90_min": round(r["holdout"].wait_p90_min, 2),
                "sim_holdout_p90_min": round(r["validation_sim_result"]["wait_p90_min"], 2),
                "sim_utilization_unvalidated": round(r["validation_sim_result"]["utilization"], 2),
            }
        )
    return pd.DataFrame(rows)
