"""The interference study (PRD Section 11 #1): quantify the bias of a naive
rider-randomized A/B test vs. a switchback (time-block) design, for the
same driver-incentive intervention, against KNOWN simulator ground truth.

Mechanism (see ridepulse/simulation/engine.py SimParams docstring): the
incentive makes a treatment-tagged rider's matched trip finish faster
(treatment_speedup < 1), which returns that driver to the SHARED pool
sooner -- benefiting whichever rider is matched next, regardless of that
next rider's own tag. This is a real interference mechanism (shared-
resource turnover externality), not invented for convenience.

Three estimators, same warm-up/measure pattern as calibration.py (a real
rush hour resets daily, not a continuous overload -- see that module for
why):
- TRUE EFFECT: treatment_prob=1.0 (whole world treated) vs. 0.0 (whole
  world control), run as separate clean simulations. Unbiased by
  construction -- neither run ever mixes tags in the same driver pool.
- NAIVE: ONE shared simulation, treatment_prob=0.5, both tags coexist in
  the same pool. Compares mean wait for treatment-tagged vs. control-tagged
  riders WITHIN that shared, contaminated pool.
- SWITCHBACK: many independent all-or-nothing blocks (reusing the same
  clean single-condition runs as the true-effect calculation, just
  resampled and relabeled as blocks), comparing mean block-level wait
  across treatment blocks vs. control blocks. No within-block contamination
  by construction.

This uses the simulator for a RELATIVE comparison of estimators against
each other and against its own internal ground truth -- not an absolute
real-world wait-time claim, which docs/simulator_calibration.md already
found the simulator isn't precise enough for.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ridepulse.simulation.calibration import WARMUP_HOURS
from ridepulse.simulation.engine import SimParams, run_simulation

MEASURE_HOURS = 1
SIM_DURATION_HOURS = WARMUP_HOURS + MEASURE_HOURS


def _measured_waits(result, treatment_only: bool | None = None) -> list[float]:
    """Waits from matches in the measurement window (after warm-up), optionally
    filtered to only treatment-tagged (True) or only control-tagged (False) riders."""
    out = []
    for wait, match_time, treated in zip(result.wait_times_min, result.match_times_min, result.treatment_flags):
        if match_time < WARMUP_HOURS * 60:
            continue
        if treatment_only is not None and treated != treatment_only:
            continue
        out.append(wait)
    return out


def _run(arrival_rate: float, n_drivers: int, mean_trip_minutes: float, mean_patience_minutes: float,
         treatment_prob: float, treatment_speedup: float, seed: int):
    return run_simulation(
        SimParams(
            arrival_rate_per_hour=arrival_rate,
            n_drivers=n_drivers,
            duration_hours=SIM_DURATION_HOURS,
            mean_trip_minutes=mean_trip_minutes,
            mean_patience_minutes=mean_patience_minutes,
            treatment_prob=treatment_prob,
            treatment_speedup=treatment_speedup,
            seed=seed,
        )
    )


@dataclass
class InterferenceStudyResult:
    true_effect_min: float
    naive_estimate_min: float
    switchback_estimate_min: float
    naive_bias_pct: float
    switchback_bias_pct: float
    n_reps: int


def run_interference_study(
    arrival_rate: float,
    n_drivers: int,
    mean_trip_minutes: float,
    mean_patience_minutes: float,
    treatment_speedup: float,
    n_reps: int = 100,
) -> InterferenceStudyResult:
    control_waits, treatment_waits = [], []
    naive_control_waits, naive_treatment_waits = [], []
    block_means: list[tuple[float, bool]] = []  # (block mean wait, is_treatment_block)

    for seed in range(n_reps):
        # true-effect / switchback source: two clean, single-condition runs per rep
        control_run = _run(arrival_rate, n_drivers, mean_trip_minutes, mean_patience_minutes,
                            treatment_prob=0.0, treatment_speedup=treatment_speedup, seed=seed)
        treatment_run = _run(arrival_rate, n_drivers, mean_trip_minutes, mean_patience_minutes,
                              treatment_prob=1.0, treatment_speedup=treatment_speedup, seed=seed + 1_000_000)
        control_waits.extend(_measured_waits(control_run))
        treatment_waits.extend(_measured_waits(treatment_run))

        c_block = _measured_waits(control_run)
        t_block = _measured_waits(treatment_run)
        if c_block:
            block_means.append((float(np.mean(c_block)), False))
        if t_block:
            block_means.append((float(np.mean(t_block)), True))

        # naive: one shared, contaminated run per rep
        naive_run = _run(arrival_rate, n_drivers, mean_trip_minutes, mean_patience_minutes,
                          treatment_prob=0.5, treatment_speedup=treatment_speedup, seed=seed + 2_000_000)
        naive_control_waits.extend(_measured_waits(naive_run, treatment_only=False))
        naive_treatment_waits.extend(_measured_waits(naive_run, treatment_only=True))

    true_effect = float(np.mean(treatment_waits) - np.mean(control_waits))
    naive_estimate = float(np.mean(naive_treatment_waits) - np.mean(naive_control_waits))

    treatment_blocks = [m for m, is_t in block_means if is_t]
    control_blocks = [m for m, is_t in block_means if not is_t]
    switchback_estimate = float(np.mean(treatment_blocks) - np.mean(control_blocks))

    naive_bias_pct = (naive_estimate - true_effect) / true_effect * 100 if true_effect else float("nan")
    switchback_bias_pct = (switchback_estimate - true_effect) / true_effect * 100 if true_effect else float("nan")

    return InterferenceStudyResult(
        true_effect_min=true_effect,
        naive_estimate_min=naive_estimate,
        switchback_estimate_min=switchback_estimate,
        naive_bias_pct=naive_bias_pct,
        switchback_bias_pct=switchback_bias_pct,
        n_reps=n_reps,
    )
