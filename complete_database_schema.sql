-- ============================================================================
-- INS DASHBOARD - Complete Database Schema
-- ============================================================================
--
-- Project: INS (Integrated Neuromuscular Science) Dashboard
-- Team: Saint-Laurent Sélect Running Club
-- Database: PostgreSQL via Supabase
-- Target Project: vqcqqfddgnvhcrxcaxjf
--
-- This file contains the complete database schema for deploying to a new
-- Supabase account. It includes:
--   - Core tables (Phase 1)
--   - Feature tables (Phase 2)
--   - All indexes and constraints
--   - RLS policies
--   - Functions and triggers
--   - Materialized views
--
-- Deployment: Run this entire file in Supabase SQL Editor
-- Estimated execution time: 30-60 seconds
--
-- ============================================================================

-- ============================================================================
-- SECTION 1: CORE TABLES (Phase 1 - Foundation)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Table: athlete
-- Purpose: Athlete profiles with Intervals.icu IDs and equipment specs
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS athlete (
    athlete_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    intervals_icu_id TEXT,
    coach_id TEXT,
    equipment_watch TEXT,
    equipment_footpod TEXT,
    equipment_hrm TEXT,
    weight_kg DECIMAL(5,2),
    max_hr INTEGER,
    resting_hr INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_athlete_name ON athlete(name);
CREATE INDEX IF NOT EXISTS idx_athlete_intervals_id ON athlete(intervals_icu_id);

COMMENT ON TABLE athlete IS 'Athlete profiles with Intervals.icu integration and equipment specifications';
COMMENT ON COLUMN athlete.athlete_id IS 'Primary identifier, typically matches Intervals.icu ID';
COMMENT ON COLUMN athlete.intervals_icu_id IS 'Intervals.icu athlete ID for API integration';

-- ----------------------------------------------------------------------------
-- Table: users
-- Purpose: Authentication and access control
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('athlete', 'coach')),
    athlete_id TEXT REFERENCES athlete(athlete_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_athlete ON users(athlete_id);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

COMMENT ON TABLE users IS 'User authentication and role-based access control';
COMMENT ON COLUMN users.role IS 'User role: athlete (own data only) or coach (all athletes)';
COMMENT ON COLUMN users.password_hash IS 'bcrypt hashed password';

-- ----------------------------------------------------------------------------
-- Table: activity_metadata
-- Purpose: Activity summaries with weather and performance metrics
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activity_metadata (
    id SERIAL PRIMARY KEY,
    activity_id TEXT NOT NULL,
    athlete_id TEXT NOT NULL REFERENCES athlete(athlete_id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    date DATE NOT NULL,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    distance_m INTEGER,
    duration_sec INTEGER,
    avg_hr INTEGER,
    max_hr INTEGER,
    start_lat DECIMAL(10,7),
    start_lon DECIMAL(10,7),
    start_elevation_m REAL,

    -- Weather data
    weather_temp_c REAL,
    weather_humidity_pct INTEGER,
    weather_dew_point_c REAL,
    weather_wind_speed_ms REAL,
    weather_wind_gust_ms REAL,
    weather_wind_dir_deg INTEGER,
    weather_pressure_hpa REAL,
    weather_cloudcover_pct INTEGER,
    weather_precip_mm REAL,
    weather_source TEXT,
    weather_error TEXT,

    -- Air quality data
    air_pm2_5 REAL,
    air_pm10 REAL,
    air_ozone REAL,
    air_no2 REAL,
    air_so2 REAL,
    air_co REAL,
    air_us_aqi INTEGER,

    -- Metadata
    source TEXT,
    fit_available BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Ensure activity_id is unique (required for foreign key references)
    UNIQUE(activity_id)
);

CREATE INDEX IF NOT EXISTS idx_activity_metadata_athlete ON activity_metadata(athlete_id);
CREATE INDEX IF NOT EXISTS idx_activity_metadata_date ON activity_metadata(date DESC);
CREATE INDEX IF NOT EXISTS idx_activity_metadata_type ON activity_metadata(type);
CREATE INDEX IF NOT EXISTS idx_activity_metadata_activity_id ON activity_metadata(activity_id);
CREATE INDEX IF NOT EXISTS idx_activity_metadata_athlete_date ON activity_metadata(athlete_id, date DESC);

COMMENT ON TABLE activity_metadata IS 'Activity summary metrics with weather enrichment';
COMMENT ON COLUMN activity_metadata.activity_id IS 'Intervals.icu activity identifier';
COMMENT ON COLUMN activity_metadata.source IS 'Data source: fit_file, intervals_streams, or intervals_basic';
COMMENT ON COLUMN activity_metadata.weather_source IS 'Weather data source: archive, forecast, or NULL if unavailable';

-- ----------------------------------------------------------------------------
-- Table: activity
-- Purpose: Second-by-second timeseries data (GPS, HR, power, biomechanics)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activity (
    id BIGSERIAL PRIMARY KEY,
    activity_id TEXT NOT NULL,
    ts_offset_ms INTEGER,
    time INTEGER,

    -- GPS data
    lat DECIMAL(10,7),
    lng DECIMAL(10,7),
    enhanced_altitude INTEGER,
    speed REAL,
    enhanced_speed REAL,
    velocity_smooth REAL,

    -- Physiological data
    heartrate INTEGER,
    cadence INTEGER,
    watts INTEGER,

    -- Biomechanics (Stryd)
    vertical_oscillation REAL,
    ground_contact_time REAL,
    stance_time_percent REAL,
    stance_time_balance REAL,
    vertical_ratio REAL,
    step_length REAL,
    leg_spring_stiffness REAL,

    -- Moving time calculation
    t_active_sec INTEGER,

    FOREIGN KEY (activity_id) REFERENCES activity_metadata(activity_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_activity_activity_id ON activity(activity_id);
CREATE INDEX IF NOT EXISTS idx_activity_time ON activity(activity_id, time);

COMMENT ON TABLE activity IS 'Second-by-second timeseries data for activities';
COMMENT ON COLUMN activity.t_active_sec IS 'Cumulative moving time in seconds (Strava algorithm)';
COMMENT ON COLUMN activity.leg_spring_stiffness IS 'Leg spring stiffness from Stryd (kN/m)';

-- ----------------------------------------------------------------------------
-- Table: activity_intervals
-- Purpose: Workout interval segments with performance metrics
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activity_intervals (
    id SERIAL PRIMARY KEY,
    activity_id TEXT NOT NULL,
    interval_id INTEGER NOT NULL,
    start_index INTEGER,
    end_index INTEGER,
    start_time INTEGER,
    end_time INTEGER,
    type TEXT,

    -- Distance and time
    distance REAL,
    moving_time INTEGER,
    elapsed_time INTEGER,

    -- Power metrics
    average_watts REAL,
    min_watts REAL,
    max_watts REAL,
    average_watts_kg REAL,
    max_watts_kg REAL,
    weighted_average_watts REAL,
    training_load REAL,
    joules REAL,
    decoupling REAL,

    -- Zone information
    intensity TEXT,
    zone INTEGER,
    zone_min_watts REAL,
    zone_max_watts REAL,

    -- Speed metrics
    average_speed REAL,
    min_speed REAL,
    max_speed REAL,

    -- Heart rate metrics
    average_heartrate INTEGER,
    min_heartrate INTEGER,
    max_heartrate INTEGER,

    -- Cadence metrics
    average_cadence INTEGER,
    min_cadence INTEGER,
    max_cadence INTEGER,

    -- Torque metrics
    average_torque REAL,
    min_torque REAL,
    max_torque REAL,

    -- Elevation metrics
    total_elevation_gain REAL,
    min_altitude REAL,
    max_altitude REAL,
    average_gradient REAL,

    -- Grouping and active time
    group_id INTEGER,
    start_t_active REAL,
    end_t_active REAL,

    FOREIGN KEY (activity_id) REFERENCES activity_metadata(activity_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_activity_intervals_activity_id ON activity_intervals(activity_id);
CREATE INDEX IF NOT EXISTS idx_activity_intervals_type ON activity_intervals(type);

COMMENT ON TABLE activity_intervals IS 'Workout interval segments with performance metrics';
COMMENT ON COLUMN activity_intervals.type IS 'Interval type: warmup, work, rest, cooldown, etc.';

-- ----------------------------------------------------------------------------
-- Table: wellness
-- Purpose: Daily wellness metrics (HRV, sleep, resting HR)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wellness (
    id SERIAL PRIMARY KEY,
    athlete_id TEXT NOT NULL REFERENCES athlete(athlete_id) ON DELETE CASCADE,
    date DATE NOT NULL,

    -- Physiological metrics
    hrv REAL,
    resting_hr INTEGER,
    weight_kg DECIMAL(5,2),

    -- Subjective metrics
    sleep_quality INTEGER CHECK (sleep_quality >= 1 AND sleep_quality <= 10),
    sleep_duration_hours REAL,
    fatigue INTEGER CHECK (fatigue >= 0 AND fatigue <= 10),
    soreness INTEGER CHECK (soreness >= 0 AND soreness <= 10),
    mood INTEGER CHECK (mood >= 1 AND mood <= 10),
    stress INTEGER CHECK (stress >= 0 AND stress <= 10),
    motivation INTEGER CHECK (motivation >= 1 AND motivation <= 10),
    readiness INTEGER CHECK (readiness >= 0 AND readiness <= 10),

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(athlete_id, date)
);

CREATE INDEX IF NOT EXISTS idx_wellness_athlete ON wellness(athlete_id);
CREATE INDEX IF NOT EXISTS idx_wellness_date ON wellness(date DESC);
CREATE INDEX IF NOT EXISTS idx_wellness_athlete_date ON wellness(athlete_id, date DESC);

COMMENT ON TABLE wellness IS 'Daily wellness and recovery metrics';
COMMENT ON COLUMN wellness.hrv IS 'Heart rate variability (rMSSD in ms)';

-- ============================================================================
-- SECTION 2: MIGRATION 1 - Add activity_metadata unique constraint
-- ============================================================================

-- NOTE: This constraint is now added inline in the activity_metadata table definition above.
-- No additional migration needed.

-- ============================================================================
-- SECTION 3: MIGRATION 2 - Add leg spring stiffness column
-- ============================================================================

-- Leg spring stiffness from Stryd footpod (already included in activity table above)
-- This migration is redundant with the main activity table definition
-- Keeping comment for reference
COMMENT ON COLUMN activity.leg_spring_stiffness IS 'Leg spring stiffness from Stryd footpod (kN/m). Measures musculoskeletal stiffness during running.';

-- ============================================================================
-- SECTION 4: MIGRATION 3 - Personal Records Tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS personal_records (
    record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    athlete_id TEXT NOT NULL REFERENCES athlete(athlete_id) ON DELETE CASCADE,
    distance_type TEXT NOT NULL CHECK (
        distance_type IN (
            '1000m',
            '1500m',
            '1mile',
            '3000m',
            '5000m',
            '10000m',
            'half_marathon'
        )
    ),
    time_seconds INTEGER NOT NULL CHECK (time_seconds > 0),
    record_date DATE,
    race_priority TEXT CHECK (race_priority IN ('A', 'B', 'C') OR race_priority IS NULL),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- One record per athlete per distance
    UNIQUE(athlete_id, distance_type)
);

CREATE INDEX IF NOT EXISTS idx_personal_records_athlete ON personal_records(athlete_id);

-- History table to track PR progression over time
CREATE TABLE IF NOT EXISTS personal_records_history (
    history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_id UUID NOT NULL,
    athlete_id TEXT NOT NULL,
    distance_type TEXT NOT NULL,
    time_seconds INTEGER NOT NULL,
    record_date DATE,
    race_priority TEXT,
    notes TEXT,
    archived_at TIMESTAMPTZ DEFAULT NOW()
);

-- Trigger to archive old records when updating
CREATE OR REPLACE FUNCTION archive_personal_record()
RETURNS TRIGGER AS $$
BEGIN
    -- Only archive if time actually changed
    IF OLD.time_seconds != NEW.time_seconds THEN
        INSERT INTO personal_records_history (
            record_id,
            athlete_id,
            distance_type,
            time_seconds,
            record_date,
            race_priority,
            notes
        ) VALUES (
            OLD.record_id,
            OLD.athlete_id,
            OLD.distance_type,
            OLD.time_seconds,
            OLD.record_date,
            OLD.race_priority,
            OLD.notes
        );
    END IF;

    -- Update the updated_at timestamp
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER personal_records_archive_trigger
    BEFORE UPDATE ON personal_records
    FOR EACH ROW
    EXECUTE FUNCTION archive_personal_record();

-- Enable RLS
ALTER TABLE personal_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE personal_records_history ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Athletes can view own records"
    ON personal_records FOR SELECT
    USING (athlete_id = current_setting('request.jwt.claims', true)::json->>'sub');

CREATE POLICY "Athletes can insert own records"
    ON personal_records FOR INSERT
    WITH CHECK (athlete_id = current_setting('request.jwt.claims', true)::json->>'sub');

CREATE POLICY "Athletes can update own records"
    ON personal_records FOR UPDATE
    USING (athlete_id = current_setting('request.jwt.claims', true)::json->>'sub');

CREATE POLICY "Athletes can delete own records"
    ON personal_records FOR DELETE
    USING (athlete_id = current_setting('request.jwt.claims', true)::json->>'sub');

CREATE POLICY "Athletes can view own history"
    ON personal_records_history FOR SELECT
    USING (athlete_id = current_setting('request.jwt.claims', true)::json->>'sub');

COMMENT ON TABLE personal_records IS 'Stores athlete personal best times for standard race distances';
COMMENT ON COLUMN personal_records.race_priority IS 'Race priority: A (goal race), B (important), C (training race)';

-- ============================================================================
-- SECTION 5: MIGRATION 4 - Training Zones Tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS athlete_training_zones (
    -- Primary key and identifiers
    zone_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    athlete_id TEXT NOT NULL,

    -- Versioning fields
    effective_from_date DATE NOT NULL,
    num_zones INTEGER NOT NULL CHECK (num_zones BETWEEN 1 AND 10),
    zone_number INTEGER NOT NULL CHECK (zone_number BETWEEN 1 AND 10),

    -- Heart Rate zones (optional)
    hr_min DECIMAL(5,1) CHECK (hr_min >= 0 AND hr_min <= 250),
    hr_max DECIMAL(5,1) CHECK (hr_max >= 0 AND hr_max <= 250),

    -- Pace zones (stored as seconds per km, optional)
    pace_min_sec_per_km DECIMAL(6,2) CHECK (pace_min_sec_per_km >= 0 AND pace_min_sec_per_km <= 3600),
    pace_max_sec_per_km DECIMAL(6,2) CHECK (pace_max_sec_per_km >= 0 AND pace_max_sec_per_km <= 3600),

    -- Lactate zones (optional)
    lactate_min DECIMAL(4,2) CHECK (lactate_min >= 0 AND lactate_min <= 30),
    lactate_max DECIMAL(4,2) CHECK (lactate_max >= 0 AND lactate_max <= 30),

    -- Audit fields
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Foreign key constraint
    CONSTRAINT fk_athlete FOREIGN KEY (athlete_id) REFERENCES athlete(athlete_id) ON DELETE CASCADE,

    -- Ensure uniqueness
    CONSTRAINT unique_athlete_date_zone UNIQUE(athlete_id, effective_from_date, zone_number),

    -- Ensure zone_number doesn't exceed num_zones
    CONSTRAINT valid_zone_number CHECK (zone_number <= num_zones),

    -- Ensure min values are less than or equal to max values
    CONSTRAINT valid_hr_range CHECK (hr_min IS NULL OR hr_max IS NULL OR hr_min <= hr_max),
    CONSTRAINT valid_pace_range CHECK (pace_min_sec_per_km IS NULL OR pace_max_sec_per_km IS NULL OR pace_min_sec_per_km <= pace_max_sec_per_km),
    CONSTRAINT valid_lactate_range CHECK (lactate_min IS NULL OR lactate_max IS NULL OR lactate_min <= lactate_max)
);

CREATE INDEX idx_zones_athlete_date ON athlete_training_zones(athlete_id, effective_from_date DESC);
CREATE INDEX idx_zones_lookup ON athlete_training_zones(athlete_id, effective_from_date, zone_number);

-- Enable RLS
ALTER TABLE athlete_training_zones ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Coaches can view all athlete zones"
    ON athlete_training_zones
    FOR SELECT
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM athlete a
            WHERE a.athlete_id = athlete_training_zones.athlete_id
            AND a.coach_id = auth.jwt() ->> 'email'
        )
        OR
        athlete_id = auth.jwt() ->> 'email'
    );

CREATE POLICY "Coaches can insert zones for their athletes"
    ON athlete_training_zones
    FOR INSERT
    TO authenticated
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM athlete a
            WHERE a.athlete_id = athlete_training_zones.athlete_id
            AND a.coach_id = auth.jwt() ->> 'email'
        )
        OR
        athlete_id = auth.jwt() ->> 'email'
    );

-- Helper function: Get zones for a specific workout date
CREATE OR REPLACE FUNCTION get_athlete_zones_for_date(
    p_athlete_id TEXT,
    p_workout_date DATE
)
RETURNS TABLE (
    zone_number INTEGER,
    hr_min DECIMAL,
    hr_max DECIMAL,
    pace_min_sec_per_km DECIMAL,
    pace_max_sec_per_km DECIMAL,
    lactate_min DECIMAL,
    lactate_max DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        z.zone_number,
        z.hr_min,
        z.hr_max,
        z.pace_min_sec_per_km,
        z.pace_max_sec_per_km,
        z.lactate_min,
        z.lactate_max
    FROM athlete_training_zones z
    WHERE z.athlete_id = p_athlete_id
    AND z.effective_from_date <= p_workout_date
    AND z.effective_from_date = (
        SELECT MAX(effective_from_date)
        FROM athlete_training_zones
        WHERE athlete_id = p_athlete_id
        AND effective_from_date <= p_workout_date
    )
    ORDER BY z.zone_number;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

GRANT EXECUTE ON FUNCTION get_athlete_zones_for_date(TEXT, DATE) TO authenticated;

COMMENT ON TABLE athlete_training_zones IS 'Versioned training zones configuration. Append-only for historical tracking.';
COMMENT ON COLUMN athlete_training_zones.effective_from_date IS 'User-selected date when zones become active. Can be backdated.';

-- ============================================================================
-- SECTION 6: MIGRATION 5 - Daily Workout Surveys
-- ============================================================================

CREATE TABLE IF NOT EXISTS daily_workout_surveys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    athlete_id TEXT NOT NULL REFERENCES athlete(athlete_id) ON DELETE CASCADE,
    activity_id TEXT NOT NULL REFERENCES activity_metadata(activity_id) ON DELETE CASCADE,

    -- S1: Session metadata
    date_seance DATE NOT NULL,
    duree_min INTEGER,

    -- S2: Perceived effort and goal achievement
    rpe_cr10 INTEGER NOT NULL CHECK (rpe_cr10 >= 0 AND rpe_cr10 <= 10),
    atteinte_obj INTEGER NOT NULL CHECK (atteinte_obj >= 0 AND atteinte_obj <= 10),

    -- S3: Pain/discomfort (OSLO-style branching)
    douleur_oui BOOLEAN NOT NULL DEFAULT FALSE,
    douleur_intensite INTEGER CHECK (douleur_intensite >= 0 AND douleur_intensite <= 10),
    douleur_type_zone TEXT,
    douleur_impact BOOLEAN,

    -- S4: Context
    en_groupe BOOLEAN NOT NULL DEFAULT FALSE,

    -- S5: Paces, comments, modifications
    allures TEXT,
    commentaires TEXT,
    modifs_oui BOOLEAN NOT NULL DEFAULT FALSE,
    modifs_details TEXT,

    -- Metadata
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_activity_per_athlete UNIQUE (activity_id, athlete_id)
);

CREATE INDEX IF NOT EXISTS idx_daily_surveys_athlete ON daily_workout_surveys(athlete_id);
CREATE INDEX IF NOT EXISTS idx_daily_surveys_activity ON daily_workout_surveys(activity_id);
CREATE INDEX IF NOT EXISTS idx_daily_surveys_date ON daily_workout_surveys(date_seance DESC);

ALTER TABLE daily_workout_surveys ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE daily_workout_surveys IS 'Post-workout questionnaire responses (RPE, goal achievement, pain, context)';
COMMENT ON COLUMN daily_workout_surveys.rpe_cr10 IS 'Rate of Perceived Exertion (CR10: 0=nothing, 10=maximal)';

-- ============================================================================
-- SECTION 7: MIGRATION 6 - Weekly Wellness Surveys
-- ============================================================================

CREATE TABLE IF NOT EXISTS weekly_wellness_surveys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    athlete_id TEXT NOT NULL REFERENCES athlete(athlete_id) ON DELETE CASCADE,
    week_start_date DATE NOT NULL,

    -- S1: General well-being (Noon-like sliders 0-10)
    fatigue INTEGER CHECK (fatigue >= 0 AND fatigue <= 10),
    doms INTEGER CHECK (doms >= 0 AND doms <= 10),
    stress_global INTEGER CHECK (stress_global >= 0 AND stress_global <= 10),
    humeur_globale INTEGER CHECK (humeur_globale >= 0 AND humeur_globale <= 10),
    readiness INTEGER CHECK (readiness >= 0 AND readiness <= 10),

    -- S2: Mood (BRUMS/POMS abbreviated - Likert 0-4)
    brums_tension INTEGER CHECK (brums_tension >= 0 AND brums_tension <= 4),
    brums_depression INTEGER CHECK (brums_depression >= 0 AND brums_depression <= 4),
    brums_colere INTEGER CHECK (brums_colere >= 0 AND brums_colere <= 4),
    brums_vigueur INTEGER CHECK (brums_vigueur >= 0 AND brums_vigueur <= 4),
    brums_fatigue INTEGER CHECK (brums_fatigue >= 0 AND brums_fatigue <= 4),
    brums_confusion INTEGER CHECK (brums_confusion >= 0 AND brums_confusion <= 4),

    -- S3: Stress & Recovery (REST-Q abbreviated - Likert 0-4)
    restq_emotion INTEGER CHECK (restq_emotion >= 0 AND restq_emotion <= 4),
    restq_physique INTEGER CHECK (restq_physique >= 0 AND restq_physique <= 4),
    restq_sommeil INTEGER CHECK (restq_sommeil >= 0 AND restq_sommeil <= 4),
    restq_recup_phys INTEGER CHECK (restq_recup_phys >= 0 AND restq_recup_phys <= 4),
    restq_social INTEGER CHECK (restq_social >= 0 AND restq_social <= 4),
    restq_relax INTEGER CHECK (restq_relax >= 0 AND restq_relax <= 4),

    -- S4: Injuries/Illness (OSLO-style)
    oslo_participation BOOLEAN DEFAULT FALSE,
    oslo_volume BOOLEAN DEFAULT FALSE,
    oslo_performance BOOLEAN DEFAULT FALSE,
    oslo_symptomes BOOLEAN DEFAULT FALSE,
    douleur_intensite INTEGER CHECK (douleur_intensite >= 1 AND douleur_intensite <= 10),
    douleur_description TEXT,
    douleur_modif BOOLEAN,

    -- S5: Sleep, nutrition, workload, weight
    sommeil_qualite INTEGER CHECK (sommeil_qualite >= 1 AND sommeil_qualite <= 10),
    alimentation_qualite INTEGER CHECK (alimentation_qualite >= 1 AND alimentation_qualite <= 10),
    charge_acad_pro INTEGER CHECK (charge_acad_pro >= 0 AND charge_acad_pro <= 10),
    poids DECIMAL(5,1),

    -- Metadata
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_week_per_athlete UNIQUE (athlete_id, week_start_date)
);

CREATE INDEX IF NOT EXISTS idx_weekly_surveys_athlete ON weekly_wellness_surveys(athlete_id);
CREATE INDEX IF NOT EXISTS idx_weekly_surveys_week ON weekly_wellness_surveys(week_start_date DESC);

ALTER TABLE weekly_wellness_surveys ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE weekly_wellness_surveys IS 'Weekly wellness questionnaire (BRUMS, REST-Q, OSLO, well-being)';
COMMENT ON COLUMN weekly_wellness_surveys.week_start_date IS 'Monday of the week being reported';

-- ============================================================================
-- SECTION 8: MIGRATION 7 - Pace Zones Materialized View
-- ============================================================================

DROP MATERIALIZED VIEW IF EXISTS activity_pace_zones CASCADE;

CREATE MATERIALIZED VIEW activity_pace_zones AS
WITH pace_data AS (
    SELECT
        activity_id,
        CASE
            WHEN speed > 0 THEN 1000.0 / speed
            ELSE NULL
        END as pace_sec_per_km
    FROM activity
    WHERE speed IS NOT NULL AND speed > 0
),
zone_counts AS (
    SELECT
        activity_id,
        COUNT(*) FILTER (WHERE pace_sec_per_km < 180) as zone_under_3_00,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 180 AND pace_sec_per_km < 195) as zone_3_00_3_15,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 195 AND pace_sec_per_km < 210) as zone_3_15_3_30,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 210 AND pace_sec_per_km < 225) as zone_3_30_3_45,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 225 AND pace_sec_per_km < 240) as zone_3_45_4_00,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 240 AND pace_sec_per_km < 255) as zone_4_00_4_15,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 255 AND pace_sec_per_km < 270) as zone_4_15_4_30,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 270 AND pace_sec_per_km < 285) as zone_4_30_4_45,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 285 AND pace_sec_per_km < 300) as zone_4_45_5_00,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 300 AND pace_sec_per_km < 315) as zone_5_00_5_15,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 315 AND pace_sec_per_km < 330) as zone_5_15_5_30,
        COUNT(*) FILTER (WHERE pace_sec_per_km >= 330) as zone_over_5_30,
        COUNT(*) as total_seconds
    FROM pace_data
    GROUP BY activity_id
)
SELECT
    zc.activity_id,
    zc.zone_under_3_00,
    zc.zone_3_00_3_15,
    zc.zone_3_15_3_30,
    zc.zone_3_30_3_45,
    zc.zone_3_45_4_00,
    zc.zone_4_00_4_15,
    zc.zone_4_15_4_30,
    zc.zone_4_30_4_45,
    zc.zone_4_45_5_00,
    zc.zone_5_00_5_15,
    zc.zone_5_15_5_30,
    zc.zone_over_5_30,
    zc.total_seconds,
    am.athlete_id,
    am.date,
    am.type
FROM zone_counts zc
JOIN activity_metadata am ON zc.activity_id = am.activity_id
WHERE zc.total_seconds > 0;

CREATE INDEX idx_pace_zones_athlete_date ON activity_pace_zones(athlete_id, date);
CREATE INDEX idx_pace_zones_date ON activity_pace_zones(date);

COMMENT ON MATERIALIZED VIEW activity_pace_zones IS
'Pre-calculated pace zone distribution. Refresh after imports: REFRESH MATERIALIZED VIEW activity_pace_zones;';

-- Convenience function to refresh
CREATE OR REPLACE FUNCTION refresh_pace_zones_view()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW activity_pace_zones;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- SECTION 9: FINAL SETUP
-- ============================================================================

-- Grant permissions
GRANT USAGE ON SCHEMA public TO authenticated, anon;
GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO authenticated;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO authenticated;

-- ============================================================================
-- DEPLOYMENT COMPLETE
-- ============================================================================
--
-- ✅ Database schema deployed successfully!
--
-- Next steps:
-- 1. Verify tables created: Run verification script
-- 2. Update environment variables with new project credentials
-- 3. Test dashboard connection
-- 4. Import data using ingestion scripts
--
-- ============================================================================
