-- =====================================================
-- ROSTER UPDATE - January 14, 2026
-- Complete roster replacement for Saint-Laurent Select
-- =====================================================
--
-- This migration:
-- 1. Inserts 12 new athletes with Intervals.icu IDs
-- 2. Creates placeholder training zones for each new athlete
-- 3. Optionally removes old athletes (commented out for safety)
--
-- Run this in Supabase SQL Editor before running create_users.py
-- =====================================================

-- =====================================================
-- STEP 1: INSERT NEW ATHLETES
-- =====================================================
-- Note: Existing athletes (Matthew, Kevin R., Kevin A., Sophie, Zakary)
-- are already in the database - no need to re-insert them.

INSERT INTO athlete (athlete_id, name, intervals_icu_id) VALUES
  ('i453408', 'Alex Larochelle', 'i453408'),
  ('i454587', 'Alexandrine Coursol', 'i454587'),
  ('i453651', 'Doan Tran', 'i453651'),
  ('jadeessabar', 'Jade Essabar', 'jadeessabar'),
  ('i453625', 'Marc-Andre Trudeau Perron', 'i453625'),
  ('i197667', 'Marine Garnier', 'i197667'),
  ('i453790', 'Myriam Poirier', 'i453790'),
  ('i453396', 'Nazim Berrichi', 'i453396'),
  ('i453411', 'Robin Lefebvre', 'i453411'),
  ('i453944', 'Yassine Aber', 'i453944'),
  ('i454589', 'Evans Stephen', 'i454589'),
  ('i453407', 'Elie Nayrand', 'i453407'),
  ('i248571', 'Ilyass Kasmi', 'i248571'),
  ('i172048', 'Emma Veilleux', 'i172048')
ON CONFLICT (athlete_id) DO UPDATE SET
  name = EXCLUDED.name,
  intervals_icu_id = EXCLUDED.intervals_icu_id,
  updated_at = NOW();

-- =====================================================
-- STEP 2: INSERT PLACEHOLDER TRAINING ZONES
-- =====================================================
-- Default 6-zone system with placeholder pace boundaries
-- These should be updated with real athlete-specific zones later
-- Effective from 2020-01-01 to cover all historical data

-- Alex Larochelle (i453408)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km)
VALUES
  ('i453408', '2020-01-01', 6, 6, NULL, 150),
  ('i453408', '2020-01-01', 5, 6, 150, 190),
  ('i453408', '2020-01-01', 4, 6, 190, 205),
  ('i453408', '2020-01-01', 3, 6, 205, 215),
  ('i453408', '2020-01-01', 2, 6, 215, 230),
  ('i453408', '2020-01-01', 1, 6, 230, NULL)
ON CONFLICT (athlete_id, effective_from_date, zone_number) DO NOTHING;

-- Alexandrine Coursol (i454587)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km)
VALUES
  ('i454587', '2020-01-01', 6, 6, NULL, 150),
  ('i454587', '2020-01-01', 5, 6, 150, 190),
  ('i454587', '2020-01-01', 4, 6, 190, 205),
  ('i454587', '2020-01-01', 3, 6, 205, 215),
  ('i454587', '2020-01-01', 2, 6, 215, 230),
  ('i454587', '2020-01-01', 1, 6, 230, NULL)
ON CONFLICT (athlete_id, effective_from_date, zone_number) DO NOTHING;

-- Doan Tran (i453651)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km)
VALUES
  ('i453651', '2020-01-01', 6, 6, NULL, 150),
  ('i453651', '2020-01-01', 5, 6, 150, 190),
  ('i453651', '2020-01-01', 4, 6, 190, 205),
  ('i453651', '2020-01-01', 3, 6, 205, 215),
  ('i453651', '2020-01-01', 2, 6, 215, 230),
  ('i453651', '2020-01-01', 1, 6, 230, NULL)
ON CONFLICT (athlete_id, effective_from_date, zone_number) DO NOTHING;

-- Jade Essabar (jadeessabar)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km)
VALUES
  ('jadeessabar', '2020-01-01', 6, 6, NULL, 150),
  ('jadeessabar', '2020-01-01', 5, 6, 150, 190),
  ('jadeessabar', '2020-01-01', 4, 6, 190, 205),
  ('jadeessabar', '2020-01-01', 3, 6, 205, 215),
  ('jadeessabar', '2020-01-01', 2, 6, 215, 230),
  ('jadeessabar', '2020-01-01', 1, 6, 230, NULL)
ON CONFLICT (athlete_id, effective_from_date, zone_number) DO NOTHING;

-- Marc-Andre Trudeau Perron (i453625)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km)
VALUES
  ('i453625', '2020-01-01', 6, 6, NULL, 150),
  ('i453625', '2020-01-01', 5, 6, 150, 190),
  ('i453625', '2020-01-01', 4, 6, 190, 205),
  ('i453625', '2020-01-01', 3, 6, 205, 215),
  ('i453625', '2020-01-01', 2, 6, 215, 230),
  ('i453625', '2020-01-01', 1, 6, 230, NULL)
ON CONFLICT (athlete_id, effective_from_date, zone_number) DO NOTHING;

-- Marine Garnier (i197667)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km)
VALUES
  ('i197667', '2020-01-01', 6, 6, NULL, 150),
  ('i197667', '2020-01-01', 5, 6, 150, 190),
  ('i197667', '2020-01-01', 4, 6, 190, 205),
  ('i197667', '2020-01-01', 3, 6, 205, 215),
  ('i197667', '2020-01-01', 2, 6, 215, 230),
  ('i197667', '2020-01-01', 1, 6, 230, NULL)
ON CONFLICT (athlete_id, effective_from_date, zone_number) DO NOTHING;

-- Myriam Poirier (i453790)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km)
VALUES
  ('i453790', '2020-01-01', 6, 6, NULL, 150),
  ('i453790', '2020-01-01', 5, 6, 150, 190),
  ('i453790', '2020-01-01', 4, 6, 190, 205),
  ('i453790', '2020-01-01', 3, 6, 205, 215),
  ('i453790', '2020-01-01', 2, 6, 215, 230),
  ('i453790', '2020-01-01', 1, 6, 230, NULL)
ON CONFLICT (athlete_id, effective_from_date, zone_number) DO NOTHING;

-- Nazim Berrichi (i453396)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km)
VALUES
  ('i453396', '2020-01-01', 6, 6, NULL, 150),
  ('i453396', '2020-01-01', 5, 6, 150, 190),
  ('i453396', '2020-01-01', 4, 6, 190, 205),
  ('i453396', '2020-01-01', 3, 6, 205, 215),
  ('i453396', '2020-01-01', 2, 6, 215, 230),
  ('i453396', '2020-01-01', 1, 6, 230, NULL)
ON CONFLICT (athlete_id, effective_from_date, zone_number) DO NOTHING;

-- Robin Lefebvre (i453411)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km)
VALUES
  ('i453411', '2020-01-01', 6, 6, NULL, 150),
  ('i453411', '2020-01-01', 5, 6, 150, 190),
  ('i453411', '2020-01-01', 4, 6, 190, 205),
  ('i453411', '2020-01-01', 3, 6, 205, 215),
  ('i453411', '2020-01-01', 2, 6, 215, 230),
  ('i453411', '2020-01-01', 1, 6, 230, NULL)
ON CONFLICT (athlete_id, effective_from_date, zone_number) DO NOTHING;

-- Yassine Aber (i453944)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km)
VALUES
  ('i453944', '2020-01-01', 6, 6, NULL, 150),
  ('i453944', '2020-01-01', 5, 6, 150, 190),
  ('i453944', '2020-01-01', 4, 6, 190, 205),
  ('i453944', '2020-01-01', 3, 6, 205, 215),
  ('i453944', '2020-01-01', 2, 6, 215, 230),
  ('i453944', '2020-01-01', 1, 6, 230, NULL)
ON CONFLICT (athlete_id, effective_from_date, zone_number) DO NOTHING;

-- Evans Stephen (i454589)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km)
VALUES
  ('i454589', '2020-01-01', 6, 6, NULL, 150),
  ('i454589', '2020-01-01', 5, 6, 150, 190),
  ('i454589', '2020-01-01', 4, 6, 190, 205),
  ('i454589', '2020-01-01', 3, 6, 205, 215),
  ('i454589', '2020-01-01', 2, 6, 215, 230),
  ('i454589', '2020-01-01', 1, 6, 230, NULL)
ON CONFLICT (athlete_id, effective_from_date, zone_number) DO NOTHING;

-- Elie Nayrand (i453407) - API KEY PENDING
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km)
VALUES
  ('i453407', '2020-01-01', 6, 6, NULL, 150),
  ('i453407', '2020-01-01', 5, 6, 150, 190),
  ('i453407', '2020-01-01', 4, 6, 190, 205),
  ('i453407', '2020-01-01', 3, 6, 205, 215),
  ('i453407', '2020-01-01', 2, 6, 215, 230),
  ('i453407', '2020-01-01', 1, 6, 230, NULL)
ON CONFLICT (athlete_id, effective_from_date, zone_number) DO NOTHING;

-- Ilyass Kasmi (i248571)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km)
VALUES
  ('i248571', '2020-01-01', 6, 6, NULL, 150),
  ('i248571', '2020-01-01', 5, 6, 150, 190),
  ('i248571', '2020-01-01', 4, 6, 190, 205),
  ('i248571', '2020-01-01', 3, 6, 205, 215),
  ('i248571', '2020-01-01', 2, 6, 215, 230),
  ('i248571', '2020-01-01', 1, 6, 230, NULL)
ON CONFLICT (athlete_id, effective_from_date, zone_number) DO NOTHING;

-- Emma Veilleux (i172048)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km)
VALUES
  ('i172048', '2020-01-01', 6, 6, NULL, 150),
  ('i172048', '2020-01-01', 5, 6, 150, 190),
  ('i172048', '2020-01-01', 4, 6, 190, 205),
  ('i172048', '2020-01-01', 3, 6, 205, 215),
  ('i172048', '2020-01-01', 2, 6, 215, 230),
  ('i172048', '2020-01-01', 1, 6, 230, NULL)
ON CONFLICT (athlete_id, effective_from_date, zone_number) DO NOTHING;

-- =====================================================
-- STEP 3: REMOVE OLD ATHLETES (OPTIONAL)
-- =====================================================
-- WARNING: Uncommenting these will CASCADE DELETE all related data:
-- - activities, GPS records, intervals
-- - surveys (daily_workout_surveys, weekly_wellness_surveys)
-- - personal_records, training_zones, zone_time calculations
--
-- Only uncomment if you are SURE you want to permanently delete this data.

-- DELETE FROM athlete WHERE athlete_id = 'i241477';  -- Jerome
-- DELETE FROM athlete WHERE athlete_id = 'i172061';  -- Thibault
-- DELETE FROM athlete WHERE athlete_id = 'i406391';  -- Rafael Venne
-- DELETE FROM athlete WHERE athlete_id = 'i104883';  -- Jean-Rene Caron
-- DELETE FROM athlete WHERE athlete_id = 'i154178';  -- Atsushi
-- DELETE FROM athlete WHERE athlete_id = 'i172070';  -- Sofia
-- DELETE FROM athlete WHERE athlete_id = 'i172037';  -- Simon Picard
-- DELETE FROM athlete WHERE athlete_id = 'i409793';  -- Emile Perin

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================
-- Run these after the migration to verify success:

-- SELECT COUNT(*) as athlete_count FROM athlete;
-- Expected: 17 (5 existing + 12 new) or 25 if old athletes not deleted

-- SELECT athlete_id, name FROM athlete ORDER BY name;

-- SELECT athlete_id, COUNT(*) as zone_count
-- FROM athlete_training_zones
-- GROUP BY athlete_id
-- ORDER BY athlete_id;
-- Expected: 6 zones per athlete

-- =====================================================
-- END OF MIGRATION
-- =====================================================
