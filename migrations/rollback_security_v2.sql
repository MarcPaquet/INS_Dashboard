-- =============================================================================
-- Migration: ROLLBACK v2 - Complete RLS Disable
-- Created: January 16, 2026
-- Purpose: Completely disable RLS on problematic tables to restore access
-- =============================================================================

-- =============================================================================
-- SECTION 1: Drop ALL policies on affected tables
-- =============================================================================

-- Drop all policies on activity_zone_time
DROP POLICY IF EXISTS "Block direct API access to activity_zone_time" ON activity_zone_time;
DROP POLICY IF EXISTS "Allow service role access to activity_zone_time" ON activity_zone_time;

-- Drop all policies on weekly_monotony_strain
DROP POLICY IF EXISTS "Block direct API access to weekly_monotony_strain" ON weekly_monotony_strain;
DROP POLICY IF EXISTS "Allow service role access to weekly_monotony_strain" ON weekly_monotony_strain;

-- Drop all policies on lactate_tests
DROP POLICY IF EXISTS "Block direct API access to lactate_tests" ON lactate_tests;
DROP POLICY IF EXISTS "Allow service role access to lactate_tests" ON lactate_tests;
DROP POLICY IF EXISTS "Allow all access to lactate_tests" ON lactate_tests;

-- =============================================================================
-- SECTION 2: DISABLE RLS entirely on these tables
-- =============================================================================

ALTER TABLE activity_zone_time DISABLE ROW LEVEL SECURITY;
ALTER TABLE weekly_monotony_strain DISABLE ROW LEVEL SECURITY;
ALTER TABLE lactate_tests DISABLE ROW LEVEL SECURITY;

-- =============================================================================
-- SECTION 3: Ensure materialized views are accessible
-- =============================================================================

GRANT SELECT ON activity_pace_zones TO anon, authenticated, service_role;
GRANT SELECT ON weekly_zone_time TO anon, authenticated, service_role;

-- =============================================================================
-- SECTION 4: Verify access is restored (run these manually after)
-- =============================================================================

-- Check RLS status on tables
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
AND tablename IN ('activity_zone_time', 'weekly_monotony_strain', 'lactate_tests');

-- Check counts to verify access
SELECT 'activity_zone_time' as table_name, COUNT(*) as row_count FROM activity_zone_time
UNION ALL
SELECT 'weekly_monotony_strain', COUNT(*) FROM weekly_monotony_strain
UNION ALL
SELECT 'lactate_tests', COUNT(*) FROM lactate_tests;
