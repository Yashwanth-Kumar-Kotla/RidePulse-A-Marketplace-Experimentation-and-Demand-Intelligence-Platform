# PRD: RidePulse — Marketplace Experimentation & Demand Intelligence Platform

**Owner:** Yashwanth Kumar Kotla
**Status:** Draft v1.0
**Date:** August 20, 2026
**Target completion:** ~9 to 11 weeks of focused effort (compressible to ~7, see Roadmap)
**Primary audience for the finished artifact:** Uber DS I / product analytics hiring managers and interviewers; secondarily Lyft, DoorDash, Instacart, and other marketplace analytics teams

---

## 1. Problem Statement

Two-sided marketplaces (riders and drivers) constantly face a coordination problem: demand and supply are imbalanced across space and time. Riders in undersupplied zones wait longer or cancel; drivers in oversupplied zones earn less. Platforms respond with forecasts, experiments, and incentive spend, but each of these can silently fail:

- Forecasts can be miscalibrated and quietly worse than a naive baseline.
- A/B tests in a marketplace are biased by interference (treating some riders changes driver availability for control riders).
- Incentive budgets allocated by intuition or greedy heuristics waste money.

RidePulse is an end-to-end analytics system built on real Uber/Lyft trip data (NYC TLC High Volume FHV records) that (1) defines marketplace health metrics in SQL at 200M+ row scale, (2) forecasts zone-hour demand with rigorous backtesting, (3) stress-tests experimentation methods on a calibrated marketplace simulator with known ground truth, and (4) converts forecasts and uplift estimates into budget-constrained incentive decisions.

## 2. Why This Project Exists (Career Context)

This project is purpose-built to close the specific gaps between the current resume and an Uber Data Scientist I (analytics track) candidacy:

| Gap in current resume | How RidePulse closes it |
|---|---|
| Zero experimentation projects | Full experimentation engine: power/MDE, fixed-horizon A/B, CUPED, mSPRT, switchback designs |
| Zero time-series projects | Zone-hour demand forecasting with rolling-origin backtests and calibrated intervals |
| SQL claimed but never demonstrated | DuckDB warehouse with layered SQL models over 200M+ real trips |
| No marketplace / funnel / cohort framing | All metrics and decisions framed around two-sided marketplace balance |
| No prediction-to-decision layer | Uplift + budget knapsack incentive optimizer evaluated on marketplace outcomes |
| No public Tableau artifact despite listing Tableau | Published Tableau Public KPI dashboard |

It intentionally mirrors current (2025 to 2026) Uber engineering direction: uplift + constraint optimization for incentives (Tarot, May 2026), calibration-first forecasting contracts (DeepETT, May 2026), marketplace simulation as an experimentation testbed, and a multi-methodology experimentation platform (A/B/N, sequential, causal, CUPED, switchback-style designs).

## 3. Goals

1. **G1. Metrics layer:** Define and compute 12+ marketplace KPIs in layered SQL over 200M+ NYC HVFHV trips, with documented definitions, tradeoffs, and automated data-quality checks.
2. **G2. Forecasting layer:** Produce zone-hour demand forecasts that measurably beat a seasonal-naive baseline under a 12-fold rolling-origin backtest, with honest probabilistic calibration reporting.
3. **G3. Experimentation layer (centerpiece):** Build a marketplace simulator calibrated to the real data, then use its ground truth to quantify (a) bias of naive rider-randomized A/B tests under interference, (b) bias correction from switchback designs, (c) variance/sample-size savings from CUPED, and (d) false-positive inflation from peeking vs. mSPRT.
4. **G4. Decision layer:** Allocate a fixed weekly incentive budget across zone-hours via integer optimization on top of uplift curves, and beat uniform and greedy baselines on simulated unfulfilled demand at equal spend.
5. **G5. Communication:** Ship a public Tableau dashboard, a Streamlit experiment-readout app, a README written like an experiment doc, and 3 to 4 defensible resume bullets with measured (never fabricated) numbers.

## 4. Non-Goals (Explicitly Out of Scope)

Do NOT build any of the following. Each one is a deliberate exclusion, not an oversight:

- **No deep learning forecasters** (transformers, LSTMs, DeepETA/DeepETT clones). Wrong role (analytics DS I), wrong data scale, and it invites unwinnable comparisons to production systems.
- **No reinforcement learning** for dispatch or pricing. Months of fragile work the JD never asks for.
- **No two-tower recommenders, no LLM/agentic layers.** The resume already covers LLMs via FilingPulse, Aura Duo, and Commander.ai. Adding them here dilutes the analytics signal.
- **No Kafka / streaming ingestion.** The data is monthly batch parquet; streaming would be a buzzword bolt-on.
- **No new FinBERT/finance/XGBoost-churn variants.** Zero marginal resume signal.
- **No dashboard-only scope.** Dashboards are the garnish, not the dish.
- **No fabricated metrics anywhere.** Resume bullets carry bracketed placeholders until measured.
- **No committed raw data in the repo.** Download scripts only.

## 5. Users and Use Cases

- **Primary user:** an interviewer or hiring manager skimming the GitHub README for 3 minutes, then digging for 20. The README must land the three "wow" charts fast (see Section 11).
- **Secondary user:** the candidate (self), using the project as an interview talking-points library for experimentation, causal inference, forecasting, and SQL questions.
- **Tertiary user:** recruiters clicking the Tableau/Streamlit links from the portfolio site.

## 6. Data

| Source | Contents | Role |
|---|---|---|
| NYC TLC High Volume FHV trip records (2023 to 2025, monthly parquet) | Uber (HV0003) and Lyft trips: request/pickup/dropoff timestamps, zones, trip miles/time, base fare, tips, driver pay, shared/airport flags | Primary. ~150 to 250M rows/year. Request-to-pickup delta = real wait time; driver pay = real earnings |
| NOAA GHCN daily weather (NYC stations) | Precipitation, temperature, snow | Exogenous demand features; extreme-event context |
| TLC taxi zone shapefiles | Zone geometries, boroughs | Spatial joins, maps |
| NYC holiday/event calendar | Holidays, major events | Calendar features |
| (Optional) Chicago TNP trips | Same shape, different city | Generalization check; first cut if time is short |

**Constraints:** 512GB local storage total. Use 2023 to 2025 only (< 100GB as parquet). DuckDB chosen deliberately: forces real SQL, runs on the M5 MacBook, costs $0, and the SQL layer ports conceptually to Presto/Hive (state this in README).

**Excluded data:** stale Kaggle "Uber" datasets (tiny, tutorial-coded).

## 7. System Requirements by Layer

### 7.1 Ingestion & Warehouse
- Python scripts pull monthly TLC parquet + NOAA data; schema validation on load (column types, null thresholds, timestamp sanity, duplicate detection).
- DuckDB database with layered SQL: `01_staging` (raw typed), `02_marts` (cleaned trips, zone_hour_demand, cohort tables), `03_metrics` (KPI views).
- Data-quality audit notebook: missingness, outliers (negative durations, impossible speeds), definitional decisions documented (e.g., what counts as a "fulfilled" request given no explicit cancellation records; state the proxy and its limits).

### 7.2 Metrics Layer (G1)
Minimum KPI set (each with a written definition, rationale, and known tradeoff):
1. Trip volume (zone-hour, borough-day)
2. p50 / p90 request-to-pickup wait time
3. Fulfillment proxy rate (define carefully; document limitation)
4. Driver utilization (engaged time share)
5. Driver earnings per active hour
6. Effective $/mile and $/minute
7. Tip rate and tip incidence
8. Shared-ride share
9. Airport trip share
10. Supply-demand imbalance index per zone-hour
11. Surge proxy (fare vs. baseline fare for comparable trips)
12. Week-over-week metric deltas with anomaly flags (simple robust z-score)

Deliverables: SQL views + a metrics definitions table in `docs/` + Tableau Public dashboard.

### 7.3 Forecasting Layer (G2)
- Target: trips per (zone, hour). Cold/near-zero zones handled explicitly (zone pooling or hierarchical fallback).
- Models, in order: (1) seasonal-naive (same hour last week) as the mandatory baseline; (2) SARIMAX / Holt-Winters on top zone families plus pooled linear regression with Fourier seasonality; (3) one pooled LightGBM with lag, calendar, and weather features, quantile objectives (p10/p50/p90).
- Backtesting harness: 12-fold rolling-origin, CLI-invocable (`python -m ridepulse.backtest --folds 12`). Metrics: WAPE (not MAPE; document why), pinball loss, 80% interval coverage, calibration plots.
- Rule: any model that fails to beat seasonal-naive is reported as such. No silent deletion of losing models.
- MLflow tracks every backtest run.

### 7.4 Simulator (foundation for G3, G4)
- Discrete-event marketplace: riders arrive per calibrated zone-hour demand; drivers have shifts, acceptance behavior, and simple repositioning; a matcher pairs requests to nearest available drivers; wait times, cancellations (patience threshold), utilization, and earnings emerge.
- **Calibration requirement (credibility gate):** simulated wait-time and utilization distributions must be validated against the real data on held-out weeks, with overlay plots in the README. Calibrate on some quantities, hold out others, and say which.
- Honest framing in all docs: the simulator validates METHODS (does CUPED reduce variance, does switchback remove bias), not the world.

### 7.5 Experimentation Engine (G3)
1. Power / MDE calculator used before every simulated experiment.
2. Fixed-horizon A/B/N: t-tests, confidence intervals, sample ratio mismatch check.
3. CUPED with pre-period covariates; report measured variance reduction % and implied sample-size savings.
4. mSPRT sequential testing; empirical peeking study showing naive daily peeking inflates false positives (target: demonstrate inflation to roughly 20 to 30% vs. controlled alpha under mSPRT).
5. Interference study (the flagship result): run the same driver-incentive intervention as (a) naive rider-randomized A/B and (b) switchback (time-block randomization). Because ground truth is known, quantify bias of each estimator. One chart: true effect vs. naive estimate vs. switchback estimate.
6. Correctness tests in CI: e.g., under a null simulation, the A/B pipeline's false-positive rate ≈ alpha.

### 7.6 Causal Add-on (observational)
- Difference-in-differences on a real natural experiment in the NYC data (candidate: 2019 congestion surcharge or a documented fare-rule change; confirm feasibility with 2023 to 2025 window or extend data for this analysis only).
- Parallel-trends diagnostics required; if they fail, report the failure and the caveat. This section may be cut if the timeline slips (see Roadmap priorities).

### 7.7 Decision Layer (G4)
- Simulated heterogeneous driver response to incentive levels; fit uplift models (T-learner and/or uplift trees, reusing existing uplift/calibration experience).
- Allocate fixed weekly budget (e.g., $50K simulated) across zone-hours via knapsack/LP (OR-Tools CP-SAT or PuLP).
- Evaluate in the simulator against (a) uniform spend and (b) greedy highest-demand-first. Report marketplace outcomes: unfulfilled demand reduction, p90 wait change, spend per incremental completed trip. Include a fairness note (borough-level distribution of spend vs. pure efficiency).

### 7.8 Productionization (deliberately light)
- FastAPI endpoint serving zone-hour forecasts and experiment readouts; Docker.
- GitHub Actions: unit tests, data-quality checks, statistical correctness tests.
- Streamlit experiment-readout page.
- Tableau Public dashboard (KPIs).
- MLflow for forecast experiments.
- Explicitly NOT building: model registry, streaming, k8s, feature store.

## 8. Architecture Overview

```text
NYC TLC HVFHV parquet     NOAA weather     Taxi zone shapefiles
        │                     │                    │
        └──── ingestion (Python, schema validation) ┘
                        │
              DuckDB warehouse (200M+ rows)
                        │
      Layered SQL (staging → marts → metrics views)
                        │
   ┌────────────────────┼─────────────────────────┐
Forecasting          Simulator               Metrics/Dashboards
(rolling-origin      (calibrated riders/     (Tableau Public,
backtests,           drivers/matching)       Plotly + anomaly flags)
quantile preds)          │
   │                     │
   └── Experimentation engine (A/B, CUPED, mSPRT, switchback;
       bias measured against simulator ground truth)
                        │
       Incentive optimizer (uplift + budget knapsack/LP)
                        │
       FastAPI + Docker + CI (stats tests) + Streamlit readouts
```

## 9. Repository Structure

```text
ridepulse/
├── README.md
├── data/                 # download scripts only, no raw data committed
├── sql/                  # 01_staging/ 02_marts/ 03_metrics/
├── ridepulse/
│   ├── ingestion/        # TLC + NOAA pulls, schema validation
│   ├── forecasting/      # models.py, backtest.py, calibration.py
│   ├── simulation/       # marketplace.py, calibration.py, agents.py
│   ├── experiments/      # assignment.py, cuped.py, msprt.py, switchback.py
│   ├── optimization/     # uplift.py, allocator.py
│   └── evaluation/       # metrics.py, plots.py
├── notebooks/            # 01_data_audit … 06_incentive_policy (numbered narrative)
├── api/                  # FastAPI app
├── dashboard/            # Streamlit readouts + Tableau workbook link
├── tests/                # unit + statistical correctness tests
├── configs/
├── docker/
└── docs/                 # metrics definitions, experiment docs, limitations
```

## 10. Success Metrics (How We Know It Worked)

### 10.1 Technical acceptance criteria
| Layer | Criterion |
|---|---|
| Warehouse | 200M+ rows loaded; all quality checks pass in CI; 12+ KPI views documented |
| Forecasting | LightGBM beats seasonal-naive WAPE on the 12-fold backtest (target: meaningful, honestly reported improvement; if it doesn't, report why); 80% intervals achieve near-80% empirical coverage |
| Simulator | Held-out simulated wait-time and utilization distributions visually and statistically close to real data; calibration overlays published |
| Experimentation | Null-simulation false-positive rate ≈ alpha (CI-tested); CUPED variance reduction measured and reported; peeking inflation demonstrated; naive-A/B bias under interference quantified with switchback recovering the truth within stated tolerance |
| Decision layer | Optimizer beats uniform and greedy baselines on unfulfilled demand at equal budget, with results reported per baseline |
| Reproducibility | Fresh clone → `make setup && make backtest` (or documented equivalent) runs end to end |

### 10.2 Portfolio / career success criteria
- 3 to 4 resume bullets with all placeholder numbers replaced by measured results.
- README lands the three "wow" charts in the first screen-and-a-half: (1) interference bias chart, (2) CUPED sample-size savings, (3) optimizer vs. greedy at equal spend.
- Public Tableau dashboard live and linked; Streamlit readout deployed.
- Project occupies the #1 "Best Work" slot on the portfolio; FilingPulse #2; Layoff Radar moves off the resume to the portfolio site.
- Candidate can answer, unassisted, all 25 interview questions in the interview-prep doc (15 technical + 10 deep dives), including the honest answers ("the simulator tests methods, not the world"; "here is why seasonal-naive is hard to beat").

### 10.3 Anti-success (fail conditions)
- Any fabricated or unverifiable number on the resume.
- A simulator with no calibration evidence.
- Forecast results reported without the naive baseline comparison.
- Buzzword additions (streaming, DL, RL, LLMs) that violate Section 4.

## 11. The Three "Wow" Components (Protect These)

1. **Interference bias chart:** true effect vs. naive rider-randomized A/B estimate vs. switchback estimate, with bias percentages. This is the single highest-value artifact in the project. If scope must be cut, cut around this, never through it.
2. **CUPED savings:** "my CUPED implementation cut required sample size by X%," with the variance-reduction math shown.
3. **Prediction-to-decision:** "my incentive optimizer beat greedy allocation by X% on unfulfilled demand at equal budget."

## 12. Roadmap and Milestones

Capacity reality: RSNA Kaggle deadline mid-October, coursework through December, active applications. Sequence phases; do not run them parallel to the competition, or Phase 3 dies half-finished.

| Phase | Duration | Deliverables | Definition of done |
|---|---|---|---|
| 1. MVP | 2 weeks | Ingestion, DuckDB warehouse, SQL metrics layer, data-quality audit, Tableau dashboard, seasonal-naive baseline | Dashboard public; metrics documented; already resume-mentionable |
| 2. Forecasting rigor | 2 to 3 weeks | SARIMAX + quantile LightGBM, rolling-origin backtest harness, calibration analysis, MLflow | Backtest CLI reproducible; WAPE + coverage reported vs. baseline |
| 3. Experimentation + simulator | 3 to 4 weeks | Calibrated simulator, power/MDE tools, CUPED, mSPRT + peeking study, interference/switchback study | The three core experiment results measured; calibration overlays published |
| 4. Decision layer + productionization | 1.5 weeks | Uplift curves, OR-Tools allocator, policy evaluation, FastAPI, Docker, CI stats tests | Optimizer beats both baselines or the honest result is documented |
| 5. Write-up | 1 week | README as experiment doc, blog-style post, portfolio update, resume bullets with real numbers | All Section 10.2 criteria met |

**Cut order if time collapses:** Chicago generalization → DiD analysis → mSPRT (keep the peeking demo simple) → SARIMAX (keep naive + LightGBM). Never cut: SQL metrics layer, backtest harness, simulator calibration, interference study.

## 13. Risks and Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Simulator becomes an unvalidated toy | Medium | Calibration gate in Section 7.4 is a hard requirement before any experiment results are reported |
| Scope creep toward ML-engineering shininess | High (pattern: three prior projects share XGBoost/FinBERT/FastAPI DNA; multiple past competitions abandoned) | Section 4 non-goals are binding; review this PRD before adding anything |
| LightGBM fails to beat seasonal-naive | Medium | Acceptable outcome if honestly reported; the story becomes "why naive baselines are strong," which itself interviews well |
| Timeline collision with RSNA / coursework / applications | High | Sequencing rule + cut order in Section 12 |
| Fulfillment metric is only a proxy (no cancellation records) | Certain | Document the proxy definition and its limits in metrics docs and README limitations |
| Interference bias result doesn't transfer to real marketplaces | Certain (it's a simulation) | Frame everywhere as method validation with known ground truth, not a claim about production Uber |
| Storage limits (512GB machine) | Low | 2023 to 2025 window only; parquet + DuckDB; no raw data in git |

## 14. Companion Fixes Outside This Project

- **Upskill churn bullet:** 7,043 telecom rows is recognizably the IBM Telco Kaggle dataset. Either build a defensible derivation for the "$1M+ revenue protection" claim (customers saved × ARPU × margin, assumptions stated) or soften the claim before Uber-track interviews.
- **Interview prep is a separate workstream:** SQL screens and stats fundamentals (probability, CIs, experiment design under pressure) get the offer; the project gets the conversation. Budget prep time independently of build time.
- **Application note:** the specific Uber DS I posting has PERM-style language (fixed "Rate of Pay," "Employer will accept," rigid skill list, "May telecommute") and may be tied to an existing employee's immigration filing. Apply, but treat this build as preparation for the whole marketplace-analytics pipeline (Uber, Lyft, DoorDash, Instacart), not one req.

## 15. Final Output Checklist

- [ ] DuckDB warehouse, 200M+ rows, CI quality checks green
- [ ] 12+ documented KPIs + metrics definitions doc
- [ ] Tableau Public dashboard live
- [ ] 12-fold rolling-origin backtest results (WAPE, pinball, coverage) vs. seasonal-naive
- [ ] Simulator calibration overlays (held-out validation)
- [ ] Interference bias chart (naive A/B vs. switchback vs. truth)
- [ ] CUPED variance-reduction result
- [ ] Peeking / mSPRT false-positive study
- [ ] Incentive optimizer vs. uniform and greedy baselines
- [ ] FastAPI + Docker + Streamlit readout deployed
- [ ] README ordered: Problem → Why → Architecture → Data audit → Metrics → Forecasting → Simulator calibration → Experiments → Optimization → Limitations → Future work
- [ ] Resume bullets updated with measured numbers only
- [ ] 25 interview questions answerable cold
