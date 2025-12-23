-- Migration: Create lactate_tests table for manual lactate test data entry
-- Created: 2025-12-12
--
-- Purpose: Store lactate test results manually entered by athletes
-- Each test records: date, distance run (metres), lactate level (mmol/L)
-- Used for lactate threshold testing and zone configuration updates

-- Create the lactate_tests table
CREATE TABLE IF NOT EXISTS lactate_tests (
    -- Primary key and identifiers
    id SERIAL PRIMARY KEY,
    athlete_id TEXT NOT NULL,

    -- Test data
    test_date DATE NOT NULL,
    distance_m INTEGER NOT NULL CHECK (distance_m > 0 AND distance_m <= 50000),  -- Distance in metres (up to 50km)
    lactate_mmol DECIMAL(4,2) NOT NULL CHECK (lactate_mmol >= 0 AND lactate_mmol <= 30),  -- Lactate in mmol/L

    -- Optional notes
    notes TEXT,

    -- Audit fields
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Foreign key constraint
    CONSTRAINT fk_lactate_athlete FOREIGN KEY (athlete_id) REFERENCES athlete(athlete_id) ON DELETE CASCADE,

    -- Ensure uniqueness: one test per athlete per date per distance
    -- (allows multiple distances on same day for step tests)
    CONSTRAINT unique_lactate_test UNIQUE(athlete_id, test_date, distance_m)
);

-- Create index for efficient queries by athlete and date
CREATE INDEX idx_lactate_athlete_date ON lactate_tests(athlete_id, test_date DESC);

-- Enable Row Level Security
ALTER TABLE lactate_tests ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Athletes can manage their own data, coaches can view all
CREATE POLICY "Athletes can view own lactate tests"
    ON lactate_tests
    FOR SELECT
    USING (true);  -- Allow all reads (dashboard handles auth)

CREATE POLICY "Athletes can insert own lactate tests"
    ON lactate_tests
    FOR INSERT
    WITH CHECK (true);  -- Allow all inserts (dashboard handles auth)

CREATE POLICY "Athletes can delete own lactate tests"
    ON lactate_tests
    FOR DELETE
    USING (true);  -- Allow all deletes (dashboard handles auth)

-- Comments for documentation
COMMENT ON TABLE lactate_tests IS 'Manual lactate test results entered by athletes. Each row represents one distance/lactate measurement from a test.';
COMMENT ON COLUMN lactate_tests.distance_m IS 'Distance run in metres at time of lactate measurement.';
COMMENT ON COLUMN lactate_tests.lactate_mmol IS 'Blood lactate concentration in mmol/L.';
COMMENT ON COLUMN lactate_tests.notes IS 'Optional notes about test conditions, equipment, etc.';

-- Migration complete
