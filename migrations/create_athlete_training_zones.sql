-- Migration: Create athlete_training_zones table for versioned training zones configuration
-- Created: 2024-11-15
--
-- Purpose: Store historical training zones configurations for athletes
-- Each athlete can have multiple zone configurations with different effective dates
-- Zones are versioned (append-only) to support historical analysis
--
-- Features:
-- - Versioned zones with user-selectable effective dates
-- - Support for HR (bpm), Pace (min/km), and Lactate (mmol/L) metrics
-- - All metrics are optional (nullable)
-- - 1-10 zones configurable per athlete
-- - Temporal queries to find zones for any workout date
-- - Access control: Coaches can configure any athlete, athletes only themselves

-- Create the athlete_training_zones table
CREATE TABLE IF NOT EXISTS athlete_training_zones (
    -- Primary key and identifiers
    zone_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    athlete_id TEXT NOT NULL,

    -- Versioning fields
    effective_from_date DATE NOT NULL,  -- User-selected, can be backdated to test dates
    num_zones INTEGER NOT NULL CHECK (num_zones BETWEEN 1 AND 10),
    zone_number INTEGER NOT NULL CHECK (zone_number BETWEEN 1 AND 10),

    -- Heart Rate zones (optional)
    hr_min DECIMAL(5,1) CHECK (hr_min >= 0 AND hr_min <= 250),
    hr_max DECIMAL(5,1) CHECK (hr_max >= 0 AND hr_max <= 250),

    -- Pace zones (stored as seconds per km, optional)
    -- Input format will be MM:SS, converted to seconds for storage
    pace_min_sec_per_km DECIMAL(6,2) CHECK (pace_min_sec_per_km >= 0 AND pace_min_sec_per_km <= 3600),
    pace_max_sec_per_km DECIMAL(6,2) CHECK (pace_max_sec_per_km >= 0 AND pace_max_sec_per_km <= 3600),

    -- Lactate zones (optional)
    lactate_min DECIMAL(4,2) CHECK (lactate_min >= 0 AND lactate_min <= 30),
    lactate_max DECIMAL(4,2) CHECK (lactate_max >= 0 AND lactate_max <= 30),

    -- Audit fields
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Foreign key constraint
    CONSTRAINT fk_athlete FOREIGN KEY (athlete_id) REFERENCES athlete(athlete_id) ON DELETE CASCADE,

    -- Ensure uniqueness: one zone configuration per athlete per date per zone number
    CONSTRAINT unique_athlete_date_zone UNIQUE(athlete_id, effective_from_date, zone_number),

    -- Ensure zone_number doesn't exceed num_zones
    CONSTRAINT valid_zone_number CHECK (zone_number <= num_zones),

    -- Ensure min values are less than or equal to max values
    CONSTRAINT valid_hr_range CHECK (hr_min IS NULL OR hr_max IS NULL OR hr_min <= hr_max),
    CONSTRAINT valid_pace_range CHECK (pace_min_sec_per_km IS NULL OR pace_max_sec_per_km IS NULL OR pace_min_sec_per_km <= pace_max_sec_per_km),
    CONSTRAINT valid_lactate_range CHECK (lactate_min IS NULL OR lactate_max IS NULL OR lactate_min <= lactate_max)
);

-- Create index for efficient temporal queries
-- When looking up zones for a workout, we need: athlete_id + effective_from_date <= workout_date
CREATE INDEX idx_zones_athlete_date ON athlete_training_zones(athlete_id, effective_from_date DESC);

-- Create index for efficient zone retrieval
CREATE INDEX idx_zones_lookup ON athlete_training_zones(athlete_id, effective_from_date, zone_number);

-- Enable Row Level Security
ALTER TABLE athlete_training_zones ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Coaches can view and manage zones for all their athletes
CREATE POLICY "Coaches can view all athlete zones"
    ON athlete_training_zones
    FOR SELECT
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM athlete a
            WHERE a.athlete_id = athlete_training_zones.athlete_id
            AND a.coach_id = auth.jwt() ->> 'email'
        )
        OR
        athlete_id = auth.jwt() ->> 'email'
    );

CREATE POLICY "Coaches can insert zones for their athletes"
    ON athlete_training_zones
    FOR INSERT
    TO authenticated
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM athlete a
            WHERE a.athlete_id = athlete_training_zones.athlete_id
            AND a.coach_id = auth.jwt() ->> 'email'
        )
        OR
        athlete_id = auth.jwt() ->> 'email'
    );

-- Note: No UPDATE or DELETE policies - zones are append-only (versioned)
-- Historical integrity is maintained by never modifying or deleting existing records

-- Helper function: Get most recent zones for an athlete as of a specific date
CREATE OR REPLACE FUNCTION get_athlete_zones_for_date(
    p_athlete_id TEXT,
    p_workout_date DATE
)
RETURNS TABLE (
    zone_number INTEGER,
    hr_min DECIMAL,
    hr_max DECIMAL,
    pace_min_sec_per_km DECIMAL,
    pace_max_sec_per_km DECIMAL,
    lactate_min DECIMAL,
    lactate_max DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        z.zone_number,
        z.hr_min,
        z.hr_max,
        z.pace_min_sec_per_km,
        z.pace_max_sec_per_km,
        z.lactate_min,
        z.lactate_max
    FROM athlete_training_zones z
    WHERE z.athlete_id = p_athlete_id
    AND z.effective_from_date <= p_workout_date
    AND z.effective_from_date = (
        -- Get the most recent effective_from_date for this athlete before/on the workout date
        SELECT MAX(effective_from_date)
        FROM athlete_training_zones
        WHERE athlete_id = p_athlete_id
        AND effective_from_date <= p_workout_date
    )
    ORDER BY z.zone_number;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

-- Grant execute permission on helper function
GRANT EXECUTE ON FUNCTION get_athlete_zones_for_date(TEXT, DATE) TO authenticated;

-- Comments for documentation
COMMENT ON TABLE athlete_training_zones IS 'Versioned training zones configuration for athletes. Append-only table for historical tracking.';
COMMENT ON COLUMN athlete_training_zones.effective_from_date IS 'User-selected date when these zones become active. Can be backdated to test dates.';
COMMENT ON COLUMN athlete_training_zones.num_zones IS 'Total number of active zones for this configuration (1-10). All 10 zones stored but only num_zones are active.';
COMMENT ON COLUMN athlete_training_zones.pace_min_sec_per_km IS 'Minimum pace in seconds per kilometer. UI converts MM:SS format.';
COMMENT ON COLUMN athlete_training_zones.pace_max_sec_per_km IS 'Maximum pace in seconds per kilometer. UI converts MM:SS format.';

-- Migration complete
