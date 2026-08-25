-- KPI 12: Week-over-week metric deltas with anomaly flags (robust z-score).
-- Grain: (zone, hour-of-day, day-of-week) -- same recurrence logic as the
-- surge proxy, sidesteps the non-contiguous pilot-month issue that affects
-- literal calendar-date lags (see forecasting/baseline.py).
-- Robust z-score = (x - median) / (1.4826 * MAD), the standard normal-
-- consistent scaling of median absolute deviation -- less sensitive to
-- outliers than a mean/stddev z-score, appropriate for trip counts that can
-- spike on holidays/events.
CREATE OR REPLACE TABLE mart_wow_trip_counts AS
SELECT
    pu_location_id,
    date_part('hour', pickup_hour) AS hour_of_day,
    date_part('dow', pickup_hour) AS day_of_week,
    date_trunc('week', pickup_hour) AS week_start,
    sum(trip_count) AS trip_count
FROM mart_zone_hour_demand
GROUP BY 1, 2, 3, 4;

-- Two-stage CTE, not one: a window function's argument can't itself contain
-- another window function (median(...) OVER (...) nested inside another
-- OVER isn't valid SQL) -- median_trip_count has to be materialized in its
-- own step before MAD can reference it.
CREATE OR REPLACE VIEW kpi_wow_anomaly AS
WITH with_median AS (
    SELECT
        pu_location_id,
        hour_of_day,
        day_of_week,
        week_start,
        trip_count,
        median(trip_count) OVER (PARTITION BY pu_location_id, hour_of_day, day_of_week) AS median_trip_count
    FROM mart_wow_trip_counts
),
with_mad AS (
    SELECT
        *,
        median(abs(trip_count - median_trip_count))
            OVER (PARTITION BY pu_location_id, hour_of_day, day_of_week) AS mad,
        count(*) OVER (PARTITION BY pu_location_id, hour_of_day, day_of_week) AS n_weeks_observed
    FROM with_median
)
SELECT
    pu_location_id,
    hour_of_day,
    day_of_week,
    week_start,
    trip_count,
    median_trip_count,
    (trip_count - median_trip_count) / nullif(1.4826 * mad, 0) AS robust_z_score,
    n_weeks_observed,
    abs((trip_count - median_trip_count) / nullif(1.4826 * mad, 0)) > 3 AS is_anomaly
FROM with_mad;
