-- Typed staging table over raw HVFHS parquet files.
-- Dedups exact-duplicate rows (see docs/data_quality_notes.md: <0.0003% of rows)
-- and flags -- but does not drop -- rows where request_datetime is unusable
-- for wait-time math (~0.95% of rows; see docs/data_quality_notes.md).
CREATE OR REPLACE TABLE stg_trips AS
SELECT DISTINCT
    hvfhs_license_num,
    CASE hvfhs_license_num
        WHEN 'HV0003' THEN 'Uber'
        WHEN 'HV0005' THEN 'Lyft'
        WHEN 'HV0004' THEN 'Via'
        WHEN 'HV0002' THEN 'Juno'
    END AS platform,
    dispatching_base_num,
    originating_base_num,
    request_datetime,
    on_scene_datetime,
    pickup_datetime,
    dropoff_datetime,
    request_datetime <= pickup_datetime AS request_ts_valid,
    "PULocationID" AS pu_location_id,
    "DOLocationID" AS do_location_id,
    trip_miles,
    trip_time,
    base_passenger_fare,
    tolls,
    bcf,
    sales_tax,
    congestion_surcharge,
    airport_fee,
    tips,
    driver_pay,
    shared_request_flag = 'Y' AS shared_request,
    shared_match_flag = 'Y' AS shared_match,
    wav_request_flag = 'Y' AS wav_request,
    wav_match_flag = 'Y' AS wav_match,
    -- request-to-pickup wait, seconds; NULL when request_ts_valid is false
    CASE WHEN request_datetime <= pickup_datetime
         THEN date_diff('second', request_datetime, pickup_datetime)
    END AS wait_time_seconds
FROM read_parquet('data/raw/tlc/fhvhv_tripdata_*.parquet')
WHERE hvfhs_license_num IN ('HV0003', 'HV0005'); -- Uber + Lyft only, per PRD scope
