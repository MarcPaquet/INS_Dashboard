-- =============================================================================
-- Materialized View: activity_zone_time
-- Purpose: Pre-calculate time (minutes) spent in each athlete-specific training
--          zone for each activity, using temporal zone matching
-- Created: December 12, 2025
--
-- Refresh: SELECT refresh_all_zone_views();
-- =============================================================================

DROP MATERIALIZED VIEW IF EXISTS weekly_zone_time CASCADE;
DROP MATERIALIZED VIEW IF EXISTS activity_zone_time CASCADE;

CREATE MATERIALIZED VIEW activity_zone_time AS
WITH
-- Step 1: Get effective zones for each activity (temporal matching)
-- Each activity uses zones that were effective on that activity's date
activity_effective_zones AS (
    SELECT DISTINCT ON (am.activity_id, atz.zone_number)
        am.activity_id,
        am.athlete_id,
        am.date AS activity_date,
        atz.zone_number,
        atz.pace_min_sec_per_km,
        atz.pace_max_sec_per_km
    FROM activity_metadata am
    INNER JOIN athlete_training_zones atz
        ON atz.athlete_id = am.athlete_id
        AND atz.effective_from_date <= am.date
    WHERE LOWER(am.type) IN ('run', 'trailrun', 'virtualrun', 'treadmill')
    ORDER BY am.activity_id, atz.zone_number, atz.effective_from_date DESC
),

-- Step 2: Calculate pace for each timeseries row
-- Use GREATEST to pick best available speed source (matches dashboard logic)
-- Pace = 1000 / speed (seconds per km)
activity_pace AS (
    SELECT
        a.activity_id,
        CASE
            WHEN GREATEST(
                COALESCE(a.speed, 0),
                COALESCE(a.enhanced_speed, 0),
                COALESCE(a.velocity_smooth, 0)
            ) > 0.1
            THEN 1000.0 / GREATEST(
                COALESCE(a.speed, 0),
                COALESCE(a.enhanced_speed, 0),
                COALESCE(a.velocity_smooth, 0)
            )
            ELSE NULL
        END AS pace_sec_per_km
    FROM activity a
),

-- Step 3: Count seconds in each zone per activity
-- Each row in activity table = ~1 second of data
zone_time_per_activity AS (
    SELECT
        aez.activity_id,
        aez.athlete_id,
        aez.activity_date,
        aez.zone_number,
        COUNT(*) AS zone_seconds
    FROM activity_pace ap
    INNER JOIN activity_effective_zones aez ON ap.activity_id = aez.activity_id
    WHERE ap.pace_sec_per_km IS NOT NULL
      AND (
          -- Zone 6: pace <= pace_max (INCLUSIVE, fastest zone)
          (aez.pace_min_sec_per_km IS NULL AND ap.pace_sec_per_km <= aez.pace_max_sec_per_km)
          OR
          -- Zone 1: pace > pace_min (slowest zone)
          (aez.pace_max_sec_per_km IS NULL AND ap.pace_sec_per_km > aez.pace_min_sec_per_km)
          OR
          -- Middle zones (2-5): pace_min < pace <= pace_max
          (aez.pace_min_sec_per_km IS NOT NULL
           AND aez.pace_max_sec_per_km IS NOT NULL
           AND ap.pace_sec_per_km > aez.pace_min_sec_per_km
           AND ap.pace_sec_per_km <= aez.pace_max_sec_per_km)
      )
    GROUP BY aez.activity_id, aez.athlete_id, aez.activity_date, aez.zone_number
)

-- Step 4: Pivot to one row per activity with zone columns
SELECT
    am.activity_id,
    am.athlete_id,
    am.date AS activity_date,
    COALESCE(SUM(CASE WHEN zt.zone_number = 1 THEN zt.zone_seconds END) / 60.0, 0) AS zone_1_minutes,
    COALESCE(SUM(CASE WHEN zt.zone_number = 2 THEN zt.zone_seconds END) / 60.0, 0) AS zone_2_minutes,
    COALESCE(SUM(CASE WHEN zt.zone_number = 3 THEN zt.zone_seconds END) / 60.0, 0) AS zone_3_minutes,
    COALESCE(SUM(CASE WHEN zt.zone_number = 4 THEN zt.zone_seconds END) / 60.0, 0) AS zone_4_minutes,
    COALESCE(SUM(CASE WHEN zt.zone_number = 5 THEN zt.zone_seconds END) / 60.0, 0) AS zone_5_minutes,
    COALESCE(SUM(CASE WHEN zt.zone_number = 6 THEN zt.zone_seconds END) / 60.0, 0) AS zone_6_minutes,
    COALESCE(SUM(zt.zone_seconds) / 60.0, 0) AS total_zone_minutes
FROM activity_metadata am
LEFT JOIN zone_time_per_activity zt ON am.activity_id = zt.activity_id
WHERE LOWER(am.type) IN ('run', 'trailrun', 'virtualrun', 'treadmill')
GROUP BY am.activity_id, am.athlete_id, am.date;

-- Unique index required for CONCURRENTLY refresh
CREATE UNIQUE INDEX idx_activity_zone_time_pk ON activity_zone_time(activity_id);

-- Performance indexes
CREATE INDEX idx_activity_zone_time_athlete_date ON activity_zone_time(athlete_id, activity_date DESC);
CREATE INDEX idx_activity_zone_time_athlete ON activity_zone_time(athlete_id);

COMMENT ON MATERIALIZED VIEW activity_zone_time IS
'Pre-calculated time in athlete-specific training zones per activity.
Uses temporal zone matching - each activity uses zones effective on that date.
Refresh after imports: SELECT refresh_all_zone_views();';
