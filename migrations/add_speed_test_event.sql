-- Migration: Add speed_test event type to lactate_tests
-- Date: 2026-02-08
-- Purpose: Support maximal speed tests (e.g., 40m sprint) with auto-calculated m/s

-- ============================================
-- STEP 1: Add speed_ms column
-- ============================================
ALTER TABLE lactate_tests ADD COLUMN IF NOT EXISTS speed_ms DECIMAL(6,3);

-- ============================================
-- STEP 2: Drop and recreate affected CHECK constraints
-- ============================================

-- Update test_type to include 'speed_test'
ALTER TABLE lactate_tests DROP CONSTRAINT IF EXISTS chk_test_type;
ALTER TABLE lactate_tests ADD CONSTRAINT chk_test_type
    CHECK (test_type IN ('lactate', 'race', 'injury', 'speed_test'));

-- Distance required for lactate, race, AND speed_test (not injury)
ALTER TABLE lactate_tests DROP CONSTRAINT IF EXISTS chk_distance_required;
ALTER TABLE lactate_tests ADD CONSTRAINT chk_distance_required
    CHECK (test_type = 'injury' OR distance_m IS NOT NULL);

-- Race time allowed for race AND speed_test (stores the raw time)
ALTER TABLE lactate_tests DROP CONSTRAINT IF EXISTS chk_race_time_only_for_races;
ALTER TABLE lactate_tests ADD CONSTRAINT chk_race_time_only_for_races
    CHECK (test_type IN ('race', 'speed_test') OR race_time_seconds IS NULL);

-- Speed only for speed_tests
ALTER TABLE lactate_tests ADD CONSTRAINT chk_speed_only_for_speed_tests
    CHECK (test_type = 'speed_test' OR speed_ms IS NULL);

-- ============================================
-- STEP 3: Partial index for speed test queries
-- ============================================
CREATE INDEX IF NOT EXISTS idx_lactate_tests_speed
    ON lactate_tests(athlete_id, test_type, test_date DESC)
    WHERE test_type = 'speed_test';

-- ============================================
-- VERIFICATION QUERY (run after migration)
-- ============================================
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'lactate_tests'
-- ORDER BY ordinal_position;
