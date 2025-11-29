# INS Dashboard - Data Flow & Calculations Diagram Context

## Purpose
Generate a visual diagram showing the complete data pipeline from source APIs to dashboard visualization, including all calculations performed at each step.

---

## HIGH-LEVEL DATA FLOW

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  INTERVALS.ICU  │────▶│   INGESTION     │────▶│    SUPABASE     │────▶│   DASHBOARD     │
│  (Source API)   │     │   (Python)      │     │   (PostgreSQL)  │     │   (Shiny)       │
└─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │
        │               ┌───────┴───────┐
        │               │               │
        ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   FIT FILES     │ │  OPEN-METEO     │ │  AIR QUALITY    │
│   (Binary)      │ │  (Weather API)  │ │  (API)          │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

---

## DETAILED DATA FLOW WITH CALCULATIONS

### STAGE 1: DATA SOURCES

#### 1.1 Intervals.icu API
- **Endpoint:** `https://intervals.icu/api/v1/athlete/{id}/activities`
- **Data Retrieved:**
  - Activity list (id, type, date, distance, duration)
  - FIT file URL for download
  - Intervals/workout structure
  - Basic metrics (avg_hr if available)

#### 1.2 FIT File (Binary)
- **Source:** Garmin/Stryd watch export via Intervals.icu
- **Contains:** Second-by-second timeseries data
- **Fields:**
  - GPS: latitude, longitude (semicircles → degrees)
  - Altitude (meters)
  - Heart rate (bpm)
  - Cadence (spm)
  - Power (watts) - if Stryd
  - Vertical oscillation (mm)
  - Ground contact time (ms)
  - Leg spring stiffness (kN/m)

#### 1.3 Open-Meteo API (Weather)
- **Archive API:** Historical weather (2-5 day delay)
- **Forecast API:** Recent weather (fallback)
- **Fields:**
  - Temperature (°C)
  - Humidity (%)
  - Dew point (°C)
  - Wind speed (m/s)
  - Wind gusts (m/s)
  - Wind direction (degrees)
  - Pressure (hPa)
  - Cloud cover (%)
  - Precipitation (mm)

#### 1.4 Air Quality API
- **Fields:**
  - PM2.5, PM10
  - Ozone, NO2, SO2, CO
  - US AQI index

---

### STAGE 2: INGESTION CALCULATIONS

#### 2.1 GPS Coordinate Conversion
```
Input:  position_lat (semicircles), position_long (semicircles)
Formula: degrees = semicircles × (180 / 2^31)
Output: lat (decimal degrees), lng (decimal degrees)
```

#### 2.2 Moving Time Calculation (Strava Algorithm)
```
Input:  GPS points with timestamps, speed values
Logic:
  - Point is "moving" if speed > threshold (0.5 m/s for running)
  - Cumulative sum of moving seconds
Output: t_active_sec (cumulative moving time per point)
```

#### 2.3 Average Heart Rate (with Fallback Cascade)
```
Priority 1: FIT session metadata (avg_heart_rate field)
Priority 2: Streams API (if FIT fails)
Priority 3: Calculate from records: AVG(heartrate) WHERE heartrate > 0
Output: avg_hr (integer bpm)
```

#### 2.4 Weather Data Selection
```
Input:  activity start_lat, start_lon, start_time
Logic:
  1. Try Archive API (3 retries with exponential backoff)
  2. If fail → Try Forecast API (3 retries)
  3. If fail → Store NULL, log error
Output: weather_source ('archive', 'forecast', or NULL)
```

#### 2.5 Integer Type Conversion (for INTEGER columns)
```
Fields: heartrate, cadence, time, ts_offset_ms, enhanced_altitude, t_active_sec
Formula: int(round(float(value)))
Purpose: PostgreSQL INTEGER compatibility
```

#### 2.6 Cross-Training Detection
```
Input:  activity_type
Logic:
  - If type IN ('Run', 'TrailRun', 'VirtualRun') → Full import (FIT + weather + intervals)
  - Else → Basic metadata only (no FIT download, no weather)
Output: source = 'intervals_fit' OR 'intervals_basic'
```

---

### STAGE 3: DATABASE SCHEMA

#### 3.1 activity_metadata (Summary per activity)
| Column | Type | Source | Calculation |
|--------|------|--------|-------------|
| activity_id | TEXT | Intervals.icu | Direct |
| athlete_id | TEXT | Config | Direct |
| type | TEXT | Intervals.icu | Direct |
| date | DATE | Intervals.icu | Extract from start_time |
| distance_m | INTEGER | FIT/API | Direct (meters) |
| duration_sec | INTEGER | FIT | total_timer_time |
| avg_hr | INTEGER | FIT/Calc | See 2.3 |
| start_lat, start_lon | DECIMAL | FIT | First GPS point |
| weather_* | REAL/INT | Open-Meteo | See 2.4 |
| air_* | REAL/INT | Air Quality API | Direct |

#### 3.2 activity (Timeseries - 1 row per second)
| Column | Type | Source | Calculation |
|--------|------|--------|-------------|
| activity_id | TEXT | FIT | Direct |
| ts_offset_ms | INTEGER | Calc | index × 1000 |
| time | INTEGER | FIT | seconds since start |
| lat, lng | DECIMAL | FIT | See 2.1 |
| enhanced_altitude | INTEGER | FIT | Direct |
| heartrate | INTEGER | FIT | Direct |
| cadence | INTEGER | FIT | Direct |
| watts | INTEGER | FIT/Stryd | Direct |
| vertical_oscillation | REAL | FIT/Stryd | Direct |
| ground_contact_time | REAL | FIT/Stryd | stance_time |
| leg_spring_stiffness | REAL | FIT/Stryd | Direct |
| t_active_sec | INTEGER | Calc | See 2.2 |

#### 3.3 activity_intervals (Workout segments)
| Column | Type | Source | Calculation |
|--------|------|--------|-------------|
| activity_id | TEXT | Intervals.icu | Direct |
| interval_id | INTEGER | Intervals.icu | Direct |
| type | TEXT | Intervals.icu | 'WORK', 'RECOVERY', 'REST' |
| distance | REAL | Intervals.icu | meters |
| moving_time | INTEGER | Intervals.icu | seconds |
| average_heartrate | INTEGER | Intervals.icu | Direct |
| average_speed | REAL | Intervals.icu | m/s |
| average_watts | REAL | Intervals.icu | Direct (if power meter) |
| intensity | TEXT | Intervals.icu | Percentage string |

---

### STAGE 4: DASHBOARD CALCULATIONS

#### 4.1 Computed Columns (Python - on data load)
```python
distance_km = distance_m / 1000
duration_min = duration_sec / 60
pace_skm = duration_min / distance_km  # min/km
type_lower = type.lower()
```

#### 4.2 Training Load Metrics
```
CTL (Chronic Training Load) = 42-day exponential moving average of TSS
ATL (Acute Training Load) = 7-day exponential moving average of TSS
TSB (Training Stress Balance) = CTL - ATL
```

#### 4.3 Pace Zones Distribution
```
For each activity:
  - Calculate pace per GPS point: 1000 / speed (sec/km)
  - Classify into zones (Z1-Z5 based on threshold pace)
  - Sum time in each zone
```

#### 4.4 Weekly Volume Aggregation
```sql
SELECT
  DATE_TRUNC('week', date) as week,
  SUM(distance_m) / 1000 as total_km,
  SUM(duration_sec) / 3600 as total_hours,
  COUNT(*) as num_activities
FROM activity_metadata
GROUP BY week
```

#### 4.5 Calendar Heatmap
```
For each date:
  - Count activities
  - Sum distance
  - Color intensity based on volume
```

---

### STAGE 5: AUTOMATION ARCHITECTURE

#### 5.1 Bulk Import (One-time)
```
AWS EC2 (t3.small)
  └─▶ 5 parallel Python processes (1 per athlete)
      └─▶ intervals_hybrid_to_supabase.py --athlete "Name"
          └─▶ Supabase REST API
```

#### 5.2 Daily Automation (Ongoing)
```
AWS EventBridge (cron: 0 6 * * *)
  └─▶ AWS Lambda (Python 3.11)
      └─▶ intervals_hybrid_to_supabase.py
          └─▶ Supabase REST API
```

#### 5.3 Weather Backfill
```
Daily at import:
  - Check activities 3-7 days old with weather_source='forecast'
  - Re-fetch from Archive API (now available)
  - Update records via PATCH request
```

---

## DIAGRAM SUGGESTIONS

### Option 1: Flowchart (Mermaid)
Best for showing the step-by-step process with decision points.

### Option 2: Architecture Diagram
Best for showing system components and their connections.

### Option 3: Data Lineage Diagram
Best for showing how each field is calculated/transformed.

### Option 4: Swimlane Diagram
Best for showing which system handles each step.

---

## REQUEST FOR CLAUDE DESKTOP

Please create a visual diagram showing:

1. **Data Sources** (left side)
   - Intervals.icu API
   - FIT Files
   - Open-Meteo Weather
   - Air Quality API

2. **Ingestion Layer** (middle)
   - Python script with key calculations:
     - GPS conversion
     - Moving time calculation
     - HR fallback cascade
     - Weather enrichment
     - Type conversions

3. **Database Layer** (middle-right)
   - 3 main tables:
     - activity_metadata (summaries)
     - activity (timeseries)
     - activity_intervals (workouts)

4. **Dashboard Layer** (right side)
   - Shiny Python app
   - Key visualizations:
     - CTL/ATL/TSB chart
     - Pace zones pie chart
     - Weekly volume chart
     - Calendar heatmap

5. **Automation Layer** (bottom)
   - AWS EC2 for bulk import
   - AWS Lambda for daily cron
   - Weather backfill process

Use colors to distinguish:
- Blue: Data sources
- Green: Processing/calculations
- Orange: Storage
- Purple: Visualization
- Gray: Automation

Include the key formulas/calculations as annotations on the arrows between stages.
