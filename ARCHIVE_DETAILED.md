# 📚 INS DASHBOARD - Detailed Archive

**Purpose:** Complete historical record of all project phases, implementation details, and deprecated plans.
**Created:** November 29, 2025
**Note:** This is the archive companion to `CLAUDE.md`. All active planning is in `CLAUDE.md`.

---

# TABLE OF CONTENTS

1. [Sports Science Metrics](#sports-science-metrics)
2. [Critical Success Factors](#critical-success-factors)
3. [Development Workflow](#development-workflow)
4. [Detailed Database Schema](#detailed-database-schema)
5. [File Organization](#file-organization)
6. [Questionnaire System Details](#questionnaire-system-details)
7. [Training Zones System](#training-zones-system)
8. [Alliance Canada Plans (Deprecated)](#alliance-canada-plans-deprecated)
9. [Phase Completion Details](#phase-completion-details)
10. [Bug Fixes & Troubleshooting History](#bug-fixes--troubleshooting-history)
11. [Data Quality Metrics](#data-quality-metrics)
12. [Lessons Learned](#lessons-learned)

---

# SPORTS SCIENCE METRICS

## Objective Metrics (Auto-Collected)

### Power Metrics
- **Normalized Power** - Weighted average power accounting for variability
- **TSS (Training Stress Score)** - Quantifies training load
- **CTL (Chronic Training Load)** - 42-day exponential moving average of TSS
- **ATL (Acute Training Load)** - 7-day exponential moving average of TSS
- **TSB (Training Stress Balance)** - CTL - ATL (form/freshness indicator)

### Biomechanics (Stryd Pod)
- **Ground Contact Time (GCT)** - Time foot spends on ground (ms)
- **Vertical Oscillation (VO)** - Up/down movement per stride (mm)
- **Leg Spring Stiffness (LSS)** - Leg stiffness during stance (kN/m)
- **Stance Time** - Duration of ground contact phase
- **Step Length** - Distance covered per step (meters)
- **Stance Time Balance** - Left/right symmetry (%)
- **Vertical Ratio** - Vertical oscillation / step length

### Cardiovascular
- **Heart Rate** - Average, max, zones distribution
- **HR Recovery** - Drop in HR after effort
- **HRV (Heart Rate Variability)** - From Intervals.icu wellness data
- **Cardiac Drift** - HR increase at constant pace/power

### Performance
- **Pace** - min/km
- **Distance** - meters
- **Duration** - seconds (elapsed and moving time)
- **Elevation Gain** - meters
- **Moving Time vs Elapsed Time** - Strava algorithm calculation

### Environmental
- **Temperature** - °C
- **Humidity** - %
- **Dew Point** - °C
- **Wind Speed/Gusts** - m/s
- **Wind Direction** - degrees
- **Pressure** - hPa
- **Cloud Cover** - %
- **Precipitation** - mm
- **Air Quality** - PM2.5, PM10, Ozone, NO2, SO2, CO, US AQI

## Subjective Metrics (Manual Entry)

### Workout Perception (Daily Survey)
- **RPE (Rate of Perceived Exertion)** - CR-10 scale (0-10)
- **Workout Difficulty** - How hard the session felt (1-5)
- **Goal Achievement** - Did you meet workout objectives? (1-5)
- **Satisfaction** - Overall workout satisfaction (1-5)

### Physical State
- **Sleep Quality** - 1-10 scale
- **Fatigue** - 1-10 scale
- **Muscle Soreness (DOMS)** - 1-10 scale

### Mental State (BRUMS - Abbreviated)
- **Tension** - 0-4 scale
- **Depression** - 0-4 scale
- **Anger** - 0-4 scale
- **Vigor** - 0-4 scale
- **Fatigue** - 0-4 scale
- **Confusion** - 0-4 scale

### Recovery (REST-Q Abbreviated)
- **Emotional Stress** - 0-4 scale
- **Physical Stress** - 0-4 scale
- **Sleep Quality** - 0-4 scale
- **Recovery** - 0-4 scale
- **Social Recovery** - 0-4 scale
- **Relaxation** - 0-4 scale

### Injury Tracking (OSLO Style)
- **Participation Impact** - Did injury affect training?
- **Volume Reduction** - How much did you reduce?
- **Performance Reduction** - How much did performance suffer?
- **Pain Intensity** - 1-10 scale
- **Symptoms Description** - Free text
- **Modifications Made** - Free text

### Lifestyle
- **Academic/Professional Workload** - 0-10 scale
- **Body Weight** - kg

## Planned Correlations (Phase 3)

When sufficient data collected (60-90 days at 70-90% completion rate):

1. **CTL vs Fatigue** - Training load accumulation vs subjective tiredness
2. **RPE Calibration** - Map perceived effort to actual HR zones
3. **Sleep vs Performance** - Impact of poor sleep on pace/power
4. **GCT/LSS vs Soreness** - Biomechanical fatigue indicators vs injury risk
5. **Motivation Trends** - Early burnout detection
6. **Drift Analysis** - "Same workout feels harder = fatigue accumulation"

---

# CRITICAL SUCCESS FACTORS

## For Closed-Loop Analytics to Work

### 1. Survey Completion Rate: 70-90% Consistency

**Why:** Inconsistent data = unreliable correlations, missing surveys = gaps in analysis

**Requirements:**
- Athletes must complete surveys regularly
- Data points need consistent timing (e.g., every morning)
- Gaps reduce statistical power

### 2. Data Authenticity: Athletes MUST Enter Their Own Surveys

**Why:** Coach-entered surveys corrupt analytics, honest self-reporting is essential

**Requirements:**
- Individual athlete accounts with authentication
- No proxy entry by coaches/trainers
- Privacy to encourage honesty

### 3. Time Investment: 60-90 Days of Data Needed

**Why:** Can't rush correlation analysis, need sufficient data points

**Requirements:**
- Patience during data collection phase
- Quality over speed
- Continuous monitoring of completion rates

### 4. UI/UX for Compliance: Make Surveys Quick and Frictionless

**Why:** Friction = poor compliance = bad data

**Considerations:**
- Survey takes <60 seconds
- Mobile-friendly interface
- Gamification elements (streaks, badges)
- Reminders without annoyance
- Show athletes WHY surveys matter (feedback loop)

### 5. Document ALL Deployment Information

**Why:** Lost app_ids = cannot update production apps

**Requirements:**
- ALWAYS document app_ids immediately after creating apps
- Store deployment cache files in version control
- Document deployment URLs, app names, and app_ids

**Lesson Learned (Nov 28, 2025):**
- Lost app_id for `saintlaurentselect_dashboard` production app
- Could not deploy performance optimizations without manual manager intervention
- Impact: Hours of troubleshooting, delayed production deployment

---

# DEVELOPMENT WORKFLOW

## Dual-Claude System

Marc acts as supervisor, coordinating two Claude instances:

1. **Claude (Strategist)**: Analyzes problems, proposes solutions, creates plans
2. **Claude Code in Windsurf IDE (Implementer)**: Executes technical instructions

## Workflow

```
1. Marc provides context via CLAUDE.md
2. Claude analyzes and creates strategic plan
3. Marc reviews and approves
4. Marc sends structured prompts to Claude Code
5. Claude Code implements
6. Marc tests and validates
7. Repeat for next phase
```

## Phase Transition Philosophy

- Complete thorough testing before advancing to next phase
- Prioritize validation over speed
- Never commit broken features to production
- If data issues arise: analyze thoroughly before deciding repair vs re-import

## Response Format Preferences

**For Marc (Strategic Planning):**
- Detailed prose with analysis and recommendations
- Explain trade-offs and dependencies
- Anticipate edge cases
- Consider scalability impact across all athletes

**For Claude Code (Technical Instructions):**
- Structured, step-by-step prompts
- Clear context and goals
- Specific file paths and function names
- Expected outcomes for validation

---

# DETAILED DATABASE SCHEMA

## Table: athlete

```sql
CREATE TABLE athlete (
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
```

## Table: users

```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('athlete', 'coach')),
    athlete_id TEXT REFERENCES athlete(athlete_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Table: activity_metadata

```sql
CREATE TABLE activity_metadata (
    id SERIAL PRIMARY KEY,
    activity_id TEXT NOT NULL UNIQUE,
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
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Table: activity (Timeseries)

```sql
CREATE TABLE activity (
    id BIGSERIAL PRIMARY KEY,
    activity_id TEXT NOT NULL REFERENCES activity_metadata(activity_id) ON DELETE CASCADE,
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
    t_active_sec INTEGER
);
```

## Table: activity_intervals

```sql
CREATE TABLE activity_intervals (
    id SERIAL PRIMARY KEY,
    activity_id TEXT NOT NULL REFERENCES activity_metadata(activity_id) ON DELETE CASCADE,
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
    end_t_active REAL
);
```

## Table: wellness

```sql
CREATE TABLE wellness (
    id SERIAL PRIMARY KEY,
    athlete_id TEXT NOT NULL REFERENCES athlete(athlete_id) ON DELETE CASCADE,
    date DATE NOT NULL,
    hrv REAL,
    resting_hr INTEGER,
    sleep_quality INTEGER,
    sleep_duration_hours REAL,
    fatigue INTEGER,
    soreness INTEGER,
    stress INTEGER,
    mood INTEGER,
    motivation INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(athlete_id, date)
);
```

## Table: daily_workout_surveys

```sql
CREATE TABLE daily_workout_surveys (
    id SERIAL PRIMARY KEY,
    athlete_id TEXT NOT NULL REFERENCES athlete(athlete_id) ON DELETE CASCADE,
    activity_id TEXT REFERENCES activity_metadata(activity_id) ON DELETE SET NULL,
    survey_date DATE NOT NULL,

    -- S2: Effort perçu (RPE CR-10)
    rpe INTEGER CHECK (rpe >= 0 AND rpe <= 10),

    -- S3: Atteinte des objectifs
    goal_achievement INTEGER CHECK (goal_achievement >= 1 AND goal_achievement <= 5),

    -- S4: Contexte
    sleep_quality INTEGER CHECK (sleep_quality >= 1 AND sleep_quality <= 10),
    nutrition_quality INTEGER CHECK (nutrition_quality >= 1 AND nutrition_quality <= 10),

    -- S5: Difficulté perçue
    perceived_difficulty INTEGER CHECK (perceived_difficulty >= 1 AND perceived_difficulty <= 5),

    -- S6: Satisfaction générale
    satisfaction INTEGER CHECK (satisfaction >= 1 AND satisfaction <= 5),

    -- S7: Commentaires
    notes TEXT,

    -- Timestamps
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(athlete_id, activity_id)
);
```

## Table: weekly_wellness_surveys

```sql
CREATE TABLE weekly_wellness_surveys (
    id SERIAL PRIMARY KEY,
    athlete_id TEXT NOT NULL REFERENCES athlete(athlete_id) ON DELETE CASCADE,
    week_start_date DATE NOT NULL,

    -- S1: Bien-être général (Noon-style 0-10)
    general_fatigue INTEGER CHECK (general_fatigue >= 0 AND general_fatigue <= 10),
    doms INTEGER CHECK (doms >= 0 AND doms <= 10),
    stress_level INTEGER CHECK (stress_level >= 0 AND stress_level <= 10),
    mood INTEGER CHECK (mood >= 0 AND mood <= 10),
    readiness INTEGER CHECK (readiness >= 0 AND readiness <= 10),

    -- S2: Humeur BRUMS (0-4 each)
    brums_tension INTEGER CHECK (brums_tension >= 0 AND brums_tension <= 4),
    brums_depression INTEGER CHECK (brums_depression >= 0 AND brums_depression <= 4),
    brums_anger INTEGER CHECK (brums_anger >= 0 AND brums_anger <= 4),
    brums_vigor INTEGER CHECK (brums_vigor >= 0 AND brums_vigor <= 4),
    brums_fatigue INTEGER CHECK (brums_fatigue >= 0 AND brums_fatigue <= 4),
    brums_confusion INTEGER CHECK (brums_confusion >= 0 AND brums_confusion <= 4),

    -- S3: REST-Q (0-4 each)
    restq_emotional_stress INTEGER,
    restq_physical_stress INTEGER,
    restq_sleep_quality INTEGER,
    restq_recovery INTEGER,
    restq_social INTEGER,
    restq_relaxation INTEGER,

    -- S4: OSLO Injury
    oslo_participation INTEGER,
    oslo_volume_reduction INTEGER,
    oslo_performance_reduction INTEGER,
    oslo_symptoms TEXT,
    pain_intensity INTEGER CHECK (pain_intensity >= 0 AND pain_intensity <= 10),
    pain_description TEXT,
    modifications TEXT,

    -- S5: Lifestyle
    sleep_quality INTEGER CHECK (sleep_quality >= 1 AND sleep_quality <= 10),
    nutrition_quality INTEGER CHECK (nutrition_quality >= 1 AND nutrition_quality <= 10),
    workload INTEGER CHECK (workload >= 0 AND workload <= 10),
    body_weight DECIMAL(5,2),

    -- Timestamps
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(athlete_id, week_start_date)
);
```

## Table: personal_records

```sql
CREATE TABLE personal_records (
    id SERIAL PRIMARY KEY,
    athlete_id TEXT NOT NULL REFERENCES athlete(athlete_id) ON DELETE CASCADE,
    distance_type TEXT NOT NULL,
    time_seconds INTEGER NOT NULL,
    date DATE,
    activity_id TEXT REFERENCES activity_metadata(activity_id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(athlete_id, distance_type)
);
```

## Table: athlete_training_zones

```sql
CREATE TABLE athlete_training_zones (
    zone_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    athlete_id TEXT NOT NULL REFERENCES athlete(athlete_id) ON DELETE CASCADE,
    effective_from_date DATE NOT NULL,
    zone_number INTEGER NOT NULL CHECK (zone_number >= 1 AND zone_number <= 10),
    num_zones INTEGER NOT NULL CHECK (num_zones >= 1 AND num_zones <= 10),

    -- Heart Rate zones (bpm)
    hr_min DECIMAL(5,1) CHECK (hr_min >= 0 AND hr_min <= 250),
    hr_max DECIMAL(5,1) CHECK (hr_max >= 0 AND hr_max <= 250),

    -- Pace zones (seconds per km)
    pace_min_sec_per_km DECIMAL(6,2) CHECK (pace_min_sec_per_km >= 0 AND pace_min_sec_per_km <= 3600),
    pace_max_sec_per_km DECIMAL(6,2) CHECK (pace_max_sec_per_km >= 0 AND pace_max_sec_per_km <= 3600),

    -- Lactate zones (mmol/L)
    lactate_min DECIMAL(4,2) CHECK (lactate_min >= 0 AND lactate_min <= 30),
    lactate_max DECIMAL(4,2) CHECK (lactate_max >= 0 AND lactate_max <= 30),

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(athlete_id, effective_from_date, zone_number),
    CHECK (zone_number <= num_zones),
    CHECK (hr_min IS NULL OR hr_max IS NULL OR hr_min <= hr_max),
    CHECK (lactate_min IS NULL OR lactate_max IS NULL OR lactate_min <= lactate_max)
);
```

---

# FILE ORGANIZATION

```
INS/
├── 📄 Core Scripts (Production)
│   ├── supabase_shiny.py                  # Main dashboard (~6000 lines)
│   ├── intervals_hybrid_to_supabase.py    # Activity ingestion (~1700 lines)
│   ├── intervals_wellness_to_supabase.py  # Wellness ingestion
│   ├── moving_time.py                     # Strava algorithm
│   ├── auth_utils.py                      # Password hashing (bcrypt)
│   ├── create_users.py                    # User management
│   └── bulk_import.py                     # Master orchestration
│
├── 📁 scripts/                            # Utility scripts
│   ├── check_database_schema.py
│   ├── check_data_integrity.py
│   ├── check_import_progress.py
│   ├── create_athletes_json.py
│   ├── fix_missing_avg_hr.py
│   ├── find_test_intervals.py
│   ├── get_test_athlete.py
│   ├── export_complete_schema.py
│   └── verify_new_database.py
│
├── 📁 tests/                              # Test suite
│   ├── test_integration_with_db.py
│   ├── test_interval_functions.py
│   ├── test_intervals_tags.py
│   └── test_wellness_ingestion.py
│
├── 📁 migrations/                         # Database migrations
│   ├── add_activity_metadata_pk.sql
│   ├── add_leg_spring_stiffness.sql
│   ├── add_race_priority.sql
│   ├── create_athlete_training_zones.sql
│   ├── create_daily_workout_surveys.sql
│   ├── create_pace_zones_view.sql
│   ├── create_personal_records_table.sql
│   └── create_weekly_wellness_surveys.sql
│
├── 📁 test_deploy/                        # Deployment staging
│   ├── supabase_shiny.py                  # Copy for deployment
│   ├── deploy.sh                          # Deployment script
│   └── requirements.txt
│
├── 📄 Configuration
│   ├── .env.example                       # Environment template
│   ├── requirements.txt                   # Python dependencies
│   ├── .gitignore                         # Version control rules
│   └── complete_database_schema.sql       # Master schema (1100+ lines)
│
├── 📄 Documentation
│   ├── README.md                          # Project overview
│   ├── CLAUDE.md                          # Active context & backlog
│   ├── ARCHIVE_DETAILED.md                # This file
│   └── DIAGRAM_CONTEXT.md                 # For diagram generation
│
└── 📄 Local Files (not in repo)
    ├── .env.ingestion.local               # Ingestion secrets
    ├── .env.dashboard.local               # Dashboard secrets
    └── athletes.json.local                # Athlete API keys
```

---

# QUESTIONNAIRE SYSTEM DETAILS

## Daily Workout Survey Sections

### S1: Métadonnées séance
- Date selector (calendar)
- Activity selector (dropdown of day's runs)

### S2: Effort perçu (RPE CR-10)
- Slider 0-10
- Labels: 0=Aucun effort, 5=Difficile, 10=Effort maximal

### S3: Atteinte des objectifs
- Radio buttons 1-5
- Labels: 1=Pas du tout, 5=Complètement

### S4: Contexte
- Sleep quality slider 1-10
- Nutrition quality slider 1-10

### S5: Difficulté perçue
- Radio buttons 1-5
- Labels: 1=Très facile, 5=Très difficile

### S6: Satisfaction générale
- Radio buttons 1-5
- Labels: 1=Très insatisfait, 5=Très satisfait

### S7: Commentaires libres
- Text area (optional)

## Weekly Wellness Survey Sections

### S1: Bien-être général (Noon-style)
- 5 sliders (0-10 each):
  - Fatigue générale
  - Courbatures (DOMS)
  - Niveau de stress
  - Humeur générale
  - Prêt à performer

### S2: Humeur (BRUMS Abbreviated)
- 6 items (0-4 each):
  - Tension/Anxiété
  - Dépression/Tristesse
  - Colère/Hostilité
  - Vigueur/Énergie
  - Fatigue
  - Confusion

### S3: Stress & Récupération (REST-Q Abbreviated)
- 6 items (0-4 each):
  - Stress émotionnel
  - Stress physique
  - Qualité du sommeil
  - Récupération générale
  - Récupération sociale
  - Détente/Relaxation

### S4: Blessures/Maladies (OSLO-style)
- Participation impact (checkbox)
- Volume reduction (0-100%)
- Performance reduction (0-100%)
- Symptoms checklist
- Pain intensity (1-10)
- Pain description (text)
- Modifications made (text)

### S5: Mode de vie
- Sleep quality (1-10)
- Nutrition quality (1-10)
- Academic/professional workload (0-10)
- Body weight (kg input)

---

# TRAINING ZONES SYSTEM

## Design Philosophy

### Versioned Configuration (Append-Only)
- Never UPDATE or DELETE existing zones
- New configuration = new rows with new effective_from_date
- Historical analysis uses zones active at workout date

### Backdatable Effective Dates
- User can set effective_from_date to past (e.g., match lactate test date)
- Enables retroactive zone assignment for historical workouts

### Temporal Zone Lookup
```sql
-- Get zones for a specific workout date
SELECT * FROM athlete_training_zones
WHERE athlete_id = $1
  AND effective_from_date <= $workout_date
ORDER BY effective_from_date DESC
LIMIT (SELECT num_zones FROM athlete_training_zones
       WHERE athlete_id = $1
       ORDER BY effective_from_date DESC
       LIMIT 1);
```

## UI Implementation

### Coach View
- Athlete selector dropdown
- Effective date picker (backdatable)
- Number of zones selector (1-10)
- 10-row table with 3 metric columns each:
  - Heart Rate: min/max (bpm)
  - Pace: min/max (MM:SS format → stored as seconds/km)
  - Lactate: min/max (mmol/L)

### Athlete View
- Same as coach but no athlete selector (auto-selects self)

### Pace Format Conversion
```python
# Display → Storage
def pace_mmss_to_seconds(pace_str):  # "4:30" → 270.0
    parts = pace_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])

# Storage → Display
def pace_seconds_to_mmss(seconds):  # 270.0 → "4:30"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"
```

---

# ALLIANCE CANADA PLANS (DEPRECATED)

**Status:** Cancelled November 29, 2025 - Replaced with AWS

## Why Cancelled
- User received approval to use AWS instead
- AWS provides zero maintenance (vs 47 hours/year for Alliance)
- More reliable for production automation
- Simpler architecture

## Original Plan (For Reference Only)

### Béluga Cloud VM
- Purpose: Daily cron job at 6 AM
- Flavor: p2-4gb (2 vCPU, 4GB RAM)
- Cost: $0 (included in Alliance allocation)
- Maintenance: ~47 hours/year

### Nibi HPC Cluster
- Purpose: Bulk historical import (2021-2024)
- Workers: 32 parallel SLURM jobs
- Expected: ~30 minutes for 3,000 activities
- Cost: $0 (included in Alliance allocation)

### Why It Was Attractive
- Free (no monetary cost)
- Canadian data sovereignty
- Large compute resources available

### Why AWS Won
- Zero maintenance overhead
- Precise scheduling (EventBridge cron)
- Built-in monitoring (CloudWatch)
- Auto-retry on failures
- Enterprise-grade reliability

---

# PHASE COMPLETION DETAILS

## Phase 0: Audit & Testing (Oct 22, 2025)

**Duration:** ~1 hour

**Key Findings:**
- 495 activities in database
- 3 critical issues identified:
  1. HR Data Loss: 210 activities (42%) missing HR from streams fallback
  2. No Weather Retry: Single API timeout = permanent weather loss
  3. No API Resilience: No retry logic for external APIs

**Testing Results:**
- 3/3 dry-run tests passed
- 55 activities tested successfully
- 100% weather coverage (lucky, not guaranteed)

---

## Phase 1: Core Improvements (Oct 22, 2025)

**Duration:** ~3 hours

### Weather Retry Cascade
- 6-attempt cascade: Archive API (3x) → Forecast API (3x) → Continue
- Exponential backoff: 1s, 2s delays between retries
- Never blocks imports
- Database tracking: weather_source ('archive'/'forecast'/NULL)

### HR Fallback Fix
- MAJOR FIX: Stream HR capture 0% → 100%
- Complete cascade: Activity metadata → Streams data → Calculate from records
- Universal logic: Works for all athletes and watch types
- Fixed 210 affected activities

### Generic Retry Wrapper
- All external APIs now have retry logic
- Smart error handling: Client vs server errors
- Rate limit support: 5s fixed delay for 429 responses
- Applied to: FIT downloads, Streams API, Weather APIs

**Success Metrics:**
- 0% activities blocked
- 100% weather coverage in testing
- 100% HR coverage when data available
- Universal logic (no athlete-specific code)

---

## Phase 1.5: Advanced Visualizations (Oct 24, 2025)

**Duration:** ~2 hours

- Intervals visualization with vertical shaded regions
- Bootstrap table styling
- Auto-pattern detection (warmup, intervals, cooldown)
- LRU caching achieving sub-5ms query performance

---

## Phase 1.6: Dual Y-Axis & UI (Oct 24, 2025)

**Duration:** ~3 hours

### Dual Y-Axis Implementation
- Display two metrics simultaneously
- Primary Y-axis (left): Blue solid line
- Secondary Y-axis (right): Orange dashed line
- Independent axis scaling
- Automatic pace reversal (faster = higher)

### Available Metrics (7 total)
1. Fréquence cardiaque (bpm)
2. Cadence (spm)
3. Allure (min/km)
4. Altitude (m)
5. Puissance (W)
6. Oscillation verticale (mm)
7. Temps de contact au sol (ms)

---

## Phase 2A: Authentication (Nov 5-15, 2025)

**Duration:** ~2 weeks

### 7 Completed Steps
1. Users table created (6 accounts)
2. RLS enabled on new tables
3. auth_utils.py created (bcrypt)
4. create_users.py script
5. Login UI with session management
6. Data filtering by role
7. Coach athlete selector dropdown

### Security Architecture
- Application-level filtering (primary)
- Service role key (bypasses RLS by design)
- Appropriate for 6 trusted users
- RLS enabled on newer tables

---

## Phase 2B: Questionnaires (Nov 14, 2025)

**Duration:** ~4 hours

### Daily Workout Surveys
- 7 sections implemented
- Activity selector with date picker
- "Already filled" detection
- Database writes via REST API

### Weekly Wellness Surveys
- 5 major sections (BRUMS, REST-Q, OSLO)
- Week selector (Monday-based)
- Conditional fields for injuries
- French localization throughout

---

## Phase 2C: Personal Records & Training Zones (Nov 14, 2025)

**Duration:** ~3 hours

### Personal Records
- 7 distance types (1000m → Half Marathon)
- Manual entry with validation
- Priority/goal race flagging

### Training Zones
- 1-10 configurable zones
- 3 metrics: HR, Pace, Lactate
- Versioned with effective dates
- Coach/athlete role access

---

## Phase 2D: Database Migration (Nov 21-22, 2025)

**Duration:** ~6 hours over 2 days

### Day 1: Schema Deployment
- Created complete_database_schema.sql (1100+ lines)
- Fixed FK constraint (UNIQUE on activity_id)
- Deployed to new Supabase (vqcqqfddgnvhcrxcaxjf)
- Created 6 user accounts

### Day 2: Bug Fixes
- Intervals bug: group_id missing to_int()
- Cross-training bug: activity_type None check
- 100% intervals success after fix

### Weather Backfill System
- 3-7 day rolling window
- Checks forecast → updates to archive
- PATCH requests for updates
- Integrated into main workflow

---

## Phase 2E: Mobile-First Design (Nov 22, 2025)

**Duration:** ~4 hours

### Responsive Implementation
- Viewport meta tag added
- 164 lines mobile-first CSS
- Breakpoints: xs(<576px), sm, md, lg, xl
- Calendar hidden on mobile (<768px)

### Plotly Charts
- 15 charts with autosize=True
- Auto-resize on viewport change

### Layout Columns
- 20 instances updated
- Pattern: col_widths={"xs": 12, "md": [...]}

### Data Refresh Button
- "🔄 Actualiser" in header
- Clears memory + disk cache
- Triggers reactive reload

---

## Phase 2F: Production Deployment (Nov 23, 2025)

**Duration:** ~2 hours

### Deployment Process
1. Fixed rsconnect manifest (removed old cache)
2. Used --new flag for fresh deployment
3. Custom URL: saintlaurentselect_dashboard
4. All validation passed

### Result
- URL: https://insquebec-sportsciences.shinyapps.io/saintlaurentselect_dashboard/
- App ID: 16149191
- 956 activities loaded
- All users can access

---

## Phase 2G: Performance Optimization (Nov 28, 2025)

**Duration:** ~2 hours

### N+1 Query Fix
- Before: 1 query per activity for intervals check
- After: 1 batch query for all activities
- Impact: 50-100x faster

### Vectorized Operations
- Replaced .iterrows() with vectorized pandas
- Replaced .apply() with column operations
- Impact: 10x faster label generation

### Calendar Aggregation
- Before: Manual loop with iterrows
- After: df.groupby().size().to_dict()
- Impact: 10-50x faster

---

## Phase 2H: Ingestion Validation (Nov 29, 2025)

**Duration:** ~2 hours

### Testing Completed
1. Dry-run: 14 activities, all passed
2. Real import: 36,262 records, 103 intervals
3. Data integrity: Verified in Supabase

### Decimal Precision Fix
- 9 fields changed from to_int() to raw value
- Preserves: min_watts, max_watts, joules, torque fields
- intensity kept as TEXT

### Decision: AWS for Automation
- EC2 for bulk import (one-time)
- Lambda for daily cron (ongoing)
- Alliance Canada cancelled

---

# BUG FIXES & TROUBLESHOOTING HISTORY

## Intervals Integer Conversion Bug (Nov 22, 2025)

**Error:** `invalid input syntax for type integer: "2328s@155bpm80rpm"`

**Root Cause:** Line 909 - group_id not using to_int()

**Fix:**
```python
# Before
'group_id': interval.get('group_id')

# After
'group_id': to_int(interval.get('group_id'))
```

**Impact:** 100% intervals failure → 100% success

---

## Cross-Training NoneType Bug (Nov 22, 2025)

**Error:** `AttributeError: 'NoneType' object has no attribute 'lower'`

**Root Cause:** Line 1262 - activity_type could be None

**Fix:**
```python
# Before
is_running = activity_type.lower() in RUNNING_TYPES

# After
is_running = activity_type and activity_type.lower() in RUNNING_TYPES
```

---

## Sophie's FIT File Issue

**Error:** `Invalid field size 1 for type 'uint32' (expected a multiple of 4)`

**Cause:** Watch firmware bug in FIT file structure

**Solution:** Stream API fallback handles it automatically

**Impact:** None - fallback works perfectly

---

## SSL Certificate Error (Nov 28, 2025)

**Error:** Certificate verification failed during deployment

**Fix:**
```bash
pip install --upgrade certifi
# Updated: certifi 2025.10.5 → 2025.11.12
```

---

## Lost App ID Issue (Nov 28, 2025)

**Problem:** Could not deploy to production (app_id unknown)

**Resolution:** Manager provided app_id: 16149191

**Prevention:** Always document app_ids in CLAUDE.md immediately

---

# DATA QUALITY METRICS

## Production Statistics (Nov 29, 2025)

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Total Activities | 970 | - | ✅ |
| GPS Records | 2.5M+ | - | ✅ |
| Intervals | 10,398 | - | ✅ |
| Weather Coverage | 100% | >90% | ✅ |
| HR Coverage | 100% | >90% | ✅ |
| Import Success | 100% | >95% | ✅ |
| Blocked Activities | 0 | 0 | ✅ |

## Data Sources

| Source | Count | Percentage |
|--------|-------|------------|
| FIT Files | ~700 | 71% |
| Streams API | ~270 | 28% |
| Basic Metadata | ~10 | 1% |

## Weather Sources

| Source | Count | Note |
|--------|-------|------|
| Archive | 746 | Preferred |
| Forecast | 0 | Fallback |
| Missing | 0 | Only indoor |

---

# LESSONS LEARNED

## Technical

1. **Retry logic is mandatory** for external APIs in production
2. **Fallback cascades** prevent permanent data loss
3. **Universal logic** scales better than athlete-specific solutions
4. **Best effort > perfection** for data capture
5. **Exponential backoff** is the right approach for retries
6. **Type conversions** must be explicit (to_int for INTEGER, raw for REAL)
7. **Document app_ids immediately** after deployment

## Process

1. **Test failure scenarios** as thoroughly as success
2. **Phase-by-phase validation** prevents compounding issues
3. **Documentation matters** for debugging and onboarding
4. **Universal principles** should be established early
5. **Athlete-specific code** is a red flag for scalability

## Project Management

1. **Start with audit** to understand current state
2. **Comprehensive testing** before production
3. **File cleanup** improves maintainability
4. **Clear documentation** enables faster development
5. **Authentication first** prevents data access issues

## Architecture Decisions

1. **AWS > Self-managed VMs** for production automation (reliability wins)
2. **Calculate at ingestion** when possible (saves dashboard load time)
3. **Append-only zones** enables historical analysis
4. **Application-level filtering** is fine for trusted small teams
5. **Mobile-first CSS** with responsive breakpoints (not afterthought)

---

**END OF ARCHIVE**

*This document contains the complete historical record of the INS Dashboard project.*
*Active planning and current state are in CLAUDE.md*
