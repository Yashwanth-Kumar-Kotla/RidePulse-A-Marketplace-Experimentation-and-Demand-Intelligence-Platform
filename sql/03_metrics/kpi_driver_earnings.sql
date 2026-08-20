-- KPI 5/6: driver earnings and effective $/mile, $/minute, zone-hour grain.
CREATE OR REPLACE VIEW kpi_driver_earnings_zone_hour AS
SELECT
    pu_location_id,
    pickup_hour,
    platform,
    trip_count,
    total_driver_pay,
    avg_driver_pay,
    avg_fare_per_mile,
    avg_fare_per_minute
FROM mart_zone_hour_demand;
