-- Add leg_spring_stiffness column to activity table
-- This field comes from Stryd footpod data
-- Units: kN/m (kilonewtons per meter)
-- Typical range: 5-15 kN/m for runners

ALTER TABLE activity
ADD COLUMN IF NOT EXISTS leg_spring_stiffness REAL;

-- Add index for performance when querying this metric
CREATE INDEX IF NOT EXISTS idx_activity_leg_spring_stiffness
ON activity(activity_id, leg_spring_stiffness)
WHERE leg_spring_stiffness IS NOT NULL;

-- Add comment to document the column
COMMENT ON COLUMN activity.leg_spring_stiffness IS 'Leg spring stiffness from Stryd footpod (kN/m). Measures musculoskeletal stiffness during running.';
