-- Personal Records Table for Manual Data Entry
-- Stores athlete personal bests for standard race distances

CREATE TABLE IF NOT EXISTS personal_records (
    record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    athlete_id TEXT NOT NULL REFERENCES athlete(athlete_id) ON DELETE CASCADE,
    distance_type TEXT NOT NULL CHECK (
        distance_type IN (
            '1000m',
            '1500m', 
            '1mile',
            '3000m',
            '5000m',
            '10000m',
            'half_marathon'
        )
    ),
    time_seconds INTEGER NOT NULL CHECK (time_seconds > 0),
    record_date DATE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- One record per athlete per distance
    UNIQUE(athlete_id, distance_type)
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_personal_records_athlete ON personal_records(athlete_id);

-- Optional: History table to track PR progression over time
CREATE TABLE IF NOT EXISTS personal_records_history (
    history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_id UUID NOT NULL,
    athlete_id TEXT NOT NULL,
    distance_type TEXT NOT NULL,
    time_seconds INTEGER NOT NULL,
    record_date DATE,
    notes TEXT,
    archived_at TIMESTAMPTZ DEFAULT NOW()
);

-- Trigger to archive old records when updating
CREATE OR REPLACE FUNCTION archive_personal_record()
RETURNS TRIGGER AS $$
BEGIN
    -- Only archive if time actually changed
    IF OLD.time_seconds != NEW.time_seconds THEN
        INSERT INTO personal_records_history (
            record_id,
            athlete_id,
            distance_type,
            time_seconds,
            record_date,
            notes
        ) VALUES (
            OLD.record_id,
            OLD.athlete_id,
            OLD.distance_type,
            OLD.time_seconds,
            OLD.record_date,
            OLD.notes
        );
    END IF;
    
    -- Update the updated_at timestamp
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER personal_records_archive_trigger
    BEFORE UPDATE ON personal_records
    FOR EACH ROW
    EXECUTE FUNCTION archive_personal_record();

-- Enable RLS (Row Level Security)
ALTER TABLE personal_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE personal_records_history ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Athletes can only see/modify their own records
CREATE POLICY "Athletes can view own records"
    ON personal_records FOR SELECT
    USING (athlete_id = current_setting('request.jwt.claims', true)::json->>'sub');

CREATE POLICY "Athletes can insert own records"
    ON personal_records FOR INSERT
    WITH CHECK (athlete_id = current_setting('request.jwt.claims', true)::json->>'sub');

CREATE POLICY "Athletes can update own records"
    ON personal_records FOR UPDATE
    USING (athlete_id = current_setting('request.jwt.claims', true)::json->>'sub');

CREATE POLICY "Athletes can delete own records"
    ON personal_records FOR DELETE
    USING (athlete_id = current_setting('request.jwt.claims', true)::json->>'sub');

-- History table policies
CREATE POLICY "Athletes can view own history"
    ON personal_records_history FOR SELECT
    USING (athlete_id = current_setting('request.jwt.claims', true)::json->>'sub');

COMMENT ON TABLE personal_records IS 'Stores athlete personal best times for standard race distances';
COMMENT ON COLUMN personal_records.distance_type IS 'Standard race distance identifier';
COMMENT ON COLUMN personal_records.time_seconds IS 'Time in total seconds';
COMMENT ON COLUMN personal_records.record_date IS 'Date when the record was achieved (optional)';
