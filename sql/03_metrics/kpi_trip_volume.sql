-- KPI 1: Trip volume, zone-hour and borough-day grains.
CREATE OR REPLACE VIEW kpi_trip_volume_zone_hour AS
SELECT pu_location_id, pickup_hour, platform, trip_count
FROM mart_zone_hour_demand;

CREATE OR REPLACE VIEW kpi_trip_volume_borough_day AS
SELECT
    z.borough,
    date_trunc('day', d.pickup_hour) AS trip_date,
    sum(d.trip_count) AS trip_count
FROM mart_zone_hour_demand d
JOIN stg_zones z ON d.pu_location_id = z.location_id
GROUP BY 1, 2;
