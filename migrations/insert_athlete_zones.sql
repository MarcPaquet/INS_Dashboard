-- =============================================================================
-- Migration: Insert Athlete Training Zones
-- Purpose: Delete existing zones and insert new 6-zone configurations
-- Effective Date: 2020-01-01 (covers all historical data)
-- Created: December 12, 2025
-- =============================================================================

-- Delete existing zones
DELETE FROM athlete_training_zones;

-- Zone Logic:
-- Zone 6: pace <= pace_max (INCLUSIVE, fastest, no lower bound)
-- Zones 5-2: pace_min < pace <= pace_max (exclusive lower, inclusive upper)
-- Zone 1: pace > pace_min (slowest, no upper bound)

-- Sophie Courville (i95073)
-- Z6: <=2:25 (145s), Z5: 2:25-3:05, Z4: 3:05-3:20, Z3: 3:20-3:30, Z2: 3:30-3:40, Z1: >3:40 (220s)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km) VALUES
('i95073', '2020-01-01', 6, 6, NULL, 145),
('i95073', '2020-01-01', 5, 6, 145, 185),
('i95073', '2020-01-01', 4, 6, 185, 200),
('i95073', '2020-01-01', 3, 6, 200, 210),
('i95073', '2020-01-01', 2, 6, 210, 220),
('i95073', '2020-01-01', 1, 6, 220, NULL);

-- Kevin A. Robertson (i344980)
-- Z6: <=2:10 (130s), Z5: 2:10-2:45, Z4: 2:45-2:55, Z3: 2:55-3:00, Z2: 3:00-3:05, Z1: >3:05 (185s)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km) VALUES
('i344980', '2020-01-01', 6, 6, NULL, 130),
('i344980', '2020-01-01', 5, 6, 130, 165),
('i344980', '2020-01-01', 4, 6, 165, 175),
('i344980', '2020-01-01', 3, 6, 175, 180),
('i344980', '2020-01-01', 2, 6, 180, 185),
('i344980', '2020-01-01', 1, 6, 185, NULL);

-- Matthew Beaudet (i344978)
-- Z6: <=2:05 (125s), Z5: 2:05-2:40, Z4: 2:40-2:50, Z3: 2:50-3:00, Z2: 3:00-3:10, Z1: >3:10 (190s)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km) VALUES
('i344978', '2020-01-01', 6, 6, NULL, 125),
('i344978', '2020-01-01', 5, 6, 125, 160),
('i344978', '2020-01-01', 4, 6, 160, 170),
('i344978', '2020-01-01', 3, 6, 170, 180),
('i344978', '2020-01-01', 2, 6, 180, 190),
('i344978', '2020-01-01', 1, 6, 190, NULL);

-- Zakary Mama-Yari (i347434)
-- Z6: <=2:00 (120s), Z5: 2:00-2:50, Z4: 2:50-3:30, Z3: 3:30-3:40, Z2: 3:40-3:55, Z1: >3:55 (235s)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km) VALUES
('i347434', '2020-01-01', 6, 6, NULL, 120),
('i347434', '2020-01-01', 5, 6, 120, 170),
('i347434', '2020-01-01', 4, 6, 170, 210),
('i347434', '2020-01-01', 3, 6, 210, 220),
('i347434', '2020-01-01', 2, 6, 220, 235),
('i347434', '2020-01-01', 1, 6, 235, NULL);

-- Kevin Robertson (i344979)
-- Z6: <=2:10 (130s), Z5: 2:10-2:40, Z4: 2:40-3:00, Z3: 3:00-3:05, Z2: 3:05-3:15, Z1: >3:15 (195s)
INSERT INTO athlete_training_zones (athlete_id, effective_from_date, zone_number, num_zones, pace_min_sec_per_km, pace_max_sec_per_km) VALUES
('i344979', '2020-01-01', 6, 6, NULL, 130),
('i344979', '2020-01-01', 5, 6, 130, 160),
('i344979', '2020-01-01', 4, 6, 160, 180),
('i344979', '2020-01-01', 3, 6, 180, 185),
('i344979', '2020-01-01', 2, 6, 185, 195),
('i344979', '2020-01-01', 1, 6, 195, NULL);

-- Verify: Should have 30 rows (5 athletes x 6 zones)
-- SELECT athlete_id, COUNT(*) as zones FROM athlete_training_zones GROUP BY athlete_id;
