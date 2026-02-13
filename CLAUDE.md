# 📊 INS DASHBOARD - Master Context & Backlog

**Project:** Intervals.icu → Supabase Data Ingestion System
**Team:** Saint-Laurent Sélect Running Club
**Last Updated:** February 12, 2026 (METRIC ROUNDING)
**Status:** ✅ **FULLY AUTOMATED** - Dashboard + Daily Lambda Cron Running

---

## 📖 HOW TO USE THIS DOCUMENT

| Audience | What to Read |
|----------|--------------|
| **Marc (Owner)** | Update after each session. Keep CONTEXT current, move completed tasks to ARCHIVE. |
| **Claude Code** | Read CONTEXT first, check BACKLOG for priorities, reference ARCHIVE for history. |

### When to Use ARCHIVE_DETAILED.md

| Situation | Use CLAUDE.md | Use ARCHIVE_DETAILED.md |
|-----------|---------------|-------------------------|
| **Quick context on project status** | ✅ | |
| **Current priorities and backlog** | ✅ | |
| **Summary of what was done** | ✅ | |
| **Debugging a similar issue** | | ✅ (has error messages, solutions) |
| **Updating Lambda code** | | ✅ (has build commands, config) |
| **Understanding implementation details** | | ✅ (has code snippets, architecture) |
| **Replicating a previous setup** | | ✅ (has step-by-step details) |
| **Sports science metrics reference** | | ✅ (has full metric definitions) |
| **Database schema deep-dive** | | ✅ (has detailed table structures) |

**Rule of thumb:** CLAUDE.md tells you *what* was done; ARCHIVE_DETAILED.md tells you *how* it was done.

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
| Jade Essabar | `i453683` | athlete |
| Marc-Andre Trudeau Perron | `i453625` | athlete |
| Marine Garnier | `i197667` | athlete |
| Myriam Poirier | `i453790` | athlete |
| Nazim Berrichi | `i453396` | athlete |
| Robin Lefebvre | `i453411` | athlete |
| Yassine Aber | `i453944` | athlete |
| Evans Stephen | `i454589` | athlete |
| Cedrik Flipo | `i486574` | athlete |
| Renaud Bordeleau | `i482119` | athlete |

**Login-Only Athletes (3) - No data import:**
| Member | Intervals.icu ID | Note |
|--------|------------------|------|
| Genevieve Paquin | - | No Intervals.icu |
| Simone Plourde | - | No Intervals.icu |
| Elie Nayrand | `i453407` | **API KEY ERROR** |

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
| `lambda/lambda_function.py` | AWS Lambda handler |
| `lambda/aws_secrets_loader.py` | Secrets Manager integration |
| `lambda/build_lambda.sh` | Lambda deployment build script |

---

## 📍 CURRENT STATE

### ✅ PRODUCTION LIVE + AUTOMATED

| Component | Status | Details |
|-----------|--------|---------|
| **Dashboard** | ✅ Working | All graphs render, login works |
| **Database** | ✅ Working | All queries functioning |
| **Authentication** | ✅ Working | Login modal, session management |
| **Ingestion Script** | ✅ Validated | Tested Nov 29, 2025 - all checks passed |
| **Mobile Design** | ✅ Responsive | All breakpoints working |
| **AWS Lambda Cron** | ✅ Running | Daily 6 AM ET, 18/18 athletes success |
| **Bulk Import** | ✅ Complete | EC2 terminated, data imported |

### 📊 Data Statistics (as of Jan 18, 2026)

| Metric | Count |
|--------|-------|
| Activities | 970+ (bulk import in progress) |
| GPS Records | 2.5M+ points |
| Intervals | 10,398+ |
| Weather Coverage | 100% (outdoor activities) |
| HR Coverage | 100% (when monitor used) |

### 🔧 Recent Session (Jan 18, 2026) - CRASH RESOLVED

**✅ SHINYWIDGETS CRASH FIX**

The crash that occurred after login was caused by `shinywidgets` library incompatibility with ShinyApps.io Python environment. Fixed by converting all Plotly graphs from `@render_plotly` + `output_widget()` to `@render.ui` + Plotly HTML rendering. See Phase 3C in Archive for details.

---

## CRASH RESOLUTION SUMMARY (Jan 18, 2026)

### Root Cause
The `shinywidgets` library (`output_widget`, `@render_plotly`) is incompatible with ShinyApps.io's Python environment. It works locally but crashes on production ~2 seconds after login when any Plotly graph tries to render.

### Solution (Phase 3C)
Converted all Plotly graphs from shinywidgets rendering to HTML rendering:
- Commented out `from shinywidgets import output_widget, render_plotly`
- Created `plotly_to_html()` helper function using `fig.to_html()`
- Changed all `@render_plotly` decorators to `@output` + `@render.ui`
- Changed all `output_widget("name")` to `ui.output_ui("name")`
- All 7 graph functions now return `plotly_to_html(fig)` instead of `fig`

### What Was NOT the Cause
- Database RLS policies
- SQL function search_path changes
- Security migrations
- Race feature code (Phase 3B)

All previous troubleshooting around database issues was a red herring - the root cause was the shinywidgets library itself.

---

## Phase 3B Features (NOW DEPLOYED)

**Feature 1: Lactate Test vs Race Toggle**
- ✅ Created database migration: `migrations/add_lactate_test_type.sql`
- ✅ Added `test_type` column ('lactate' or 'race') with check constraint
- ✅ Added `race_time_seconds` column (DECIMAL(10,2)) for race times
- ✅ Made `lactate_mmol` nullable (only required for lactate tests)
- ✅ Form now shows radio buttons to choose test type
- ✅ Conditional fields: lactate input or race time based on selection
- ✅ Results table shows type badge (gold for race, blue for lactate)
- ✅ Created partial index for efficient race queries

**Feature 2: Coach Questionnaire**
- ✅ Investigated why coach Kerrian couldn't submit questionnaires
- ✅ Confirmed this is BY DESIGN for data authenticity
- ✅ Coaches see "Les questionnaires sont réservés aux athlètes"
- ✅ No code changes needed - inform Kerrian this is expected behavior

**Feature 3: Race Visualization on "Résumé de période"**
- ✅ Added `get_athlete_races()` helper function with caching
- ✅ Added `get_race_by_id()` helper function
- ✅ Race selector dropdown showing all races ever recorded
- ✅ Gold vertical line markers on CTL/ATL and zone graphs
- ✅ "Simuler une date alternative" checkbox with date picker
- ✅ Purple dashed markers for simulated race position

**Code Location:** Commits 699c370, b0a3263, 299c1cc on main branch

**Files Modified:**
| File | Changes |
|------|---------|
| `supabase_shiny.py` | +620 lines: form UI, conditional fields, race selector, graph markers |
| `complete_database_schema.sql` | Updated lactate_tests table with new columns |
| `migrations/add_lactate_test_type.sql` | NEW - Database migration |

---

### Current Session (Feb 12, 2026) - METRIC ROUNDING

**Session Summary:**
1. Cataloged all numeric metrics displayed in the dashboard
2. Rounded CTL/ATL/TSB to 1 decimal in hover tooltips
3. Rounded Vertical Oscillation to 1 decimal in XY graph and comparison hover
4. Rounded LSS to 2 decimals in XY graph and comparison hover
5. Confirmed rounding should be frontend-only (not ingestion)

**Design Decision: Frontend Rounding, Not Ingestion**

- **CTL/ATL/TSB** are calculated in the dashboard via EWM — they don't exist in the database, so ingestion rounding is not applicable
- **Vertical Oscillation & LSS** are raw sensor data stored in the `activity` table. Keeping full precision in the DB preserves accuracy for future analytics/correlations. Rounding is purely a display concern

**Changes (`supabase_shiny.py`):**

| Location | Metric | Before | After |
|----------|--------|--------|-------|
| `run_duration_trend()` ~line 3910 | CTL hover | Raw float (`42.38291746382`) | `.1f` (`42.4`) |
| `run_duration_trend()` ~line 3921 | ATL hover | Raw float | `.1f` |
| `run_duration_trend()` ~line 3929 | TSB hover | Raw float | `.1f` |
| `plot_xy()` ~line 5277 | Vertical Oscillation hover | Raw float (`82.199997`) | `.1f` (`82.2`) |
| `plot_xy()` ~line 5277 | LSS hover | Raw float (`9.83456`) | `.2f` (`9.83`) |
| `comparison_plot()` ~line 6653 | All comparison hovers | `.1f` for all non-pace | Variable-specific via `_fmt_hover_vals()` |

**Implementation Details:**
- Added `hovertemplate` with `%{y:.1f}` to CTL/ATL/TSB `go.Scatter()` traces
- Created `_hover_format` dict in `plot_xy()` mapping variable names to format strings
- Created `_fmt_hover_vals()` helper in `comparison_plot()` for consistent formatting
- Both primary and secondary Y-axis traces are covered in XY graph and comparison graph

**Deployed:** Dashboard live on production (commit `90dd2cf`)
- GitHub: Pushed to `main` (21 files, +4837/-636 lines — includes all Phases 3E-3I)
- ShinyApps.io: Deployed successfully to https://insquebec-sportsciences.shinyapps.io/saintlaurentselect_dashboard/
- Lambda source files (`lambda/`) now tracked in git (excluding `package/` and `.zip`)

---

### Previous Session (Feb 8, 2026) - MULTI-FEATURE SESSION (2 parts)

**Session Summary (Part 1):**
1. Fixed zone error ("Invalid value '0' for dtype 'str'")
2. Per-athlete sync button (athletes sync only themselves, coaches sync all)
3. Added maximal speed test event type to Events card
4. Body picker in daily questionnaire (front+back SVG, multi-select, capacité d'exécution 0-3)
5. LSS troubleshooting (Intervals.icu API strips Stryd developer fields)
6. Prevention staff login added to to-do list

**Session Summary (Part 2 - Same Day):**
7. Fixed body picker click handlers (SVG parts were not clickable)
8. Made front/back body parts independent (no cross-selection)
9. Removed pain intensity slider from questionnaire (redundant with per-part severity)
10. Added dots toggle on "Allure vs Fréquence cardiaque" graph
11. Removed injury type from Events card (pain tracking is in questionnaire only)
12. Added milliseconds support to speed test time input label

---

**Feature 1: Zone Error Fix**

**Problem:** "Invalid value '0' for dtype 'str'" in "Résumé de période" tab zone graph.

**Root Cause:** `pandas DataFrame.reindex(fill_value=0)` at line ~4500 attempted to fill ALL columns including `athlete_id` (string) with integer 0.

**Fix:** Drop non-numeric columns before reindexing:
```python
non_numeric_cols = weekly_df.select_dtypes(exclude='number').columns.difference(["week_start"])
weekly_df = weekly_df.drop(columns=non_numeric_cols, errors="ignore")
weekly_df = weekly_df.set_index("week_start").reindex(full_weeks, fill_value=0).reset_index()
weekly_df = weekly_df.rename(columns={"index": "week_start"})
```

**File:** `supabase_shiny.py` line ~4500

---

**Feature 2: Per-Athlete Sync Button**

**Goal:** Athletes sync only their own data. Coaches sync everyone.

**Dashboard Changes (`supabase_shiny.py`):**
- In `handle_refresh_data()`: Check `user_role.get()` and `user_name.get()`
- If athlete: sends `json={"athlete_name": "Name"}` to Lambda
- If coach: sends `json={}` (empty = sync all, backward compatible)
- Status message: "vos données" for athletes vs "tous les athlètes" for coaches

**Lambda Changes (`lambda/lambda_function.py`):**
- Parses optional `athlete_name` from HTTP request body
- Filters athlete list if present (exact match, then case-insensitive fallback)
- Returns 404 if athlete not found
- Empty body = process all athletes (backward compatible with EventBridge cron)

**Tested:**
- Single athlete: 5.5s, 188 MB → 1/1 success
- All athletes: 83s, 211 MB → 18/18 success

**Lambda needs redeployment:** `cd lambda/ && ./build_lambda.sh` → Upload ZIP to AWS Console

---

**Feature 3: Maximal Speed Test Event Type**

**Goal:** New "Test de vitesse max" event type (e.g., 40m sprint) with auto-calculated m/s.

**Database Migration (`migrations/add_speed_test_event.sql`):**
- Added `speed_ms` DECIMAL(6,3) column to `lactate_tests`
- Updated `test_type` CHECK: `IN ('lactate', 'race', 'injury', 'speed_test')`
- Updated `chk_race_time_only_for_races`: allows `race_time_seconds` for speed_test
- Added `chk_speed_only_for_speed_tests`: `speed_ms` only for speed_test
- Updated `chk_distance_required`: distance required for speed_test too
- Created partial index `idx_lactate_tests_speed`

**Dashboard Changes (`supabase_shiny.py`):**
- Type radio buttons: Added `"speed_test": "Test de vitesse max"`
- Conditional fields for speed_test: Distance (10-1000m) + Time (MM:SS or raw seconds)
- `speed_test_calculated()` render function: Auto-calculates and displays "X.XX m/s"
- Save handler: Validates, parses time, calculates `speed_ms = distance / time_seconds`
- Results table: Green "Vitesse" badge, displays speed in m/s

**Reuses existing:** `parse_time_to_seconds()`, `format_time_from_seconds()` functions

---

**Feature 4: Body Picker in Daily Questionnaire**

**Goal:** Replace text input for pain location with front+back SVG body pickers (multi-select) and add 0-3 training execution capacity scale.

**Database Migration (`migrations/create_workout_pain_entries.sql`):**
- New table `workout_pain_entries`:
  - `id` UUID PK
  - `survey_id` UUID FK → `daily_workout_surveys(id)` ON DELETE CASCADE
  - `body_part` TEXT (e.g., 'left_knee')
  - `body_view` TEXT CHECK ('front' or 'back')
  - `severity` INTEGER (1-3)
  - RLS enabled with allow-all policy
- New column on `daily_workout_surveys`:
  - `capacite_execution` INTEGER (0-3, nullable)

**Dashboard Changes (`supabase_shiny.py`):**

*UI (lines ~2827-2850 replaced):*
- Dual SVG body picker (front + back views side by side)
- Front view: head, neck, shoulders, arms, chest, abdomen, hips, quads, knees, shins, ankles, feet
- Back view: head, neck, shoulders, arms, upper_back, lower_back, glutes, hamstrings, knees, calves, ankles, feet
- Multi-select JavaScript: click toggles selection, severity per part (1-3 color coding)
- Event delegation on `document` for reliable click handling (not direct listeners)
- Composite keys `view:partId` (e.g., `front:left_knee`) for independent front/back selection
- Selected parts list below SVGs with per-part severity dropdowns and remove buttons
- `Shiny.setInputValue('daily_pain_selections', JSON.stringify(selections))` for JS→Python sync
- Removed `douleur_intensite` slider (redundant with per-part severity 1-3)
- Added `capacite_execution` radio buttons:
  - 0: Entraînement non complété
  - 1: Fortement limité
  - 2: Partiellement limité
  - 3: Pleine capacité (aucune limitation)
- Kept existing `douleur_impact` Yes/No radio

*Submission handler (`handle_daily_survey_submit()`):*
- Changed `"Prefer": "return=minimal"` to `"Prefer": "return=representation"` to get survey UUID
- Parses `input.daily_pain_selections()` JSON string
- Inserts one row per selected body part into `workout_pain_entries` (batch insert)
- Stores `capacite_execution` in main survey row
- Sets `douleur_type_zone` to `None` (deprecated, replaced by structured data)

---

**Feature 5: LSS Troubleshooting (Investigation)**

**Findings:**
- Database: 2.4M rows LSS > 0, 515K rows LSS = 0, 3.2M rows LSS NULL
- Only 2 athletes have any LSS data (Matthew Beaudet, Kevin A. Robertson)
- Downloaded FIT files from Intervals.icu API → `developer_data_id` messages exist but NO `field_description` messages
- **Conclusion:** Intervals.icu API strips Stryd developer data from FIT file exports
- LSS data only comes from watch sync directly (not via Intervals.icu API)
- The zeros are legitimate data points where no valid stride was detected
- **No code fix possible** - this is an API limitation

**File investigated:** `intervals_hybrid_to_supabase.py` line 1162: `elif field.name == 'Leg Spring Stiffness'`

---

**Feature 6: Prevention Staff Login (To-Do)**

Added to to-do list for future implementation:
- New role for physiotherapy/prevention staff
- Restricted dashboard access (injury data only)
- Notion MCP not available during session - noted for manual addition

---

**Feature 7: Body Picker Click Fix**

**Problem:** SVG body parts in the daily questionnaire were visible but not clickable. No selections appeared.

**Root Cause:** The JavaScript click handlers were inside a `<script>` tag within `ui.HTML()`. When Shiny injects HTML via `innerHTML`, browsers do **not execute** `<script>` tags (standard browser security behavior). The SVG elements rendered correctly, but no click handlers were attached.

**Fix:**
1. Moved the JavaScript out of `ui.HTML('''...''')` into a separate `ui.tags.script("""...""")` element (which Shiny properly executes)
2. Replaced direct `querySelectorAll().forEach(addEventListener)` with **event delegation** on `document` — works regardless of when SVG elements appear in the DOM
3. Added `if (window._dailyBPInitialized) return;` guard to prevent double initialization

**Code Location:** `supabase_shiny.py` lines ~2902-2989

---

**Feature 8: Independent Front/Back Body Parts**

**Problem:** Clicking a body part (e.g., "left knee") on the front view also highlighted the same part on the back view, because both used the same `data-part` key.

**Fix:** Changed JavaScript selection keys from `partId` (e.g., `left_knee`) to composite keys `view:partId` (e.g., `front:left_knee`, `back:left_knee`). Each view's selections are now fully independent.

**Changes:**
- **JS click handler:** Creates composite key `view + ':' + partId`
- **JS render function:** Matches SVG elements by determining their parent `[data-view]` and building composite key
- **JS selected list:** Parses composite key to extract `partId` for label lookup
- **Python submission handler:** Parses composite key (`front:left_knee` → `body_part="left_knee"`, `body_view="front"`) — backward compatible with old format

**Code Location:** `supabase_shiny.py` lines ~2902-2989 (JS), lines ~7898-7912 (Python handler)

---

**Feature 9: Removed Pain Intensity Slider**

Removed the "Intensité de la douleur" 0-10 slider from the daily questionnaire pain section. It was redundant since each body part already has its own severity (1-3: Légère, Modérée, Sévère).

**Changes:**
- Removed `scale_with_tooltip("Intensite de la douleur", ui.input_slider(...))` from UI
- Set `douleur_intensite` to `None` in submission handler (column still exists in DB for backward compatibility)

---

**Feature 10: Pace/HR Dots Toggle**

**Goal:** Reduce visual noise on "Allure vs Fréquence cardiaque — par mois" graph when viewing old data with many data points.

**Changes:**
- Added `ui.input_checkbox("show_pace_hr_dots", "Afficher les points", value=True)` inside the card
- Scatter point traces only added when checkbox is checked (default: on)
- Trend lines always visible
- When dots hidden, trend line legend entries become visible (so user can identify months)

**Code Location:** `supabase_shiny.py` line ~2622 (UI), lines ~4132-4167 (graph logic)

---

**Feature 11: Removed Injury Type from Events Card**

Removed "Douleur/Blessure" option from the Events card ("Entrée de données manuelle" tab). Pain/injury tracking is now exclusively in the daily questionnaire body picker.

**What was removed:**
- "injury" choice from `lactate_test_type` radio buttons (now 3 types: Lactate, Course, Vitesse max)
- Entire `elif test_type == "injury"` block in `lactate_conditional_fields()` (~180 lines: SVG body picker, location dropdown, severity selector, status selector)
- Injury validation and record building in save handler
- Injury-specific success title

**Kept:** Existing injury records still display correctly in the results table (backward compatible)

---

**Feature 12: Speed Test Milliseconds Label**

Updated the speed test time input label from "Temps (MM:SS ou SS)" to "Temps (MM:SS:MS ou SS)" and placeholder from "ex: 0:05 ou 5.2" to "ex: 0:05:23 ou 5.2". The `parse_time_to_seconds()` function already supported `MM:SS:ms` format — only the label needed updating.

---

**Files Modified (Part 2):**

| File | Changes |
|------|---------|
| `supabase_shiny.py` | Body picker JS fix (event delegation), composite keys, removed pain slider, dots toggle, removed injury from Events card, speed test label |

**Deployed:** Dashboard live on production (2 deployments in Part 2).

---

### Previous Session (Feb 2, 2026) - EVENTS CARD + INJURY TRACKING

**Session Summary:**
1. Restructured "Entrée de données manuelle" tab with new card order
2. Added injury/pain tracking with interactive SVG body picker (Events card)
3. Extended lactate_tests table to support injuries as events
4. Made all cards available to all users (removed role restrictions)

**Key Changes:**
- Card order: Events (TOP) → Training Zones → Personal Records (BOTTOM)
- Renamed "Tests et courses" → "Événements"
- SVG body picker for injury location (22 zones, 3 severity levels)
- Extended `test_type` CHECK to include 'injury'
- Added columns: `injury_location`, `injury_severity`, `injury_status`
- **Migration:** `migrations/extend_lactate_tests_for_injuries.sql`
- **Deployed:** Live on production

---

### Previous Session (Jan 30, 2026) - SYNC BUTTON + SECURITY FIXES

**Session Summary:**
1. Fixed all Supabase linter security errors and warnings
2. Added manual "Sync" button to trigger data refresh from dashboard
3. Implemented rate limiting (3 syncs per day)
4. UI styling fixes (button borders)

---

**Feature 1: Supabase Security Fixes**

Fixed all linter errors and warnings:

| Category | Count | Fix |
|----------|-------|-----|
| RLS disabled on tables | 3 | Enabled RLS + policies |
| Function search_path mutable | 10 | Set `search_path = public` |
| Materialized views in API | 2 | Revoked anon/authenticated access |
| RLS policies always true | 3 | Service-role specific policies |

**Migrations Created:**
- `migrations/enable_rls_missing_tables.sql`
- `migrations/fix_security_warnings.sql`

**Tables with RLS enabled:**
- `lactate_tests`
- `weekly_monotony_strain`
- `activity_zone_time`

---

**Feature 2: Manual Sync Button**

Added a "Sync" button to the dashboard header that triggers the Lambda function for on-demand data refresh.

**Architecture:**
```
Dashboard (Sync button)
    ↓ HTTP POST with Bearer token
Lambda Function URL
    ↓ Validates token
Lambda executes ingestion (3-day window)
    ↓ Returns JSON result
Dashboard shows status
```

**AWS Setup:**
1. Created Lambda Function URL on `ins-dashboard-daily-ingestion`
2. Added `REFRESH_TOKEN` environment variable to Lambda
3. CORS enabled for cross-origin requests

**Dashboard Changes:**
- Sync button next to user name (blue, no border)
- Status display showing progress/result
- Async handler to not block UI during 10-min sync

**Files Modified:**
| File | Changes |
|------|---------|
| `lambda/lambda_function.py` | Added Function URL support with Bearer auth |
| `supabase_shiny.py` | Added Sync button, status display, async handler |
| `.env` | Added `LAMBDA_FUNCTION_URL` and `LAMBDA_REFRESH_TOKEN` |
| `shiny_env.env` | Added same Lambda config for backup |

**Environment Variables Added:**
```
LAMBDA_FUNCTION_URL=https://yr3tu22orzlav5jwoxly3c5rmu0fnxns.lambda-url.ca-central-1.on.aws/
LAMBDA_REFRESH_TOKEN=<secret>
```

---

**Feature 3: Rate Limiting (3 per day)**

Implemented rate limiting to prevent abuse of the Sync button.

**Implementation:**
- New `sync_log` table tracks each sync attempt
- `check_sync_allowed()` SQL function checks daily count
- Dashboard checks limit before triggering Lambda
- Shows "Limite atteinte (3/3 aujourd'hui)" when limit reached

**Migration:** `migrations/create_sync_log.sql`

**Database Table:**
```sql
CREATE TABLE sync_log (
    id SERIAL PRIMARY KEY,
    triggered_at TIMESTAMPTZ DEFAULT NOW(),
    triggered_by TEXT,
    status TEXT DEFAULT 'started',
    message TEXT
);
```

---

**Feature 4: UI Styling Fixes**

- Removed red border from Logout button
- Removed blue border from Sync button
- Consistent button styling (no borders, subtle hover effects)

---

### Previous Session (Jan 29, 2026) - FAST LOGIN + QUESTIONNAIRES VALIDATED

**Session Summary:**
1. Validated questionnaires are working correctly (tested with Kevin Robertson)
2. Deleted test questionnaire data from database
3. Updated lactate test form - Distance field now beside Lactate field
4. Fixed slow login (7-10 seconds → <1 second)

---

**Feature 1: Questionnaire Validation**
- Tested daily workout survey and weekly wellness survey
- Both working correctly and saving to database
- Deleted test data for Kevin Robertson (week Jan 26, activity May 2)

**Feature 2: Lactate Form UI Update**
- Moved Distance field to appear beside Lactate field for lactate tests
- For races: Distance | Race Time side by side
- For lactate tests: Lactate | Distance side by side

**Feature 3: Fast Login Performance Fix**

**Problem:** Login took 7-10 seconds because it looped through ALL 24 users running bcrypt verification on each (~186ms per user).

**Solution:** Added SHA256 password prefix for O(1) database lookup.

| Before | After |
|--------|-------|
| Fetch all 24 users | Query by prefix (instant) |
| bcrypt verify each (186ms × 24) | bcrypt verify 1 user (186ms) |
| **Total: 7-10 seconds** | **Total: <1 second** |

**Implementation:**
1. Added `password_prefix` column to `users` table (first 16 chars of SHA256 hash)
2. Created index on `password_prefix` for fast lookup
3. Updated all 24 users with their password prefixes
4. Login now: generate prefix → query by prefix → verify single match

**Files Modified:**
| File | Changes |
|------|---------|
| `auth_utils.py` | Added `generate_password_prefix()` function |
| `supabase_shiny.py` | Updated login handler to use prefix lookup |
| `migrations/add_password_prefix.sql` | NEW - Database migration |

**Database Changes:**
```sql
ALTER TABLE users ADD COLUMN password_prefix TEXT;
CREATE INDEX idx_users_password_prefix ON users(password_prefix);
```

**Security Note:** The SHA256 prefix is NOT secure for password storage alone - it's only used for fast lookup. The actual password verification still uses bcrypt.

---

### Previous Session (Jan 20, 2026) - AWS LAMBDA CRON COMPLETE

**AWS Lambda Daily Automation - LIVE AND RUNNING**

Successfully deployed and tested AWS Lambda function for automated daily ingestion.

**What Was Done:**
- ✅ Terminated EC2 bulk import instance (completed Jan 18)
- ✅ Created IAM Role `INS-Dashboard-Lambda-Role` with Secrets Manager access
- ✅ Created Lambda function `ins-dashboard-daily-ingestion` (Python 3.11)
- ✅ Built deployment package with Linux-compatible pandas/numpy binaries
- ✅ Configured Lambda: 15 min timeout, 512 MB memory
- ✅ Created EventBridge schedule: daily at 6 AM Eastern (cron `0 6 * * ? *`)
- ✅ Fixed multiple issues during testing (see Phase 3D in Archive)
- ✅ Final test: **18/18 athletes successful**

**Lambda Configuration:**

| Setting | Value |
|---------|-------|
| Function name | `ins-dashboard-daily-ingestion` |
| Runtime | Python 3.11 |
| Memory | 512 MB |
| Timeout | 15 minutes |
| Per-athlete timeout | 5 minutes (300s) |
| Date range | Last 3 days (rolling window) |
| Schedule | Daily 6 AM Eastern |

**Files Created in `lambda/` Directory:**
- `lambda_function.py` - Main Lambda handler
- `aws_secrets_loader.py` - Loads credentials from Secrets Manager
- `build_lambda.sh` - Build script for deployment package

**Key Features:**
- **3-day rolling window:** Always imports last 3 days for overlap safety
- **Duplicate prevention:** Script checks existing activity IDs before import
- **No missed workouts:** Even if Lambda fails one day, next run catches up
- **Weather included:** Daily cron fetches weather (unlike bulk import)

**AWS Resources (Final):**

| Resource | Name | Region | Status |
|----------|------|--------|--------|
| Secret | `ins-dashboard/supabase` | ca-central-1 | ✅ Active |
| Secret | `ins-dashboard/athletes` | ca-central-1 | ✅ Active |
| IAM Role | `INS-Dashboard-Lambda-Role` | Global | ✅ Active |
| Lambda | `ins-dashboard-daily-ingestion` | ca-central-1 | ✅ Running |
| EventBridge | Daily 6 AM ET schedule | ca-central-1 | ✅ Active |
| EC2 | `INS-Bulk-Import` | ca-central-1 | ❌ Terminated |

---

### Previous Session (Jan 18, 2026)

**AWS EC2 Bulk Import - COMPLETED**

Successfully ran bulk import for all 18 athletes on EC2, then terminated instance.

**Bulk Import Results:**
- Date range: 2025-01-01 to 2026-01-18
- Athletes: 18 processed
- Weather: Skipped (--skip-weather)
- Status: ✅ Complete

**EC2 Instance:** Terminated after import to avoid ongoing charges.

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

**Database Objects Verified (18 total):**
| Type | Objects |
|------|---------|
| Tables (16) | athlete, users, activity_metadata, activity, activity_intervals, wellness, personal_records, personal_records_history, athlete_training_zones, daily_workout_surveys, weekly_wellness_surveys, lactate_tests, activity_zone_time, weekly_monotony_strain, sync_log, workout_pain_entries |
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
| Set-up AWS pour ingestion | ✅ Terminé | Moyenne | Critique |
| Set-up cron dans AWS | ✅ Terminé | Moyenne | Critique |
| Ajouter tableau de suivi des RPE | Pas commencé | Faible | Fonctionnalité |
| Ajouter tableau suivi wellness | Pas commencé | Faible | Fonctionnalité |
| Ajout de marqueur pour race | ✅ Terminé | Faible | Fonctionnalité |

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

### ✅ AWS Automation - COMPLETE

**Goal:** Automated daily ingestion + one-time bulk historical import
**Status:** ✅ FULLY OPERATIONAL (Jan 20, 2026)
**Region:** `ca-central-1` (Canada Central)

| Task | Service | Status |
|------|---------|--------|
| Set up billing alert ($10) | AWS Console | ✅ Done |
| Store credentials | Secrets Manager | ✅ Done (2 secrets) |
| Bulk import historical data | EC2 | ✅ Complete (terminated) |
| Create IAM role for Lambda | IAM | ✅ Done (`INS-Dashboard-Lambda-Role`) |
| Deploy Lambda function | Lambda | ✅ Done (`ins-dashboard-daily-ingestion`) |
| Configure daily cron (6 AM ET) | EventBridge | ✅ Done |
| Test end-to-end | Lambda Test | ✅ 18/18 athletes success |

**AWS Services & Actual Costs:**

| Service | Purpose | Cost |
|---------|---------|------|
| Secrets Manager | Store credentials (2 secrets) | ~$0.80/month |
| Lambda | Daily ingestion (~10 min/day) | ~$2-5/month |
| EventBridge | Cron trigger | Free |
| CloudWatch | Logs & monitoring | ~$1-2/month |

**Total: ~$4-8/month ongoing**

### 🟡 Next Priorities

| Priority | Task | Status |
|----------|------|--------|
| 1 | Monitor Lambda for 7 days | ⏳ In progress |
| 2 | Run remaining migrations if needed | ⏳ Pending |
| 3 | Git commit Lambda files | ⏳ Pending |

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

**Total: 16 Tables + 2 Materialized Views**

### Core Tables (6)

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `athlete` | Profiles | athlete_id, name, intervals_icu_id |
| `users` | Authentication | id, name, password_hash, password_prefix, role, athlete_id |
| `activity_metadata` | Activity summaries | activity_id, date, distance_m, duration_sec, avg_hr, weather_* |
| `activity` | GPS timeseries | activity_id, lat, lng, heartrate, cadence, watts |
| `activity_intervals` | Workout segments | activity_id, type, distance, moving_time, average_heartrate |
| `wellness` | Daily wellness | athlete_id, date, hrv, sleep_quality, soreness |

### Survey Tables (3)

| Table | Purpose |
|-------|---------|
| `daily_workout_surveys` | Post-workout RPE, satisfaction, goals, capacite_execution (0-3) |
| `weekly_wellness_surveys` | BRUMS, REST-Q, OSLO metrics |
| `workout_pain_entries` | Structured pain data from body picker (one row per body part per survey) |

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
| `lactate_tests` | Events: lactate tests, races, injuries, and speed tests |

### Materialized Views (2)

| View | Purpose |
|------|---------|
| `activity_pace_zones` | Pace zone distribution per activity |
| `weekly_zone_time` | Zone time aggregated by week |

### Operational Tables (1)

| Table | Purpose |
|-------|---------|
| `sync_log` | Rate limiting for manual sync (3/day limit) |

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
  "SUPABASE_URL": "<STORED IN AWS SECRETS MANAGER>",
  "SUPABASE_SERVICE_ROLE_KEY": "<STORED IN AWS SECRETS MANAGER>"
}
```

#### Secret 2: `ins-dashboard/athletes` (JSON)
```
18 athletes with Intervals.icu API keys — stored in AWS Secrets Manager.
Local copy: athletes.json.local (gitignored)
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
  --secret-string '{"SUPABASE_URL":"<YOUR_URL>","SUPABASE_SERVICE_ROLE_KEY":"<YOUR_KEY>"}'

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

### Phase 3A: Mobile Tab Restriction (Jan 3, 2026) ✅
- **Feature** - Restricted mobile users to only see "Questionnaires" and "Entrée de données manuelle" tabs
- **Code Changes (supabase_shiny.py):**
  - Lines 2000-2020: CSS media query rules to hide 3 desktop-only tabs on mobile
  - Lines 2289-2338: JavaScript enforcement logic (IIFE with tab restriction)
- **Behavior:**
  - Mobile users (< 768px) only see: "Questionnaires", "Entrée de données manuelle"
  - Defaults to "Questionnaires" tab on mobile
  - Applies to both athletes and coaches
- **Deployed:** Live on production

### Phase 3B: Lactate/Race Toggle + Race Visualization (Jan 16, 2026) ✅
- **Feature 1: Lactate Test vs Race Toggle**
  - Form supports both lactate tests and race results
  - Radio buttons to switch between "Test de lactate" and "Course"
  - Conditional fields: lactate input or race time based on type
  - Results table shows type badge (gold for race, blue for lactate)
- **Database Changes:**
  - `test_type` TEXT column ('lactate' or 'race') with check constraint
  - `race_time_seconds` DECIMAL(10,2) for race times
  - `lactate_mmol` made nullable (only required for lactate tests)
  - Partial index `idx_lactate_tests_races` for efficient race queries
- **Feature 2: Coach Questionnaire Investigation**
  - Confirmed blocking is BY DESIGN for data authenticity
  - Coaches see "Les questionnaires sont réservés aux athlètes"
  - No code changes - inform Kerrian this is expected behavior
- **Feature 3: Race Visualization on "Résumé de période"**
  - `get_athlete_races()` helper with 15-minute cache
  - `get_race_by_id()` helper for single race lookup
  - Race selector dropdown showing all races ever recorded
  - Gold vertical line markers on CTL/ATL and zone graphs
  - "Simuler une date alternative" checkbox with date picker
  - Purple dashed markers for simulated race position
- **Code Changes (supabase_shiny.py):**
  - Lines ~572-642: `get_athlete_races()` and `get_race_by_id()` functions
  - Lines ~2544-2558: Race selector UI controls
  - Lines ~4062-4102: `race_selector_dropdown` render function
  - Lines ~3573-3616: Race markers in `run_duration_trend()`
  - Lines ~4454-4499: Race markers in `zone_time_longitudinal()`
  - Lines ~7881-7934: Updated results table with type column
  - Lines ~7936-8025: Updated form with type toggle
  - Lines ~8419-8439: `lactate_conditional_fields` render function
  - Lines ~8469-8572: Updated submission handler
- **Migration Required:** `migrations/add_lactate_test_type.sql`
- **Deployed:** Live on production (commit `699c370`)

### Phase 3C: ShinyWidgets Crash Fix (Jan 18, 2026) ✅
- **Problem:** Dashboard crashed ~2 seconds after login on ShinyApps.io (worked locally)
- **Root Cause:** `shinywidgets` library incompatible with ShinyApps.io Python environment
- **Solution:** Convert all Plotly graphs from shinywidgets to HTML rendering
- **Code Changes (supabase_shiny.py):**
  - Commented out: `from shinywidgets import output_widget, render_plotly`
  - Added `plotly_to_html()` helper function (uses `fig.to_html()` with inline JS)
  - Changed 7 graph functions from `@render_plotly` to `@output` + `@render.ui`
  - Changed all `output_widget("name")` to `ui.output_ui("name")`
  - All `return fig` statements now `return plotly_to_html(fig)`
- **Graphs Converted:**
  - `run_duration_trend()` - CTL/ATL/TSB trend
  - `pie_types()` - Activity type distribution
  - `pace_hr_scatter()` - Pace vs HR scatter
  - `weekly_volume()` - Weekly volume bars
  - `zone_time_longitudinal()` - Zone time over time
  - `plot_xy()` - Single activity XY graph
  - `comparison_plot()` - Activity comparison
- **Technical Note:** First graph uses `include_plotlyjs=True` (inline JS), subsequent use CDN to avoid duplicate JS loading
- **Deployed:** Live on production

### Phase 3D: AWS Lambda Daily Automation (Jan 20, 2026) ✅
- **Goal:** Automated daily ingestion of athlete data without manual intervention
- **Architecture:**
  - EventBridge Scheduler triggers Lambda at 6 AM Eastern daily
  - Lambda loads credentials from Secrets Manager
  - Processes 18 athletes sequentially with 5-min timeout each
  - Uses 3-day rolling window for overlap safety
  - Duplicate prevention via `get_existing_activity_ids()`
- **Files Created:**
  - `lambda/lambda_function.py` - Main Lambda handler
  - `lambda/aws_secrets_loader.py` - Secrets Manager integration
  - `lambda/build_lambda.sh` - Build script for deployment package
- **Code Changes (intervals_hybrid_to_supabase.py):**
  - Line 806: Added `ATHLETES_JSON_PATH` env var support for Lambda
  - Line 2218: Fixed exit code logic (return 0 when no new activities, not 1)
- **Issues Solved During Setup:**
  1. **pandas not found:** Lambda Layers not accessible by subprocess → included in deployment package
  2. **numpy C-extensions failed:** macOS binaries uploaded → used `--platform manylinux2014_x86_64`
  3. **fitparse no Linux wheel:** Pure Python packages → split pip install commands
  4. **Timeouts:** 2-min Lambda timeout too short → increased to 15 min
  5. **False failures:** Script returned 1 when no new activities → fixed exit code logic
- **Lambda Configuration:**
  - Function: `ins-dashboard-daily-ingestion`
  - Runtime: Python 3.11
  - Memory: 512 MB
  - Timeout: 15 minutes
  - Schedule: `cron(0 6 * * ? *)` with America/Toronto timezone
- **Build Command (for updates):**
  ```bash
  cd lambda/
  ./build_lambda.sh
  # Then upload lambda_deployment.zip to AWS Lambda console
  ```
- **Result:** 18/18 athletes processing successfully

### Phase 3E: Fast Login + Questionnaire Validation (Jan 29, 2026) ✅
- **Questionnaire Validation:**
  - Tested daily workout and weekly wellness surveys - both working
  - Deleted test data for Kevin Robertson
- **Lactate Form UI Update:**
  - Distance field now beside Lactate field for lactate tests
  - Distance | Race Time side by side for races
- **Fast Login Performance Fix:**
  - **Problem:** Login took 7-10 seconds (bcrypt loop through all 24 users)
  - **Solution:** SHA256 password prefix for O(1) lookup
  - **Result:** Login now <1 second
- **Implementation:**
  - Added `password_prefix` column to `users` table
  - Added `generate_password_prefix()` to `auth_utils.py`
  - Login: generate prefix → query by prefix → bcrypt verify 1 user
- **Database Migration:** `migrations/add_password_prefix.sql`
- **Files Modified:**
  - `auth_utils.py`: Added `generate_password_prefix()` function
  - `supabase_shiny.py`: Updated login handler, lactate form UI
- **Deployed:** Live on production

### Phase 3F: Sync Button + Security Fixes (Jan 30, 2026) ✅
- **Supabase Security Fixes:**
  - Enabled RLS on 3 tables: `lactate_tests`, `weekly_monotony_strain`, `activity_zone_time`
  - Fixed mutable `search_path` on 10 functions
  - Revoked anon/authenticated access from materialized views
  - Created service-role specific policies
- **Migrations Created:**
  - `migrations/enable_rls_missing_tables.sql`
  - `migrations/fix_security_warnings.sql`
- **Manual Sync Button:**
  - Added "Sync" button to dashboard header (next to Logout)
  - Triggers Lambda Function URL for on-demand data refresh
  - Syncs ALL 18 athletes (3-day rolling window)
  - Available to everyone (athletes + coach)
  - Shows progress/result status
- **Lambda Updates:**
  - Added Function URL support with Bearer token authentication
  - Added CORS headers for cross-origin requests
  - Still works with EventBridge scheduled trigger
- **Rate Limiting:**
  - Created `sync_log` table to track sync attempts
  - `check_sync_allowed()` SQL function limits to 3 per day
  - Dashboard checks limit before triggering Lambda
- **Migration:** `migrations/create_sync_log.sql`
- **Files Modified:**
  - `lambda/lambda_function.py`: Function URL + Bearer auth
  - `supabase_shiny.py`: Sync button, status display, rate limiting
  - `.env`, `shiny_env.env`: Added Lambda credentials
- **UI Styling:** Removed borders from Logout and Sync buttons
- **Documentation:** Created `AWS_REFRESH_SETUP.md` with setup guide
- **Deployed:** Live on production

### Phase 3G: Events Card + Injury Tracking (Feb 2, 2026) ✅
- **Tab Restructure:**
  - Reordered cards: Events (TOP) → Training Zones → Personal Records (BOTTOM)
  - Renamed "Tests et courses" to "Événements"
  - Removed role restrictions (all users see all cards)
- **Interactive SVG Body Picker:**
  - 22 clickable body zones (runner-focused)
  - 3 intensity levels: Green (légère), Yellow (modérée), Red (sévère)
  - Status tracking: active, recovering, resolved
  - JavaScript/CSS for hover/click interactions
- **Database Migration:**
  - Extended `test_type` CHECK to include 'injury'
  - Added columns: `injury_location`, `injury_severity`, `injury_status`
  - Made `distance_m` nullable (not needed for injuries)
  - Added CHECK constraints for data integrity
- **Migration:** `migrations/extend_lactate_tests_for_injuries.sql`
- **Files Modified:**
  - `supabase_shiny.py`: SVG body picker, injury UI, card reorder, handler updates
- **Code Location:**
  - SVG body picker: `lactate_conditional_fields()` function (~line 8915)
  - Card reorder: `manual_entry_content()` function (~line 8210)
  - Injury handler: `handle_save_lactate_test()` function (~line 8977)
- **Deployed:** Live on production

### Phase 3I: Metric Rounding (Feb 12, 2026) ✅
- **Hover Tooltip Rounding:**
  - CTL → `.1f` (was raw float with 10+ decimals)
  - ATL → `.1f`
  - TSB → `.1f`
  - Vertical Oscillation → `.1f` in XY graph + comparison hovers
  - LSS → `.2f` in XY graph + comparison hovers
- **Design Decision:** Frontend-only rounding
  - CTL/ATL/TSB are EWM-calculated in dashboard — no DB storage
  - VO/LSS are raw sensor data — full precision preserved in DB for future analytics
- **Implementation:**
  - Added `hovertemplate` with `%{y:.1f}` to CTL/ATL/TSB `go.Scatter()` traces in `run_duration_trend()`
  - Created `_hover_format` dict in `plot_xy()` for variable-specific formatting
  - Created `_fmt_hover_vals()` helper in `comparison_plot()` for consistent formatting
  - Covers both primary and secondary Y-axis traces
- **Files Modified:** `supabase_shiny.py` only
- **Deployed:** Live on production (commit `90dd2cf`), pushed to GitHub

### Phase 3H: Multi-Feature Session (Feb 8, 2026) ✅
- **Zone Error Fix:**
  - Root cause: `reindex(fill_value=0)` on DataFrame with string columns
  - Fix: Drop non-numeric columns before reindexing
  - File: `supabase_shiny.py` line ~4500
- **Per-Athlete Sync Button:**
  - Athletes sync only their own data, coaches sync all
  - Dashboard sends `{"athlete_name": "Name"}` for athletes, `{}` for coaches
  - Lambda parses optional filter, falls back to all athletes if absent
  - Backward compatible with EventBridge daily cron
  - Files: `supabase_shiny.py` (handle_refresh_data), `lambda/lambda_function.py`
  - Lambda redeployed and tested: 1/1 single athlete (5.5s) and 18/18 all (83s)
- **Maximal Speed Test Event:**
  - New `speed_test` type in Events card (3 types now: Lactate, Course, Vitesse max)
  - Added `speed_ms` DECIMAL(6,3) column to `lactate_tests`
  - Auto-calculates m/s from distance and time
  - Time input supports MM:SS:MS format (milliseconds)
  - Reuses `parse_time_to_seconds()` with fallback for raw seconds
  - Migration: `migrations/add_speed_test_event.sql`
- **Body Picker in Daily Questionnaire:**
  - Dual SVG body picker (front + back) with multi-select
  - Per-body-part severity (1-3) with color coding
  - JS moved from `ui.HTML()` `<script>` to `ui.tags.script()` (fixes non-execution bug)
  - Event delegation on `document` for reliable click handling
  - Composite keys `view:partId` for independent front/back selections
  - New `workout_pain_entries` table (one row per selected body part per survey)
  - New `capacite_execution` column (0-3 scale) on `daily_workout_surveys`
  - Removed `douleur_intensite` slider (redundant with per-part severity)
  - Submission handler: `return=representation` → gets UUID → batch inserts pain entries
  - Migration: `migrations/create_workout_pain_entries.sql`
- **Pace/HR Dots Toggle:**
  - Added "Afficher les points" checkbox to "Allure vs Fréquence cardiaque" card
  - Scatter dots conditionally rendered; trend lines always visible
  - When dots hidden, legend shows on trend lines instead
- **Removed Injury from Events Card:**
  - "Douleur/Blessure" type removed from Events card radio buttons
  - SVG body picker, location dropdown, severity/status selectors removed (~180 lines)
  - Pain tracking now exclusively in daily questionnaire body picker
  - Existing injury records still display in results table (backward compatible)
- **LSS Investigation:**
  - Intervals.icu API strips Stryd developer fields from FIT exports
  - Only 2 athletes have LSS data (from direct watch sync)
  - No code fix possible - API limitation
  - File investigated: `intervals_hybrid_to_supabase.py` line 1162
- **Prevention Staff Login:** Added to to-do for future implementation
- **Deployment Notes:**
  - Added `--exclude "lambda"` to deploy command (lambda/package/ has spaces in folder names)
  - Added `import json` at top of `supabase_shiny.py` (was only imported locally before)
- **Files Modified:**
  - `supabase_shiny.py`: Zone fix, sync update, speed test, body picker (JS fix + composite keys + removed slider), dots toggle, removed injury from Events, json import
  - `lambda/lambda_function.py`: Per-athlete filter
  - `complete_database_schema.sql`: New table + columns documented
  - `migrations/add_speed_test_event.sql` (NEW)
  - `migrations/create_workout_pain_entries.sql` (NEW)
- **Deployed:** Dashboard + Lambda both live (3 deployments total)

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
  --exclude "manifest.json" \
  --exclude "lambda"
```

**Deployment Checklist:**
- [ ] Do NOT create `.python-version` file (ShinyApps.io only supports Python 3.9.x)
- [ ] Use `app.py` as entrypoint (wrapper with error handling)
- [ ] `requirements.txt` should have NO version constraints (just package names)
- [ ] Use `--app-id 16149191` to update existing app (NOT create new one)
- [ ] Exclude all unnecessary files (see command above)
- [ ] **NEVER use shinywidgets** - causes crashes on ShinyApps.io (use `plotly_to_html()` instead)

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

**Troubleshooting "Disconnected from server" after login:**
- If app crashes ~2 seconds after login with Plotly graphs
- ROOT CAUSE: `shinywidgets` library incompatible with ShinyApps.io
- SOLUTION: Use `plotly_to_html()` helper instead of `@render_plotly` / `output_widget()`
- See Phase 3C in Archive for full details

### ShinyApps.io Registry

| App Name | App ID | Status |
|----------|--------|--------|
| saintlaurentselect_dashboard | 16149191 | ✅ PRODUCTION |
| ins_dashboard | 16146104 | ⏸️ Not in use |

### Supabase Database
- **Project:** vqcqqfddgnvhcrxcaxjf
- **Region:** Default
- **Tables:** 16 (athlete, users, activity_metadata, activity, activity_intervals, wellness, daily_workout_surveys, weekly_wellness_surveys, personal_records, personal_records_history, athlete_training_zones, activity_zone_time, weekly_zone_time, lactate_tests, weekly_monotony_strain, sync_log, workout_pain_entries)

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

### ✅ Recently Fixed (Feb 2026)

| Feature | Issue | Status |
|---------|-------|--------|
| **Body Picker Not Clickable** | SVG parts visible but click handlers not attached | ✅ Fixed (Feb 8, 2026) - Phase 3H |
| **Front/Back Cross-Selection** | Clicking front knee also selected back knee | ✅ Fixed (Feb 8, 2026) - Phase 3H |
| **Pace/HR Graph Noise** | Too many dots on old data, no way to hide them | ✅ Fixed (Feb 8, 2026) - Phase 3H |
| **Zone Error** | "Invalid value '0' for dtype 'str'" on zone graph | ✅ Fixed (Feb 8, 2026) - Phase 3H |
| **Per-Athlete Sync** | All syncs triggered full team sync | ✅ Fixed (Feb 8, 2026) - Phase 3H |
| **Speed Test Event** | No way to record sprint times (now with ms support) | ✅ Added (Feb 8, 2026) - Phase 3H |
| **Body Picker** | Pain location was text-only input | ✅ Added (Feb 8, 2026) - Phase 3H |
| **Events Card** | No injury tracking | ✅ Added (Feb 2, 2026) - Phase 3G → Moved to questionnaire only |

### ✅ Recently Fixed (Jan 2026)

| Feature | Issue | Status |
|---------|-------|--------|
| **Supabase Security** | RLS disabled, mutable search_path | ✅ Fixed (Jan 30, 2026) - Phase 3F |
| **Manual Sync Button** | No on-demand refresh | ✅ Added (Jan 30, 2026) - Phase 3F |
| **Slow Login** | 7-10 second login time | ✅ Fixed (Jan 29, 2026) - SHA256 prefix lookup |
| **AWS Lambda Cron** | Daily automation not running | ✅ Fixed (Jan 20, 2026) |
| **ShinyWidgets Crash** | Dashboard crash on production | ✅ Fixed (Jan 18, 2026) |
| **Bulk Import** | Historical data missing | ✅ Complete (Jan 18, 2026) |

### ✅ Recently Fixed (Dec 2025)

| Issue | Phase | Solution |
|-------|-------|----------|
| Zone Time Performance | 2O, 2S | Materialized views + incremental calculation |
| Monotony/Strain Performance | 2V | Pre-calculated in database (111 weeks backfilled) |
| Tooltips Behind Headers | 2T | JavaScript-powered positioning |
| Zone Graph Display | 2N | Plotly responsiveness + timestamp conversion |
| Coach Selector | 2Q | Added reactive event decorator |

### 🔴 Known Limitations

| Issue | Details |
|-------|---------|
| **LSS (Leg Spring Stiffness)** | Intervals.icu API strips Stryd developer fields from FIT exports. Only 2 athletes have LSS data (from direct watch sync). No code fix possible - API limitation. |

### 🟡 Next Priorities

1. **Prevention staff login** - New role for physio/prevention staff with restricted access
2. **Git commit all changes** - Push lambda/ directory + session changes to GitHub
3. **Dashboard enhancements** - RPE tracking table, wellness tracking table

---

**END OF DOCUMENT**

*Last Updated: February 12, 2026*
