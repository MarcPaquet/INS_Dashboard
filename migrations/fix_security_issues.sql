-- =============================================================================
-- Migration: Fix Supabase Security Lint Errors and Warnings
-- Created: January 16, 2026
-- Purpose: Address all security issues flagged by Supabase linter
--
-- This migration fixes:
-- 1. ERRORS: RLS disabled on activity_zone_time and weekly_monotony_strain
-- 2. WARNINGS: Function search_path mutable (10 functions)
-- 3. WARNINGS: Materialized views accessible via API (2 views)
-- 4. WARNING: Overly permissive RLS policy on lactate_tests
--
-- IMPORTANT CONTEXT:
-- - Dashboard uses service_role key which BYPASSES RLS entirely
-- - Dashboard has custom auth (users table with bcrypt), NOT Supabase Auth
-- - auth.uid() is NOT populated by our custom auth system
-- - These policies block direct API access via anon/authenticated roles
-- - All legitimate access goes through service_role (dashboard/ingestion)
-- =============================================================================

-- =============================================================================
-- SECTION 1: Enable RLS on tables missing it (ERRORS)
-- =============================================================================

-- Enable RLS on activity_zone_time
ALTER TABLE activity_zone_time ENABLE ROW LEVEL SECURITY;

-- Enable RLS on weekly_monotony_strain
ALTER TABLE weekly_monotony_strain ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for activity_zone_time
-- Block direct API access - all legitimate access uses service_role key
-- Service role bypasses RLS, so these policies effectively block anon/authenticated
CREATE POLICY "Block direct API access to activity_zone_time"
    ON activity_zone_time
    FOR ALL
    USING (false)
    WITH CHECK (false);

-- Create RLS policies for weekly_monotony_strain
-- Block direct API access - all legitimate access uses service_role key
CREATE POLICY "Block direct API access to weekly_monotony_strain"
    ON weekly_monotony_strain
    FOR ALL
    USING (false)
    WITH CHECK (false);

-- =============================================================================
-- SECTION 2: Fix overly permissive RLS policy on lactate_tests (WARNING)
-- =============================================================================

-- Drop the overly permissive policy
DROP POLICY IF EXISTS "Allow all access to lactate_tests" ON lactate_tests;

-- Drop existing granular policies if they exist (to recreate with secure policy)
DROP POLICY IF EXISTS "Athletes can view own lactate tests" ON lactate_tests;
DROP POLICY IF EXISTS "Athletes can insert own lactate tests" ON lactate_tests;
DROP POLICY IF EXISTS "Athletes can update own lactate tests" ON lactate_tests;
DROP POLICY IF EXISTS "Athletes can delete own lactate tests" ON lactate_tests;

-- Create secure RLS policy for lactate_tests
-- Block direct API access - all legitimate access uses service_role key
CREATE POLICY "Block direct API access to lactate_tests"
    ON lactate_tests
    FOR ALL
    USING (false)
    WITH CHECK (false);

-- =============================================================================
-- SECTION 3: Fix function search_path mutable warnings
-- Add SET search_path = '' for security (prevents search_path injection)
-- =============================================================================

-- Fix calculate_zone_time_for_activity
ALTER FUNCTION calculate_zone_time_for_activity(TEXT) SET search_path = '';

-- Fix recalculate_all_zone_times
ALTER FUNCTION recalculate_all_zone_times() SET search_path = '';

-- Fix archive_personal_record
ALTER FUNCTION archive_personal_record() SET search_path = '';

-- Fix get_athlete_zones_for_date
ALTER FUNCTION get_athlete_zones_for_date(TEXT, DATE) SET search_path = '';

-- Fix refresh_pace_zones_view
ALTER FUNCTION refresh_pace_zones_view() SET search_path = '';

-- Fix recalculate_zones_for_affected_activities
ALTER FUNCTION recalculate_zones_for_affected_activities() SET search_path = '';

-- Fix backfill_monotony_strain
ALTER FUNCTION backfill_monotony_strain() SET search_path = '';

-- Fix refresh_all_zone_views
ALTER FUNCTION refresh_all_zone_views() SET search_path = '';

-- Fix recalculate_monotony_strain_for_athlete
ALTER FUNCTION recalculate_monotony_strain_for_athlete(TEXT) SET search_path = '';

-- Fix calculate_monotony_strain_for_week
ALTER FUNCTION calculate_monotony_strain_for_week(TEXT, DATE) SET search_path = '';

-- =============================================================================
-- SECTION 4: Restrict materialized view access (WARNINGS)
-- Revoke SELECT from anon and authenticated roles on materialized views
-- Dashboard uses service_role which has full access
-- =============================================================================

-- Revoke public access to activity_pace_zones
REVOKE SELECT ON activity_pace_zones FROM anon;
REVOKE SELECT ON activity_pace_zones FROM authenticated;

-- Revoke public access to weekly_zone_time
REVOKE SELECT ON weekly_zone_time FROM anon;
REVOKE SELECT ON weekly_zone_time FROM authenticated;

-- Grant explicit access to service_role (should already have it, but be explicit)
GRANT SELECT ON activity_pace_zones TO service_role;
GRANT SELECT ON weekly_zone_time TO service_role;

-- =============================================================================
-- VERIFICATION QUERIES (run after migration)
-- =============================================================================

-- Check RLS is enabled on all tables
-- SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public' AND tablename IN ('activity_zone_time', 'weekly_monotony_strain', 'lactate_tests');

-- Check function search_path settings
-- SELECT proname, proconfig FROM pg_proc WHERE proname IN ('calculate_zone_time_for_activity', 'recalculate_all_zone_times', 'refresh_all_zone_views');

-- Check materialized view permissions
-- SELECT grantee, privilege_type FROM information_schema.role_table_grants WHERE table_name IN ('activity_pace_zones', 'weekly_zone_time');

-- =============================================================================
-- NOTES
-- =============================================================================
--
-- Auth Warnings (not addressable via SQL):
-- - "Leaked Password Protection Disabled" - Enable in Supabase Dashboard > Auth > Settings
-- - "Insufficient MFA Options" - Enable MFA in Supabase Dashboard > Auth > Settings
--
-- These auth settings must be configured in the Supabase web console, not via SQL.
-- =============================================================================
