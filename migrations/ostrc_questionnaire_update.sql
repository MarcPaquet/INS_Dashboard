-- Migration: OSTRC questionnaire columns on workout_pain_entries
-- Date: 2026-02-16
-- Purpose: Replace simple severity (1-3) with standardized OSTRC-H2 questions per body part
-- Reference: Oslo Sports Trauma Research Centre Overuse Injury Questionnaire (OSTRC-H2)
--
-- OSTRC scoring: ((q1/3 + q2/4 + q3/4 + q4/3) / 4) * 100  →  0 (no problem) to 100 (max severity)
--
-- Q1: Participation (0-3): "Have you had any difficulties participating in training/competition?"
-- Q2: Training volume (0-4): "To what extent have you reduced training volume?"
-- Q3: Performance (0-4): "To what extent has this affected your performance?"
-- Q4: Pain/symptoms (0-3): "To what extent have you experienced pain/symptoms?"

-- ============================================
-- STEP 1: Add OSTRC columns to workout_pain_entries
-- ============================================

-- Q1: Participation difficulty (0=full participation, 1=with minor problems, 2=with major problems, 3=cannot participate)
ALTER TABLE workout_pain_entries ADD COLUMN IF NOT EXISTS
    ostrc_q1_participation INTEGER CHECK (ostrc_q1_participation IS NULL OR (ostrc_q1_participation >= 0 AND ostrc_q1_participation <= 3));

-- Q2: Training volume reduction (0=none, 1=slight, 2=moderate, 3=major, 4=cannot train)
ALTER TABLE workout_pain_entries ADD COLUMN IF NOT EXISTS
    ostrc_q2_training_volume INTEGER CHECK (ostrc_q2_training_volume IS NULL OR (ostrc_q2_training_volume >= 0 AND ostrc_q2_training_volume <= 4));

-- Q3: Performance impact (0=none, 1=slight, 2=moderate, 3=major, 4=cannot perform)
ALTER TABLE workout_pain_entries ADD COLUMN IF NOT EXISTS
    ostrc_q3_performance INTEGER CHECK (ostrc_q3_performance IS NULL OR (ostrc_q3_performance >= 0 AND ostrc_q3_performance <= 4));

-- Q4: Pain/symptoms severity (0=none, 1=mild, 2=moderate, 3=severe)
ALTER TABLE workout_pain_entries ADD COLUMN IF NOT EXISTS
    ostrc_q4_pain INTEGER CHECK (ostrc_q4_pain IS NULL OR (ostrc_q4_pain >= 0 AND ostrc_q4_pain <= 3));

-- Computed OSTRC score (0-100), stored for easy querying
ALTER TABLE workout_pain_entries ADD COLUMN IF NOT EXISTS
    ostrc_score DECIMAL(5,1) CHECK (ostrc_score IS NULL OR (ostrc_score >= 0 AND ostrc_score <= 100));

-- ============================================
-- STEP 2: Make severity nullable (backward compat)
-- ============================================
-- Old rows have severity 1-3; new rows will have OSTRC scores instead.
-- Drop the NOT NULL constraint on severity so new entries can omit it.
ALTER TABLE workout_pain_entries ALTER COLUMN severity DROP NOT NULL;

-- ============================================
-- VERIFICATION QUERY (run after migration)
-- ============================================
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'workout_pain_entries'
-- ORDER BY ordinal_position;
