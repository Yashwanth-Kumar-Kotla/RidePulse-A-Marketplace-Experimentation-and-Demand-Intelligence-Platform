-- Grain: one row per (pickup zone, pickup hour). This is the primary
-- forecasting target table (trips per zone-hour) and the base for most
-- marketplace KPIs.
CREATE OR REPLACE TABLE mart_zone_hour_demand AS
SELECT
    pu_location_id,
    date_trunc('hour', pickup_datetime) AS pickup_hour,
    platform,
    count(*) AS trip_count,
    approx_quantile(wait_time_seconds, 0.5) FILTER (WHERE request_ts_valid) AS wait_p50_seconds,
    approx_quantile(wait_time_seconds, 0.9) FILTER (WHERE request_ts_valid) AS wait_p90_seconds,
    count(*) FILTER (WHERE request_ts_valid) AS wait_time_sample_size,
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
GROUP BY 1, 2, 3;
