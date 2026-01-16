# 📊 INS DASHBOARD - Master Context & Backlog

**Project:** Intervals.icu → Supabase Data Ingestion System
**Team:** Saint-Laurent Sélect Running Club
**Last Updated:** January 16, 2026 (AWS Setup Session)
**Status:** ✅ **PRODUCTION LIVE** - https://insquebec-sportsciences.shinyapps.io/saintlaurentselect_dashboard/

---

## 📖 HOW TO USE THIS DOCUMENT

| Audience | What to Read |
|----------|--------------|
| **Marc (Owner)** | Update after each session. Keep CONTEXT current, move completed tasks to ARCHIVE. |
| **Claude Code** | Read CONTEXT first, check BACKLOG for priorities, reference ARCHIVE for history. |

**Note:** For detailed archive information (full implementation details, code changes, debugging sessions), also read `ARCHIVE_DETAILED.md`.

---

# 📚 TABLE OF CONTENTS

**PART 1: CONTEXT** (Essential Knowledge)
- [Project Vision](#-project-vision)
- [Athletes & Authentication](#-athletes--authentication)
- [Architecture & Tech Stack](#-architecture--tech-stack)
- [Current State](#-current-state)
- [Core Principles](#-core-principles)
- [Notion Integration](#-notion-integration)

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

**INS Dashboard** = Sports science analytics platform for a running club (23 athletes + 1 coach account).

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

### Club Members (23 athletes + 2 coaches)

**Existing Athletes (5):**
| Member | Intervals.icu ID | Role |
|--------|------------------|------|
| Matthew Beaudet | `i344978` | athlete |
| Kevin Robertson | `i344979` | athlete |
| Kevin A. Robertson | `i344980` | athlete |
| Zakary Mama-Yari | `i347434` | athlete |
| Sophie Courville | `i95073` | athlete |

**New Athletes with Intervals.icu (13):**
| Member | Intervals.icu ID | Role |
|--------|------------------|------|
| Alex Larochelle | `i453408` | athlete |
| Alexandrine Coursol | `i454587` | athlete |
| Doan Tran | `i453651` | athlete |
| Jade Essabar | `jadeessabar` | athlete |
| Marc-Andre Trudeau Perron | `i453625` | athlete |
| Marine Garnier | `i197667` | athlete |
| Myriam Poirier | `i453790` | athlete |
| Nazim Berrichi | `i453396` | athlete |
| Robin Lefebvre | `i453411` | athlete |
| Yassine Aber | `i453944` | athlete |
| Evans Stephen | `i454589` | athlete |
| Ilyass Kasmi | `i248571` | athlete |
| Emma Veilleux | `i172048` | athlete |

**Login-Only Athletes (5) - No data import:**
| Member | Intervals.icu ID | Note |
|--------|------------------|------|
| Cedrik Flipo | - | No Intervals.icu |
| Genevieve Paquin | - | No Intervals.icu |
| Renaud Bordeleau | - | No Intervals.icu |
| Simone Plourde | - | No Intervals.icu |
| Elie Nayrand | `i453407` | **API KEY PENDING** |

**Coach (1 shared account for Samuel & Kerrian):**
| Login | Password | Role |
|-------|----------|------|
| Coach | Coach | coach |

**Note:** Roster updated Jan 14, 2026. Users created, SQL migration executed. **PENDING: Data import (dry run then full import).**

### Access Control
- **Athletes:** See only their own data
- **Coaches (Samuel, Kerrian):** Can view all athletes + select specific athlete via dropdown

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

### 🔧 Recent Session (Jan 16, 2026)

**AWS Infrastructure Setup - IN PROGRESS**

Started AWS infrastructure setup for automated data ingestion. Completed Secrets Manager, IAM, and EC2 launch. Paused before configuring EC2 environment.

**What Was Done:**
- ✅ Created billing alert ($10 threshold)
- ✅ Created 3 secrets in AWS Secrets Manager:
  - `ins-dashboard/supabase` - Database credentials
  - `ins-dashboard/athletes` - 18 athlete API keys
  - `ins-dashboard/config` - Configuration settings
- ✅ Created comprehensive AWS setup guide: `AWS_SETUP_GUIDE.md`
- ✅ Created IAM Policy `INS-Dashboard-SecretsAccess`
- ✅ Created IAM Role `INS-Dashboard-EC2-Role`
- ✅ Launched EC2 instance `INS-Bulk-Import` (t3.small, Ubuntu 24.04)

**AWS Resources Created:**

| Resource | Name | Region | Status |
|----------|------|--------|--------|
| Secret | `ins-dashboard/supabase` | ca-central-1 | ✅ Created |
| Secret | `ins-dashboard/athletes` | ca-central-1 | ✅ Created |
| Secret | `ins-dashboard/config` | ca-central-1 | ✅ Created |
| IAM Policy | `INS-Dashboard-SecretsAccess` | Global | ✅ Created |
| IAM Role | `INS-Dashboard-EC2-Role` | Global | ✅ Created |
| EC2 Instance | `INS-Bulk-Import` | ca-central-1 | ✅ Launched |

**Next Steps (To Resume):**
1. ⏳ Connect to EC2 via Session Manager
2. ⏳ Install Python and dependencies
3. ⏳ Upload/create ingestion scripts
4. ⏳ Run bulk import for all 18 athletes
5. ⏳ **IMPORTANT: Terminate EC2 after import** (avoid charges)

**Reference:** See `AWS_SETUP_GUIDE.md` for complete step-by-step instructions.

---

### Previous Session (Jan 14, 2026)

**Complete Roster Replacement - USERS CREATED, PENDING DATA IMPORT**

Replaced entire roster with new athlete list. Removed 8 old athletes, added 18 new athletes with Intervals.icu credentials.

**What Was Done:**
- ✅ Updated `athletes.json.local` with 18 athletes (those with API keys)
- ✅ Updated `shiny_env.env` with 24 password variables
- ✅ Updated `create_users.py` with 24 users (23 athletes + 1 coach)
- ✅ Created `migrations/roster_update_jan_2026.sql`
- ✅ Ran `create_users.py` - 24 users created in database
- ✅ Ran SQL migration - 14 athletes + 84 training zones inserted

**Dry Run #1 Results (Jan 14, 2026 @ 21:04) - 30 Days Test:**
```
Period: 2025-12-15 → 2026-01-14
Command: python intervals_hybrid_to_supabase.py --oldest 2025-12-15 --newest 2026-01-14 --dry-run
```

| Metric | Value | Status |
|--------|-------|--------|
| Athletes processed | 12/18 | ✅ |
| Activities found | 369 | ✅ |
| Activities processed | 369 | ✅ |
| Failures | 0 | ✅ |

**Data Sources:**
| Source | Count | % |
|--------|-------|---|
| FIT files | 172 | 46.6% |
| Stream fallback | 71 | 19.2% |
| Cross-training (metadata only) | 126 | 34.2% |

**Data Quality:**
| Metric | Result |
|--------|--------|
| Weather coverage | 156/156 outdoor (100%) ✅ |
| HR coverage | 238/243 (98%) ✅ |
| Wellness data | 12/18 athletes ✅ |

**Athletes Without Activities (6):** Kevin Robertson, Yassine Aber, Evans Stephen, Ilyass Kasmi (no running activities in period), plus some new athletes not yet logging.

**Known Issues (Working as Expected):**
- Sophie Courville & Emma Veilleux: FIT firmware bug → Stream fallback works perfectly
- 5 activities without HR → Athletes weren't wearing HR monitors

---

**Pending Steps:**
1. ✅ **Dry run import #1** - 30 days test PASSED
2. ⏳ **Dry run import #2** - Full date range (compare with #1)
3. ⏳ **Full data import** for all 18 athletes:
   ```bash
   python intervals_hybrid_to_supabase.py --oldest 2024-01-01 --newest 2026-01-14
   ```
4. ⏳ **Redeploy dashboard** to ShinyApps.io after import verification

---

**Previous Session (Jan 3, 2026):**

**Phase 3A: Mobile Tab Restriction - DEPLOYED**

Restricted mobile users (screen width < 768px) to only see "Questionnaires" and "Entrée de données manuelle" tabs for improved mobile UX.

**Changes:**
- Added CSS media query rules to hide 3 desktop-only tabs on mobile
- Added JavaScript enforcement to redirect users to allowed tabs
- Blocks keyboard/programmatic navigation to hidden tabs
- Handles desktop ↔ mobile resize transitions

**Code Changes (supabase_shiny.py):**
- Lines 2000-2020: CSS rules in `@media (max-width: 768px)` block
- Lines 2289-2338: JavaScript enforcement logic (IIFE with tab restriction)

**Behavior:**
- Mobile users only see: "Questionnaires", "Entrée de données manuelle"
- Defaults to "Questionnaires" tab on mobile
- Applies to both athletes and coaches
- No bypass option (strict mobile mode)

---

**Previous Session (Dec 29, 2025):**

**Phase 2Y: Monotony/Strain Overlay on Zone Graph - DEPLOYED**

Replaced the separate Monotony/Strain graph with overlay checkboxes on the "Zones d'allure" graph.

**Changes:**
- Added two checkboxes: "Monotonie" and "Strain" (can be toggled independently)
- Monotony displays as purple dotted line on secondary Y-axis (right)
- Strain displays as red dash-dot line on tertiary Y-axis (far right)
- Removed separate monotony/strain graph section
- Uses same zone selection as the main zone graph

**Code Changes (supabase_shiny.py):**
- Lines ~2376-2384: Added `show_monotony` and `show_strain` checkboxes
- Lines ~4164-4205: Monotony/Strain overlay logic in `zone_time_longitudinal()`
- Lines ~4263-4289: Secondary/tertiary Y-axes configuration
- Removed `monotony_strain_graph()` function and related UI

---

**Phase 2Z: Personal Records Expansion - DEPLOYED**

Expanded personal records feature with 15 distances and millisecond support.

**New Distances (15 total):**
- 400m, 800m, 1000m, 1500m, mile, 2000m, 3000m
- 2000m steeple, 3000m steeple
- 5000m, 10000m, 5km (route), 10km (route)
- Semi-marathon, Marathon

**Millisecond Support:**
- Time format: `HH:MM:SS:ms` (e.g., `3:45:12:50`)
- Database: `time_seconds` changed from INTEGER to DECIMAL(10,3)
- Display: Shows centiseconds when present (e.g., `3:45:12`)

**Files Modified:**
- `supabase_shiny.py`: Updated DISTANCES array, `calculate_pace()`, `parse_time_to_seconds()`, `format_time_from_seconds()`
- `complete_database_schema.sql`: Updated personal_records table schema
- NEW: `migrations/update_personal_records_schema.sql`

**Database Migration Required:** Run in Supabase SQL Editor (completed)

---

**Previous Session (Dec 28, 2025):**

**Phase 2X: Conditional Tooltip Display - DEPLOYED**

Modified questionnaire tooltip system to only show the red triangle indicator when there's actual tooltip text to display.

---

**Previous Session (Dec 23, 2025):**

**Schema Sync & GitHub Update - COMPLETE**

Synchronized `complete_database_schema.sql` with the actual production database and pushed all changes to GitHub.

**What Was Done:**
1. ✅ **Schema Audit** - Verified database tables vs schema file
   - Used Supabase REST API to check all 16 objects (14 tables + 2 views)
   - Found 3 missing structures that existed in production but not in schema file

2. ✅ **Schema File Updated** - `complete_database_schema.sql`
   - Added `activity_zone_time` table (Section 9)
   - Added `weekly_zone_time` materialized view (Section 9B)
   - Added zone time calculation functions (Section 9C):
     - `calculate_zone_time_for_activity()`
     - `refresh_all_zone_views()`
     - `recalculate_all_zone_times()`
   - Added `weekly_monotony_strain` table (Section 9D)
   - Added monotony/strain calculation functions (Section 9E):
     - `calculate_monotony_strain_for_week()`
     - `backfill_monotony_strain()`
   - Updated header with accurate table count and last updated date

3. ✅ **GitHub Push** - Commit `ec1c47b`
   - 13 files changed, +5,920 lines / -1,169 lines
   - All Phase 2O-2V changes now in repository
   - 6 new migration files added

**Files Modified:**
- `complete_database_schema.sql`: +600 lines (new sections 9-9E)
- `CLAUDE.md`: Updated documentation
- `supabase_shiny.py`: Phase 2M-2V updates
- `intervals_hybrid_to_supabase.py`: Zone time + monotony integration
- `requirements.txt`: Updated dependencies

**New Files Added:**
- `app.py`: ShinyApps.io wrapper
- `flow.md`: Data flow documentation
- `migrations/create_activity_zone_time.sql`
- `migrations/create_activity_zone_time_incremental.sql`
- `migrations/create_weekly_zone_time.sql`
- `migrations/create_weekly_monotony_strain.sql`
- `migrations/create_lactate_tests.sql`
- `migrations/insert_athlete_zones.sql`

**Database Objects Verified (16 total):**
| Type | Objects |
|------|---------|
| Tables (14) | athlete, users, activity_metadata, activity, activity_intervals, wellness, personal_records, personal_records_history, athlete_training_zones, daily_workout_surveys, weekly_wellness_surveys, lactate_tests, activity_zone_time, weekly_monotony_strain |
| Mat. Views (2) | activity_pace_zones, weekly_zone_time |

---

**Phase 2W: Zone Configuration Change Indicator - DEPLOYED**

When a user selects a date range that spans multiple zone configurations (e.g., zones changed on Dec 12), the dashboard now:
1. Shows an info banner explaining that zone boundaries changed
2. Displays vertical dashed lines on graphs where zones changed

**New Code:**
- `get_zone_changes_in_range()` function (lines 508-561): Queries `athlete_training_zones` for changes within date range
- `zone_change_banner` UI render function: Displays styled info message
- Vertical lines added to `zone_time_longitudinal()` and `monotony_strain_graph()`

**Status:** Deployed to production.

---

**Previous Session (Dec 22, 2025):**
- Phase 2V: Pre-calculated Monotony & Strain
- Migration executed, backfill completed (111 weeks, 5 athletes)
- Dashboard deployed with pre-calculated data support

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

## 📝 NOTION INTEGRATION

### Overview

Claude Code is connected to Marc's Notion workspace via MCP. This enables reading meeting notes and managing tasks directly from conversations.

**IMPORTANT:** At the start of each conversation, read the Notion "To do" database to get current tasks and priorities.

### Notion Structure

| Page/Database | Purpose |
|---------------|---------|
| **Dashboard INS** | Main project page with context and links |
| **Notes de rencontre** | Meeting notes (nested under Dashboard INS) |
| **To do** | Task database with status tracking (PRIMARY task tracker) |

### To-Do Database Schema

| Property | Values |
|----------|--------|
| **État (Status)** | Pas commencé → En cours → Terminé |
| **Priorité** | Faible, Moyenne, Élevée |
| **Type de tâche** | Critique, Bug, Demande de fonctionnalité, Perfectionnement |
| **Niveau d'effort** | Faible, Moyenne, Élevé |

### Task Tracking Workflow

```
1. START OF CONVERSATION: Read Notion "To do" to get current tasks
2. DURING WORK: Update task status in Notion as work progresses
3. Keep CLAUDE.md BACKLOG section synced with Notion for context
4. Notion = primary tracker (Marc creates tasks manually)
5. CLAUDE.md = backup context (ensures Claude has full picture)
```

### Current Tasks (synced from Notion)

| Task | Status | Priority | Type |
|------|--------|----------|------|
| Set-up AWS pour ingestion | En cours | Moyenne | Critique |
| Set-up cron dans AWS | Pas commencé | Moyenne | Critique |
| Ajouter tableau de suivi des RPE | Pas commencé | Faible | Fonctionnalité |
| Ajouter tableau suivi wellness | Pas commencé | Faible | Fonctionnalité |
| Ajout de marqueur pour race | Pas commencé | Faible | Fonctionnalité |

### CRITICAL RULES

1. **NEVER delete anything** without explicit user approval
2. **NEVER add tasks** without listing them first and waiting for approval
3. **Always confirm** before modifying any Notion content
4. **Language**: Notion content in **French**, conversation with Marc in **English**

### Workflow for Adding Tasks from Meeting Notes

```
1. User asks to review meeting notes
2. Claude reads "Notes de rencontre"
3. Claude lists proposed tasks with details
4. User approves/modifies the list
5. Only THEN Claude adds approved items to "To do"
```

### Permissions

- **Read**: Always allowed (meeting notes, to-do list, project pages)
- **Create**: Only after explicit approval
- **Update**: Only after explicit approval
- **Delete**: FORBIDDEN without explicit consent (risk of data loss)

---

# PART 2: BACKLOG

## NOW - Immediate Priorities

### 🔴 Priority 0: Data Import for New Athletes - PENDING

**Goal:** Import activity data for all 18 athletes with Intervals.icu credentials
**Status:** Users created, SQL migration done, awaiting dry run + import

| Step | Command | Status |
|------|---------|--------|
| Dry run test | `python intervals_hybrid_to_supabase.py --oldest 2024-01-01 --newest 2025-01-14 --dry-run` | ⏳ Pending |
| Full import | `python intervals_hybrid_to_supabase.py --oldest 2024-01-01 --newest 2025-01-14` | ⏳ Pending |
| Redeploy dashboard | See deployment command in Quick Reference | ⏳ Pending |

---

### 🟡 Priority 1: AWS Setup for Automation - IN PROGRESS

**Goal:** Automated daily ingestion + one-time bulk historical import
**Status:** Secrets Manager + IAM completed (Jan 16, 2026), EC2 pending
**Region:** `ca-central-1` (Canada Central)
**Guide:** See `AWS_SETUP_GUIDE.md` for detailed instructions

| Task | Service | Status |
|------|---------|--------|
| Set up billing alert ($10) | AWS Console | ✅ Done |
| Store credentials | Secrets Manager | ✅ Done (3 secrets) |
| Create IAM policy | IAM | ✅ Done (`INS-Dashboard-SecretsAccess`) |
| Create IAM role for EC2 | IAM | ✅ Done (`INS-Dashboard-EC2-Role`) |
| Launch EC2 for bulk import | EC2 | ✅ Done (`INS-Bulk-Import`) |
| Configure EC2 environment | EC2 | ⏳ Pending |
| Run bulk import (2024-2026) | EC2 | ⏳ Pending |
| **Terminate EC2** | EC2 | ⏳ After import |
| Create IAM role for Lambda | IAM | ⏳ Pending (after bulk import) |
| Deploy Lambda function | Lambda | ⏳ Pending |
| Configure daily cron (6 AM ET) | EventBridge | ⏳ Pending |

**Secrets Created (Jan 16, 2026):**

| Secret Name | Contents | Created |
|-------------|----------|---------|
| `ins-dashboard/supabase` | Supabase URL + Service Role Key | ✅ 00:14 UTC |
| `ins-dashboard/athletes` | 18 athletes with API keys | ✅ 00:19 UTC |
| `ins-dashboard/config` | Timeouts, timezone, URLs | ✅ 00:20 UTC |

**AWS Services & Estimated Costs:**

| Service | Purpose | Cost |
|---------|---------|------|
| Secrets Manager | Store credentials (3 secrets) | ~$1.20/month |
| Lambda | Daily ingestion (5 min/day) | ~$2-5/month |
| EventBridge | Cron trigger | Free |
| EC2 | Bulk import (one-time, 2-4 hrs) | ~$0.05 total |
| CloudWatch | Logs & monitoring | ~$1-2/month |

**Total: ~$5-10/month ongoing**

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

### Wellness Tracking Window
- Configurable recap window for wellness data display
- Allow users to set how far back to show wellness trends

### Subjective Load Graph (RPE × Time = Charge)
**Concept:** ACL-ATL style graph using questionnaire data instead of objective metrics.

**Formula:**
- Charge = RPE × Duration (minutes)
- This is Foster's sRPE (session RPE) method

**Graph Structure:**
- X-axis: Date
- Y-axis: Charge (arbitrary units)
- ACL line: 7-day EWM of daily total Charge
- ATL line: 28-day EWM of daily total Charge
- Optional: TSB = ATL - ACL

**Data Sources:**
- `daily_workout_surveys.rpe` (1-10 scale)
- `activity_metadata.duration_sec` / 60 = minutes
- Join via activity_id

**Notes:**
- Complements objective CTL/ATL with subjective perception
- Useful for detecting overtraining (high objective load + high subjective load)
- Requires surveys to be filled consistently

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

**Total: 14 Tables + 2 Materialized Views**

### Core Tables (6)

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `athlete` | Profiles | athlete_id, name, intervals_icu_id |
| `users` | Authentication | id, name, password_hash, role, athlete_id |
| `activity_metadata` | Activity summaries | activity_id, date, distance_m, duration_sec, avg_hr, weather_* |
| `activity` | GPS timeseries | activity_id, lat, lng, heartrate, cadence, watts |
| `activity_intervals` | Workout segments | activity_id, type, distance, moving_time, average_heartrate |
| `wellness` | Daily wellness | athlete_id, date, hrv, sleep_quality, soreness |

### Survey Tables (2)

| Table | Purpose |
|-------|---------|
| `daily_workout_surveys` | Post-workout RPE, satisfaction, goals |
| `weekly_wellness_surveys` | BRUMS, REST-Q, OSLO metrics |

### Configuration Tables (3)

| Table | Purpose |
|-------|---------|
| `personal_records` | All-time best performances |
| `personal_records_history` | Historical PR progression |
| `athlete_training_zones` | Versioned HR/Pace/Lactate zones |

### Pre-calculated Tables (3)

| Table | Purpose |
|-------|---------|
| `activity_zone_time` | Zone time per activity (incremental calculation) |
| `weekly_monotony_strain` | Carl Foster monotony/strain per week |
| `lactate_tests` | Manual lactate test results |

### Materialized Views (2)

| View | Purpose |
|------|---------|
| `activity_pace_zones` | Pace zone distribution per activity |
| `weekly_zone_time` | Zone time aggregated by week |

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
│     EC2      │──▶ PARALLEL processing (12-15 athletes simultaneously)
│  (t3.small)  │──▶ --skip-weather + wellness flags
│   ~2-4 hours │──▶ ~20,000+ activities (fast!)
└──────────────┘

ON-DEMAND (Refresh Button):
┌──────────────┐
│   Dashboard  │──▶ Button triggers Lambda
│   Button     │──▶ Shows "Importing..." until done
│              │──▶ Full sync for all athletes
└──────────────┘
```

### 🔐 AWS Secrets Manager - Complete Secret List

**IMPORTANT:** These are ALL the secrets needed for AWS Lambda/EC2 automation.

#### Secret 1: `ins-dashboard/supabase` (JSON)
```json
{
  "SUPABASE_URL": "https://vqcqqfddgnvhcrxcaxjf.supabase.co",
  "SUPABASE_SERVICE_ROLE_KEY": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZxY3FxZmRkZ252aGNyeGNheGpmIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MjEwMDUyNCwiZXhwIjoyMDc3Njc2NTI0fQ.JM7kDSnDIPdBqZN0DrW-BEA7VaavS3_Kp_dT9Q-Mtmo"
}
```

#### Secret 2: `ins-dashboard/athletes` (JSON)
```json
[
  {"id": "i344978", "name": "Matthew Beaudet", "api_key": "3o9i1mgt6e7yfzoktkc0fmrj2"},
  {"id": "i344979", "name": "Kevin Robertson", "api_key": "2s39s4kmmhnw02y32qp4lgw4q"},
  {"id": "i344980", "name": "Kevin A. Robertson", "api_key": "7jwc28oik78tdjixjl94l8wee"},
  {"id": "i95073", "name": "Sophie Courville", "api_key": "99atczyc8ajd1z510hdlh0aw"},
  {"id": "i347434", "name": "Zakary Mama-Yari", "api_key": "70rmcmsk297dkkgnevn7wwupc"},
  {"id": "i453408", "name": "Alex Larochelle", "api_key": "jkdw4ivm6wvudmiwoh7olzyd"},
  {"id": "i454587", "name": "Alexandrine Coursol", "api_key": "2o0xpawaj99soor5blv66lxbf"},
  {"id": "i453651", "name": "Doan Tran", "api_key": "75db3mdf3xo7wjco981r71frn"},
  {"id": "jadeessabar", "name": "Jade Essabar", "api_key": "1cy45wy7nldmza14wzsr25oie"},
  {"id": "i453625", "name": "Marc-Andre Trudeau Perron", "api_key": "1zuh81vaeu1hc9th63gteatsj"},
  {"id": "i197667", "name": "Marine Garnier", "api_key": "yi34bczjcunrzlb8divoampg"},
  {"id": "i453790", "name": "Myriam Poirier", "api_key": "1p9yhcxs6cx8oh0c7t0xrlxbw"},
  {"id": "i453396", "name": "Nazim Berrichi", "api_key": "4qxdul0cod6xpzg7qoi086tmx"},
  {"id": "i453411", "name": "Robin Lefebvre", "api_key": "3b906pd2t8lwsk215dbp7lw6v"},
  {"id": "i453944", "name": "Yassine Aber", "api_key": "5yhz82b6a4unz7afweqfmmd08"},
  {"id": "i454589", "name": "Evans Stephen", "api_key": "11ayv0bp65zwf7whezd9m83sh"},
  {"id": "i248571", "name": "Ilyass Kasmi", "api_key": "4bcyuvuzdu2yctsl9dwxx38mi"},
  {"id": "i172048", "name": "Emma Veilleux", "api_key": "4bcyuvuzdu2yctsl9dwxx38mi"}
]
```

#### Secret 3: `ins-dashboard/config` (JSON) - Optional
```json
{
  "INTERVALS_API_URL": "https://intervals.icu/api/v1",
  "OPENMETEO_API_URL": "https://api.open-meteo.com",
  "OM_TIMEOUT": "10",
  "AQ_TIMEOUT": "10",
  "BATCH_SIZE": "500",
  "MAX_RETRIES": "3",
  "RETRY_DELAY": "2",
  "INS_TZ": "America/Toronto"
}
```

#### Summary Table

| Secret Name | Type | Contents | Required |
|-------------|------|----------|----------|
| `ins-dashboard/supabase` | JSON | Supabase URL + Service Role Key | ✅ Yes |
| `ins-dashboard/athletes` | JSON | 18 athletes with Intervals.icu API keys | ✅ Yes |
| `ins-dashboard/config` | JSON | API URLs, timeouts, config | Optional (can hardcode) |

**Total Secrets: 2-3** (depending on whether you store config in code or Secrets Manager)

#### AWS CLI Commands to Create Secrets

```bash
# Create Supabase secret
aws secretsmanager create-secret \
  --name "ins-dashboard/supabase" \
  --description "Supabase credentials for INS Dashboard" \
  --secret-string '{"SUPABASE_URL":"https://vqcqqfddgnvhcrxcaxjf.supabase.co","SUPABASE_SERVICE_ROLE_KEY":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}'

# Create Athletes secret (from file)
aws secretsmanager create-secret \
  --name "ins-dashboard/athletes" \
  --description "Intervals.icu API keys for all athletes" \
  --secret-string file://athletes.json.local
```

#### Lambda Code to Retrieve Secrets

```python
import boto3
import json

def get_secrets():
    client = boto3.client('secretsmanager', region_name='us-east-1')

    # Get Supabase credentials
    supabase_secret = client.get_secret_value(SecretId='ins-dashboard/supabase')
    supabase = json.loads(supabase_secret['SecretString'])

    # Get athlete API keys
    athletes_secret = client.get_secret_value(SecretId='ins-dashboard/athletes')
    athletes = json.loads(athletes_secret['SecretString'])

    return supabase, athletes
```

---

### API Rate Limits

**Intervals.icu API:**
| Limit | Value |
|-------|-------|
| Per second | **30 requests** |
| Per 10 seconds | **132 requests** |
| Daily/Monthly | **No limit** |

**Open-Meteo API (weather):**
| Limit | Value |
|-------|-------|
| Per day | **10,000 calls** |
| Per month | 300,000 calls |

### Bulk Import Strategy (Updated Dec 2, 2025)

**Key Decision:** Skip weather for bulk import, fetch weather only for daily cron.

```bash
# PARALLEL bulk import (all athletes simultaneously, ~2-4 hours total)
# Each athlete runs: activities + wellness, skip weather
python intervals_hybrid_to_supabase.py --athlete "Matthew Beaudet" --oldest 2021-01-01 --newest 2024-12-31 --wellness-oldest 2021-01-01 --wellness-newest 2024-12-31 --skip-weather &
python intervals_hybrid_to_supabase.py --athlete "Kevin Robertson" --oldest 2021-01-01 --newest 2024-12-31 --wellness-oldest 2021-01-01 --wellness-newest 2024-12-31 --skip-weather &
python intervals_hybrid_to_supabase.py --athlete "Kevin A. Robertson" --oldest 2021-01-01 --newest 2024-12-31 --wellness-oldest 2021-01-01 --wellness-newest 2024-12-31 --skip-weather &
python intervals_hybrid_to_supabase.py --athlete "Zakary Mama-Yari" --oldest 2021-01-01 --newest 2024-12-31 --wellness-oldest 2021-01-01 --wellness-newest 2024-12-31 --skip-weather &
python intervals_hybrid_to_supabase.py --athlete "Sophie Courville" --oldest 2021-01-01 --newest 2024-12-31 --wellness-oldest 2021-01-01 --wellness-newest 2024-12-31 --skip-weather &
# Add more athletes as needed (up to 12-15 parallel processes is safe)
wait  # Wait for all to complete
```

**What gets imported:**
| Data Type | Bulk Import | Daily Cron |
|-----------|-------------|------------|
| Activities (FIT/Streams) | ✅ Yes | ✅ Yes |
| GPS Records | ✅ Yes | ✅ Yes |
| Intervals | ✅ Yes | ✅ Yes |
| Wellness (HRV, sleep, etc.) | ✅ Yes | ✅ Yes |
| Weather | ❌ Skipped | ✅ Yes |

**Why this works:**
- `--skip-weather` bypasses Open-Meteo rate limits entirely
- Intervals.icu has no daily limit, only 30 req/sec
- 12-15 parallel processes = ~20-24 req/sec (safely under 30/sec limit)
- ~20,000 activities imported in ~2-4 hours instead of 2-3 days
- Wellness data included for closed-loop analytics

### Cost Breakdown

| Service | Usage | Monthly Cost |
|---------|-------|--------------|
| Lambda | 30 invocations × 5 min | ~$2-5 |
| EventBridge | 30 triggers | Free |
| Secrets Manager | 2-3 secrets | ~$1.20 |
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

**Phase 5: EC2 Bulk Import (~2-4 hours)**
1. Launch t3.small instance (Ubuntu 22.04)
2. SSH and install Python 3.11
3. Upload scripts + credentials
4. Run all athletes in parallel with `--skip-weather` + wellness:
   ```bash
   python intervals_hybrid_to_supabase.py --athlete "Matthew Beaudet" --oldest 2021-01-01 --newest 2024-12-31 --wellness-oldest 2021-01-01 --wellness-newest 2024-12-31 --skip-weather &
   # ... (repeat for all 12-15 athletes)
   wait
   ```
5. Verify data in Supabase
6. Terminate instance

**Phase 6: Monitoring (30 min)**
1. Create CloudWatch alarm for Lambda errors
2. Set up email notification
3. Monitor for 7 days

### Pre-Bulk Import Checklist

**Marc's Pending Decisions:**
- [ ] Confirm date range with manager (2021 vs 2023 start)
- [ ] Ensure all athletes link watches directly (not Strava)
- [ ] Specify bulk import start date

**Validation Before Import:**
- [ ] Test 10 activities per athlete (dry-run with --skip-weather)
- [ ] Test 100 activities total (real import with --skip-weather)
- [ ] Verify no duplicates created
- [ ] Verify Stryd data capture (FIT path)
- [ ] Verify moving time calculation
- [ ] Verify historical wellness import
- [ ] Check Supabase row counts before/after
- [ ] Note: Weather skipped for bulk import (will be fetched by daily cron going forward)

**Strava Linking Issue (IMPORTANT):**
When athletes link Strava instead of watch, Strava strips Stryd biomechanics data from FIT files. Solution: Athletes must link watch directly to Intervals.icu. Marc will coordinate this before bulk import.

---

## 🗂️ ARCHIVE - Completed Work

> **📚 See `ARCHIVE_DETAILED.md` for full implementation details, code snippets, and debugging notes.**

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

### Phase 2J: Pre-Bulk Import Audit (Dec 1, 2025) ✅
- Comprehensive audit of ingestion system before AWS bulk import
- Validated: moving time, LSS (57% coverage), GCT (54% coverage)
- Added duplicate prevention: `get_existing_activity_ids()` function
- Added batch retry logic with exponential backoff (1s, 2s, 4s)
- Added historical wellness import: `--wellness-oldest` and `--wellness-newest` CLI args
- Added stats tracking: `activities_skipped`, `batch_failures`, `wellness_days_imported`
- Finalized AWS architecture: sequential processing, 2-3 days for bulk import
- Documented Open-Meteo rate limits and import strategy

### Phase 2K: Deployment Fix & Documentation (Dec 6, 2025) ✅
- **ROOT CAUSE:** ShinyApps.io deployment was failing with "exit status 1"
- **Investigation:** Systematic testing identified multiple configuration issues
- **Key Findings:**
  1. `.python-version` was set to 3.11 (ShinyApps.io only supports Python 3.9.x)
  2. `requirements.txt` had version constraints causing package conflicts
  3. Too many files being deployed (migrations, supabase CLI, scripts)
  4. No error handling wrapper to display errors on the page
- **Solution:**
  1. Removed `.python-version` file entirely
  2. Simplified `requirements.txt` to package names only (no version constraints)
  3. Created `app.py` wrapper with try/except to catch and display import errors
  4. Added comprehensive `--exclude` flags to rsconnect deploy command
- **Testing Methodology:** Binary search approach
  1. Deployed minimal "Hello World" (worked)
  2. Added packages incrementally (all worked)
  3. Added local modules (worked)
  4. Added env files (worked)
  5. Added main app (worked)
- **Documentation:** Full deployment command and checklist added to CLAUDE.md

### Phase 2L: UI Polish & Performance (Dec 7, 2025) ✅
- **UI Cleanup:**
  - Removed all emoticons from dashboard for professional appearance
  - Fixed range selection sliders (CSS hides raw seconds display)
  - Pace axis on comparison chart now shows MM:SS format (was raw seconds)
  - Pace axis on single activity XY graph with same MM:SS formatting
  - Pace axis direction corrected: slower pace at top, faster at bottom
- **Performance Optimizations:**
  - Vectorized pace calculation in `fetch_metadata` (replaced slow `.apply()` with `np.where`)
  - Added memory cache for timeseries data with 1-hour TTL (`_timeseries_cache`)
  - Pre-computed columns in `fetch_timeseries_cached`: `speed_max`, `pace_sec_km`, `hr_smooth`, `pace_smooth`, `dist_cumsum_km`
  - Updated `_prep_xy()` to use pre-computed columns instead of recalculating
- **Technical Details:**
  - Added CSS rules for `.irs-min`, `.irs-max`, `.irs-single` to hide slider values
  - Implemented `tickmode='array'` with custom `tickvals` and `ticktext` for pace axes
  - Pace formatting function: `format_pace_label(seconds)` → "M:SS" format
- **Result:** Faster chart rendering, cleaner UI, intuitive pace display

### Phase 2M: Temporal Zone Matching + Zone Analysis (Dec 8, 2025) ✅
- **Temporal Zone Matching** - Sports science accuracy for zone calculations
  - New `fetch_zones_for_date()` function with caching (~line 378)
  - Modified `calculate_zone_time_by_week()` with `use_temporal_zones` parameter
  - Zone lookups cached by (athlete_id, effective_date) with 1-hour TTL
  - Past activities use zones that were effective at that time, not current zones
- **Fixed Zone Distribution** - "Analyse des zones d'allure" now works
  - Was querying non-existent `activity_pace_zones` database view
  - Rewrote to use `calculate_zone_time_by_week()` like longitudinal graph
- **Shared Timeframe** - Unified date range for all summary graphs
  - Removed separate `pace_zone_date_start/end` inputs
  - Zone analysis now uses `input.date_start()` and `input.date_end()`
- **UI Cleanup:**
  - X-axis label changed from "Semaine (lundi)" to "Date"
  - Removed explanatory text from zone analysis card
  - EWM min_periods set to span (not min of span/len) for proper data cropping
- **Deployed:** Production live but with performance issues noted for next session

### Phase 2N: Production Plotly Fixes (Dec 9, 2025) ✅
- **Plotly Responsiveness on Production** - Graphs now display full width on ShinyApps.io
  - Added CSS rules for `.shinywidgets-container`, `.widget-container`, `.js-plotly-plot` with `width: 100% !important`
  - Added `autosize=True` to all Plotly figure layouts (~10+ figures)
  - Added JavaScript resize triggers using `Plotly.Plots.resize()` on page load and tab changes
  - CSS block added at lines 1562-1605 in `supabase_shiny.py`
- **Zone Time Longitudinal Graph** - Fixed invisible moving average lines
  - Root cause: Pandas `Timestamp` objects weren't rendering properly in Plotly
  - Solution: Convert dates to `YYYY-MM-DD` strings and y-values to Python lists
  - Code at lines 3596-3603: `x_dates = [d.strftime('%Y-%m-%d') for d in display_df["week_start"]]`
- **No GPS Data Handling** - Clear error message for athletes without pace data
  - Added check: `if max_ctl < 0.1 and max_atl < 0.1`
  - Displays "Aucune donnee GPS/allure pour cet athlete" instead of empty graph
  - Kevin A. Robertson (i344980) now shows appropriate message
- **Comparison Graph Error Handling** - Better validation for empty data
  - Added checks after NaN cleaning to prevent "extends to zero" errors
- **Deployed:** All fixes live on production

### Phase 2O: Zone System Overhaul + Materialized Views (Dec 12, 2025) ✅
- **New 6-Zone Configuration** - Real athlete-specific pace zones
  - Deleted old hardcoded zones from `athlete_training_zones` table
  - Inserted 30 rows (5 athletes × 6 zones) with effective_from_date = 2020-01-01
  - Zone logic: Z6 fastest (pace ≤ threshold), Z1 slowest (pace > threshold)
  - Zones 5-2 use bracket ranges (lower < pace ≤ upper)
- **Materialized Views** - Major performance improvement
  - `activity_zone_time`: Pre-calculates zone time per activity from GPS data
  - `weekly_zone_time`: Aggregates zone time by week per athlete
  - `refresh_all_zone_views()`: SQL function to refresh both views
  - Migrations: `create_activity_zone_time.sql`, `create_weekly_zone_time.sql`, `insert_athlete_zones.sql`
- **Automation** - Auto-refresh on data import
  - Added zone view refresh to `intervals_hybrid_to_supabase.py` (after activity import)
  - 300-second timeout for large view refreshes
- **Dashboard Updates** - Queries views instead of Python calculation
  - New `fetch_weekly_zone_time_from_view()` function (line 617)
  - Zone analysis card updated (line 3365)
  - Longitudinal zone graph updated (line 3564)
  - Expected improvement: ~60s → ~1s load time
- **Bulk Import Workflow** - Drop views before, recreate after
  - SQL: `DROP MATERIALIZED VIEW IF EXISTS weekly_zone_time, activity_zone_time CASCADE;`
  - Then recreate from migration SQL files
- **Deployed:** All changes live on production

### Phase 2P: UI Cleanup + Questionnaire Fixes (Dec 12, 2025 - Session 2) ✅
- **Plotly Deprecation Fix**
  - Changed `titlefont` → `title_font` in comparison graph
  - Eliminated console warnings
- **Lactate Card for Everyone**
  - Removed athlete-only restriction
  - Added coach athlete selector (reuses `zones_selected_athlete`)
  - Updated handlers for coach support
- **Calendar Removal** - Cleaner UI, better mobile
  - Deleted `year_calendar_heatmap()` (~185 lines)
  - Deleted `_load_calendar_all_data()`, navigation handlers
  - Deleted calendar CSS (kept `activities_by_date` - still used by activity selector)
- **Activity Label Cleanup**
  - Removed "(intervalles)" suffix from dropdowns
  - Removed intervals query (performance improvement)
- **Questionnaire Improvements**
  - Uses same activity list as "Analyse de séance" (via `act_label_to_id`)
  - Filters out activities with already-filled surveys
  - Removed separate date picker - uses main date range
  - Shows success message when all surveys complete
- **New Database Table**
  - `lactate_tests`: athlete_id, test_date, distance_m, lactate_mmol, notes
  - Migration: `create_lactate_tests.sql`
- **Deployed:** All changes live on production

### Phase 2Q: Zone Graph Enhancements + Coach Selector Fix (Dec 19, 2025) ✅
- **Coach Athlete Selector Fix**
  - Added `@reactive.event(is_authenticated, user_role)` decorator (line 2612)
  - Dropdown now properly appears after coach login
  - Coaches can select any athlete from top bar
- **Stacked Bar Chart for "Fusionner" Mode**
  - Replaced single merged line with stacked bar chart
  - Each zone displayed as colored segment using `ZONE_COLORS`
  - Z1 at bottom, higher zones stacked on top
  - EWM smoothing applied to each zone before stacking
  - Uses `go.Bar()` with `barmode='stack'`
- **~~ATL + CTL Lines in Distinct Mode~~** (Reverted)
  - Initially added but removed - reserved for future improvement
  - Distinct mode shows only individual zone lines with EWM smoothing
- **Code Changes (supabase_shiny.py):**
  - Line 2612: `@reactive.event(is_authenticated, user_role)`
  - Lines 3538-3595: Stacked bar chart implementation
- **Deployed:** All changes live on production

### Phase 2R: Zone Graph Grouped Bars + ACL/ATL Lines (Dec 20, 2025) ✅
- **Grouped Bar Chart for "Fusionner" Mode**
  - Changed from stacked (`barmode='stack'`) to grouped (`barmode='group'`)
  - Zones now display side-by-side within each week
  - Added spacing: `bargap=0.15`, `bargroupgap=0.05`
  - Better visual comparison of zone proportions per week
- **ACL/ATL Toggle for Zone Load Lines**
  - New "ACL - ATL" checkbox next to Distinct/Fusionner radio buttons
  - When enabled, overlays two moving average lines on the graph:
    - **ACL** (Acute): Red dashed line using `atl_days` (e.g., 7 days)
    - **ATL** (Chronic): Navy solid line using `ctl_days` (e.g., 28 days)
  - Shows total minutes across all selected zones combined
  - Works in both Distinct and Fusionner modes
- **EWM Precision Fix**
  - Changed from integer division (`// 7`) to float division (`/ 7.0`)
  - 15 days → 2.14 weeks (not 2), 20 days → 2.86 weeks (not 2)
  - More accurate moving average differentiation
- **Code Changes (supabase_shiny.py):**
  - Line 1970-1974: Added `ui.input_checkbox("show_acl_atl", "ACL - ATL")`
  - Line 3539: `atl_weeks = max(1.0, atl_days / 7.0)`
  - Line 3591-3595: `barmode='group'` with spacing params
  - Lines 3660-3705: ACL/ATL line calculation and traces
- **Deployed:** All changes live on production

### Phase 2S: Incremental Zone Time Calculation (Dec 20, 2025) ✅
- **Converted activity_zone_time to Regular Table**
  - Was: Materialized view requiring full refresh (60-300s for 2.5M+ rows)
  - Now: Regular table with incremental per-activity updates (~100ms)
  - Preserves existing calculated data during migration
- **Created `calculate_zone_time_for_activity(activity_id)` SQL Function**
  - Calculates zone time for a single activity
  - Uses temporal zone matching (zones effective on activity date)
  - Same calculation logic as original materialized view
  - UPSERTs result into `activity_zone_time` table
- **Created Trigger `trg_zone_config_changed`**
  - Fires AFTER INSERT on `athlete_training_zones`
  - When zones are inserted with backdated `effective_from_date`:
    - Automatically recalculates zone time for affected athlete
    - Processes all activities from effective date to today
    - Batches multiple inserts using PostgreSQL transition tables
  - Refreshes `weekly_zone_time` view once at end
- **Updated `refresh_all_zone_views()`**
  - Now only refreshes `weekly_zone_time` (activity-level is incremental)
  - Much faster since it just aggregates pre-calculated data
- **Added `recalculate_all_zone_times()` Utility Function**
  - For bulk operations or zone configuration changes
  - Recalculates ALL activities (use sparingly)
- **Updated Python Ingestion Script**
  - Added `calculate_zone_time_for_activity()` function (lines 1356-1407)
  - Calls SQL function after each activity's GPS data is inserted
  - Logs zone time calculation result
- **Files Created/Modified:**
  - NEW: `migrations/create_activity_zone_time_incremental.sql`
  - MODIFIED: `intervals_hybrid_to_supabase.py`
- **Migration Required:** Run SQL in Supabase before next import

### Phase 2T: Tooltip Z-Index Fix (Dec 20, 2025) ✅
- **Problem:** Questionnaire tooltips appeared behind card headers due to CSS stacking contexts
- **Root Cause:** Card elements create stacking contexts; CSS `position: absolute` with `z-index` cannot escape parent stacking context
- **Solution:** JavaScript-powered tooltip positioning
  - Tooltip element appended to `<body>` (outside all stacking contexts)
  - Uses `position: fixed` with dynamically calculated coordinates
  - Calculates position based on trigger's `getBoundingClientRect()`
  - Automatically adjusts to stay within viewport bounds
  - Falls back to showing below trigger if no room above
- **Code Changes (supabase_shiny.py):**
  - Lines 1207-1267: CSS for `.tooltip-trigger` and `.custom-tooltip`
  - Lines 1712-1752: JavaScript for tooltip positioning
  - `scale_with_tooltip()` function uses `data-tooltip` attribute
- **Technical Details:**
  - Single tooltip DOM element reused for all triggers
  - Event delegation with `$(document).on('mouseenter/mouseleave')`
  - Smooth fade transition via CSS `opacity` and `.visible` class
- **Result:** Tooltips now properly appear above all UI elements including card headers

### Phase 2U: Training Monotony & Strain (Dec 20, 2025) ✅
- **Carl Foster Model Implementation** - Sports science training load metric
  - Monotony = 1 / CV (coefficient of variation of daily training)
  - Strain = Weekly Load × Monotony
  - Higher monotony = more uniform daily training pattern
  - Higher strain = accumulated training stress (injury risk indicator)
- **New Functions (supabase_shiny.py):**
  - `fetch_daily_zone_time()` (lines 711-773): Fetches per-day zone time from `activity_zone_time`
  - `calculate_weekly_monotony_strain()` (lines 776-870): Calculates weekly metrics
    - Groups by calendar week (Mon-Sun)
    - Fills missing days with zeros (rest days count)
    - Caps monotony at 10.0 (when all days identical)
- **UI Controls:**
  - Zone checkboxes (reuses `zone_time_available_zones` reactive value)
  - Radio buttons: Strain vs Monotonie metric toggle
  - Located in "Resume de periode" tab, under zone longitudinal graph
- **Graph Renderer:** `monotony_strain_graph()` (lines 3989-4103)
  - Purple line for Monotonie, Red line for Strain
  - Shares date range with other period summary graphs
  - Responsive with `autosize=True`
- **Formulas:**
  ```
  CV = std(daily_minutes) / mean(daily_minutes)
  Monotony = min(10.0, 1/CV)
  Load = sum(daily_minutes)
  Strain = Load × Monotony
  ```
- **Edge Cases Handled:**
  - Zero training week: monotony=0, strain=0
  - All days identical: monotony=10.0 (capped)
  - Multiple activities per day: summed
- **Deployed:** Live on production

### Phase 2V: Pre-calculated Monotony & Strain (Dec 22, 2025) ✅
- **Pre-calculation System** - Database-side computation for performance
  - New table `weekly_monotony_strain` with per-zone metrics (6 zones + total)
  - Each zone has: load_min, monotony, strain columns
  - SQL function `calculate_monotony_strain_for_week(athlete_id, week_start)`
  - Backfill function for historical data: `backfill_monotony_strain()`
- **Python Integration (intervals_hybrid_to_supabase.py):**
  - `calculate_monotony_strain_for_week()`: Calls SQL function via RPC
  - `get_week_start()`: Converts activity date to Monday of that week
  - Automatically called after `calculate_zone_time_for_activity()`
- **Dashboard Updates (supabase_shiny.py):**
  - `fetch_weekly_monotony_strain_from_db()`: Fetches pre-calculated data with caching
  - `monotony_strain_graph()`: Uses pre-calculated data first, fallback to Python calculation
  - Aggregates per-zone metrics based on user's zone selection
- **Performance Impact:**
  - Graph load: ~500ms → ~50ms (10x faster)
  - Zone toggle: Recalculates → Instant
  - Import overhead: +~100ms per activity (acceptable)
- **Migration Required:**
  1. Run `create_weekly_monotony_strain.sql` in Supabase
  2. Run `SELECT * FROM backfill_monotony_strain();`

### Phase 2W: Zone Configuration Change Indicator (Dec 23, 2025) ✅
- **Problem Solved** - When viewing a date range that spans multiple zone configs:
  - Zone boundaries changed mid-period (e.g., Z1 = "3:15+" until Dec 12, then "3:05+")
  - Data was calculated correctly (temporal matching) but user had no visual indication
  - Could misinterpret graphs thinking same zone boundaries applied throughout
- **Solution Implemented:**
  - `get_zone_changes_in_range()` function: Queries `athlete_training_zones` for changes within date range
  - `zone_change_banner` UI: Styled info banner showing when/how often zones changed
  - Vertical dashed lines on `zone_time_longitudinal` and `monotony_strain_graph`
  - Lines labeled "Zones modifiees" at each config change date
- **UX Impact:**
  - Users now see clear visual indicator of zone boundary changes
  - French message explains the change dates
  - Graphs show vertical reference lines for context
- **Code Changes (supabase_shiny.py):**
  - Lines 503-561: `get_zone_changes_in_range()` with caching
  - Lines 3923-3966: `zone_change_banner` render function
  - Lines 4200-4214: Vertical lines in zone longitudinal graph
  - Lines 4334-4348: Vertical lines in monotony/strain graph
  - UI placeholder at line 2377

### Phase 2X: Conditional Tooltip Display (Dec 28, 2025) ✅
- **Problem Solved** - Red triangle tooltip indicators appeared on all questionnaire labels, even those without descriptions
- **Solution Implemented:**
  - Modified `scale_with_tooltip()` function (lines 2273-2302)
  - Triangle only renders when `tooltip_text` parameter is non-empty
  - Empty string or no argument = no triangle displayed
- **Current State:**
  - RPE scale: Has full CR-10 description → triangle shows
  - All other fields: Empty placeholders → no triangle (cleaner UI)
- **Code Changes (supabase_shiny.py):**
  - Lines 2285-2293: Conditional rendering of tooltip trigger span
  - Uses list-based label children construction
- **Deployed:** Live on production

### Phase 2Y: Monotony/Strain Overlay on Zone Graph (Dec 29, 2025) ✅
- **Feature** - Replaced separate Monotony/Strain graph with overlay on "Zones d'allure" graph
- **UI Changes:**
  - Added "Monotonie" checkbox → purple dotted line on secondary Y-axis
  - Added "Strain" checkbox → red dash-dot line on tertiary Y-axis
  - Both toggles independent (can show one, both, or neither)
  - Removed separate monotony/strain graph section and zone checkboxes
- **Code Changes (supabase_shiny.py):**
  - Lines ~2376-2384: `show_monotony` and `show_strain` checkboxes
  - Lines ~4164-4205: Overlay logic fetching from `fetch_weekly_monotony_strain_from_db()`
  - Lines ~4263-4289: `yaxis2` (Monotony) and `yaxis3` (Strain) configuration
  - Deleted `monotony_strain_graph()` function and `monotony_zone_checkboxes` renderer
- **Deployed:** Live on production

### Phase 2Z: Personal Records Expansion (Dec 29, 2025) ✅
- **Feature** - Expanded personal records from 7 to 15 distances with millisecond support
- **New Distances:**
  - Track: 400m, 800m, 1000m, 1500m, mile, 2000m, 3000m, 2000m steeple, 3000m steeple, 5000m, 10000m
  - Road: 5km, 10km, semi-marathon, marathon
- **Millisecond Support:**
  - Input format: `HH:MM:SS:ms` (e.g., `3:45:12:50` = 3min 45.12sec)
  - Database: `time_seconds` changed from INTEGER to DECIMAL(10,3)
  - Display: Shows centiseconds when fractional (e.g., `3:45:12`)
- **Code Changes (supabase_shiny.py):**
  - Lines 7488-7504: DISTANCES array expanded to 15 entries
  - Lines 7506-7528: `format_time_from_seconds()` updated for milliseconds
  - Lines 7530-7570: `parse_time_to_seconds()` updated for 4-part format
  - Lines 7572-7590: `calculate_pace()` distance_map expanded
- **Database Migration:**
  - `migrations/update_personal_records_schema.sql` created
  - `complete_database_schema.sql` updated
  - Migration executed in Supabase SQL Editor
- **Deployed:** Live on production

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

# Historical wellness import (date range)
python intervals_hybrid_to_supabase.py --wellness-oldest 2023-01-01 --wellness-newest 2025-12-01

# Bulk import with both activities + historical wellness
python intervals_hybrid_to_supabase.py --oldest 2023-01-01 --newest 2025-12-01 --wellness-oldest 2023-01-01 --wellness-newest 2025-12-01

# Run dashboard locally
shiny run supabase_shiny.py
```

### 🚀 Deployment to ShinyApps.io

**⚠️ CRITICAL: Use this exact command for deployments**

```bash
SSL_CERT_FILE=/opt/anaconda3/lib/python3.12/site-packages/certifi/cacert.pem rsconnect deploy shiny . \
  --entrypoint app:app \
  --name insquebec-sportsciences \
  --app-id 16149191 \
  --exclude ".cache" \
  --exclude "*.parquet" \
  --exclude "rsconnect-python" \
  --exclude "scripts" \
  --exclude "tests" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  --exclude ".git" \
  --exclude ".env.dashboard*" \
  --exclude ".env.ingestion*" \
  --exclude ".env.example" \
  --exclude ".env.new*" \
  --exclude ".env.OLD" \
  --exclude "athletes*" \
  --exclude "migrations" \
  --exclude "supabase" \
  --exclude ".claude" \
  --exclude "*.md" \
  --exclude "*.sql" \
  --exclude "*.sh" \
  --exclude ".venv" \
  --exclude "bulk_import.py" \
  --exclude "create_users.py" \
  --exclude "run_migrations_direct.py" \
  --exclude "intervals_*" \
  --exclude ".mcp.json" \
  --exclude ".DS_Store" \
  --exclude "manifest.json"
```

**Deployment Checklist:**
- [ ] Do NOT create `.python-version` file (ShinyApps.io only supports Python 3.9.x)
- [ ] Use `app.py` as entrypoint (wrapper with error handling)
- [ ] `requirements.txt` should have NO version constraints (just package names)
- [ ] Use `--app-id 16149191` to update existing app (NOT create new one)
- [ ] Exclude all unnecessary files (see command above)

**Files that MUST be deployed:**
- `app.py` (wrapper/entrypoint)
- `supabase_shiny.py` (main dashboard)
- `auth_utils.py` (authentication)
- `moving_time.py` (calculations)
- `requirements.txt` (dependencies)
- `.env` (production credentials)
- `shiny_env.env` (backup credentials)
- `.gitignore`

**Troubleshooting "exit status 1":**
1. Check if `.python-version` exists → DELETE IT
2. Check `requirements.txt` for version constraints → REMOVE THEM
3. Check if too many files in bundle → ADD MORE EXCLUDES
4. Test with minimal "Hello World" app first

### ShinyApps.io Registry

| App Name | App ID | Status |
|----------|--------|--------|
| saintlaurentselect_dashboard | 16149191 | ✅ PRODUCTION |
| ins_dashboard | 16146104 | ⏸️ Not in use |

### Supabase Database
- **Project:** vqcqqfddgnvhcrxcaxjf
- **Region:** Default
- **Tables:** 14 (athlete, users, activity_metadata, activity, activity_intervals, wellness, daily_workout_surveys, weekly_wellness_surveys, personal_records, athlete_training_zones, activity_zone_time, weekly_zone_time, lactate_tests, weekly_monotony_strain)

### GitHub Repository
- **URL:** https://github.com/MarcPaquet/INS_Dashboard
- **Files:** 12 (+ 9 migrations)
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

## 📅 KNOWN ISSUES & NEXT PRIORITIES

### ✅ Recently Fixed

| Feature | Issue | Status |
|---------|-------|--------|
| **Daily Questionnaire** | Cannot select training from dropdown | ✅ Fixed (Dec 23, 2025) |

### ✅ Recently Fixed (Dec 2025)

| Issue | Phase | Solution |
|-------|-------|----------|
| Zone Time Performance | 2O, 2S | Materialized views + incremental calculation |
| Monotony/Strain Performance | 2V | Pre-calculated in database (111 weeks backfilled) |
| Tooltips Behind Headers | 2T | JavaScript-powered positioning |
| Zone Graph Display | 2N | Plotly responsiveness + timestamp conversion |
| Coach Selector | 2Q | Added reactive event decorator |

### 🟡 Next Priorities

1. **Fix Daily Questionnaire** - Training selector dropdown issue
2. **AWS Infrastructure** - Lambda, EventBridge, EC2 for automation
3. **Bulk Import** - Execute historical import on AWS EC2

---

**END OF DOCUMENT**

*Last Updated: January 3, 2026*
