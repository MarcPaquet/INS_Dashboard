-- Migration: Create workout_pain_entries table + add capacite_execution column
-- Date: 2026-02-08
-- Purpose: Support multi-select body picker in daily questionnaire with front/back views

-- ============================================
-- STEP 1: Create workout_pain_entries table
-- ============================================
CREATE TABLE IF NOT EXISTS workout_pain_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    survey_id UUID NOT NULL REFERENCES daily_workout_surveys(id) ON DELETE CASCADE,
    body_part TEXT NOT NULL,
    body_view TEXT NOT NULL CHECK (body_view IN ('front', 'back')),
    severity INTEGER NOT NULL CHECK (severity >= 1 AND severity <= 3),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pain_entries_survey ON workout_pain_entries(survey_id);

-- ============================================
-- STEP 2: Enable RLS
-- ============================================
ALTER TABLE workout_pain_entries ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all access to workout_pain_entries"
    ON workout_pain_entries
    FOR ALL
    USING (true);

-- ============================================
-- STEP 3: Add capacite_execution column to daily_workout_surveys
-- ============================================
ALTER TABLE daily_workout_surveys ADD COLUMN IF NOT EXISTS
    capacite_execution INTEGER CHECK (capacite_execution IS NULL OR (capacite_execution >= 0 AND capacite_execution <= 3));

-- ============================================
-- VERIFICATION QUERY (run after migration)
-- ============================================
-- SELECT table_name, column_name, data_type
-- FROM information_schema.columns
-- WHERE table_name IN ('workout_pain_entries', 'daily_workout_surveys')
-- ORDER BY table_name, ordinal_position;
