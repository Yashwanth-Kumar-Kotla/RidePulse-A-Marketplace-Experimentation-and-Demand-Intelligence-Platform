"""Generate the decision-layer comparison chart: optimizer vs. greedy vs.
uniform, total unfulfilled-demand reduction at a fixed budget."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ridepulse.optimization.allocator import (
    greedy_by_demand_allocation,
    optimize_allocation,
    uniform_allocation,
)
from ridepulse.optimization.uplift import ZoneParams, build_uplift_curve

ZONES = [
    ZoneParams(zone=79, label="Manhattan-high", borough="Manhattan", n_drivers=85, mean_patience_minutes=10,
               arrival_rate=362.3, mean_trip_minutes=18.1, real_trip_count=269982),
    ZoneParams(zone=106, label="Brooklyn-medium", borough="Brooklyn", n_drivers=12, mean_patience_minutes=5,
               arrival_rate=89.7, mean_trip_minutes=16.55, real_trip_count=38928),
    ZoneParams(zone=251, label="StatenIsland-low", borough="Staten Island", n_drivers=3, mean_patience_minutes=7,
               arrival_rate=23.67, mean_trip_minutes=10.92, real_trip_count=14586),
]
SPEND_LEVELS = [0, 100, 200, 300, 400]
BUDGET = 700


def main() -> None:
    curves = {z.zone: build_uplift_curve(z, SPEND_LEVELS, n_reps=200) for z in ZONES}
    zone_by = {z.zone: z for z in ZONES}
    zones_by_demand = sorted(zone_by, key=lambda z: -zone_by[z].real_trip_count)

    opt = optimize_allocation(curves, BUDGET)
    greedy = greedy_by_demand_allocation(curves, BUDGET, zones_by_demand)
    uniform = uniform_allocation(curves, BUDGET)

    labels = ["Optimizer\n(LP over uplift curves)", "Greedy\n(highest demand first)", "Uniform\n(equal split)"]
    values = [opt.total_unfulfilled_reduction, greedy.total_unfulfilled_reduction, uniform.total_unfulfilled_reduction]
    colors = ["#2a6f97", "#e07a5f", "#81b29a"]

    fig, ax = plt.subplots(figsize=(7, 5))
    bars = ax.bar(labels, values, color=colors)
    ax.set_ylabel("Additional completed trips/hour vs. no spend")
    ax.set_title(f"Incentive budget allocation (${BUDGET}): optimizer vs. baselines")
    y_range = max(values) - min(0, min(values))
    pad = y_range * 0.03
    ax.set_ylim(0, max(values) + y_range * 0.15)
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, val + pad, f"+{val:.1f}", ha="center", va="bottom", fontsize=11)

    vs_greedy = (opt.total_unfulfilled_reduction / greedy.total_unfulfilled_reduction - 1) * 100
    vs_uniform = (opt.total_unfulfilled_reduction / uniform.total_unfulfilled_reduction - 1) * 100
    ax.text(0.5, -0.18, f"Optimizer beats greedy by {vs_greedy:+.1f}%, uniform by {vs_uniform:+.1f}%",
             transform=ax.transAxes, ha="center", fontsize=9, color="#555555")

    fig.tight_layout()
    fig.savefig("docs/decision_layer.png", dpi=130)
    print(f"saved docs/decision_layer.png -- optimizer={opt.total_unfulfilled_reduction:.2f} "
          f"greedy={greedy.total_unfulfilled_reduction:.2f} uniform={uniform.total_unfulfilled_reduction:.2f}")
    print("optimizer spend:", opt.spend_by_zone)
    print("greedy spend:", greedy.spend_by_zone)


if __name__ == "__main__":
    main()
