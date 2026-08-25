-- KPI 11: Surge proxy -- fare vs. baseline fare for comparable trips.
-- "Comparable" = same zone, same hour-of-day, same day-of-week. Baseline =
-- median $/mile across all observed instances of that (zone, hour, dow) in
-- the pilot window (day-of-week/hour-of-day recurs across non-contiguous
-- months the same way it would across contiguous ones, unlike a literal
-- calendar-date lag -- no month-boundary issue here, unlike the forecasting
-- lag features).
-- This is a PROXY: HVFHS doesn't expose Uber's/Lyft's actual surge
-- multiplier, so this infers price elevation from realized fares, which
-- also reflects genuine trip-mix shifts (longer/shorter trips), not only
-- surge pricing. Stated in docs/metrics_definitions.md.
CREATE OR REPLACE TABLE mart_surge_baseline AS
SELECT
    pu_location_id,
    date_part('hour', pickup_hour) AS hour_of_day,
    date_part('dow', pickup_hour) AS day_of_week,
    median(avg_fare_per_mile) AS baseline_fare_per_mile,
    count(*) AS n_weeks_observed
FROM mart_zone_hour_demand
WHERE avg_fare_per_mile IS NOT NULL
GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW kpi_surge_proxy AS
SELECT
    d.pu_location_id,
    d.pickup_hour,
    d.platform,
    d.avg_fare_per_mile,
    b.baseline_fare_per_mile,
    b.n_weeks_observed,
    d.avg_fare_per_mile / nullif(b.baseline_fare_per_mile, 0) AS surge_ratio
FROM mart_zone_hour_demand d
JOIN mart_surge_baseline b
    ON d.pu_location_id = b.pu_location_id
    AND date_part('hour', d.pickup_hour) = b.hour_of_day
    AND date_part('dow', d.pickup_hour) = b.day_of_week
WHERE d.avg_fare_per_mile IS NOT NULL;
