-- Grain: one row per (pickup zone, pickup hour). This is the primary
-- forecasting target table (trips per zone-hour) and the base for most
-- marketplace KPIs. Wait-time percentiles come from mart_wait_time_percentiles
-- (built by the prior file in this layer) rather than an inline
-- approx_quantile -- see that file's header comment for why.
CREATE OR REPLACE TABLE mart_zone_hour_demand AS
WITH cheap_aggregates AS (
    -- All streaming aggregates (count/sum/avg) -- deliberately excludes the
    -- wait-time percentiles, which come from a join below instead of an
    -- inline holistic aggregate. Grouping here first, before the join, keeps
    -- the join itself cheap (~1.1M rows on each side instead of joining the
    -- full 59M-row stg_trips against the percentile table pre-aggregation).
    SELECT
        pu_location_id,
        date_trunc('hour', pickup_datetime) AS pickup_hour,
        platform,
        count(*) AS trip_count,
        avg(trip_miles) AS avg_trip_miles,
        avg(trip_time) AS avg_trip_time_seconds,
        sum(driver_pay) AS total_driver_pay,
        avg(driver_pay) AS avg_driver_pay,
        sum(base_passenger_fare) AS total_base_fare,
        avg(base_passenger_fare) AS avg_base_fare,
        avg(base_passenger_fare / nullif(trip_miles, 0)) AS avg_fare_per_mile,
        avg(base_passenger_fare / nullif(trip_time / 60.0, 0)) AS avg_fare_per_minute,
        sum(tips) AS total_tips,
        avg(CASE WHEN tips > 0 THEN 1.0 ELSE 0.0 END) AS tip_incidence_rate,
        avg(tips / nullif(base_passenger_fare, 0)) FILTER (WHERE tips > 0) AS avg_tip_rate_when_tipped,
        avg(CASE WHEN shared_request THEN 1.0 ELSE 0.0 END) AS shared_request_share,
        avg(CASE WHEN shared_match THEN 1.0 ELSE 0.0 END) AS shared_match_share,
        avg(CASE WHEN airport_fee > 0 THEN 1.0 ELSE 0.0 END) AS airport_trip_share
    FROM stg_trips
    GROUP BY 1, 2, 3
)
SELECT
    a.*,
    w.wait_p50_seconds,
    w.wait_p90_seconds,
    w.wait_time_sample_size
FROM cheap_aggregates a
LEFT JOIN mart_wait_time_percentiles w
    ON a.pu_location_id = w.pu_location_id
    AND a.pickup_hour = w.pickup_hour
    AND a.platform = w.platform;
