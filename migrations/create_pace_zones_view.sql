-- Materialized View for Pace Zone Analysis
-- Pre-calculates time spent in each pace zone for each activity
-- This avoids fetching full timeseries data in the dashboard

-- Drop existing view if it exists
DROP MATERIALIZED VIEW IF EXISTS activity_pace_zones CASCADE;

-- Create materialized view
CREATE MATERIALIZED VIEW activity_pace_zones AS
WITH pace_data AS (
    SELECT 
        activity_id,
        -- Calculate pace in seconds per km from speed (m/s)
        CASE 
            WHEN speed > 0 THEN 1000.0 / speed
            ELSE NULL
        END as pace_sec_per_km
    FROM activity
    WHERE speed IS NOT NULL AND speed > 0
),
zone_counts AS (
    SELECT 
        activity_id,
        -- Count seconds in each pace zone
        COUNT(*) FILTER (WHERE pace_sec_per_km < 180) as zone_under_3_00,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 180 AND pace_sec_per_km < 195) as zone_3_00_3_15,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 195 AND pace_sec_per_km < 210) as zone_3_15_3_30,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 210 AND pace_sec_per_km < 225) as zone_3_30_3_45,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 225 AND pace_sec_per_km < 240) as zone_3_45_4_00,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 240 AND pace_sec_per_km < 255) as zone_4_00_4_15,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 255 AND pace_sec_per_km < 270) as zone_4_15_4_30,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 270 AND pace_sec_per_km < 285) as zone_4_30_4_45,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 285 AND pace_sec_per_km < 300) as zone_4_45_5_00,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 300 AND pace_sec_per_km < 315) as zone_5_00_5_15,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 315 AND pace_sec_per_km < 330) as zone_5_15_5_30,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 330) as zone_over_5_30,
        COUNT(*) as total_seconds
    FROM pace_data
    GROUP BY activity_id
)
SELECT 
    zc.activity_id,
    zc.zone_under_3_00,
    zc.zone_3_00_3_15,
    zc.zone_3_15_3_30,
    zc.zone_3_30_3_45,
    zc.zone_3_45_4_00,
    zc.zone_4_00_4_15,
    zc.zone_4_15_4_30,
    zc.zone_4_30_4_45,
    zc.zone_4_45_5_00,
    zc.zone_5_00_5_15,
    zc.zone_5_15_5_30,
    zc.zone_over_5_30,
    zc.total_seconds,
    -- Join with metadata for filtering
    am.athlete_id,
    am.date,
    am.type
FROM zone_counts zc
JOIN activity_metadata am ON zc.activity_id = am.activity_id
WHERE zc.total_seconds > 0;  -- Only include activities with pace data

-- Create index for fast filtering
CREATE INDEX idx_pace_zones_athlete_date ON activity_pace_zones(athlete_id, date);
CREATE INDEX idx_pace_zones_date ON activity_pace_zones(date);

-- Refresh the view (run this after new activities are imported)
-- REFRESH MATERIALIZED VIEW activity_pace_zones;

COMMENT ON MATERIALIZED VIEW activity_pace_zones IS 
'Pre-calculated pace zone distribution for each activity. 
Refresh after importing new activities: REFRESH MATERIALIZED VIEW activity_pace_zones;';

-- Optional: Create a function to auto-refresh the view
CREATE OR REPLACE FUNCTION refresh_pace_zones_view()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW activity_pace_zones;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION refresh_pace_zones_view() IS 
'Convenience function to refresh pace zones view. Call after bulk imports.';
