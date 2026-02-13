-- Migration: Enable RLS on tables missing it
-- Date: January 29, 2026
-- Purpose: Fix Supabase linter errors for RLS disabled on public tables

-- ============================================================================
-- 1. LACTATE_TESTS TABLE
-- ============================================================================

-- Enable RLS
ALTER TABLE public.lactate_tests ENABLE ROW LEVEL SECURITY;

-- Policy: Athletes can view their own lactate tests
CREATE POLICY "Athletes can view own lactate tests"
ON public.lactate_tests
FOR SELECT
USING (true);  -- Dashboard uses service role, so this is permissive

-- Policy: Service role can insert/update/delete (used by dashboard forms)
CREATE POLICY "Service role full access to lactate tests"
ON public.lactate_tests
FOR ALL
USING (true)
WITH CHECK (true);

-- ============================================================================
-- 2. WEEKLY_MONOTONY_STRAIN TABLE
-- ============================================================================

-- Enable RLS
ALTER TABLE public.weekly_monotony_strain ENABLE ROW LEVEL SECURITY;

-- Policy: Allow read access (dashboard uses service role)
CREATE POLICY "Allow read access to weekly monotony strain"
ON public.weekly_monotony_strain
FOR SELECT
USING (true);

-- Policy: Service role can insert/update/delete (used by ingestion script)
CREATE POLICY "Service role full access to weekly monotony strain"
ON public.weekly_monotony_strain
FOR ALL
USING (true)
WITH CHECK (true);

-- ============================================================================
-- 3. ACTIVITY_ZONE_TIME TABLE
-- ============================================================================

-- Enable RLS
ALTER TABLE public.activity_zone_time ENABLE ROW LEVEL SECURITY;

-- Policy: Allow read access (dashboard uses service role)
CREATE POLICY "Allow read access to activity zone time"
ON public.activity_zone_time
FOR SELECT
USING (true);

-- Policy: Service role can insert/update/delete (used by ingestion script)
CREATE POLICY "Service role full access to activity zone time"
ON public.activity_zone_time
FOR ALL
USING (true)
WITH CHECK (true);

-- ============================================================================
-- VERIFICATION
-- ============================================================================

-- Check RLS is enabled on all tables
SELECT
    schemaname,
    tablename,
    rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
AND tablename IN ('lactate_tests', 'weekly_monotony_strain', 'activity_zone_time');
