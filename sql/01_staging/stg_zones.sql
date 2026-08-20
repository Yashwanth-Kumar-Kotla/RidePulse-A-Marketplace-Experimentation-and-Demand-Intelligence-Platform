CREATE OR REPLACE TABLE stg_zones AS
SELECT
    "LocationID"::INTEGER AS location_id,
    "Borough" AS borough,
    "Zone" AS zone,
    service_zone
FROM read_csv('data/raw/zones/taxi_zone_lookup.csv', header = true);
