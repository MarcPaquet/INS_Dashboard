-- Migration: Add test_type and race_time columns to lactate_tests table
-- Date: 2026-01-16
-- Purpose: Allow the lactate_tests table to store both lactate tests AND race results

-- Step 1: Add test_type column to distinguish lactate tests from races
-- Default to 'lactate' so existing records are preserved
ALTER TABLE lactate_tests
ADD COLUMN test_type TEXT NOT NULL DEFAULT 'lactate';

-- Step 2: Add check constraint for test_type values
ALTER TABLE lactate_tests
ADD CONSTRAINT chk_test_type CHECK (test_type IN ('lactate', 'race'));

-- Step 3: Add race_time column for race results (stored as seconds with decimals for precision)
-- This allows times like 42:30.55 to be stored as 2550.55
ALTER TABLE lactate_tests
ADD COLUMN race_time_seconds DECIMAL(10,2) NULL;

-- Step 4: Make lactate_mmol nullable (required only for lactate tests, not races)
-- First, we need to drop the existing NOT NULL constraint
ALTER TABLE lactate_tests
ALTER COLUMN lactate_mmol DROP NOT NULL;

-- Step 5: Add constraint - lactate value required only when type is 'lactate'
-- This ensures data integrity: lactate tests must have lactate values
ALTER TABLE lactate_tests
ADD CONSTRAINT chk_lactate_required
CHECK (test_type != 'lactate' OR lactate_mmol IS NOT NULL);

-- Step 6: Add constraint - race_time should only be set for races
-- This prevents confusion: lactate tests shouldn't have race times
ALTER TABLE lactate_tests
ADD CONSTRAINT chk_race_time_only_for_races
CHECK (test_type = 'race' OR race_time_seconds IS NULL);

-- Step 7: Create index for efficient race queries
-- This speeds up the race dropdown in "Résumé de période"
CREATE INDEX idx_lactate_tests_races ON lactate_tests(athlete_id, test_type, test_date DESC)
WHERE test_type = 'race';

-- Verification query (run after migration to confirm success):
-- SELECT column_name, data_type, is_nullable, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'lactate_tests'
-- ORDER BY ordinal_position;
