-- ============================================================================
-- Migration: Create weekly_wellness_surveys table
-- Purpose: Store weekly wellness questionnaire responses
-- Spec: Manager's weekly questionnaire (≤1 minute)
-- Created: November 14, 2025
-- ============================================================================

-- Create weekly_wellness_surveys table
CREATE TABLE IF NOT EXISTS weekly_wellness_surveys (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign keys
    athlete_id TEXT NOT NULL REFERENCES athlete(athlete_id) ON DELETE CASCADE,
    week_start_date DATE NOT NULL, -- Monday of the week

    -- S1: Bien-être général (Noon-like) - Sliders 0-10
    fatigue INTEGER CHECK (fatigue >= 0 AND fatigue <= 10),
    doms INTEGER CHECK (doms >= 0 AND doms <= 10), -- Delayed Onset Muscle Soreness
    stress_global INTEGER CHECK (stress_global >= 0 AND stress_global <= 10),
    humeur_globale INTEGER CHECK (humeur_globale >= 0 AND humeur_globale <= 10),
    readiness INTEGER CHECK (readiness >= 0 AND readiness <= 10),

    -- S2: Humeur (BRUMS/POMS abrégé) - Likert 0-4
    brums_tension INTEGER CHECK (brums_tension >= 0 AND brums_tension <= 4),
    brums_depression INTEGER CHECK (brums_depression >= 0 AND brums_depression <= 4),
    brums_colere INTEGER CHECK (brums_colere >= 0 AND brums_colere <= 4),
    brums_vigueur INTEGER CHECK (brums_vigueur >= 0 AND brums_vigueur <= 4),
    brums_fatigue INTEGER CHECK (brums_fatigue >= 0 AND brums_fatigue <= 4),
    brums_confusion INTEGER CHECK (brums_confusion >= 0 AND brums_confusion <= 4),

    -- S3: Stress & Récupération (REST-Q abrégé) - Likert 0-4
    restq_emotion INTEGER CHECK (restq_emotion >= 0 AND restq_emotion <= 4),
    restq_physique INTEGER CHECK (restq_physique >= 0 AND restq_physique <= 4),
    restq_sommeil INTEGER CHECK (restq_sommeil >= 0 AND restq_sommeil <= 4),
    restq_recup_phys INTEGER CHECK (restq_recup_phys >= 0 AND restq_recup_phys <= 4),
    restq_social INTEGER CHECK (restq_social >= 0 AND restq_social <= 4),
    restq_relax INTEGER CHECK (restq_relax >= 0 AND restq_relax <= 4),

    -- S4: Blessures/Maladies (OSLO-style)
    oslo_participation BOOLEAN DEFAULT FALSE,
    oslo_volume BOOLEAN DEFAULT FALSE,
    oslo_performance BOOLEAN DEFAULT FALSE,
    oslo_symptomes BOOLEAN DEFAULT FALSE,
    douleur_intensite INTEGER CHECK (douleur_intensite >= 1 AND douleur_intensite <= 10),
    douleur_description TEXT,
    douleur_modif BOOLEAN,

    -- S5: Sommeil, alimentation, charge, poids
    sommeil_qualite INTEGER CHECK (sommeil_qualite >= 1 AND sommeil_qualite <= 10),
    alimentation_qualite INTEGER CHECK (alimentation_qualite >= 1 AND alimentation_qualite <= 10),
    charge_acad_pro INTEGER CHECK (charge_acad_pro >= 0 AND charge_acad_pro <= 10),
    poids DECIMAL(5,1), -- kg, with 1 decimal place

    -- Metadata
    submitted_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_week_per_athlete UNIQUE (athlete_id, week_start_date)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_weekly_surveys_athlete ON weekly_wellness_surveys(athlete_id);
CREATE INDEX IF NOT EXISTS idx_weekly_surveys_week ON weekly_wellness_surveys(week_start_date DESC);
CREATE INDEX IF NOT EXISTS idx_weekly_surveys_submitted ON weekly_wellness_surveys(submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_weekly_surveys_athlete_week ON weekly_wellness_surveys(athlete_id, week_start_date);

-- Add comments for documentation
COMMENT ON TABLE weekly_wellness_surveys IS 'Weekly wellness questionnaire (BRUMS, REST-Q, OSLO, well-being metrics)';
COMMENT ON COLUMN weekly_wellness_surveys.week_start_date IS 'Monday of the week being reported';
COMMENT ON COLUMN weekly_wellness_surveys.fatigue IS 'Fatigue level (0=none, 10=extreme)';
COMMENT ON COLUMN weekly_wellness_surveys.doms IS 'Delayed Onset Muscle Soreness (0=none, 10=very bothersome)';
COMMENT ON COLUMN weekly_wellness_surveys.brums_tension IS 'BRUMS: Tension (0=not at all, 4=extremely)';
COMMENT ON COLUMN weekly_wellness_surveys.brums_vigueur IS 'BRUMS: Vigor/Energy (0=not at all, 4=extremely)';
COMMENT ON COLUMN weekly_wellness_surveys.restq_emotion IS 'REST-Q: Emotional stress (0=never, 4=always)';
COMMENT ON COLUMN weekly_wellness_surveys.restq_sommeil IS 'REST-Q: Restorative sleep (0=never, 4=always)';
COMMENT ON COLUMN weekly_wellness_surveys.oslo_participation IS 'OSLO: Participation reduced due to injury/illness';
COMMENT ON COLUMN weekly_wellness_surveys.sommeil_qualite IS 'Sleep quality (1=very poor, 10=excellent)';
COMMENT ON COLUMN weekly_wellness_surveys.charge_acad_pro IS 'Academic/professional workload (0=none, 10=extreme)';

-- Enable Row Level Security (RLS)
ALTER TABLE weekly_wellness_surveys ENABLE ROW LEVEL SECURITY;

-- Note: RLS policies will be added in a separate migration after users table is fully configured
