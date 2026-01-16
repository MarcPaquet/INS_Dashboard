-- =============================================================================
-- Migration: COMPLETE ROLLBACK of fix_security_issues.sql
-- Created: January 16, 2026
-- Purpose: Undo ALL changes from the security migration
--
-- RUN THIS IN NEXT SESSION TO FULLY RESTORE DATABASE STATE
-- =============================================================================

-- =============================================================================
-- SECTION 1: Drop ALL RLS policies on affected tables
-- =============================================================================

DROP POLICY IF EXISTS "Block direct API access to activity_zone_time" ON activity_zone_time;
DROP POLICY IF EXISTS "Allow service role access to activity_zone_time" ON activity_zone_time;

DROP POLICY IF EXISTS "Block direct API access to weekly_monotony_strain" ON weekly_monotony_strain;
DROP POLICY IF EXISTS "Allow service role access to weekly_monotony_strain" ON weekly_monotony_strain;

DROP POLICY IF EXISTS "Block direct API access to lactate_tests" ON lactate_tests;
DROP POLICY IF EXISTS "Allow service role access to lactate_tests" ON lactate_tests;
DROP POLICY IF EXISTS "Allow all access to lactate_tests" ON lactate_tests;

-- =============================================================================
-- SECTION 2: DISABLE RLS on all affected tables
-- =============================================================================

ALTER TABLE activity_zone_time DISABLE ROW LEVEL SECURITY;
ALTER TABLE weekly_monotony_strain DISABLE ROW LEVEL SECURITY;
ALTER TABLE lactate_tests DISABLE ROW LEVEL SECURITY;

-- =============================================================================
-- SECTION 3: RESET function search_path (remove the SET search_path = '')
-- This may be causing function calls to fail
-- =============================================================================

ALTER FUNCTION calculate_zone_time_for_activity(TEXT) RESET search_path;
ALTER FUNCTION recalculate_all_zone_times() RESET search_path;
ALTER FUNCTION archive_personal_record() RESET search_path;
ALTER FUNCTION get_athlete_zones_for_date(TEXT, DATE) RESET search_path;
ALTER FUNCTION refresh_pace_zones_view() RESET search_path;
ALTER FUNCTION recalculate_zones_for_affected_activities() RESET search_path;
ALTER FUNCTION backfill_monotony_strain() RESET search_path;
ALTER FUNCTION refresh_all_zone_views() RESET search_path;
ALTER FUNCTION recalculate_monotony_strain_for_athlete(TEXT) RESET search_path;
ALTER FUNCTION calculate_monotony_strain_for_week(TEXT, DATE) RESET search_path;

-- =============================================================================
-- SECTION 4: Restore access to materialized views
-- =============================================================================

GRANT ALL ON activity_pace_zones TO anon, authenticated, service_role;
GRANT ALL ON weekly_zone_time TO anon, authenticated, service_role;

-- =============================================================================
-- SECTION 5: Verification queries
-- =============================================================================

-- Check RLS is disabled
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
AND tablename IN ('activity_zone_time', 'weekly_monotony_strain', 'lactate_tests');

-- Check function search_path is reset (should show NULL or empty proconfig)
SELECT proname, proconfig
FROM pg_proc
WHERE proname IN (
    'calculate_zone_time_for_activity',
    'recalculate_all_zone_times',
    'archive_personal_record',
    'get_athlete_zones_for_date',
    'refresh_pace_zones_view',
    'recalculate_zones_for_affected_activities',
    'backfill_monotony_strain',
    'refresh_all_zone_views',
    'recalculate_monotony_strain_for_athlete',
    'calculate_monotony_strain_for_week'
);

-- Check table access works
SELECT 'activity_metadata' as t, COUNT(*) FROM activity_metadata
UNION ALL SELECT 'activity', COUNT(*) FROM activity
UNION ALL SELECT 'wellness', COUNT(*) FROM wellness
UNION ALL SELECT 'athlete', COUNT(*) FROM athlete
UNION ALL SELECT 'users', COUNT(*) FROM users
UNION ALL SELECT 'activity_zone_time', COUNT(*) FROM activity_zone_time
UNION ALL SELECT 'weekly_monotony_strain', COUNT(*) FROM weekly_monotony_strain
UNION ALL SELECT 'lactate_tests', COUNT(*) FROM lactate_tests;

-- =============================================================================
