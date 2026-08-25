"""RidePulse experiment readout: the real, measured story in one page.

Displays results already computed and documented in docs/*.md -- it does
NOT re-run simulations on page load. That keeps the page fast and keeps a
single source of truth: the numbers here are copied from (and must match)
the docs they link to, not independently recomputed. If a number here ever
drifts from its source doc, the doc is the source of truth to fix it from.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"

st.set_page_config(page_title="RidePulse Experiment Readout", layout="wide")

st.title("RidePulse: Marketplace Experimentation Readout")
st.caption(
    "Real NYC TLC HVFHS data. Warehouse and forecasting run on the full 2023-2025 "
    "window (593M trips); the simulator and the three flagship experiments below "
    "still run on an earlier 3-month pilot subset (Jan/Jun/Sep 2024, ~59M trips) -- "
    "see README.md's Data Window section for why. Every number below is measured, not "
    "assumed -- each section names the docs/*.md file with the full methodology "
    "(open it directly in the repo, this page doesn't serve it)."
)

st.divider()

# ---------------------------------------------------------------------------
# 1. Interference study
# ---------------------------------------------------------------------------
st.header("1. Interference bias: naive A/B testing misses the effect almost entirely")
col1, col2 = st.columns([2, 1])
with col1:
    img_path = DOCS / "interference_bias.png"
    if img_path.exists():
        st.image(str(img_path))
    else:
        st.warning(f"Chart not found at {img_path}")
with col2:
    st.metric("True effect (ground truth)", "-1.52 min")
    st.metric("Naive A/B estimate", "+0.05 min", delta="-103% bias", delta_color="inverse")
    st.metric("Switchback estimate", "-1.56 min", delta="+3% bias", delta_color="normal")
    st.markdown(
        "The naive design gets the *sign* wrong because a driver incentive "
        "leaks through the shared driver pool into the 'control' group. "
        "Switchback avoids that by construction. "
        "Full methodology: `docs/interference_study.md`"
    )

st.divider()

# ---------------------------------------------------------------------------
# 2. CUPED
# ---------------------------------------------------------------------------
st.header("2. CUPED: 26.3% variance reduction, after a covariate that didn't work")
col1, col2 = st.columns([1, 1])
with col1:
    st.metric("First covariate attempt (same-run pre/post wait)", "0.027 correlation", help="Indistinguishable from zero -- documented, not hidden.")
    st.metric("Working covariate (real day-level demand, 20.2% CV)", "0.513 correlation")
with col2:
    st.metric("Variance reduction", "26.3%", help="Measured value equals the theoretical r^2 almost exactly, as it should for an exact OLS identity.")
    st.metric("Implied sample-size savings", "26.3%", help="Same number by direct derivation from power.py's n ~ sigma^2/mde^2, not a separate measurement.")
st.markdown(
    "A sign bug in the first version of this calculation (theoretical formula computed "
    "`1-r^2` instead of `r^2`) was caught specifically because theoretical and measured "
    "didn't match when they should have. Full methodology: `docs/cuped_analysis.md`"
)

st.divider()

# ---------------------------------------------------------------------------
# 3. Decision layer
# ---------------------------------------------------------------------------
st.header("3. Prediction to decision: optimizer vs. greedy and uniform baselines")
col1, col2 = st.columns([2, 1])
with col1:
    img_path = DOCS / "decision_layer.png"
    if img_path.exists():
        st.image(str(img_path))
    else:
        st.warning(f"Chart not found at {img_path}")
with col2:
    st.metric("Optimizer (LP over uplift curves)", "+27.1 trips/hr")
    st.metric("Greedy (highest demand first)", "+25.9 trips/hr", delta="-4.3% vs optimizer", delta_color="inverse")
    st.metric("Uniform (equal split)", "+18.7 trips/hr", delta="-44.8% vs optimizer", delta_color="inverse")
    st.markdown(
        "Margin over greedy varies by budget (ties at some levels, up to +7.6% at others) -- "
        "reported as a range from a 5-budget sweep, not one cherry-picked number. "
        "Verified against brute-force search across 8 budgets: exact match every time. "
        "Full methodology: `docs/decision_layer.md`"
    )

st.divider()

# ---------------------------------------------------------------------------
# 4. Forecasting + simulator calibration (the supporting layers, caveats included)
# ---------------------------------------------------------------------------
st.header("Supporting layers -- and their honest limits")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Forecasting (full 2023-2025 window, 120 folds)")
    st.metric("Seasonal-naive baseline", "18.2% WAPE")
    st.metric("LightGBM", "12.4% WAPE", delta="beats naive on all 120/120 folds", delta_color="off")
    st.caption("An earlier 3-month/12-fold run scored 15.2%/12.3% -- superseded by this full-window result.")

with col2:
    st.subheader("Simulator calibration")
    calib_img = DOCS / "simulator_calibration_overlay.png"
    if calib_img.exists():
        st.image(str(calib_img))
    st.warning(
        "**Partial calibration, not a clean match.** One zone's p50 is nearly exact; "
        "everything else is overestimated by 32-73%, most likely because the simulator's "
        "documented no-cross-zone-repositioning simplification makes it less elastic than "
        "the real marketplace. The three results above rely on *relative* comparisons "
        "within the simulator, not on its absolute wait-time levels being correct. "
        "Full methodology: `docs/simulator_calibration.md`"
    )

st.divider()
st.caption(
    "Every result on this page was checked against real output, not assumed to work "
    "from code review alone -- see docs/metrics_definitions.md for the full KPI catalogue "
    "and each section's linked doc above for that result's detailed methodology."
)
