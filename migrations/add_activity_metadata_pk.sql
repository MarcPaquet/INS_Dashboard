-- ============================================================================
-- Migration: Add unique constraint to activity_metadata table
-- Purpose: Enable foreign key references from daily_workout_surveys
-- Created: November 14, 2025
-- ============================================================================

-- Add unique constraint to activity_metadata table
-- This is required for the foreign key reference from daily_workout_surveys
-- Note: Table already has a primary key on another column, so we use UNIQUE instead

ALTER TABLE activity_metadata
ADD CONSTRAINT activity_metadata_activity_id_unique UNIQUE (activity_id);

-- Verify the constraint was added
COMMENT ON CONSTRAINT activity_metadata_activity_id_unique ON activity_metadata IS 'Unique constraint on activity_id to enable foreign key references';
