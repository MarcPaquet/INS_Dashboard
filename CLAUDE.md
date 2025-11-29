# 📊 INS DASHBOARD - Master Context & Backlog

**Project:** Intervals.icu → Supabase Data Ingestion System
**Team:** Saint-Laurent Sélect Running Club
**Last Updated:** November 29, 2025
**Status:** ✅ **PRODUCTION LIVE** - https://insquebec-sportsciences.shinyapps.io/saintlaurentselect_dashboard/

---

## 📖 HOW TO USE THIS DOCUMENT

| Audience | What to Read |
|----------|--------------|
| **Marc (Owner)** | Update after each session. Keep CONTEXT current, move completed tasks to ARCHIVE. |
| **Claude Code** | Read CONTEXT first, check BACKLOG for priorities, reference ARCHIVE for history. |

---

# 📚 TABLE OF CONTENTS

**PART 1: CONTEXT** (Essential Knowledge)
- [Project Vision](#-project-vision)
- [Athletes & Authentication](#-athletes--authentication)
- [Architecture & Tech Stack](#-architecture--tech-stack)
- [Current State](#-current-state)
- [Core Principles](#-core-principles)

**PART 2: BACKLOG** (What to Do)
- [NOW - Immediate Priorities](#now---immediate-priorities)
- [NEXT - Coming Soon](#next---coming-soon)
- [LATER - Future Phases](#later---future-phases)

**PART 3: REFERENCE** (Details & History)
- [Database Schema](#-database-schema)
- [Data Flow & Calculations](#-data-flow--calculations)
- [AWS Automation Plan](#-aws-automation-plan)
- [Archive - Completed Work](#-archive---completed-work)

---

# PART 1: CONTEXT

## 🎯 PROJECT VISION

### What is this?

**INS Dashboard** = Sports science analytics platform for a running club (5 athletes + 1 coach).

```
Intervals.icu (watches) → Supabase (database) → Shiny Dashboard (analytics)
```

### The Closed-Loop Concept

```
Objective Data (GPS, HR, Power, Biomechanics)
    ↓
Auto-Imported from Intervals.icu
    ↓
Athlete Manually Enters Surveys (RPE, Fatigue, Sleep)
    ↓
Analytics Engine Correlates Data
    ↓
Insights Generated ("High CTL + High Fatigue → Recommend rest")
    ↓
Better Training Decisions
    ↓
[Repeat]
```

**Key Insight:** Manual surveys aren't just for display—they enable correlation analysis for performance optimization and injury prevention.

---

## 👥 ATHLETES & AUTHENTICATION

### Club Members

| Athlete | Intervals.icu ID | Login | Role |
|---------|------------------|-------|------|
| Matthew Beaudet | `i344978` | Matthew | athlete |
| Kevin Robertson | `i344979` | Kevin1 | athlete |
| Kevin A. Robertson | `i344980` | Kevin2 | athlete |
| Zakary Mama-Yari | `i347434` | Zakary | athlete |
| Sophie Courville | `i95073` | Sophie | athlete |
| Coach | N/A | Coach | coach |

### Access Control
- **Athletes:** See only their own data
- **Coach:** Can view all athletes + select specific athlete via dropdown

---

## 🏗️ ARCHITECTURE & TECH STACK

### System Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PRODUCTION SYSTEM                            │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ INTERVALS.ICU│     │   SUPABASE   │     │ SHINYAPPS.IO │
│   (Source)   │────▶│ (PostgreSQL) │◀────│ (Dashboard)  │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    ▲                    │
       │                    │                    │
       ▼                    │                    ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  FIT Files   │     │  AWS Lambda  │     │   Athletes   │
│  (Binary)    │     │ (Daily Cron) │     │   (Users)    │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    │
       ▼                    │
┌──────────────┐            │
│  OPEN-METEO  │────────────┘
│  (Weather)   │
└──────────────┘
```

### Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Dashboard | Python + Shiny | Interactive visualizations |
| Database | PostgreSQL (Supabase) | Data storage with RLS |
| Ingestion | Python script | Intervals.icu → Supabase |
| Weather | Open-Meteo API | Weather enrichment |
| Hosting | ShinyApps.io | Dashboard hosting |
| Automation | AWS Lambda + EventBridge | Daily cron job |
| Bulk Import | AWS EC2 | One-time historical import |

### Key Files

| File | Purpose |
|------|---------|
| `supabase_shiny.py` | Main dashboard application |
| `intervals_hybrid_to_supabase.py` | Data ingestion script |
| `moving_time.py` | Moving time calculations |
| `auth_utils.py` | Password hashing |
| `athletes.json.local` | Athlete API keys (not in git) |

---

## 📍 CURRENT STATE

### ✅ What's Working (Production)

| Component | Status | Details |
|-----------|--------|---------|
| **Dashboard** | ✅ LIVE | https://insquebec-sportsciences.shinyapps.io/saintlaurentselect_dashboard/ |
| **Database** | ✅ Active | Supabase project: `vqcqqfddgnvhcrxcaxjf` |
| **Authentication** | ✅ Working | 6 users (5 athletes + 1 coach) |
| **Ingestion Script** | ✅ Validated | Tested Nov 29, 2025 - all checks passed |
| **Mobile Design** | ✅ Responsive | All breakpoints working |

### 📊 Data Statistics (as of Nov 29, 2025)

| Metric | Count |
|--------|-------|
| Activities | 970 (956 historical + 14 recent test) |
| GPS Records | 2.5M+ points |
| Intervals | 10,398 |
| Weather Coverage | 100% (outdoor activities) |
| HR Coverage | 100% (when monitor used) |

### 🔧 Recent Session (Nov 29, 2025)

**Morning - Ingestion Script Validation:**
1. ✅ Dry-run test passed (14 activities)
2. ✅ Fixed decimal precision for REAL fields (min_watts, max_watts, joules, etc.)
3. ✅ Real import test passed (36,262 records, 103 intervals)
4. ✅ Data integrity verified in Supabase

**Evening - GitHub Cleanup & Wellness Integration:**
1. ✅ GitHub repository cleaned (20+ files → gitignore, kept locally)
2. ✅ Wellness ingestion merged into main script (auto-runs for all athletes)
3. ✅ README.md updated with correct project structure
4. ✅ Pushed to GitHub: https://github.com/MarcPaquet/INS_Dashboard

**Decision Made:**
- ❌ Alliance Canada Cloud (cancelled)
- ✅ AWS for all automation (EC2 bulk + Lambda daily)

---

## 📐 CORE PRINCIPLES

### 1. Universal Scalability
**Every solution MUST work for all athletes without hardcoded logic.**

```
❌ BAD:  if athlete == "Sophie": use_streams()
✅ GOOD: if fit_parse_fails: use_streams()
```

### 2. Fastest First, Then Complete
**Never block imports. Core data first, enrichment second.**

```
✅ SUCCESS: 495 activities with 10 missing weather
❌ FAILURE: 485 activities imported but 10 blocked
```

### 3. Robust Fallbacks
**Every external dependency needs cascade fallbacks.**

```python
# Weather cascade
try: archive_api()      # 3 retries
except: forecast_api()  # 3 retries
except: store_null()    # Continue without weather

# HR cascade
try: fit_metadata()
except: streams_api()
except: calculate_from_records()
```

### 4. Calculation Priority

| Priority | Where | Example |
|----------|-------|---------|
| **1st** | Ingestion | Pre-calculate at import time |
| **2nd** | Database Views | Materialized views for aggregations |
| **3rd** | Dashboard | Only if dynamic/user-specific |

---

# PART 2: BACKLOG

## NOW - Immediate Priorities

### 🔴 Priority 1: AWS Setup for Automation

**Goal:** Automated daily ingestion + one-time bulk historical import

| Task | Service | Status |
|------|---------|--------|
| Set up billing alert ($10) | AWS Console | ⏳ Pending |
| Create IAM role | IAM | ⏳ Pending |
| Store credentials | Secrets Manager | ⏳ Pending |
| Deploy Lambda function | Lambda | ⏳ Pending |
| Configure daily cron (6 AM ET) | EventBridge | ⏳ Pending |
| Launch EC2 for bulk import | EC2 | ⏳ Pending |
| Run bulk import (2021-2024) | EC2 | ⏳ Pending |

**AWS Services:**

| Service | Purpose | Cost |
|---------|---------|------|
| Lambda | Daily ingestion (5 min/day) | ~$2-5/month |
| EventBridge | Cron trigger | Free |
| Secrets Manager | Store Supabase keys | ~$1/month |
| EC2 | Bulk import (one-time, 2-3 hrs) | ~$0.05 total |
| CloudWatch | Logs & monitoring | ~$1-2/month |

**Total: ~$5-10/month**

### 🟡 Priority 2: Run Remaining Migrations

| Migration | Purpose | Status |
|-----------|---------|--------|
| `create_personal_records_table.sql` | All-time best performances | ⏳ Pending |
| `create_athlete_training_zones.sql` | Versioned training zones | ⏳ Pending |

### 🟢 Priority 3: Git Commit ✅ DONE

All changes committed and pushed to GitHub:
- GitHub repository cleaned (20+ files removed from tracking)
- Wellness integration merged into main ingestion script
- Documentation updated

---

## NEXT - Coming Soon

### Questionnaire Database Integration
- Connect daily/weekly surveys to database
- Currently in test mode - needs real database writes
- Enable closed-loop analytics

### Dashboard Enhancements
- Intervals visualization tab (temporarily removed)
- Configurable moving averages
- Wellness recap window

---

## LATER - Future Phases

### Phase 3: Analytics Engine
*Prerequisites: 60-90 days of survey data at 70-90% completion rate*

**Correlations to Build:**
- CTL vs Fatigue (training load vs tiredness)
- RPE Calibration (map perceived effort to actual HR zones)
- Sleep vs Performance
- GCT/LSS vs Soreness (biomechanical fatigue indicators)
- Drift Analysis ("same workout feels harder")

### Phase 4: Advanced Features
- Injury risk prediction
- Performance readiness score
- Training load recommendations
- Export capabilities (CSV/Excel)

---

# PART 3: REFERENCE

## 📊 DATABASE SCHEMA

### Core Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `athlete` | Profiles | athlete_id, name, intervals_icu_id |
| `users` | Authentication | id, name, password_hash, role, athlete_id |
| `activity_metadata` | Activity summaries | activity_id, date, distance_m, duration_sec, avg_hr, weather_* |
| `activity` | GPS timeseries | activity_id, lat, lng, heartrate, cadence, watts |
| `activity_intervals` | Workout segments | activity_id, type, distance, moving_time, average_heartrate |
| `wellness` | Daily wellness | athlete_id, date, hrv, sleep_quality, soreness |

### Survey Tables

| Table | Purpose |
|-------|---------|
| `daily_workout_surveys` | Post-workout RPE, satisfaction, goals |
| `weekly_wellness_surveys` | BRUMS, REST-Q, OSLO metrics |

### Configuration Tables

| Table | Purpose |
|-------|---------|
| `personal_records` | All-time best performances |
| `athlete_training_zones` | Versioned HR/Pace/Lactate zones |

---

## 🔄 DATA FLOW & CALCULATIONS

### Ingestion Pipeline

```
1. FETCH: Intervals.icu API → Activity list
2. DOWNLOAD: FIT file (or fallback to Streams API)
3. PARSE: Extract GPS, HR, power, biomechanics
4. ENRICH: Weather from Open-Meteo (archive → forecast → null)
5. CALCULATE: Moving time (Strava algorithm)
6. NORMALIZE: Type conversions (floats → ints for INTEGER columns)
7. INSERT: Supabase REST API (metadata, records, intervals)
```

### Key Calculations

| Calculation | Location | Formula |
|-------------|----------|---------|
| GPS conversion | Ingestion | `degrees = semicircles × (180 / 2^31)` |
| Moving time | Ingestion | Strava algorithm (speed > threshold) |
| Pace | Dashboard | `pace_min_km = duration_min / distance_km` |
| CTL | Dashboard | 42-day exponential moving average of TSS |
| ATL | Dashboard | 7-day exponential moving average of TSS |
| TSB | Dashboard | `CTL - ATL` |

### Fallback Cascades

**FIT File Parsing:**
```
FIT file → Parse success → Full data
         → Parse fails → Streams API fallback
                       → Sophie's watch has firmware issue
                       → Streams work perfectly
```

**Weather Enrichment:**
```
Archive API (3 retries) → Success: weather_source='archive'
                        → Fail → Forecast API (3 retries)
                               → Success: weather_source='forecast'
                               → Fail → weather_source=NULL (continue import)
```

**Heart Rate:**
```
FIT metadata (avg_heart_rate) → Present: use it
                              → Missing → Streams API
                                        → Missing → Calculate from records
```

---

## ☁️ AWS AUTOMATION PLAN

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     AWS AUTOMATION                              │
└─────────────────────────────────────────────────────────────────┘

DAILY AUTOMATION (Ongoing):
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ EventBridge  │────▶│   Lambda     │────▶│   Supabase   │
│ (6 AM daily) │     │  (Python)    │     │  (Database)  │
└──────────────┘     └──────────────┘     └──────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │   Secrets    │
                     │   Manager    │
                     └──────────────┘

BULK IMPORT (One-time):
┌──────────────┐
│     EC2      │──▶ 5 parallel processes (1 per athlete)
│  (t3.small)  │──▶ intervals_hybrid_to_supabase.py --athlete "Name"
│   2-3 hrs    │──▶ ~3,000 activities (2021-2024)
└──────────────┘
```

### Cost Breakdown

| Service | Usage | Monthly Cost |
|---------|-------|--------------|
| Lambda | 30 invocations × 5 min | ~$2-5 |
| EventBridge | 30 triggers | Free |
| Secrets Manager | 2 secrets | ~$1 |
| CloudWatch Logs | Minimal | ~$1-2 |
| EC2 (one-time) | 3 hours | $0.05 total |
| **TOTAL** | | **~$5-10/month** |

### Implementation Steps

**Phase 1: Billing & IAM (15 min)**
1. Create billing alert ($10 threshold)
2. Create IAM execution role for Lambda
3. Attach AWSLambdaBasicExecutionRole policy

**Phase 2: Secrets (15 min)**
1. Store SUPABASE_URL in Secrets Manager
2. Store SUPABASE_SERVICE_ROLE_KEY
3. Grant Lambda role access to secrets

**Phase 3: Lambda (1 hour)**
1. Create deployment package (ZIP)
2. Deploy function (Python 3.11)
3. Configure environment variables
4. Set timeout (5 min) and memory (512 MB)
5. Test manual invocation

**Phase 4: EventBridge (15 min)**
1. Create rule: `cron(0 11 * * ? *)` (6 AM Eastern = 11 AM UTC)
2. Add Lambda as target
3. Enable rule

**Phase 5: EC2 Bulk Import (2-3 hours)**
1. Launch t3.small instance (Ubuntu 22.04)
2. SSH and install Python 3.11
3. Upload scripts + credentials
4. Run 5 parallel imports (one per athlete)
5. Verify data in Supabase
6. Terminate instance

**Phase 6: Monitoring (30 min)**
1. Create CloudWatch alarm for Lambda errors
2. Set up email notification
3. Monitor for 7 days

---

## 🗂️ ARCHIVE - Completed Work

### Phase 1: Foundation (Oct 2025) ✅
- 100% weather coverage via 6-attempt cascade
- 100% HR capture with fallback chain
- Retry logic with exponential backoff
- Universal scalability (no athlete-specific code)

### Phase 1.5-1.6: Visualizations (Oct 2025) ✅
- Intervals visualization with shaded regions
- LRU caching (sub-5ms queries)
- Dual Y-axis charts
- French localization

### Phase 2A: Authentication (Nov 2025) ✅
- 6 user accounts with bcrypt hashing
- Role-based access (athlete vs coach)
- Login modal with session management
- Coach athlete selector dropdown

### Phase 2B: Questionnaires (Nov 2025) ✅
- Daily workout surveys (RPE, satisfaction)
- Weekly wellness surveys (BRUMS, REST-Q, OSLO)
- Form validation and French UI

### Phase 2C: Personal Records & Training Zones (Nov 2025) ✅
- UI complete, migrations ready
- Versioned zone configuration
- Backdatable effective dates

### Phase 2D: Database Migration (Nov 21-22, 2025) ✅
- New Supabase database deployed
- Intervals bug fixed (100% success rate)
- Weather backfill system implemented
- 956 activities imported

### Phase 2E: Mobile-First Design (Nov 22, 2025) ✅
- Viewport meta tag
- 164 lines responsive CSS
- 15 Plotly charts with autosize
- 20 responsive layout columns

### Phase 2F: Production Deployment (Nov 23, 2025) ✅
- Dashboard live on ShinyApps.io
- App ID: 16149191
- All validation checks passed

### Phase 2G: Performance Optimization (Nov 28, 2025) ✅
- N+1 query problem fixed (50-100x faster)
- Vectorized pandas operations (10x faster)
- Deployed to production

### Phase 2H: Ingestion Validation (Nov 29, 2025) ✅
- Dry-run test passed
- Decimal precision fix applied
- Real import test passed (14 activities)
- Data integrity verified
- AWS automation plan finalized

### Phase 2I: GitHub Cleanup & Wellness Integration (Nov 29, 2025) ✅
- GitHub repository cleaned (20+ utility/test files → gitignore)
- Wellness ingestion merged into main script
- Auto-imports wellness for ALL athletes on every run
- UPSERT prevents duplicates (safe to run multiple times)
- README.md updated with correct project structure
- Pushed to: https://github.com/MarcPaquet/INS_Dashboard

---

## 📝 QUICK REFERENCE

### Athlete API Keys Location
```
~/Documents/INS/athletes.json.local
```

### Environment Variables
```
SUPABASE_URL=https://vqcqqfddgnvhcrxcaxjf.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<secret>
OM_TIMEOUT=10
AQ_TIMEOUT=10
```

### Common Commands

```bash
# Test import (dry-run) - also tests wellness
python intervals_hybrid_to_supabase.py --oldest 2025-11-25 --newest 2025-11-28 --dry-run

# Real import (specific athlete)
python intervals_hybrid_to_supabase.py --athlete "Matthew Beaudet" --oldest 2021-01-01 --newest 2024-12-31

# Run dashboard locally
shiny run supabase_shiny.py
```

### ShinyApps.io Registry

| App Name | App ID | Status |
|----------|--------|--------|
| saintlaurentselect_dashboard | 16149191 | ✅ PRODUCTION |
| ins_dashboard | 16146104 | ⏸️ Not in use |

### Supabase Database
- **Project:** vqcqqfddgnvhcrxcaxjf
- **Region:** Default
- **Tables:** 11 (athlete, users, activity_metadata, activity, activity_intervals, wellness, daily_workout_surveys, weekly_wellness_surveys, personal_records, athlete_training_zones)

### GitHub Repository
- **URL:** https://github.com/MarcPaquet/INS_Dashboard
- **Files:** 12 (+ 8 migrations)
- **Local-only:** scripts/, tests/, utility files (via .gitignore)

---

## 🌍 LANGUAGE

| Context | Language |
|---------|----------|
| Dashboard UI | French |
| Graph labels | French |
| Code comments | English |
| This document | English |
| Athlete communication | French |

---

**END OF DOCUMENT**

*Last Updated: November 29, 2025*
*Next Session: AWS automation setup*
