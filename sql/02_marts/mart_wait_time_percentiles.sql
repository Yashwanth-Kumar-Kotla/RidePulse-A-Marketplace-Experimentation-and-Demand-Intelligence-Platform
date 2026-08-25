-- p50/p90 request-to-pickup wait time, zone-hour-platform grain.
--
-- NOT computed with approx_quantile(...) GROUP BY zone-hour-platform: verified
-- directly that this OOMs on a 16GB machine even with memory_limit capped at
-- 6GB and temp_directory spilling enabled. Root cause isolated by testing at
-- different group cardinalities: approx_quantile over the full ~1.1M
-- (zone, hour, platform) groups is what blows up (minutes + OOM), while the
-- same aggregate over ~262 zone-only groups finishes in 0.7s -- so the cost
-- is the per-group t-digest sketch overhead multiplied by group count, not
-- the 59M-row scan itself (plain count/sum/avg over the same 1.1M groups
-- takes 1.3s). See docs/overnight_log.md for the isolation steps.
--
-- Fix: a manual bucketed-histogram percentile, built entirely from cheap
-- streaming aggregates (count, min/max with FILTER) instead of a per-group
-- sketch. 15-second buckets, capped at 3600s (1 hour) -- longer waits are
-- rare and collapse into the last bucket, which only affects the reported
-- p90 for zone-hours with a heavy long-wait tail. This is an approximation
-- (+/- 15s) of the same true quantity approx_quantile would estimate, not a
-- different metric.
CREATE OR REPLACE TABLE mart_wait_time_percentiles AS
WITH histogram AS (
    SELECT
        pu_location_id,
        date_trunc('hour', pickup_datetime) AS pickup_hour,
        platform,
        least(cast(wait_time_seconds / 15 AS INTEGER), 240) AS wait_bucket,
        count(*) AS bucket_n
    FROM stg_trips
    WHERE request_ts_valid
    GROUP BY 1, 2, 3, 4
),
cumulative AS (
    SELECT
        *,
        sum(bucket_n) OVER (
            PARTITION BY pu_location_id, pickup_hour, platform
            ORDER BY wait_bucket
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cum_n,
        sum(bucket_n) OVER (PARTITION BY pu_location_id, pickup_hour, platform) AS total_n
    FROM histogram
)
SELECT
    pu_location_id,
    pickup_hour,
    platform,
    max(total_n) AS wait_time_sample_size,
    min(wait_bucket) FILTER (WHERE cum_n >= 0.5 * total_n) * 15 AS wait_p50_seconds,
    min(wait_bucket) FILTER (WHERE cum_n >= 0.9 * total_n) * 15 AS wait_p90_seconds
FROM cumulative
GROUP BY 1, 2, 3;
