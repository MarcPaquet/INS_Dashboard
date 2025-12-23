-- =============================================================================
-- Migration: Weekly Monotony & Strain Pre-calculation
-- Purpose: Pre-calculate Carl Foster's Training Monotony and Strain metrics
--          per zone per week, eliminating dashboard computation
-- Created: December 22, 2025
-- Phase: 2V
-- Status: DEPLOYED to production (Dec 22, 2025)
--
-- This migration:
-- 1. Creates weekly_monotony_strain table (per-zone metrics)
-- 2. Creates calculate_monotony_strain_for_week() for incremental calculation
-- 3. Creates backfill_monotony_strain() for historical data
-- 4. Creates recalculate_monotony_strain_for_athlete() utility function
--
-- Requires: Phase 2S (activity_zone_time as table, not materialized view)
--
-- IMPORTANT BUG FIX NOTES:
-- The function uses 'out_' prefix for RETURNS TABLE columns and 'ztotal'
-- alias for total calculations to avoid PostgreSQL "ambiguous column reference"
-- error. PostgreSQL treats RETURNS TABLE column names as PL/pgSQL variables
-- visible within the function body, so they must not conflict with CTE aliases.
--
-- If re-running this migration after previous attempts:
--   DROP FUNCTION IF EXISTS calculate_monotony_strain_for_week(text, date);
-- =============================================================================

-- Step 1: Create the weekly_monotony_strain table
-- Stores per-zone and total monotony/strain for each athlete/week
CREATE TABLE IF NOT EXISTS weekly_monotony_strain (
    id SERIAL PRIMARY KEY,
    athlete_id TEXT NOT NULL REFERENCES athlete(athlete_id) ON DELETE CASCADE,
    week_start DATE NOT NULL,

    -- Zone 1 metrics
    zone_1_load_min DECIMAL(10,2) DEFAULT 0,
    zone_1_monotony DECIMAL(6,3) DEFAULT 0,
    zone_1_strain DECIMAL(12,2) DEFAULT 0,

    -- Zone 2 metrics
    zone_2_load_min DECIMAL(10,2) DEFAULT 0,
    zone_2_monotony DECIMAL(6,3) DEFAULT 0,
    zone_2_strain DECIMAL(12,2) DEFAULT 0,

    -- Zone 3 metrics
    zone_3_load_min DECIMAL(10,2) DEFAULT 0,
    zone_3_monotony DECIMAL(6,3) DEFAULT 0,
    zone_3_strain DECIMAL(12,2) DEFAULT 0,

    -- Zone 4 metrics
    zone_4_load_min DECIMAL(10,2) DEFAULT 0,
    zone_4_monotony DECIMAL(6,3) DEFAULT 0,
    zone_4_strain DECIMAL(12,2) DEFAULT 0,

    -- Zone 5 metrics
    zone_5_load_min DECIMAL(10,2) DEFAULT 0,
    zone_5_monotony DECIMAL(6,3) DEFAULT 0,
    zone_5_strain DECIMAL(12,2) DEFAULT 0,

    -- Zone 6 metrics
    zone_6_load_min DECIMAL(10,2) DEFAULT 0,
    zone_6_monotony DECIMAL(6,3) DEFAULT 0,
    zone_6_strain DECIMAL(12,2) DEFAULT 0,

    -- Total (all zones combined)
    total_load_min DECIMAL(10,2) DEFAULT 0,
    total_monotony DECIMAL(6,3) DEFAULT 0,
    total_strain DECIMAL(12,2) DEFAULT 0,

    -- Metadata
    calculated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(athlete_id, week_start)
);

-- Step 2: Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_weekly_monotony_strain_athlete_week
    ON weekly_monotony_strain(athlete_id, week_start DESC);
CREATE INDEX IF NOT EXISTS idx_weekly_monotony_strain_athlete
    ON weekly_monotony_strain(athlete_id);

-- =============================================================================
-- Function: calculate_monotony_strain_for_week
-- Purpose: Calculate and upsert monotony/strain for a specific athlete/week
-- Usage: SELECT * FROM calculate_monotony_strain_for_week('i344978', '2025-12-16');
--
-- Carl Foster Model:
--   CV = std(daily_minutes) / mean(daily_minutes)
--   Monotony = 1 / CV (capped at 10.0)
--   Load = sum(daily_minutes) for the week
--   Strain = Load × Monotony
-- =============================================================================

CREATE OR REPLACE FUNCTION calculate_monotony_strain_for_week(
    p_athlete_id TEXT,
    p_week_start DATE
) RETURNS TABLE (
    out_athlete_id TEXT,
    out_week_start DATE,
    out_zone_1_load_min DECIMAL, out_zone_1_monotony DECIMAL, out_zone_1_strain DECIMAL,
    out_zone_2_load_min DECIMAL, out_zone_2_monotony DECIMAL, out_zone_2_strain DECIMAL,
    out_zone_3_load_min DECIMAL, out_zone_3_monotony DECIMAL, out_zone_3_strain DECIMAL,
    out_zone_4_load_min DECIMAL, out_zone_4_monotony DECIMAL, out_zone_4_strain DECIMAL,
    out_zone_5_load_min DECIMAL, out_zone_5_monotony DECIMAL, out_zone_5_strain DECIMAL,
    out_zone_6_load_min DECIMAL, out_zone_6_monotony DECIMAL, out_zone_6_strain DECIMAL,
    out_total_load_min DECIMAL, out_total_monotony DECIMAL, out_total_strain DECIMAL,
    was_inserted BOOLEAN
) AS $$
DECLARE
    v_week_end DATE;
    v_result RECORD;
BEGIN
    -- Calculate week end (Sunday)
    v_week_end := p_week_start + INTERVAL '6 days';

    -- Calculate metrics using CTE
    WITH
    -- Generate all 7 days of the week
    week_days AS (
        SELECT generate_series(
            p_week_start::TIMESTAMP,
            v_week_end::TIMESTAMP,
            '1 day'::INTERVAL
        )::DATE AS day_date
    ),

    -- Get zone time per day from activity_zone_time
    -- NOTE: Using 'ztotal' alias to avoid conflict with RETURNS TABLE output columns
    daily_zone_time AS (
        SELECT
            az.activity_date,
            COALESCE(SUM(az.zone_1_minutes), 0) AS z1,
            COALESCE(SUM(az.zone_2_minutes), 0) AS z2,
            COALESCE(SUM(az.zone_3_minutes), 0) AS z3,
            COALESCE(SUM(az.zone_4_minutes), 0) AS z4,
            COALESCE(SUM(az.zone_5_minutes), 0) AS z5,
            COALESCE(SUM(az.zone_6_minutes), 0) AS z6,
            COALESCE(SUM(az.total_zone_minutes), 0) AS ztotal
        FROM activity_zone_time az
        WHERE az.athlete_id = p_athlete_id
          AND az.activity_date >= p_week_start
          AND az.activity_date <= v_week_end
        GROUP BY az.activity_date
    ),

    -- Join with all days (fill missing with zeros)
    full_week AS (
        SELECT
            wd.day_date,
            COALESCE(dzt.z1, 0) AS z1,
            COALESCE(dzt.z2, 0) AS z2,
            COALESCE(dzt.z3, 0) AS z3,
            COALESCE(dzt.z4, 0) AS z4,
            COALESCE(dzt.z5, 0) AS z5,
            COALESCE(dzt.z6, 0) AS z6,
            COALESCE(dzt.ztotal, 0) AS ztotal
        FROM week_days wd
        LEFT JOIN daily_zone_time dzt ON wd.day_date = dzt.activity_date
    ),

    -- Calculate statistics per zone
    zone_stats AS (
        SELECT
            -- Zone 1
            SUM(z1) AS z1_load,
            AVG(z1) AS z1_mean,
            STDDEV_POP(z1) AS z1_std,
            -- Zone 2
            SUM(z2) AS z2_load,
            AVG(z2) AS z2_mean,
            STDDEV_POP(z2) AS z2_std,
            -- Zone 3
            SUM(z3) AS z3_load,
            AVG(z3) AS z3_mean,
            STDDEV_POP(z3) AS z3_std,
            -- Zone 4
            SUM(z4) AS z4_load,
            AVG(z4) AS z4_mean,
            STDDEV_POP(z4) AS z4_std,
            -- Zone 5
            SUM(z5) AS z5_load,
            AVG(z5) AS z5_mean,
            STDDEV_POP(z5) AS z5_std,
            -- Zone 6
            SUM(z6) AS z6_load,
            AVG(z6) AS z6_mean,
            STDDEV_POP(z6) AS z6_std,
            -- Total (using ztotal to avoid ambiguity)
            SUM(ztotal) AS ztotal_load,
            AVG(ztotal) AS ztotal_mean,
            STDDEV_POP(ztotal) AS ztotal_std
        FROM full_week
    ),

    -- Calculate monotony and strain
    final_metrics AS (
        SELECT
            -- Zone 1
            z1_load,
            CASE
                WHEN z1_mean > 0 AND z1_std > 0 THEN LEAST(10.0, z1_mean / z1_std)
                WHEN z1_mean > 0 AND z1_std = 0 THEN 10.0  -- All days identical
                ELSE 0.0  -- No training
            END AS z1_monotony,

            -- Zone 2
            z2_load,
            CASE
                WHEN z2_mean > 0 AND z2_std > 0 THEN LEAST(10.0, z2_mean / z2_std)
                WHEN z2_mean > 0 AND z2_std = 0 THEN 10.0
                ELSE 0.0
            END AS z2_monotony,

            -- Zone 3
            z3_load,
            CASE
                WHEN z3_mean > 0 AND z3_std > 0 THEN LEAST(10.0, z3_mean / z3_std)
                WHEN z3_mean > 0 AND z3_std = 0 THEN 10.0
                ELSE 0.0
            END AS z3_monotony,

            -- Zone 4
            z4_load,
            CASE
                WHEN z4_mean > 0 AND z4_std > 0 THEN LEAST(10.0, z4_mean / z4_std)
                WHEN z4_mean > 0 AND z4_std = 0 THEN 10.0
                ELSE 0.0
            END AS z4_monotony,

            -- Zone 5
            z5_load,
            CASE
                WHEN z5_mean > 0 AND z5_std > 0 THEN LEAST(10.0, z5_mean / z5_std)
                WHEN z5_mean > 0 AND z5_std = 0 THEN 10.0
                ELSE 0.0
            END AS z5_monotony,

            -- Zone 6
            z6_load,
            CASE
                WHEN z6_mean > 0 AND z6_std > 0 THEN LEAST(10.0, z6_mean / z6_std)
                WHEN z6_mean > 0 AND z6_std = 0 THEN 10.0
                ELSE 0.0
            END AS z6_monotony,

            -- Total (using ztotal_* to avoid ambiguity with RETURNS TABLE columns)
            ztotal_load,
            CASE
                WHEN ztotal_mean > 0 AND ztotal_std > 0 THEN LEAST(10.0, ztotal_mean / ztotal_std)
                WHEN ztotal_mean > 0 AND ztotal_std = 0 THEN 10.0
                ELSE 0.0
            END AS ztotal_monotony
        FROM zone_stats
    )

    -- Upsert into weekly_monotony_strain
    INSERT INTO weekly_monotony_strain (
        athlete_id, week_start,
        zone_1_load_min, zone_1_monotony, zone_1_strain,
        zone_2_load_min, zone_2_monotony, zone_2_strain,
        zone_3_load_min, zone_3_monotony, zone_3_strain,
        zone_4_load_min, zone_4_monotony, zone_4_strain,
        zone_5_load_min, zone_5_monotony, zone_5_strain,
        zone_6_load_min, zone_6_monotony, zone_6_strain,
        total_load_min, total_monotony, total_strain,
        calculated_at
    )
    SELECT
        p_athlete_id,
        p_week_start,
        fm.z1_load, fm.z1_monotony, fm.z1_load * fm.z1_monotony,
        fm.z2_load, fm.z2_monotony, fm.z2_load * fm.z2_monotony,
        fm.z3_load, fm.z3_monotony, fm.z3_load * fm.z3_monotony,
        fm.z4_load, fm.z4_monotony, fm.z4_load * fm.z4_monotony,
        fm.z5_load, fm.z5_monotony, fm.z5_load * fm.z5_monotony,
        fm.z6_load, fm.z6_monotony, fm.z6_load * fm.z6_monotony,
        fm.ztotal_load, fm.ztotal_monotony, fm.ztotal_load * fm.ztotal_monotony,
        NOW()
    FROM final_metrics fm
    ON CONFLICT (athlete_id, week_start) DO UPDATE SET
        zone_1_load_min = EXCLUDED.zone_1_load_min,
        zone_1_monotony = EXCLUDED.zone_1_monotony,
        zone_1_strain = EXCLUDED.zone_1_strain,
        zone_2_load_min = EXCLUDED.zone_2_load_min,
        zone_2_monotony = EXCLUDED.zone_2_monotony,
        zone_2_strain = EXCLUDED.zone_2_strain,
        zone_3_load_min = EXCLUDED.zone_3_load_min,
        zone_3_monotony = EXCLUDED.zone_3_monotony,
        zone_3_strain = EXCLUDED.zone_3_strain,
        zone_4_load_min = EXCLUDED.zone_4_load_min,
        zone_4_monotony = EXCLUDED.zone_4_monotony,
        zone_4_strain = EXCLUDED.zone_4_strain,
        zone_5_load_min = EXCLUDED.zone_5_load_min,
        zone_5_monotony = EXCLUDED.zone_5_monotony,
        zone_5_strain = EXCLUDED.zone_5_strain,
        zone_6_load_min = EXCLUDED.zone_6_load_min,
        zone_6_monotony = EXCLUDED.zone_6_monotony,
        zone_6_strain = EXCLUDED.zone_6_strain,
        total_load_min = EXCLUDED.total_load_min,
        total_monotony = EXCLUDED.total_monotony,
        total_strain = EXCLUDED.total_strain,
        calculated_at = NOW()
    RETURNING * INTO v_result;

    -- Return the calculated row
    RETURN QUERY SELECT
        v_result.athlete_id,
        v_result.week_start,
        v_result.zone_1_load_min, v_result.zone_1_monotony, v_result.zone_1_strain,
        v_result.zone_2_load_min, v_result.zone_2_monotony, v_result.zone_2_strain,
        v_result.zone_3_load_min, v_result.zone_3_monotony, v_result.zone_3_strain,
        v_result.zone_4_load_min, v_result.zone_4_monotony, v_result.zone_4_strain,
        v_result.zone_5_load_min, v_result.zone_5_monotony, v_result.zone_5_strain,
        v_result.zone_6_load_min, v_result.zone_6_monotony, v_result.zone_6_strain,
        v_result.total_load_min, v_result.total_monotony, v_result.total_strain,
        TRUE;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_monotony_strain_for_week(TEXT, DATE) IS
'Calculates and upserts weekly Training Monotony and Strain (Carl Foster model)
for a specific athlete and week. Call after activity imports.

Monotony = mean / stddev (capped at 10.0)
Strain = Load × Monotony

Parameters:
  p_athlete_id: The athlete ID
  p_week_start: The Monday of the week to calculate';

-- =============================================================================
-- Function: backfill_monotony_strain
-- Purpose: Calculate monotony/strain for all historical weeks
-- Usage: SELECT * FROM backfill_monotony_strain();
-- =============================================================================

CREATE OR REPLACE FUNCTION backfill_monotony_strain()
RETURNS TABLE (
    weeks_processed INTEGER,
    athletes_processed INTEGER,
    duration_seconds DECIMAL
) AS $$
DECLARE
    v_start TIMESTAMPTZ;
    v_week_count INTEGER := 0;
    v_athlete_count INTEGER := 0;
    v_athlete_id TEXT;
    v_week_start DATE;
BEGIN
    v_start := NOW();

    -- Get all unique athlete/week combinations from activity_zone_time
    FOR v_athlete_id, v_week_start IN
        SELECT DISTINCT
            az.athlete_id,
            DATE_TRUNC('week', az.activity_date)::DATE AS week_start
        FROM activity_zone_time az
        ORDER BY az.athlete_id, week_start
    LOOP
        PERFORM calculate_monotony_strain_for_week(v_athlete_id, v_week_start);
        v_week_count := v_week_count + 1;
    END LOOP;

    -- Count distinct athletes
    SELECT COUNT(DISTINCT athlete_id) INTO v_athlete_count
    FROM weekly_monotony_strain;

    RETURN QUERY SELECT
        v_week_count,
        v_athlete_count,
        EXTRACT(EPOCH FROM NOW() - v_start)::DECIMAL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION backfill_monotony_strain() IS
'Backfills weekly_monotony_strain table with historical data.
Run once after creating the table to populate existing weeks.';

-- =============================================================================
-- Function: recalculate_monotony_strain_for_athlete
-- Purpose: Recalculate all weeks for a specific athlete
-- Usage: SELECT * FROM recalculate_monotony_strain_for_athlete('i344978');
-- =============================================================================

CREATE OR REPLACE FUNCTION recalculate_monotony_strain_for_athlete(
    p_athlete_id TEXT
) RETURNS TABLE (
    weeks_processed INTEGER,
    duration_seconds DECIMAL
) AS $$
DECLARE
    v_start TIMESTAMPTZ;
    v_week_count INTEGER := 0;
    v_week_start DATE;
BEGIN
    v_start := NOW();

    -- Get all weeks for this athlete
    FOR v_week_start IN
        SELECT DISTINCT DATE_TRUNC('week', az.activity_date)::DATE
        FROM activity_zone_time az
        WHERE az.athlete_id = p_athlete_id
        ORDER BY 1
    LOOP
        PERFORM calculate_monotony_strain_for_week(p_athlete_id, v_week_start);
        v_week_count := v_week_count + 1;
    END LOOP;

    RETURN QUERY SELECT v_week_count, EXTRACT(EPOCH FROM NOW() - v_start)::DECIMAL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION recalculate_monotony_strain_for_athlete(TEXT) IS
'Recalculates monotony/strain for all weeks of a specific athlete.
Use when zone time data changes for historical activities.';

-- =============================================================================
-- Table comment
-- =============================================================================

COMMENT ON TABLE weekly_monotony_strain IS
'Pre-calculated weekly Training Monotony and Strain (Carl Foster model).
Updated incrementally via calculate_monotony_strain_for_week() after activity imports.

Monotony = mean / stddev of daily training minutes (capped at 10.0)
Strain = Load × Monotony

Per-zone metrics allow flexible aggregation in the dashboard.';

-- =============================================================================
-- Verification queries (run manually after migration)
-- =============================================================================

-- Backfill historical data
-- SELECT * FROM backfill_monotony_strain();

-- Check record count
-- SELECT COUNT(*) as monotony_records FROM weekly_monotony_strain;

-- Test single week calculation
-- SELECT * FROM calculate_monotony_strain_for_week('i344978', '2025-12-16');

-- View sample data
-- SELECT athlete_id, week_start, total_load_min, total_monotony, total_strain
-- FROM weekly_monotony_strain
-- ORDER BY week_start DESC
-- LIMIT 10;
