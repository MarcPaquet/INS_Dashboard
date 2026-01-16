-- =============================================================================
-- Migration: ROLLBACK fix_security_issues.sql
-- Created: January 16, 2026
-- Purpose: Undo the RLS policies that are blocking ALL database access
--
-- CONTEXT:
-- The fix_security_issues.sql migration created RLS policies with USING(false)
-- that block ALL access, including from service_role key on ShinyApps.io.
-- This rollback restores access to the database.
-- =============================================================================

-- =============================================================================
-- SECTION 1: Drop blocking RLS policies
-- =============================================================================

-- Drop the blocking policy on activity_zone_time
DROP POLICY IF EXISTS "Block direct API access to activity_zone_time" ON activity_zone_time;

-- Drop the blocking policy on weekly_monotony_strain
DROP POLICY IF EXISTS "Block direct API access to weekly_monotony_strain" ON weekly_monotony_strain;

-- Drop the blocking policy on lactate_tests
DROP POLICY IF EXISTS "Block direct API access to lactate_tests" ON lactate_tests;

-- =============================================================================
-- SECTION 2: Create permissive policies for service_role access
-- These policies allow the service_role key to access the tables
-- while still blocking anon/authenticated direct API access
-- =============================================================================

-- Policy for activity_zone_time - allow service_role full access
CREATE POLICY "Allow service role access to activity_zone_time"
    ON activity_zone_time
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Policy for weekly_monotony_strain - allow service_role full access
CREATE POLICY "Allow service role access to weekly_monotony_strain"
    ON weekly_monotony_strain
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Policy for lactate_tests - allow service_role full access
CREATE POLICY "Allow service role access to lactate_tests"
    ON lactate_tests
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- =============================================================================
-- SECTION 3: Re-grant access to materialized views
-- =============================================================================

-- Grant SELECT on materialized views to all roles (service_role included)
GRANT SELECT ON activity_pace_zones TO anon, authenticated, service_role;
GRANT SELECT ON weekly_zone_time TO anon, authenticated, service_role;

-- =============================================================================
-- VERIFICATION: Run these after the rollback to confirm access is restored
-- =============================================================================

-- SELECT COUNT(*) FROM activity_zone_time;
-- SELECT COUNT(*) FROM weekly_monotony_strain;
-- SELECT COUNT(*) FROM lactate_tests;

-- =============================================================================
