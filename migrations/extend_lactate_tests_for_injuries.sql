-- Migration: Extend lactate_tests for injuries/pain tracking
-- Date: 2026-02-02
-- Purpose: Add injury support with body location, severity, and status

-- ============================================
-- STEP 1: Add test_type column if not exists
-- ============================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'lactate_tests' AND column_name = 'test_type'
    ) THEN
        ALTER TABLE lactate_tests ADD COLUMN test_type TEXT NOT NULL DEFAULT 'lactate';
    END IF;
END $$;

-- ============================================
-- STEP 2: Add race_time_seconds if not exists
-- ============================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'lactate_tests' AND column_name = 'race_time_seconds'
    ) THEN
        ALTER TABLE lactate_tests ADD COLUMN race_time_seconds DECIMAL(10,2);
    END IF;
END $$;

-- ============================================
-- STEP 3: Make lactate_mmol nullable
-- ============================================
ALTER TABLE lactate_tests ALTER COLUMN lactate_mmol DROP NOT NULL;

-- ============================================
-- STEP 4: Make distance_m nullable (not needed for injuries)
-- ============================================
ALTER TABLE lactate_tests ALTER COLUMN distance_m DROP NOT NULL;

-- ============================================
-- STEP 5: Drop existing CHECK constraints
-- ============================================
ALTER TABLE lactate_tests DROP CONSTRAINT IF EXISTS chk_test_type;
ALTER TABLE lactate_tests DROP CONSTRAINT IF EXISTS chk_lactate_required;
ALTER TABLE lactate_tests DROP CONSTRAINT IF EXISTS chk_race_time_only_for_races;

-- ============================================
-- STEP 6: Add injury-specific columns
-- ============================================
ALTER TABLE lactate_tests ADD COLUMN IF NOT EXISTS injury_location TEXT;
ALTER TABLE lactate_tests ADD COLUMN IF NOT EXISTS injury_severity INTEGER;
ALTER TABLE lactate_tests ADD COLUMN IF NOT EXISTS injury_status TEXT;

-- ============================================
-- STEP 7: Add updated CHECK constraints
-- ============================================

-- test_type must be one of: lactate, race, injury
ALTER TABLE lactate_tests ADD CONSTRAINT chk_test_type
    CHECK (test_type IN ('lactate', 'race', 'injury'));

-- injury_severity must be 1-3 when set
ALTER TABLE lactate_tests ADD CONSTRAINT chk_injury_severity_range
    CHECK (injury_severity IS NULL OR (injury_severity >= 1 AND injury_severity <= 3));

-- injury_status must be valid value when set
ALTER TABLE lactate_tests ADD CONSTRAINT chk_injury_status_values
    CHECK (injury_status IS NULL OR injury_status IN ('active', 'recovering', 'resolved'));

-- Lactate value required only for lactate tests
ALTER TABLE lactate_tests ADD CONSTRAINT chk_lactate_required
    CHECK (test_type != 'lactate' OR lactate_mmol IS NOT NULL);

-- Distance required only for lactate and race (not injury)
ALTER TABLE lactate_tests ADD CONSTRAINT chk_distance_required
    CHECK (test_type = 'injury' OR distance_m IS NOT NULL);

-- Race time only for races
ALTER TABLE lactate_tests ADD CONSTRAINT chk_race_time_only_for_races
    CHECK (test_type = 'race' OR race_time_seconds IS NULL);

-- Injury location required for injuries
ALTER TABLE lactate_tests ADD CONSTRAINT chk_injury_location_required
    CHECK (test_type != 'injury' OR injury_location IS NOT NULL);

-- Injury severity required for injuries
ALTER TABLE lactate_tests ADD CONSTRAINT chk_injury_severity_required
    CHECK (test_type != 'injury' OR injury_severity IS NOT NULL);

-- Injury status required for injuries
ALTER TABLE lactate_tests ADD CONSTRAINT chk_injury_status_required
    CHECK (test_type != 'injury' OR injury_status IS NOT NULL);

-- Injury fields only allowed for injuries
ALTER TABLE lactate_tests ADD CONSTRAINT chk_injury_fields_only_for_injuries
    CHECK (test_type = 'injury' OR (injury_location IS NULL AND injury_severity IS NULL AND injury_status IS NULL));

-- ============================================
-- STEP 8: Create indexes for efficient queries
-- ============================================
CREATE INDEX IF NOT EXISTS idx_lactate_tests_races
    ON lactate_tests(athlete_id, test_type, test_date DESC)
    WHERE test_type = 'race';

CREATE INDEX IF NOT EXISTS idx_lactate_tests_injuries
    ON lactate_tests(athlete_id, test_type, test_date DESC)
    WHERE test_type = 'injury';

-- ============================================
-- VERIFICATION QUERY (run after migration)
-- ============================================
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'lactate_tests'
-- ORDER BY ordinal_position;
