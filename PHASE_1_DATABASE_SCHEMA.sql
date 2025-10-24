-- ============================================================================
-- PHASE 1: Database Schema Updates
-- Date: October 22, 2025
-- Purpose: Support Phase 1 weather tracking and data quality improvements
-- ============================================================================

-- 1. Add weather tracking columns (if not already added)
-- ALTER TABLE public.activity_metadata 
-- ADD COLUMN weather_source TEXT,      -- 'archive', 'forecast', NULL
-- ADD COLUMN weather_error TEXT;       -- Error message if weather failed

-- 2. Weather source index (RECOMMENDED - Performance)
-- For fast queries like "how many activities use forecast vs archive?"
CREATE INDEX IF NOT EXISTS idx_metadata_weather_source 
ON public.activity_metadata USING btree (weather_source) 
TABLESPACE pg_default;

-- 3. Weather source constraint (RECOMMENDED - Data Quality)
-- Prevents typos like 'Archive' vs 'archive'
ALTER TABLE public.activity_metadata
ADD CONSTRAINT IF NOT EXISTS check_weather_source 
CHECK (weather_source IN ('archive', 'forecast') OR weather_source IS NULL);

-- 4. Additional Phase 1 indexes for analytics
-- Index for finding activities with missing weather (outdoor activities without weather)
CREATE INDEX IF NOT EXISTS idx_metadata_weather_missing 
ON public.activity_metadata(date) 
WHERE weather_temp_c IS NULL AND start_lat IS NOT NULL;

-- Index for weather error analysis
CREATE INDEX IF NOT EXISTS idx_metadata_weather_errors 
ON public.activity_metadata(weather_error) 
WHERE weather_error IS NOT NULL;

-- 5. HR completeness analysis index
-- For finding activities with HR monitor but missing avg_hr
CREATE INDEX IF NOT EXISTS idx_metadata_hr_missing 
ON public.activity_metadata(date) 
WHERE avg_hr IS NULL;

-- ============================================================================
-- VALIDATION QUERIES - Run after schema updates
-- ============================================================================

-- Query 1: Weather source distribution
SELECT 
  weather_source,
  COUNT(*) as count,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as percentage
FROM activity_metadata
WHERE start_lat IS NOT NULL  -- Only outdoor activities
GROUP BY weather_source
ORDER BY count DESC;

-- Query 2: Weather completeness by month
SELECT 
  DATE_TRUNC('month', date) as month,
  COUNT(*) as outdoor_activities,
  COUNT(weather_temp_c) as with_weather,
  ROUND(100.0 * COUNT(weather_temp_c) / COUNT(*), 1) as completeness_pct
FROM activity_metadata
WHERE start_lat IS NOT NULL
GROUP BY DATE_TRUNC('month', date)
ORDER BY month DESC;

-- Query 3: Weather errors analysis
SELECT 
  weather_error,
  COUNT(*) as occurrences,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as percentage
FROM activity_metadata
WHERE weather_error IS NOT NULL
GROUP BY weather_error
ORDER BY occurrences DESC;

-- Query 4: HR completeness analysis
SELECT 
  'Total activities' as metric,
  COUNT(*) as count
FROM activity_metadata
UNION ALL
SELECT 
  'With HR monitor (estimated)',
  COUNT(*)
FROM activity_metadata a
WHERE EXISTS (
  SELECT 1 FROM activity r 
  WHERE r.activity_id = a.activity_id 
    AND r.heartrate IS NOT NULL
)
UNION ALL
SELECT 
  'With avg_hr',
  COUNT(*)
FROM activity_metadata
WHERE avg_hr IS NOT NULL;

-- ============================================================================
-- PERFORMANCE MONITORING
-- ============================================================================

-- Monitor index usage
SELECT 
  schemaname,
  tablename,
  indexname,
  idx_scan as index_scans,
  idx_tup_read as tuples_read,
  idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes 
WHERE tablename = 'activity_metadata'
ORDER BY idx_scan DESC;

-- Monitor constraint violations (should be 0)
-- This query will show if any data violates the weather_source constraint
SELECT 
  weather_source,
  COUNT(*) as violations
FROM activity_metadata
WHERE weather_source NOT IN ('archive', 'forecast') 
  AND weather_source IS NOT NULL
GROUP BY weather_source;
