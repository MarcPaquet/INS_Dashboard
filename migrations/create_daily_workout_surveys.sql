-- ============================================================================
-- Migration: Create daily_workout_surveys table
-- Purpose: Store post-workout questionnaire responses (daily surveys)
-- Spec: Manager's daily questionnaire (≤45 seconds)
-- Created: November 14, 2025
-- ============================================================================

-- Create daily_workout_surveys table
CREATE TABLE IF NOT EXISTS daily_workout_surveys (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign keys
    athlete_id TEXT NOT NULL REFERENCES athlete(athlete_id) ON DELETE CASCADE,
    activity_id TEXT NOT NULL REFERENCES activity_metadata(activity_id) ON DELETE CASCADE,

    -- S1: Métadonnées séance
    date_seance DATE NOT NULL,
    duree_min INTEGER, -- Optional if auto-imported from activity_metadata

    -- S2: Effort perçu et atteinte des objectifs
    rpe_cr10 INTEGER NOT NULL CHECK (rpe_cr10 >= 0 AND rpe_cr10 <= 10),
    atteinte_obj INTEGER NOT NULL CHECK (atteinte_obj >= 0 AND atteinte_obj <= 10),

    -- S3: Inconfort/Douleur (OSLO-style branching)
    douleur_oui BOOLEAN NOT NULL DEFAULT FALSE,
    douleur_intensite INTEGER CHECK (douleur_intensite >= 0 AND douleur_intensite <= 10),
    douleur_type_zone TEXT,
    douleur_impact BOOLEAN,

    -- S4: Contexte de réalisation
    en_groupe BOOLEAN NOT NULL DEFAULT FALSE,

    -- S5: Allures, commentaires, modifications
    allures TEXT,
    commentaires TEXT,
    modifs_oui BOOLEAN NOT NULL DEFAULT FALSE,
    modifs_details TEXT,

    -- Metadata
    submitted_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_activity_per_athlete UNIQUE (activity_id, athlete_id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_daily_surveys_athlete ON daily_workout_surveys(athlete_id);
CREATE INDEX IF NOT EXISTS idx_daily_surveys_activity ON daily_workout_surveys(activity_id);
CREATE INDEX IF NOT EXISTS idx_daily_surveys_date ON daily_workout_surveys(date_seance DESC);
CREATE INDEX IF NOT EXISTS idx_daily_surveys_submitted ON daily_workout_surveys(submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_daily_surveys_athlete_activity ON daily_workout_surveys(athlete_id, activity_id);

-- Add comments for documentation
COMMENT ON TABLE daily_workout_surveys IS 'Post-workout questionnaire responses (CR10, goal achievement, pain, context)';
COMMENT ON COLUMN daily_workout_surveys.rpe_cr10 IS 'Rate of Perceived Exertion (CR10 scale: 0=nothing, 10=maximal)';
COMMENT ON COLUMN daily_workout_surveys.atteinte_obj IS 'Goal achievement rating (0=not at all, 10=completely achieved)';
COMMENT ON COLUMN daily_workout_surveys.douleur_oui IS 'Experienced pain or discomfort during workout';
COMMENT ON COLUMN daily_workout_surveys.douleur_intensite IS 'Pain intensity (0=none, 10=unbearable)';

-- Enable Row Level Security (RLS)
ALTER TABLE daily_workout_surveys ENABLE ROW LEVEL SECURITY;

-- Note: RLS policies will be added in a separate migration after users table is fully configured
