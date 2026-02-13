-- ============================================================================
-- INS DASHBOARD - Complete Database Schema
-- ============================================================================
--
-- Project: INS (Integrated Neuromuscular Science) Dashboard
-- Team: Saint-Laurent Sélect Running Club
-- Database: PostgreSQL via Supabase
-- Target Project: vqcqqfddgnvhcrxcaxjf
-- Last Updated: February 8, 2026
--
-- This file contains the complete database schema for deploying to a new
-- Supabase account. It includes:
--   - Core tables (Phase 1): athlete, users, activity_metadata, activity,
--     activity_intervals, wellness
--   - Feature tables (Phase 2): personal_records, personal_records_history,
--     athlete_training_zones, daily_workout_surveys, weekly_wellness_surveys,
--     lactate_tests, activity_zone_time, weekly_monotony_strain,
--     workout_pain_entries, sync_log
--   - Materialized views: activity_pace_zones, weekly_zone_time
--   - All indexes and constraints
--   - RLS policies
--   - Functions: zone time calculation, monotony/strain calculation,
--     personal records archiving, zone lookup
--   - Triggers for auto-recalculation
--
-- Tables: 14 | Materialized Views: 2 | Functions: 10+
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
            '400m',
            '800m',
            '1000m',
            '1500m',
            '1mile',
            '2000m',
            '3000m',
            '2000m_steeple',
            '3000m_steeple',
            '5000m',
            '10000m',
            '5km',
            '10km',
            'half_marathon',
            'marathon'
        )
    ),
    time_seconds DECIMAL(10,3) NOT NULL CHECK (time_seconds > 0),
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
    time_seconds DECIMAL(10,3) NOT NULL,
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
    douleur_type_zone TEXT,  -- deprecated: replaced by workout_pain_entries table
    douleur_impact BOOLEAN,
    capacite_execution INTEGER CHECK (capacite_execution IS NULL OR (capacite_execution >= 0 AND capacite_execution <= 3)),

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
COMMENT ON COLUMN daily_workout_surveys.capacite_execution IS 'Training execution capacity: 0=not completed, 1=severely limited, 2=partially limited, 3=full capacity';

-- ============================================================================
-- SECTION 6B: Workout Pain Entries (structured body picker data)
-- ============================================================================

CREATE TABLE IF NOT EXISTS workout_pain_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    survey_id UUID NOT NULL REFERENCES daily_workout_surveys(id) ON DELETE CASCADE,
    body_part TEXT NOT NULL,
    body_view TEXT NOT NULL CHECK (body_view IN ('front', 'back')),
    severity INTEGER NOT NULL CHECK (severity >= 1 AND severity <= 3),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pain_entries_survey ON workout_pain_entries(survey_id);

ALTER TABLE workout_pain_entries ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all access to workout_pain_entries"
    ON workout_pain_entries
    FOR ALL
    USING (true);

COMMENT ON TABLE workout_pain_entries IS 'Structured pain data from body picker: one row per selected body part per survey.';
COMMENT ON COLUMN workout_pain_entries.body_part IS 'Body part ID: head, neck, left_knee, right_calf, etc.';
COMMENT ON COLUMN workout_pain_entries.body_view IS 'Which SVG view the part belongs to: front or back.';
COMMENT ON COLUMN workout_pain_entries.severity IS 'Pain level 1-3: 1=légère (inconfort), 2=modérée (douleur), 3=sévère (blessure).';

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
-- SECTION 8B: EVENTS TABLE (LACTATE TESTS, RACES, AND INJURIES)
-- ============================================================================
-- Manual data entry for athlete events: lactate tests, race results, and injuries/pain.
-- Updated Jan 2026: Added test_type to distinguish lactate tests from races.
-- Updated Feb 2026: Added injury/pain tracking with body location and severity.

CREATE TABLE IF NOT EXISTS lactate_tests (
    id SERIAL PRIMARY KEY,
    athlete_id TEXT NOT NULL,
    test_date DATE NOT NULL,
    -- Distance (required for lactate/race, NULL for injuries)
    distance_m INTEGER CHECK (distance_m IS NULL OR (distance_m > 0 AND distance_m <= 50000)),
    -- Type: 'lactate' for lactate tests, 'race' for race results, 'injury' for pain/injuries, 'speed_test' for max speed tests
    test_type TEXT NOT NULL DEFAULT 'lactate' CHECK (test_type IN ('lactate', 'race', 'injury', 'speed_test')),
    -- Lactate value (required for lactate tests, NULL for races/injuries/speed_tests)
    lactate_mmol DECIMAL(4,2) CHECK (lactate_mmol IS NULL OR (lactate_mmol >= 0 AND lactate_mmol <= 30)),
    -- Race time in seconds with decimals (for races and speed_tests)
    race_time_seconds DECIMAL(10,2),
    -- Speed in m/s (only for speed_tests, auto-calculated from distance/time)
    speed_ms DECIMAL(6,3),
    -- Injury fields (only for injuries)
    injury_location TEXT,  -- Body part ID: 'left_knee', 'right_calf', etc.
    injury_severity INTEGER CHECK (injury_severity IS NULL OR (injury_severity >= 1 AND injury_severity <= 3)),
    injury_status TEXT CHECK (injury_status IS NULL OR injury_status IN ('active', 'recovering', 'resolved')),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT fk_lactate_athlete FOREIGN KEY (athlete_id) REFERENCES athlete(athlete_id) ON DELETE CASCADE,
    -- Lactate required for lactate tests
    CONSTRAINT chk_lactate_required CHECK (test_type != 'lactate' OR lactate_mmol IS NOT NULL),
    -- Distance required for lactate/race/speed_test (not injury)
    CONSTRAINT chk_distance_required CHECK (test_type = 'injury' OR distance_m IS NOT NULL),
    -- Race time for races and speed_tests
    CONSTRAINT chk_race_time_only_for_races CHECK (test_type IN ('race', 'speed_test') OR race_time_seconds IS NULL),
    -- Speed only for speed_tests
    CONSTRAINT chk_speed_only_for_speed_tests CHECK (test_type = 'speed_test' OR speed_ms IS NULL),
    -- Injury fields required for injuries
    CONSTRAINT chk_injury_location_required CHECK (test_type != 'injury' OR injury_location IS NOT NULL),
    CONSTRAINT chk_injury_severity_required CHECK (test_type != 'injury' OR injury_severity IS NOT NULL),
    CONSTRAINT chk_injury_status_required CHECK (test_type != 'injury' OR injury_status IS NOT NULL),
    -- Injury fields only for injuries
    CONSTRAINT chk_injury_fields_only_for_injuries CHECK (test_type = 'injury' OR (injury_location IS NULL AND injury_severity IS NULL AND injury_status IS NULL))
);

CREATE INDEX idx_lactate_athlete_date ON lactate_tests(athlete_id, test_date DESC);
-- Index for efficient race queries (used by race dropdown on "Résumé de période")
CREATE INDEX idx_lactate_tests_races ON lactate_tests(athlete_id, test_type, test_date DESC) WHERE test_type = 'race';
-- Index for efficient injury queries
CREATE INDEX idx_lactate_tests_injuries ON lactate_tests(athlete_id, test_type, test_date DESC) WHERE test_type = 'injury';
-- Index for efficient speed test queries
CREATE INDEX idx_lactate_tests_speed ON lactate_tests(athlete_id, test_type, test_date DESC) WHERE test_type = 'speed_test';

ALTER TABLE lactate_tests ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all access to lactate_tests"
    ON lactate_tests
    FOR ALL
    USING (true);

COMMENT ON TABLE lactate_tests IS 'Events: lactate tests, race results, injuries, and speed tests entered by athletes.';
COMMENT ON COLUMN lactate_tests.test_type IS 'Type of entry: lactate (test), race (competition), injury (pain/blessure), or speed_test (max speed).';
COMMENT ON COLUMN lactate_tests.distance_m IS 'Distance in metres (for lactate/race/speed_test, NULL for injuries).';
COMMENT ON COLUMN lactate_tests.lactate_mmol IS 'Blood lactate concentration in mmol/L (only for lactate tests).';
COMMENT ON COLUMN lactate_tests.race_time_seconds IS 'Time in seconds with decimals (for races and speed tests).';
COMMENT ON COLUMN lactate_tests.speed_ms IS 'Speed in m/s, auto-calculated from distance/time (only for speed_tests).';
COMMENT ON COLUMN lactate_tests.injury_location IS 'Body part ID: head, neck, left_knee, right_calf, etc. (only for injuries).';
COMMENT ON COLUMN lactate_tests.injury_severity IS 'Pain level 1-3: 1=légère, 2=modérée, 3=sévère (only for injuries).';
COMMENT ON COLUMN lactate_tests.injury_status IS 'Status: active, recovering, resolved (only for injuries).';

-- Body part reference for injury_location:
-- Upper: head, neck, left_shoulder, right_shoulder, left_arm, right_arm, chest
-- Core: upper_back, lower_back
-- Lower: left_hip, right_hip, left_thigh, right_thigh, left_knee, right_knee,
--        left_calf, right_calf, left_shin, right_shin, left_ankle, right_ankle,
--        left_foot, right_foot, other

-- ============================================================================
-- SECTION 9: ACTIVITY ZONE TIME TABLE (Phase 2S - Incremental Calculation)
-- ============================================================================
-- Pre-calculated time in athlete-specific training zones per activity.
-- Converted from materialized view to regular table for incremental updates.
-- Each activity uses zones effective on that date (temporal zone matching).

CREATE TABLE IF NOT EXISTS activity_zone_time (
    -- Primary key
    activity_id TEXT PRIMARY KEY,

    -- Foreign keys
    athlete_id TEXT NOT NULL REFERENCES athlete(athlete_id) ON DELETE CASCADE,
    activity_date DATE NOT NULL,

    -- Zone time in minutes (6 zones)
    zone_1_minutes DECIMAL(10,2) DEFAULT 0,
    zone_2_minutes DECIMAL(10,2) DEFAULT 0,
    zone_3_minutes DECIMAL(10,2) DEFAULT 0,
    zone_4_minutes DECIMAL(10,2) DEFAULT 0,
    zone_5_minutes DECIMAL(10,2) DEFAULT 0,
    zone_6_minutes DECIMAL(10,2) DEFAULT 0,
    total_zone_minutes DECIMAL(10,2) DEFAULT 0,

    -- Metadata
    calculated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT fk_activity_zone_time_activity
        FOREIGN KEY (activity_id)
        REFERENCES activity_metadata(activity_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_activity_zone_time_athlete_date
    ON activity_zone_time(athlete_id, activity_date DESC);
CREATE INDEX IF NOT EXISTS idx_activity_zone_time_athlete
    ON activity_zone_time(athlete_id);

COMMENT ON TABLE activity_zone_time IS
'Pre-calculated time in athlete-specific training zones per activity.
Uses temporal zone matching - each activity uses zones effective on that date.
Updated incrementally via calculate_zone_time_for_activity().';

-- ============================================================================
-- SECTION 9B: WEEKLY ZONE TIME MATERIALIZED VIEW
-- ============================================================================
-- Aggregates zone time per athlete per week for longitudinal analysis.
-- Depends on activity_zone_time table.

CREATE MATERIALIZED VIEW IF NOT EXISTS weekly_zone_time AS
SELECT
    athlete_id,
    DATE_TRUNC('week', activity_date)::DATE AS week_start,
    SUM(zone_1_minutes) AS zone_1_minutes,
    SUM(zone_2_minutes) AS zone_2_minutes,
    SUM(zone_3_minutes) AS zone_3_minutes,
    SUM(zone_4_minutes) AS zone_4_minutes,
    SUM(zone_5_minutes) AS zone_5_minutes,
    SUM(zone_6_minutes) AS zone_6_minutes,
    SUM(total_zone_minutes) AS total_minutes,
    COUNT(*) AS activity_count
FROM activity_zone_time
WHERE total_zone_minutes > 0
GROUP BY athlete_id, DATE_TRUNC('week', activity_date)::DATE;

CREATE UNIQUE INDEX IF NOT EXISTS idx_weekly_zone_time_pk
    ON weekly_zone_time(athlete_id, week_start);
CREATE INDEX IF NOT EXISTS idx_weekly_zone_time_athlete
    ON weekly_zone_time(athlete_id, week_start DESC);

COMMENT ON MATERIALIZED VIEW weekly_zone_time IS
'Weekly aggregation of zone time per athlete.
Depends on activity_zone_time table.
Refresh after imports: SELECT refresh_all_zone_views();';

-- ============================================================================
-- SECTION 9C: ZONE TIME CALCULATION FUNCTIONS
-- ============================================================================

-- Function: Calculate zone time for a single activity
CREATE OR REPLACE FUNCTION calculate_zone_time_for_activity(p_activity_id TEXT)
RETURNS TABLE (
    activity_id TEXT,
    athlete_id TEXT,
    activity_date DATE,
    zone_1_minutes DECIMAL,
    zone_2_minutes DECIMAL,
    zone_3_minutes DECIMAL,
    zone_4_minutes DECIMAL,
    zone_5_minutes DECIMAL,
    zone_6_minutes DECIMAL,
    total_zone_minutes DECIMAL,
    was_inserted BOOLEAN
) AS $$
DECLARE
    v_athlete_id TEXT;
    v_activity_date DATE;
    v_type TEXT;
    v_result RECORD;
BEGIN
    -- Get activity metadata
    SELECT am.athlete_id, am.date, LOWER(am.type)
    INTO v_athlete_id, v_activity_date, v_type
    FROM activity_metadata am
    WHERE am.activity_id = p_activity_id;

    -- Return empty if activity not found
    IF v_athlete_id IS NULL THEN
        RETURN QUERY SELECT
            p_activity_id, NULL::TEXT, NULL::DATE,
            0::DECIMAL, 0::DECIMAL, 0::DECIMAL,
            0::DECIMAL, 0::DECIMAL, 0::DECIMAL,
            0::DECIMAL, FALSE;
        RETURN;
    END IF;

    -- Skip non-running activities
    IF v_type NOT IN ('run', 'trailrun', 'virtualrun', 'treadmill') THEN
        RETURN QUERY SELECT
            p_activity_id, v_athlete_id, v_activity_date,
            0::DECIMAL, 0::DECIMAL, 0::DECIMAL,
            0::DECIMAL, 0::DECIMAL, 0::DECIMAL,
            0::DECIMAL, FALSE;
        RETURN;
    END IF;

    -- Calculate zone time using temporal zone matching
    WITH
    effective_zones AS (
        SELECT DISTINCT ON (atz.zone_number)
            atz.zone_number,
            atz.pace_min_sec_per_km,
            atz.pace_max_sec_per_km
        FROM athlete_training_zones atz
        WHERE atz.athlete_id = v_athlete_id
          AND atz.effective_from_date <= v_activity_date
        ORDER BY atz.zone_number, atz.effective_from_date DESC
    ),
    activity_pace AS (
        SELECT
            CASE
                WHEN GREATEST(
                    COALESCE(a.speed, 0),
                    COALESCE(a.enhanced_speed, 0),
                    COALESCE(a.velocity_smooth, 0)
                ) > 0.1
                THEN 1000.0 / GREATEST(
                    COALESCE(a.speed, 0),
                    COALESCE(a.enhanced_speed, 0),
                    COALESCE(a.velocity_smooth, 0)
                )
                ELSE NULL
            END AS pace_sec_per_km
        FROM activity a
        WHERE a.activity_id = p_activity_id
    ),
    zone_time AS (
        SELECT
            ez.zone_number,
            COUNT(*) AS zone_seconds
        FROM activity_pace ap
        CROSS JOIN effective_zones ez
        WHERE ap.pace_sec_per_km IS NOT NULL
          AND (
              (ez.pace_min_sec_per_km IS NULL AND ap.pace_sec_per_km <= ez.pace_max_sec_per_km)
              OR (ez.pace_max_sec_per_km IS NULL AND ap.pace_sec_per_km > ez.pace_min_sec_per_km)
              OR (ez.pace_min_sec_per_km IS NOT NULL
                  AND ez.pace_max_sec_per_km IS NOT NULL
                  AND ap.pace_sec_per_km > ez.pace_min_sec_per_km
                  AND ap.pace_sec_per_km <= ez.pace_max_sec_per_km)
          )
        GROUP BY ez.zone_number
    ),
    zone_pivot AS (
        SELECT
            COALESCE(SUM(CASE WHEN zone_number = 1 THEN zone_seconds END) / 60.0, 0) AS z1,
            COALESCE(SUM(CASE WHEN zone_number = 2 THEN zone_seconds END) / 60.0, 0) AS z2,
            COALESCE(SUM(CASE WHEN zone_number = 3 THEN zone_seconds END) / 60.0, 0) AS z3,
            COALESCE(SUM(CASE WHEN zone_number = 4 THEN zone_seconds END) / 60.0, 0) AS z4,
            COALESCE(SUM(CASE WHEN zone_number = 5 THEN zone_seconds END) / 60.0, 0) AS z5,
            COALESCE(SUM(CASE WHEN zone_number = 6 THEN zone_seconds END) / 60.0, 0) AS z6,
            COALESCE(SUM(zone_seconds) / 60.0, 0) AS total
        FROM zone_time
    )
    INSERT INTO activity_zone_time (
        activity_id, athlete_id, activity_date,
        zone_1_minutes, zone_2_minutes, zone_3_minutes,
        zone_4_minutes, zone_5_minutes, zone_6_minutes,
        total_zone_minutes, calculated_at
    )
    SELECT
        p_activity_id, v_athlete_id, v_activity_date,
        zp.z1, zp.z2, zp.z3, zp.z4, zp.z5, zp.z6,
        zp.total, NOW()
    FROM zone_pivot zp
    ON CONFLICT (activity_id) DO UPDATE SET
        zone_1_minutes = EXCLUDED.zone_1_minutes,
        zone_2_minutes = EXCLUDED.zone_2_minutes,
        zone_3_minutes = EXCLUDED.zone_3_minutes,
        zone_4_minutes = EXCLUDED.zone_4_minutes,
        zone_5_minutes = EXCLUDED.zone_5_minutes,
        zone_6_minutes = EXCLUDED.zone_6_minutes,
        total_zone_minutes = EXCLUDED.total_zone_minutes,
        calculated_at = NOW()
    RETURNING * INTO v_result;

    RETURN QUERY SELECT
        v_result.activity_id,
        v_result.athlete_id,
        v_result.activity_date,
        v_result.zone_1_minutes,
        v_result.zone_2_minutes,
        v_result.zone_3_minutes,
        v_result.zone_4_minutes,
        v_result.zone_5_minutes,
        v_result.zone_6_minutes,
        v_result.total_zone_minutes,
        TRUE;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_zone_time_for_activity(TEXT) IS
'Calculates and upserts zone time for a single activity. Uses temporal zone matching.';

-- Function: Refresh weekly zone view (activity-level is incremental)
CREATE OR REPLACE FUNCTION refresh_all_zone_views()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY weekly_zone_time;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION refresh_all_zone_views() IS
'Refreshes weekly_zone_time materialized view. Activity-level zone time is
calculated incrementally via calculate_zone_time_for_activity().';

-- Function: Recalculate all zone times (utility for bulk operations)
CREATE OR REPLACE FUNCTION recalculate_all_zone_times()
RETURNS TABLE (
    activities_processed INTEGER,
    duration_seconds DECIMAL
) AS $$
DECLARE
    v_start TIMESTAMPTZ;
    v_count INTEGER := 0;
    v_activity_id TEXT;
BEGIN
    v_start := NOW();

    FOR v_activity_id IN
        SELECT am.activity_id
        FROM activity_metadata am
        WHERE LOWER(am.type) IN ('run', 'trailrun', 'virtualrun', 'treadmill')
    LOOP
        PERFORM calculate_zone_time_for_activity(v_activity_id);
        v_count := v_count + 1;
    END LOOP;

    REFRESH MATERIALIZED VIEW CONCURRENTLY weekly_zone_time;

    RETURN QUERY SELECT v_count, EXTRACT(EPOCH FROM NOW() - v_start)::DECIMAL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION recalculate_all_zone_times() IS
'Recalculates zone time for ALL activities. Use sparingly.';

-- ============================================================================
-- SECTION 9D: WEEKLY MONOTONY & STRAIN TABLE (Phase 2V)
-- ============================================================================
-- Pre-calculated Carl Foster Training Monotony and Strain metrics.
-- Monotony = mean / stddev of daily training (variability indicator)
-- Strain = Load × Monotony (accumulated stress indicator)

CREATE TABLE IF NOT EXISTS weekly_monotony_strain (
    id SERIAL PRIMARY KEY,
    athlete_id TEXT NOT NULL REFERENCES athlete(athlete_id) ON DELETE CASCADE,
    week_start DATE NOT NULL,

    -- Zone 1 metrics
    zone_1_load_min DECIMAL(10,2) DEFAULT 0,
    zone_1_monotony DECIMAL(6,3) DEFAULT 0,
    zone_1_strain DECIMAL(12,2) DEFAULT 0,

    -- Zone 2 metrics
    zone_2_load_min DECIMAL(10,2) DEFAULT 0,
    zone_2_monotony DECIMAL(6,3) DEFAULT 0,
    zone_2_strain DECIMAL(12,2) DEFAULT 0,

    -- Zone 3 metrics
    zone_3_load_min DECIMAL(10,2) DEFAULT 0,
    zone_3_monotony DECIMAL(6,3) DEFAULT 0,
    zone_3_strain DECIMAL(12,2) DEFAULT 0,

    -- Zone 4 metrics
    zone_4_load_min DECIMAL(10,2) DEFAULT 0,
    zone_4_monotony DECIMAL(6,3) DEFAULT 0,
    zone_4_strain DECIMAL(12,2) DEFAULT 0,

    -- Zone 5 metrics
    zone_5_load_min DECIMAL(10,2) DEFAULT 0,
    zone_5_monotony DECIMAL(6,3) DEFAULT 0,
    zone_5_strain DECIMAL(12,2) DEFAULT 0,

    -- Zone 6 metrics
    zone_6_load_min DECIMAL(10,2) DEFAULT 0,
    zone_6_monotony DECIMAL(6,3) DEFAULT 0,
    zone_6_strain DECIMAL(12,2) DEFAULT 0,

    -- Total (all zones combined)
    total_load_min DECIMAL(10,2) DEFAULT 0,
    total_monotony DECIMAL(6,3) DEFAULT 0,
    total_strain DECIMAL(12,2) DEFAULT 0,

    -- Metadata
    calculated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(athlete_id, week_start)
);

CREATE INDEX IF NOT EXISTS idx_weekly_monotony_strain_athlete_week
    ON weekly_monotony_strain(athlete_id, week_start DESC);
CREATE INDEX IF NOT EXISTS idx_weekly_monotony_strain_athlete
    ON weekly_monotony_strain(athlete_id);

COMMENT ON TABLE weekly_monotony_strain IS
'Pre-calculated weekly Training Monotony and Strain (Carl Foster model).
Monotony = mean / stddev of daily training minutes (capped at 10.0).
Strain = Load × Monotony. Per-zone metrics allow flexible aggregation.';

-- ============================================================================
-- SECTION 9E: MONOTONY/STRAIN CALCULATION FUNCTIONS
-- ============================================================================

-- Function: Calculate monotony/strain for a specific week
CREATE OR REPLACE FUNCTION calculate_monotony_strain_for_week(
    p_athlete_id TEXT,
    p_week_start DATE
) RETURNS TABLE (
    out_athlete_id TEXT,
    out_week_start DATE,
    out_zone_1_load_min DECIMAL, out_zone_1_monotony DECIMAL, out_zone_1_strain DECIMAL,
    out_zone_2_load_min DECIMAL, out_zone_2_monotony DECIMAL, out_zone_2_strain DECIMAL,
    out_zone_3_load_min DECIMAL, out_zone_3_monotony DECIMAL, out_zone_3_strain DECIMAL,
    out_zone_4_load_min DECIMAL, out_zone_4_monotony DECIMAL, out_zone_4_strain DECIMAL,
    out_zone_5_load_min DECIMAL, out_zone_5_monotony DECIMAL, out_zone_5_strain DECIMAL,
    out_zone_6_load_min DECIMAL, out_zone_6_monotony DECIMAL, out_zone_6_strain DECIMAL,
    out_total_load_min DECIMAL, out_total_monotony DECIMAL, out_total_strain DECIMAL,
    was_inserted BOOLEAN
) AS $$
DECLARE
    v_week_end DATE;
    v_result RECORD;
BEGIN
    v_week_end := p_week_start + INTERVAL '6 days';

    WITH
    week_days AS (
        SELECT generate_series(
            p_week_start::TIMESTAMP,
            v_week_end::TIMESTAMP,
            '1 day'::INTERVAL
        )::DATE AS day_date
    ),
    daily_zone_time AS (
        SELECT
            az.activity_date,
            COALESCE(SUM(az.zone_1_minutes), 0) AS z1,
            COALESCE(SUM(az.zone_2_minutes), 0) AS z2,
            COALESCE(SUM(az.zone_3_minutes), 0) AS z3,
            COALESCE(SUM(az.zone_4_minutes), 0) AS z4,
            COALESCE(SUM(az.zone_5_minutes), 0) AS z5,
            COALESCE(SUM(az.zone_6_minutes), 0) AS z6,
            COALESCE(SUM(az.total_zone_minutes), 0) AS ztotal
        FROM activity_zone_time az
        WHERE az.athlete_id = p_athlete_id
          AND az.activity_date >= p_week_start
          AND az.activity_date <= v_week_end
        GROUP BY az.activity_date
    ),
    full_week AS (
        SELECT
            wd.day_date,
            COALESCE(dzt.z1, 0) AS z1,
            COALESCE(dzt.z2, 0) AS z2,
            COALESCE(dzt.z3, 0) AS z3,
            COALESCE(dzt.z4, 0) AS z4,
            COALESCE(dzt.z5, 0) AS z5,
            COALESCE(dzt.z6, 0) AS z6,
            COALESCE(dzt.ztotal, 0) AS ztotal
        FROM week_days wd
        LEFT JOIN daily_zone_time dzt ON wd.day_date = dzt.activity_date
    ),
    zone_stats AS (
        SELECT
            SUM(z1) AS z1_load, AVG(z1) AS z1_mean, STDDEV_POP(z1) AS z1_std,
            SUM(z2) AS z2_load, AVG(z2) AS z2_mean, STDDEV_POP(z2) AS z2_std,
            SUM(z3) AS z3_load, AVG(z3) AS z3_mean, STDDEV_POP(z3) AS z3_std,
            SUM(z4) AS z4_load, AVG(z4) AS z4_mean, STDDEV_POP(z4) AS z4_std,
            SUM(z5) AS z5_load, AVG(z5) AS z5_mean, STDDEV_POP(z5) AS z5_std,
            SUM(z6) AS z6_load, AVG(z6) AS z6_mean, STDDEV_POP(z6) AS z6_std,
            SUM(ztotal) AS ztotal_load, AVG(ztotal) AS ztotal_mean, STDDEV_POP(ztotal) AS ztotal_std
        FROM full_week
    ),
    final_metrics AS (
        SELECT
            z1_load,
            CASE WHEN z1_mean > 0 AND z1_std > 0 THEN LEAST(10.0, z1_mean / z1_std)
                 WHEN z1_mean > 0 AND z1_std = 0 THEN 10.0 ELSE 0.0 END AS z1_monotony,
            z2_load,
            CASE WHEN z2_mean > 0 AND z2_std > 0 THEN LEAST(10.0, z2_mean / z2_std)
                 WHEN z2_mean > 0 AND z2_std = 0 THEN 10.0 ELSE 0.0 END AS z2_monotony,
            z3_load,
            CASE WHEN z3_mean > 0 AND z3_std > 0 THEN LEAST(10.0, z3_mean / z3_std)
                 WHEN z3_mean > 0 AND z3_std = 0 THEN 10.0 ELSE 0.0 END AS z3_monotony,
            z4_load,
            CASE WHEN z4_mean > 0 AND z4_std > 0 THEN LEAST(10.0, z4_mean / z4_std)
                 WHEN z4_mean > 0 AND z4_std = 0 THEN 10.0 ELSE 0.0 END AS z4_monotony,
            z5_load,
            CASE WHEN z5_mean > 0 AND z5_std > 0 THEN LEAST(10.0, z5_mean / z5_std)
                 WHEN z5_mean > 0 AND z5_std = 0 THEN 10.0 ELSE 0.0 END AS z5_monotony,
            z6_load,
            CASE WHEN z6_mean > 0 AND z6_std > 0 THEN LEAST(10.0, z6_mean / z6_std)
                 WHEN z6_mean > 0 AND z6_std = 0 THEN 10.0 ELSE 0.0 END AS z6_monotony,
            ztotal_load,
            CASE WHEN ztotal_mean > 0 AND ztotal_std > 0 THEN LEAST(10.0, ztotal_mean / ztotal_std)
                 WHEN ztotal_mean > 0 AND ztotal_std = 0 THEN 10.0 ELSE 0.0 END AS ztotal_monotony
        FROM zone_stats
    )
    INSERT INTO weekly_monotony_strain (
        athlete_id, week_start,
        zone_1_load_min, zone_1_monotony, zone_1_strain,
        zone_2_load_min, zone_2_monotony, zone_2_strain,
        zone_3_load_min, zone_3_monotony, zone_3_strain,
        zone_4_load_min, zone_4_monotony, zone_4_strain,
        zone_5_load_min, zone_5_monotony, zone_5_strain,
        zone_6_load_min, zone_6_monotony, zone_6_strain,
        total_load_min, total_monotony, total_strain,
        calculated_at
    )
    SELECT
        p_athlete_id, p_week_start,
        fm.z1_load, fm.z1_monotony, fm.z1_load * fm.z1_monotony,
        fm.z2_load, fm.z2_monotony, fm.z2_load * fm.z2_monotony,
        fm.z3_load, fm.z3_monotony, fm.z3_load * fm.z3_monotony,
        fm.z4_load, fm.z4_monotony, fm.z4_load * fm.z4_monotony,
        fm.z5_load, fm.z5_monotony, fm.z5_load * fm.z5_monotony,
        fm.z6_load, fm.z6_monotony, fm.z6_load * fm.z6_monotony,
        fm.ztotal_load, fm.ztotal_monotony, fm.ztotal_load * fm.ztotal_monotony,
        NOW()
    FROM final_metrics fm
    ON CONFLICT (athlete_id, week_start) DO UPDATE SET
        zone_1_load_min = EXCLUDED.zone_1_load_min,
        zone_1_monotony = EXCLUDED.zone_1_monotony,
        zone_1_strain = EXCLUDED.zone_1_strain,
        zone_2_load_min = EXCLUDED.zone_2_load_min,
        zone_2_monotony = EXCLUDED.zone_2_monotony,
        zone_2_strain = EXCLUDED.zone_2_strain,
        zone_3_load_min = EXCLUDED.zone_3_load_min,
        zone_3_monotony = EXCLUDED.zone_3_monotony,
        zone_3_strain = EXCLUDED.zone_3_strain,
        zone_4_load_min = EXCLUDED.zone_4_load_min,
        zone_4_monotony = EXCLUDED.zone_4_monotony,
        zone_4_strain = EXCLUDED.zone_4_strain,
        zone_5_load_min = EXCLUDED.zone_5_load_min,
        zone_5_monotony = EXCLUDED.zone_5_monotony,
        zone_5_strain = EXCLUDED.zone_5_strain,
        zone_6_load_min = EXCLUDED.zone_6_load_min,
        zone_6_monotony = EXCLUDED.zone_6_monotony,
        zone_6_strain = EXCLUDED.zone_6_strain,
        total_load_min = EXCLUDED.total_load_min,
        total_monotony = EXCLUDED.total_monotony,
        total_strain = EXCLUDED.total_strain,
        calculated_at = NOW()
    RETURNING * INTO v_result;

    RETURN QUERY SELECT
        v_result.athlete_id, v_result.week_start,
        v_result.zone_1_load_min, v_result.zone_1_monotony, v_result.zone_1_strain,
        v_result.zone_2_load_min, v_result.zone_2_monotony, v_result.zone_2_strain,
        v_result.zone_3_load_min, v_result.zone_3_monotony, v_result.zone_3_strain,
        v_result.zone_4_load_min, v_result.zone_4_monotony, v_result.zone_4_strain,
        v_result.zone_5_load_min, v_result.zone_5_monotony, v_result.zone_5_strain,
        v_result.zone_6_load_min, v_result.zone_6_monotony, v_result.zone_6_strain,
        v_result.total_load_min, v_result.total_monotony, v_result.total_strain,
        TRUE;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_monotony_strain_for_week(TEXT, DATE) IS
'Calculates weekly Training Monotony and Strain (Carl Foster model).
Monotony = mean / stddev (capped at 10.0). Strain = Load × Monotony.';

-- Function: Backfill historical monotony/strain data
CREATE OR REPLACE FUNCTION backfill_monotony_strain()
RETURNS TABLE (
    weeks_processed INTEGER,
    athletes_processed INTEGER,
    duration_seconds DECIMAL
) AS $$
DECLARE
    v_start TIMESTAMPTZ;
    v_week_count INTEGER := 0;
    v_athlete_count INTEGER := 0;
    v_athlete_id TEXT;
    v_week_start DATE;
BEGIN
    v_start := NOW();

    FOR v_athlete_id, v_week_start IN
        SELECT DISTINCT
            az.athlete_id,
            DATE_TRUNC('week', az.activity_date)::DATE AS week_start
        FROM activity_zone_time az
        ORDER BY az.athlete_id, week_start
    LOOP
        PERFORM calculate_monotony_strain_for_week(v_athlete_id, v_week_start);
        v_week_count := v_week_count + 1;
    END LOOP;

    SELECT COUNT(DISTINCT athlete_id) INTO v_athlete_count
    FROM weekly_monotony_strain;

    RETURN QUERY SELECT v_week_count, v_athlete_count,
        EXTRACT(EPOCH FROM NOW() - v_start)::DECIMAL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION backfill_monotony_strain() IS
'Backfills weekly_monotony_strain with historical data.';

-- ============================================================================
-- SECTION 10: FINAL SETUP
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
-- Expected objects created:
-- - Tables (14): athlete, users, activity_metadata, activity, activity_intervals,
--   wellness, personal_records, personal_records_history, athlete_training_zones,
--   daily_workout_surveys, weekly_wellness_surveys, lactate_tests,
--   activity_zone_time, weekly_monotony_strain
-- - Materialized Views (2): activity_pace_zones, weekly_zone_time
-- - Functions: get_athlete_zones_for_date, archive_personal_record,
--   refresh_pace_zones_view, calculate_zone_time_for_activity,
--   refresh_all_zone_views, recalculate_all_zone_times,
--   calculate_monotony_strain_for_week, backfill_monotony_strain
--
-- Next steps:
-- 1. Verify tables: SELECT table_name FROM information_schema.tables WHERE table_schema='public';
-- 2. Update .env with new project credentials
-- 3. Run: SELECT backfill_monotony_strain(); (if importing existing data)
-- 4. Test dashboard connection
-- 5. Import data using ingestion scripts
--
-- ============================================================================
