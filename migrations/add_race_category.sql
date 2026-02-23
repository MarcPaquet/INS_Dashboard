-- Migration: Add race_category column to lactate_tests + Renaud Bordeleau athlete record
-- Date: 2026-02-22
-- Purpose: Distinguish indoor vs outdoor races; add Renaud as full athlete

-- STEP 1: Add race_category column (nullable)
ALTER TABLE lactate_tests ADD COLUMN IF NOT EXISTS race_category TEXT;

-- STEP 2: Valid values: 'indoor' or 'outdoor' only
ALTER TABLE lactate_tests ADD CONSTRAINT chk_race_category_values
    CHECK (race_category IS NULL OR race_category IN ('indoor', 'outdoor'));

-- STEP 3: Only race type can have a category
ALTER TABLE lactate_tests ADD CONSTRAINT chk_race_category_only_for_races
    CHECK (test_type = 'race' OR race_category IS NULL);

-- STEP 4: Create athlete record for Renaud Bordeleau (was login-only, now has Intervals.icu)
INSERT INTO athlete (athlete_id, name, intervals_icu_id)
VALUES ('i482119', 'Renaud Bordeleau', 'i482119')
ON CONFLICT (athlete_id) DO NOTHING;

-- STEP 5: Link Renaud's user account to his athlete record
UPDATE users SET athlete_id = 'i482119'
WHERE name = 'Renaud Bordeleau' AND athlete_id IS NULL;
