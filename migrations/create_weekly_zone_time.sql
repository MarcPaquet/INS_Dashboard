-- =============================================================================
-- Materialized View: weekly_zone_time
-- Purpose: Aggregate zone time per athlete per week for longitudinal analysis
-- Depends on: activity_zone_time materialized view
-- Created: December 12, 2025
--
-- Refresh: SELECT refresh_all_zone_views();
-- =============================================================================

DROP MATERIALIZED VIEW IF EXISTS weekly_zone_time CASCADE;

CREATE MATERIALIZED VIEW weekly_zone_time AS
SELECT
    athlete_id,
    DATE_TRUNC('week', activity_date)::DATE AS week_start,
    SUM(zone_1_minutes) AS zone_1_minutes,
    SUM(zone_2_minutes) AS zone_2_minutes,
    SUM(zone_3_minutes) AS zone_3_minutes,
    SUM(zone_4_minutes) AS zone_4_minutes,
    SUM(zone_5_minutes) AS zone_5_minutes,
    SUM(zone_6_minutes) AS zone_6_minutes,
    SUM(total_zone_minutes) AS total_minutes,
    COUNT(*) AS activity_count
FROM activity_zone_time
WHERE total_zone_minutes > 0
GROUP BY athlete_id, DATE_TRUNC('week', activity_date)::DATE;

-- Unique index required for CONCURRENTLY refresh
CREATE UNIQUE INDEX idx_weekly_zone_time_pk ON weekly_zone_time(athlete_id, week_start);

-- Performance indexes
CREATE INDEX idx_weekly_zone_time_athlete ON weekly_zone_time(athlete_id, week_start DESC);

COMMENT ON MATERIALIZED VIEW weekly_zone_time IS
'Weekly aggregation of zone time per athlete.
Depends on activity_zone_time materialized view.
Refresh after imports: SELECT refresh_all_zone_views();';

-- =============================================================================
-- Function: refresh_all_zone_views
-- Purpose: Refresh both zone materialized views in correct dependency order
-- Usage: SELECT refresh_all_zone_views();
-- =============================================================================

CREATE OR REPLACE FUNCTION refresh_all_zone_views()
RETURNS void AS $$
BEGIN
    -- First refresh activity-level view
    REFRESH MATERIALIZED VIEW CONCURRENTLY activity_zone_time;
    -- Then refresh weekly aggregation (depends on activity_zone_time)
    REFRESH MATERIALIZED VIEW CONCURRENTLY weekly_zone_time;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION refresh_all_zone_views() IS
'Refreshes both zone time materialized views in dependency order.
Call this after bulk imports or daily ingestion.';
