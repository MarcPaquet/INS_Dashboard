-- Migration: Questionnaire Enhancements (Feb 20, 2026)
-- Make atteinte_obj nullable for non-running activities (cross-training, weight lifting, etc.)
-- These activities only record RPE + notes, not goal achievement

ALTER TABLE daily_workout_surveys ALTER COLUMN atteinte_obj DROP NOT NULL;
