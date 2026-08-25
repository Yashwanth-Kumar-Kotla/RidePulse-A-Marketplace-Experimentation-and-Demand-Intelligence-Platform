"""Generate the calibration overlay plot: real vs. simulated wait-time
percentiles, held-out validation week, both calibration zones."""

from __future__ import annotations

import duckdb
import matplotlib

matplotlib.use("Agg")  # headless, no display available
import matplotlib.pyplot as plt

from ridepulse.simulation.calibration import calibrate_zone

ZONE_LABELS = {79: "Zone 79 (Manhattan, high-volume)", 106: "Zone 106 (Brooklyn/Gowanus, medium-volume)"}


def main() -> None:
    con = duckdb.connect("data/ridepulse.duckdb", read_only=True)
    fit_dates = ["2024-01-03", "2024-01-10", "2024-01-17"]
    holdout_dates = ["2024-01-24"]

    results = [
        calibrate_zone(
            con,
            zone=79,
            hour_of_day=18,
            fit_dates=fit_dates,
            holdout_dates=holdout_dates,
            n_drivers_grid=[75, 80, 85, 90, 95, 100, 105, 110, 120],
            patience_grid=[0.5, 1, 1.5, 2, 3, 5, 7, 10],
        ),
        calibrate_zone(
            con,
            zone=106,
            hour_of_day=18,
            fit_dates=fit_dates,
            holdout_dates=holdout_dates,
            n_drivers_grid=[10, 12, 14, 16, 18, 20, 22, 25],
            patience_grid=[0.5, 1, 1.5, 2, 3, 5, 7, 10],
        ),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    for ax, r in zip(axes, results):
        labels = ["p50", "p90"]
        real = [r["holdout"].wait_p50_min, r["holdout"].wait_p90_min]
        sim = [r["validation_sim_result"]["wait_p50_min"], r["validation_sim_result"]["wait_p90_min"]]
        x = range(len(labels))
        width = 0.35
        ax.bar([i - width / 2 for i in x], real, width, label="Real (held-out week)", color="#2a6f97")
        ax.bar([i + width / 2 for i in x], sim, width, label="Simulated (fitted params)", color="#e07a5f")
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels)
        ax.set_ylabel("Wait time (minutes)")
        ax.set_title(ZONE_LABELS[r["zone"]], fontsize=10)
        ax.legend(fontsize=8)

    fig.suptitle("Simulator calibration: real vs. simulated wait-time percentiles (out-of-sample)")
    fig.tight_layout()
    fig.savefig("docs/simulator_calibration_overlay.png", dpi=130)
    print("saved docs/simulator_calibration_overlay.png")


if __name__ == "__main__":
    main()
