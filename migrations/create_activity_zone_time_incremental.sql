-- =============================================================================
-- Migration: Incremental Zone Time Calculation
-- Purpose: Convert activity_zone_time from materialized view to regular table
--          with incremental per-activity calculation and zone config trigger
-- Created: December 20, 2025
--
-- This migration:
-- 1. Creates activity_zone_time as a regular table (not materialized view)
-- 2. Preserves existing calculated data
-- 3. Creates calculate_zone_time_for_activity() for incremental calculation
-- 4. Updates refresh_all_zone_views() to only refresh weekly view
-- 5. Creates trigger on athlete_training_zones for auto-recalculation
-- =============================================================================

-- Step 1: Create the new regular table
-- This will replace the materialized view
CREATE TABLE IF NOT EXISTS activity_zone_time_new (
    -- Primary key
    activity_id TEXT PRIMARY KEY,

    -- Foreign keys
    athlete_id TEXT NOT NULL,
    activity_date DATE NOT NULL,

    -- Zone time in minutes (matching current view structure)
    zone_1_minutes DECIMAL(10,2) DEFAULT 0,
    zone_2_minutes DECIMAL(10,2) DEFAULT 0,
    zone_3_minutes DECIMAL(10,2) DEFAULT 0,
    zone_4_minutes DECIMAL(10,2) DEFAULT 0,
    zone_5_minutes DECIMAL(10,2) DEFAULT 0,
    zone_6_minutes DECIMAL(10,2) DEFAULT 0,
    total_zone_minutes DECIMAL(10,2) DEFAULT 0,

    -- Metadata
    calculated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Step 2: Copy existing data from materialized view (if exists)
-- This preserves all currently calculated zone times
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_matviews WHERE matviewname = 'activity_zone_time'
    ) THEN
        INSERT INTO activity_zone_time_new (
            activity_id, athlete_id, activity_date,
            zone_1_minutes, zone_2_minutes, zone_3_minutes,
            zone_4_minutes, zone_5_minutes, zone_6_minutes,
            total_zone_minutes, calculated_at
        )
        SELECT
            activity_id, athlete_id, activity_date,
            zone_1_minutes, zone_2_minutes, zone_3_minutes,
            zone_4_minutes, zone_5_minutes, zone_6_minutes,
            total_zone_minutes, NOW()
        FROM activity_zone_time
        ON CONFLICT (activity_id) DO NOTHING;

        RAISE NOTICE 'Copied existing zone time data from materialized view';
    ELSE
        RAISE NOTICE 'No existing materialized view found, starting fresh';
    END IF;
END $$;

-- Step 3: Drop old materialized views (in dependency order)
DROP MATERIALIZED VIEW IF EXISTS weekly_zone_time CASCADE;
DROP MATERIALIZED VIEW IF EXISTS activity_zone_time CASCADE;

-- Step 4: Rename new table to final name
ALTER TABLE activity_zone_time_new RENAME TO activity_zone_time;

-- Step 5: Add foreign key constraints
ALTER TABLE activity_zone_time
    ADD CONSTRAINT fk_activity_zone_time_activity
        FOREIGN KEY (activity_id)
        REFERENCES activity_metadata(activity_id)
        ON DELETE CASCADE;

ALTER TABLE activity_zone_time
    ADD CONSTRAINT fk_activity_zone_time_athlete
        FOREIGN KEY (athlete_id)
        REFERENCES athlete(athlete_id)
        ON DELETE CASCADE;

-- Step 6: Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_activity_zone_time_athlete_date
    ON activity_zone_time(athlete_id, activity_date DESC);
CREATE INDEX IF NOT EXISTS idx_activity_zone_time_athlete
    ON activity_zone_time(athlete_id);

-- Step 7: Recreate weekly_zone_time materialized view
-- (Now depends on table instead of materialized view)
CREATE MATERIALIZED VIEW weekly_zone_time AS
SELECT
    athlete_id,
    DATE_TRUNC('week', activity_date)::DATE AS week_start,
    SUM(zone_1_minutes) AS zone_1_minutes,
    SUM(zone_2_minutes) AS zone_2_minutes,
    SUM(zone_3_minutes) AS zone_3_minutes,
    SUM(zone_4_minutes) AS zone_4_minutes,
    SUM(zone_5_minutes) AS zone_5_minutes,
    SUM(zone_6_minutes) AS zone_6_minutes,
    SUM(total_zone_minutes) AS total_minutes,
    COUNT(*) AS activity_count
FROM activity_zone_time
WHERE total_zone_minutes > 0
GROUP BY athlete_id, DATE_TRUNC('week', activity_date)::DATE;

CREATE UNIQUE INDEX idx_weekly_zone_time_pk
    ON weekly_zone_time(athlete_id, week_start);
CREATE INDEX idx_weekly_zone_time_athlete
    ON weekly_zone_time(athlete_id, week_start DESC);

-- =============================================================================
-- Function: calculate_zone_time_for_activity
-- Purpose: Calculate and upsert zone time for a single activity
-- Usage: SELECT * FROM calculate_zone_time_for_activity('activity_id_here');
-- =============================================================================

CREATE OR REPLACE FUNCTION calculate_zone_time_for_activity(p_activity_id TEXT)
RETURNS TABLE (
    activity_id TEXT,
    athlete_id TEXT,
    activity_date DATE,
    zone_1_minutes DECIMAL,
    zone_2_minutes DECIMAL,
    zone_3_minutes DECIMAL,
    zone_4_minutes DECIMAL,
    zone_5_minutes DECIMAL,
    zone_6_minutes DECIMAL,
    total_zone_minutes DECIMAL,
    was_inserted BOOLEAN
) AS $$
DECLARE
    v_athlete_id TEXT;
    v_activity_date DATE;
    v_type TEXT;
    v_result RECORD;
BEGIN
    -- Get activity metadata
    SELECT am.athlete_id, am.date, LOWER(am.type)
    INTO v_athlete_id, v_activity_date, v_type
    FROM activity_metadata am
    WHERE am.activity_id = p_activity_id;

    -- Return empty if activity not found
    IF v_athlete_id IS NULL THEN
        RETURN QUERY SELECT
            p_activity_id, NULL::TEXT, NULL::DATE,
            0::DECIMAL, 0::DECIMAL, 0::DECIMAL,
            0::DECIMAL, 0::DECIMAL, 0::DECIMAL,
            0::DECIMAL, FALSE;
        RETURN;
    END IF;

    -- Skip non-running activities
    IF v_type NOT IN ('run', 'trailrun', 'virtualrun', 'treadmill') THEN
        RETURN QUERY SELECT
            p_activity_id, v_athlete_id, v_activity_date,
            0::DECIMAL, 0::DECIMAL, 0::DECIMAL,
            0::DECIMAL, 0::DECIMAL, 0::DECIMAL,
            0::DECIMAL, FALSE;
        RETURN;
    END IF;

    -- Calculate zone time using same logic as original materialized view
    WITH
    -- Get effective zones for this activity (temporal matching)
    effective_zones AS (
        SELECT DISTINCT ON (atz.zone_number)
            atz.zone_number,
            atz.pace_min_sec_per_km,
            atz.pace_max_sec_per_km
        FROM athlete_training_zones atz
        WHERE atz.athlete_id = v_athlete_id
          AND atz.effective_from_date <= v_activity_date
        ORDER BY atz.zone_number, atz.effective_from_date DESC
    ),

    -- Calculate pace for each GPS record
    activity_pace AS (
        SELECT
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
        WHERE a.activity_id = p_activity_id
    ),

    -- Count seconds in each zone
    zone_time AS (
        SELECT
            ez.zone_number,
            COUNT(*) AS zone_seconds
        FROM activity_pace ap
        CROSS JOIN effective_zones ez
        WHERE ap.pace_sec_per_km IS NOT NULL
          AND (
              -- Zone 6: pace <= pace_max (fastest zone, no lower bound)
              (ez.pace_min_sec_per_km IS NULL AND ap.pace_sec_per_km <= ez.pace_max_sec_per_km)
              OR
              -- Zone 1: pace > pace_min (slowest zone, no upper bound)
              (ez.pace_max_sec_per_km IS NULL AND ap.pace_sec_per_km > ez.pace_min_sec_per_km)
              OR
              -- Middle zones (2-5): pace_min < pace <= pace_max
              (ez.pace_min_sec_per_km IS NOT NULL
               AND ez.pace_max_sec_per_km IS NOT NULL
               AND ap.pace_sec_per_km > ez.pace_min_sec_per_km
               AND ap.pace_sec_per_km <= ez.pace_max_sec_per_km)
          )
        GROUP BY ez.zone_number
    ),

    -- Pivot to zone columns
    zone_pivot AS (
        SELECT
            COALESCE(SUM(CASE WHEN zone_number = 1 THEN zone_seconds END) / 60.0, 0) AS z1,
            COALESCE(SUM(CASE WHEN zone_number = 2 THEN zone_seconds END) / 60.0, 0) AS z2,
            COALESCE(SUM(CASE WHEN zone_number = 3 THEN zone_seconds END) / 60.0, 0) AS z3,
            COALESCE(SUM(CASE WHEN zone_number = 4 THEN zone_seconds END) / 60.0, 0) AS z4,
            COALESCE(SUM(CASE WHEN zone_number = 5 THEN zone_seconds END) / 60.0, 0) AS z5,
            COALESCE(SUM(CASE WHEN zone_number = 6 THEN zone_seconds END) / 60.0, 0) AS z6,
            COALESCE(SUM(zone_seconds) / 60.0, 0) AS total
        FROM zone_time
    )

    -- Upsert result into activity_zone_time table
    INSERT INTO activity_zone_time (
        activity_id, athlete_id, activity_date,
        zone_1_minutes, zone_2_minutes, zone_3_minutes,
        zone_4_minutes, zone_5_minutes, zone_6_minutes,
        total_zone_minutes, calculated_at
    )
    SELECT
        p_activity_id, v_athlete_id, v_activity_date,
        zp.z1, zp.z2, zp.z3, zp.z4, zp.z5, zp.z6,
        zp.total, NOW()
    FROM zone_pivot zp
    ON CONFLICT (activity_id) DO UPDATE SET
        zone_1_minutes = EXCLUDED.zone_1_minutes,
        zone_2_minutes = EXCLUDED.zone_2_minutes,
        zone_3_minutes = EXCLUDED.zone_3_minutes,
        zone_4_minutes = EXCLUDED.zone_4_minutes,
        zone_5_minutes = EXCLUDED.zone_5_minutes,
        zone_6_minutes = EXCLUDED.zone_6_minutes,
        total_zone_minutes = EXCLUDED.total_zone_minutes,
        calculated_at = NOW()
    RETURNING * INTO v_result;

    -- Return the calculated/upserted row
    RETURN QUERY SELECT
        v_result.activity_id,
        v_result.athlete_id,
        v_result.activity_date,
        v_result.zone_1_minutes,
        v_result.zone_2_minutes,
        v_result.zone_3_minutes,
        v_result.zone_4_minutes,
        v_result.zone_5_minutes,
        v_result.zone_6_minutes,
        v_result.total_zone_minutes,
        TRUE;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_zone_time_for_activity(TEXT) IS
'Calculates and upserts zone time for a single activity. Uses temporal zone matching.
Call after each activity import. Returns the calculated row.';

-- =============================================================================
-- Function: refresh_all_zone_views (updated)
-- Purpose: Now only refreshes weekly_zone_time (activity-level already in table)
-- =============================================================================

CREATE OR REPLACE FUNCTION refresh_all_zone_views()
RETURNS void AS $$
BEGIN
    -- Only refresh weekly aggregation (activity-level is now incremental)
    REFRESH MATERIALIZED VIEW CONCURRENTLY weekly_zone_time;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION refresh_all_zone_views() IS
'Refreshes weekly_zone_time materialized view. Activity-level zone time is now
calculated incrementally via calculate_zone_time_for_activity().';

-- =============================================================================
-- Function: recalculate_all_zone_times (utility for bulk operations)
-- Purpose: Recalculate zone time for all activities (for zone config changes)
-- =============================================================================

CREATE OR REPLACE FUNCTION recalculate_all_zone_times()
RETURNS TABLE (
    activities_processed INTEGER,
    duration_seconds DECIMAL
) AS $$
DECLARE
    v_start TIMESTAMPTZ;
    v_count INTEGER := 0;
    v_activity_id TEXT;
BEGIN
    v_start := NOW();

    -- Process all running activities
    FOR v_activity_id IN
        SELECT am.activity_id
        FROM activity_metadata am
        WHERE LOWER(am.type) IN ('run', 'trailrun', 'virtualrun', 'treadmill')
    LOOP
        PERFORM calculate_zone_time_for_activity(v_activity_id);
        v_count := v_count + 1;
    END LOOP;

    -- Refresh weekly view
    REFRESH MATERIALIZED VIEW CONCURRENTLY weekly_zone_time;

    RETURN QUERY SELECT v_count, EXTRACT(EPOCH FROM NOW() - v_start)::DECIMAL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION recalculate_all_zone_times() IS
'Recalculates zone time for ALL activities. Use after zone configuration changes
or for bulk data recovery.';

-- =============================================================================
-- Trigger: Auto-recalculate when zone configuration changes
-- Purpose: When new zones are inserted with a backdated effective_from_date,
--          automatically recalculate zone time for affected activities
-- =============================================================================

CREATE OR REPLACE FUNCTION recalculate_zones_for_affected_activities()
RETURNS TRIGGER AS $$
DECLARE
    v_athlete_id TEXT;
    v_min_date DATE;
    v_activity_id TEXT;
    v_count INTEGER := 0;
BEGIN
    -- Get distinct athletes and their earliest effective date from inserted rows
    FOR v_athlete_id, v_min_date IN
        SELECT DISTINCT athlete_id, MIN(effective_from_date)
        FROM new_zones
        GROUP BY athlete_id
    LOOP
        -- Recalculate zone time for all activities from min_date to today
        FOR v_activity_id IN
            SELECT am.activity_id
            FROM activity_metadata am
            WHERE am.athlete_id = v_athlete_id
              AND am.date >= v_min_date
              AND LOWER(am.type) IN ('run', 'trailrun', 'virtualrun', 'treadmill')
            ORDER BY am.date
        LOOP
            PERFORM calculate_zone_time_for_activity(v_activity_id);
            v_count := v_count + 1;
        END LOOP;

        RAISE NOTICE 'Recalculated % activities for athlete % from %',
            v_count, v_athlete_id, v_min_date;
    END LOOP;

    -- Refresh weekly view once at end
    IF v_count > 0 THEN
        REFRESH MATERIALIZED VIEW CONCURRENTLY weekly_zone_time;
        RAISE NOTICE 'Refreshed weekly_zone_time view after recalculating % activities', v_count;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION recalculate_zones_for_affected_activities() IS
'Trigger function that recalculates zone time when new zones are inserted.
Handles backdated effective_from_date by recalculating all activities from that date.';

-- Statement-level trigger with transition table for batch efficiency
CREATE TRIGGER trg_zone_config_changed
AFTER INSERT ON athlete_training_zones
REFERENCING NEW TABLE AS new_zones
FOR EACH STATEMENT
EXECUTE FUNCTION recalculate_zones_for_affected_activities();

COMMENT ON TRIGGER trg_zone_config_changed ON athlete_training_zones IS
'Fires after zone configuration insert. Recalculates zone time for all activities
from the effective_from_date to today. Batches multiple inserts efficiently.';

-- =============================================================================
-- Add table comment
-- =============================================================================

COMMENT ON TABLE activity_zone_time IS
'Pre-calculated time in athlete-specific training zones per activity.
Uses temporal zone matching - each activity uses zones effective on that date.
Updated incrementally via calculate_zone_time_for_activity().
Auto-updated when zone configuration changes via trg_zone_config_changed trigger.';

-- =============================================================================
-- Verification queries (run manually after migration)
-- =============================================================================

-- Check record count
-- SELECT COUNT(*) as zone_records FROM activity_zone_time;

-- Test incremental calculation (replace with real activity_id)
-- SELECT * FROM calculate_zone_time_for_activity('i344978:1234567890');

-- Test weekly refresh
-- SELECT refresh_all_zone_views();

-- Check weekly view
-- SELECT COUNT(*) as weekly_records FROM weekly_zone_time;
