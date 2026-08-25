# Metrics Definitions

Status legend: **Built** (SQL view exists and runs against pilot data),
**Planned** (defined here, not yet implemented).

| # | Metric | Grain | Definition | Rationale | Known limitation | Status | Source |
|---|---|---|---|---|---|---|---|
| 1 | Trip volume | zone-hour, borough-day | Count of completed trips | Baseline demand signal; forecasting target at zone-hour grain | Counts completed trips only, not raw demand (see #3) | Built | `kpi_trip_volume.sql` |
| 2 | Wait time (p50/p90) | zone-hour | `pickup_datetime - request_datetime`, seconds | Direct rider-experience metric of marketplace responsiveness | Excludes ~0.95% of rows where `request_datetime` is unusable (see `data_quality_notes.md`); undersupply that causes a rider to cancel before pickup is invisible here (survivorship) | Built | `kpi_wait_time.sql` |
| 3 | Fulfillment proxy rate | zone-hour | **Not yet defined** — no cancellation/request-level denominator exists in HVFHS data | N/A | This is a genuine open problem, not a filled-in placeholder: candidates are wait-time inflation/dispersion or `on_scene_datetime` gap as an indirect undersupply signal | Planned | — |
| 4 | Driver utilization (engaged time share) | driver-shift or zone-hour | Share of on-duty time spent on a matched trip | Core two-sided marketplace efficiency metric | HVFHS has no explicit "on duty, no trip" timestamp; utilization must be inferred from trip density per driver-base, which is a proxy, not a direct on/off-duty signal | Planned | — |
| 5 | Driver earnings per active hour | zone-hour, driver-base | `driver_pay / (trip_time / 3600)` aggregated | Core driver-side outcome metric | Ignores unpaid idle/repositioning time between trips (ties to #4's limitation) | Built (per-trip avg only; per-active-hour aggregation pending #4) | `kpi_driver_earnings.sql` |
| 6 | Effective $/mile and $/minute | zone-hour | `base_passenger_fare / trip_miles`, `base_passenger_fare / (trip_time/60)` | Pricing/surge proxy at fine grain | Sensitive to short trips (small denominator); needs a minimum-distance/time floor before use in anomaly detection | Built | `kpi_driver_earnings.sql` |
| 7 | Tip rate and tip incidence | zone-hour | `tips / base_passenger_fare` when tipped; share of trips with `tips > 0` | Rider satisfaction / driver income signal | HVFHS often reports `tips = 0` for platforms/periods where in-app tipping wasn't yet default-visible; incidence rate is not comparable across platforms without checking this | Built | `mart_zone_hour_demand` (not yet split into its own KPI view) |
| 8 | Shared-ride share | zone-hour | Share of trips with `shared_request_flag = Y` / `shared_match_flag = Y` | Marketplace pooling efficiency | Request vs. match share diverge (a shared *request* doesn't guarantee a shared *match*) — report both, don't collapse to one number | Built | `mart_zone_hour_demand` |
| 9 | Airport trip share | zone-hour | Share of trips with `airport_fee > 0` | Distinct demand regime (predictable, less elastic) | `airport_fee > 0` is a fare-based proxy for "airport trip," not a direct flag in the schema | Built | `mart_zone_hour_demand` |
| 10 | Supply-demand imbalance index | zone-hour | **Not yet defined** — depends on resolving #3/#4 first | N/A | Same root cause as #3: no true demand denominator | Planned | — |
| 11 | Surge proxy | zone-hour | Fare ($/mile) vs. median $/mile for comparable trips (same zone, hour-of-day, day-of-week, across all observed pilot weeks) | Detects de facto price elevation without an explicit surge multiplier field | HVFHS doesn't expose Uber's/Lyft's actual surge multiplier; this is inferred from realized fares, so it conflates surge with genuine trip-mix shifts (longer/shorter trips). Measured: median ratio is exactly 1.0 by construction, p10-p90 spread is 0.85-1.23 | Built | `kpi_surge_proxy.sql` |
| 12 | Week-over-week deltas + anomaly flags | zone / hour-of-day / day-of-week | Robust z-score: `(this_week_count - median_count) / (1.4826 * MAD)` across all observed weeks for that (zone, hour, dow) | Cheap anomaly surfacing without a full time-series model | 8-14 weeks observed per group in the pilot window (varies by zone) — thin but workable for MAD, which is less sample-hungry than a mean/stddev z-score; a wider data window would still sharpen this. Measured: 3.9% of (zone, hour, dow, week) rows flagged as `|z|>3` anomalies | Built | `kpi_wow_anomaly.sql` |

## Why WAPE, not MAPE (forwarded from Section 7.3, documented here for one place of truth)

MAPE is undefined/explodes when true demand is near zero, which happens
constantly at hourly zone grain for low-volume zones. WAPE
(`sum(|error|) / sum(|actual|)`) aggregates errors and actuals separately
before dividing, so it stays well-behaved when many individual zone-hours
have near-zero trip counts.
