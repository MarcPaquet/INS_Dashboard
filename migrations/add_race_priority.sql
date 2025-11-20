-- Add race priority field to personal_records table
-- Priority indicates the importance of the race: A (highest), B (medium), C (low priority/training race)

ALTER TABLE personal_records
ADD COLUMN IF NOT EXISTS race_priority TEXT CHECK (race_priority IN ('A', 'B', 'C') OR race_priority IS NULL);

-- Also add to history table so priority is preserved in archives
ALTER TABLE personal_records_history
ADD COLUMN IF NOT EXISTS race_priority TEXT;

-- Update the archive trigger to include race_priority
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
            notes,
            race_priority
        ) VALUES (
            OLD.record_id,
            OLD.athlete_id,
            OLD.distance_type,
            OLD.time_seconds,
            OLD.record_date,
            OLD.notes,
            OLD.race_priority
        );
    END IF;

    -- Update the updated_at timestamp
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON COLUMN personal_records.race_priority IS 'Race priority: A (goal race), B (important), C (training race) - helps explain results';
