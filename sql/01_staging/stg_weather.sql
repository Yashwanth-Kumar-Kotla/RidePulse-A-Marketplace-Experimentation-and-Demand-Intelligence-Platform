CREATE OR REPLACE TABLE stg_weather AS
SELECT
    "DATE"::DATE AS weather_date,
    "PRCP"::DOUBLE AS precip_mm,
    "SNOW"::DOUBLE AS snow_mm,
    "SNWD"::DOUBLE AS snow_depth_mm,
    "TAVG"::DOUBLE AS temp_avg_c,
    "TMAX"::DOUBLE AS temp_max_c,
    "TMIN"::DOUBLE AS temp_min_c,
    "AWND"::DOUBLE AS wind_avg_ms
FROM read_csv('data/raw/noaa/nyc_weather_daily.csv', header = true);
