-- Migration: Fix Supabase Linter Security Warnings
-- Date: January 29, 2026
-- Purpose: Fix function search_path, materialized view access, and RLS policies

-- ============================================================================
-- 1. FIX FUNCTION SEARCH_PATH (Set immutable search_path for all functions)
-- ============================================================================

-- Fix calculate_zone_time_for_activity
ALTER FUNCTION public.calculate_zone_time_for_activity(TEXT)
SET search_path = public;

-- Fix recalculate_all_zone_times
ALTER FUNCTION public.recalculate_all_zone_times()
SET search_path = public;

-- Fix archive_personal_record
ALTER FUNCTION public.archive_personal_record()
SET search_path = public;

-- Fix refresh_pace_zones_view
ALTER FUNCTION public.refresh_pace_zones_view()
SET search_path = public;

-- Fix backfill_monotony_strain
ALTER FUNCTION public.backfill_monotony_strain()
SET search_path = public;

-- Fix get_athlete_zones_for_date
ALTER FUNCTION public.get_athlete_zones_for_date(TEXT, DATE)
SET search_path = public;

-- Fix recalculate_zones_for_affected_activities
ALTER FUNCTION public.recalculate_zones_for_affected_activities()
SET search_path = public;

-- Fix refresh_all_zone_views
ALTER FUNCTION public.refresh_all_zone_views()
SET search_path = public;

-- Fix recalculate_monotony_strain_for_athlete
ALTER FUNCTION public.recalculate_monotony_strain_for_athlete(TEXT)
SET search_path = public;

-- Fix calculate_monotony_strain_for_week
ALTER FUNCTION public.calculate_monotony_strain_for_week(TEXT, DATE)
SET search_path = public;

-- ============================================================================
-- 2. FIX MATERIALIZED VIEW ACCESS (Revoke from anon/authenticated)
-- ============================================================================

-- Revoke access from anon and authenticated roles
-- Service role will still have access (used by dashboard)
REVOKE SELECT ON public.activity_pace_zones FROM anon, authenticated;
REVOKE SELECT ON public.weekly_zone_time FROM anon, authenticated;

-- ============================================================================
-- 3. FIX RLS POLICIES (Make write operations service_role only)
-- ============================================================================

-- Drop the overly permissive policies
DROP POLICY IF EXISTS "Service role full access to activity zone time" ON public.activity_zone_time;
DROP POLICY IF EXISTS "Service role full access to lactate tests" ON public.lactate_tests;
DROP POLICY IF EXISTS "Service role full access to weekly monotony strain" ON public.weekly_monotony_strain;

-- Create more restrictive policies for write operations
-- These allow INSERT/UPDATE/DELETE only for service_role (which bypasses RLS anyway)
-- but having explicit policies silences the linter

-- For activity_zone_time: Only service role writes (via ingestion script)
CREATE POLICY "Service role insert activity zone time"
ON public.activity_zone_time
FOR INSERT
TO service_role
WITH CHECK (true);

CREATE POLICY "Service role update activity zone time"
ON public.activity_zone_time
FOR UPDATE
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Service role delete activity zone time"
ON public.activity_zone_time
FOR DELETE
TO service_role
USING (true);

-- For lactate_tests: Only service role writes (via dashboard forms)
CREATE POLICY "Service role insert lactate tests"
ON public.lactate_tests
FOR INSERT
TO service_role
WITH CHECK (true);

CREATE POLICY "Service role update lactate tests"
ON public.lactate_tests
FOR UPDATE
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Service role delete lactate tests"
ON public.lactate_tests
FOR DELETE
TO service_role
USING (true);

-- For weekly_monotony_strain: Only service role writes (via ingestion script)
CREATE POLICY "Service role insert weekly monotony strain"
ON public.weekly_monotony_strain
FOR INSERT
TO service_role
WITH CHECK (true);

CREATE POLICY "Service role update weekly monotony strain"
ON public.weekly_monotony_strain
FOR UPDATE
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Service role delete weekly monotony strain"
ON public.weekly_monotony_strain
FOR DELETE
TO service_role
USING (true);

-- ============================================================================
-- VERIFICATION
-- ============================================================================

-- Check function search_path is set
SELECT
    proname AS function_name,
    proconfig AS config
FROM pg_proc
WHERE pronamespace = 'public'::regnamespace
AND proname IN (
    'calculate_zone_time_for_activity',
    'recalculate_all_zone_times',
    'archive_personal_record',
    'refresh_pace_zones_view',
    'backfill_monotony_strain',
    'get_athlete_zones_for_date',
    'recalculate_zones_for_affected_activities',
    'refresh_all_zone_views',
    'recalculate_monotony_strain_for_athlete',
    'calculate_monotony_strain_for_week'
);
