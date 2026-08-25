"""Generate the interference study's flagship chart: true effect vs. naive
A/B estimate vs. switchback estimate, with bias % annotated."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ridepulse.experiments.interference import run_interference_study

PARAMS = {"arrival_rate": 89.7, "n_drivers": 12, "mean_trip_minutes": 16.55, "mean_patience_minutes": 5}


def main() -> None:
    result = run_interference_study(**PARAMS, treatment_speedup=0.7, n_reps=300)

    labels = ["True effect\n(known ground truth)", "Naive A/B\n(rider-randomized)", "Switchback\n(time-block)"]
    values = [result.true_effect_min, result.naive_estimate_min, result.switchback_estimate_min]
    colors = ["#2a6f97", "#e07a5f", "#81b29a"]

    fig, ax = plt.subplots(figsize=(7.5, 5))
    bars = ax.bar(labels, values, color=colors)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("Estimated effect on wait time (minutes)")
    ax.set_title("Interference bias: naive A/B vs. switchback, same driver-incentive intervention")

    # Give the axes headroom above/below the bars scaled to the actual data
    # range -- fixed offsets (e.g. "+0.35") broke badly here because the
    # naive bar is tiny (~0.05) while the other two are large (~-1.5), so a
    # one-size offset either overflowed the axes or collided with the bar.
    y_range = max(values) - min(values)
    pad = y_range * 0.08
    ax.set_ylim(min(values) - y_range * 0.25, max(values) + y_range * 0.25)

    annotations = [None, f"{result.naive_bias_pct:+.0f}% bias", f"{result.switchback_bias_pct:+.0f}% bias"]
    for bar, val, ann in zip(bars, values, annotations):
        above = val >= 0
        value_y = val + pad if above else val - pad
        ax.text(bar.get_x() + bar.get_width() / 2, value_y, f"{val:.2f} min",
                 ha="center", va="bottom" if above else "top", fontsize=10)
        if ann:
            bias_y = value_y + pad if above else value_y - pad
            ax.text(bar.get_x() + bar.get_width() / 2, bias_y, ann,
                     ha="center", va="bottom" if above else "top", fontsize=9, color="#555555")

    fig.tight_layout()
    fig.savefig("docs/interference_bias.png", dpi=130)
    print(f"saved docs/interference_bias.png -- true={result.true_effect_min:.3f} "
          f"naive={result.naive_estimate_min:.3f} ({result.naive_bias_pct:+.1f}%) "
          f"switchback={result.switchback_estimate_min:.3f} ({result.switchback_bias_pct:+.1f}%)")


if __name__ == "__main__":
    main()
