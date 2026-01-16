-- ============================================================================
-- Migration: Update Personal Records Schema
-- Created: 2025-12-29
-- Purpose: Add new distances and support milliseconds
-- ============================================================================

-- Step 1: Drop the constraint on distance_type to allow new values
ALTER TABLE personal_records DROP CONSTRAINT IF EXISTS personal_records_distance_type_check;

-- Step 2: Add new constraint with all distances
ALTER TABLE personal_records ADD CONSTRAINT personal_records_distance_type_check CHECK (
    distance_type IN (
        '400m',
        '800m',
        '1000m',
        '1500m',
        '1mile',
        '2000m',
        '3000m',
        '2000m_steeple',
        '3000m_steeple',
        '5000m',
        '10000m',
        '5km',
        '10km',
        'half_marathon',
        'marathon'
    )
);

-- Step 3: Change time_seconds from INTEGER to DECIMAL to support milliseconds
-- First, drop the check constraint
ALTER TABLE personal_records DROP CONSTRAINT IF EXISTS personal_records_time_seconds_check;

-- Change column type
ALTER TABLE personal_records ALTER COLUMN time_seconds TYPE DECIMAL(10,3);

-- Re-add the check constraint
ALTER TABLE personal_records ADD CONSTRAINT personal_records_time_seconds_check
    CHECK (time_seconds > 0);

-- Step 4: Update history table as well
ALTER TABLE personal_records_history ALTER COLUMN time_seconds TYPE DECIMAL(10,3);

-- Step 5: Verify the changes
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'personal_records'
ORDER BY ordinal_position;

-- ============================================================================
-- IMPORTANT: Run this migration in Supabase SQL Editor
-- ============================================================================
