-- KPI 2: p50/p90 request-to-pickup wait time, zone-hour grain.
-- Excludes rows where request_datetime is unusable (~0.95% of rows;
-- see docs/data_quality_notes.md) via wait_time_sample_size / the
-- upstream FILTER in mart_zone_hour_demand.
CREATE OR REPLACE VIEW kpi_wait_time_zone_hour AS
SELECT
    pu_location_id,
    pickup_hour,
    platform,
    wait_p50_seconds,
    wait_p90_seconds,
    wait_time_sample_size,
    trip_count
FROM mart_zone_hour_demand
WHERE wait_time_sample_size > 0;
