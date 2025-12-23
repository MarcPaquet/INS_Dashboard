# INS Dashboard - Data Flow & Automation

**Last Updated:** December 9, 2025

---

## DATA FLOW OVERVIEW

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA SOURCES                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │    GARMIN    │    │    STRYD     │    │   POLAR     │                   │
│  │   Watches    │    │   Pod        │    │   Watches   │                   │
│  └──────┬───────┘    └──────┬───────┘    └──────┬──────┘                   │
│         │                   │                   │                           │
│         └─────────┬─────────┴─────────┬─────────┘                           │
│                   │                   │                                      │
│                   ▼                   ▼                                      │
│          ┌──────────────┐    ┌──────────────┐                               │
│          │   STRAVA     │    │INTERVALS.ICU │  ◀── PREFERRED PATH           │
│          │   (Avoid!)   │    │  (Primary)   │                               │
│          └──────┬───────┘    └──────┬───────┘                               │
│                 │                   │                                        │
│                 │   ┌───────────────┘                                        │
│                 │   │                                                        │
│                 ▼   ▼                                                        │
│          ┌──────────────┐                                                    │
│          │INTERVALS.ICU │  Watch→Intervals = Full FIT data                  │
│          │    API       │  Strava→Intervals = Stripped data (NO Stryd!)     │
│          └──────┬───────┘                                                    │
│                 │                                                            │
└─────────────────┼────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INGESTION LAYER                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────┐           │
│  │              intervals_hybrid_to_supabase.py                  │           │
│  ├──────────────────────────────────────────────────────────────┤           │
│  │                                                               │           │
│  │  1. FETCH: Get activity list from Intervals.icu              │           │
│  │      └─ Check existing_ids → Skip duplicates                 │           │
│  │                                                               │           │
│  │  2. DOWNLOAD: Get FIT file (or fallback to Streams API)      │           │
│  │      └─ FIT = Full data (GPS, HR, Power, Stryd biomechanics) │           │
│  │      └─ Streams = Backup (Sophie's watch firmware issue)     │           │
│  │                                                               │           │
│  │  3. PARSE: Extract all metrics                               │           │
│  │      └─ GPS: lat/lng (semicircles → degrees)                 │           │
│  │      └─ HR: heartrate, avg_hr                                │           │
│  │      └─ Power: watts, min/max/avg                            │           │
│  │      └─ Stryd: GCT, LSS, vertical oscillation                │           │
│  │      └─ Moving time: Strava algorithm (speed > threshold)    │           │
│  │                                                               │           │
│  │  4. ENRICH: Weather data                                     │           │
│  │      └─ Archive API (3 retries)                              │           │
│  │      └─ Forecast API fallback (3 retries)                    │           │
│  │      └─ NULL if all fail (never blocks import)               │           │
│  │                                                               │           │
│  │  5. INSERT: Batch insert to Supabase                         │           │
│  │      └─ Retry with exponential backoff (1s, 2s, 4s)          │           │
│  │                                                               │           │
│  │  6. WELLNESS: Import for all athletes (UPSERT)               │           │
│  │      └─ Historical: --wellness-oldest/--wellness-newest      │           │
│  │                                                               │           │
│  └──────────────────────────────────────────────────────────────┘           │
│                 │                                                            │
└─────────────────┼────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATABASE (Supabase)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                       │
│  │   athlete    │  │    users     │  │   wellness   │                       │
│  │   (5 rows)   │  │   (6 rows)   │  │  (daily)     │                       │
│  └──────────────┘  └──────────────┘  └──────────────┘                       │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────┐            │
│  │                    activity_metadata                         │            │
│  │  (1 row per activity: date, distance, duration, weather)    │            │
│  └─────────────────────────────────────────────────────────────┘            │
│                           │                                                  │
│              ┌────────────┴────────────┐                                    │
│              ▼                         ▼                                    │
│  ┌──────────────────────┐  ┌──────────────────────┐                         │
│  │      activity        │  │  activity_intervals  │                         │
│  │  (GPS timeseries)    │  │  (workout segments)  │                         │
│  │   ~2.5M records      │  │   ~10K intervals     │                         │
│  └──────────────────────┘  └──────────────────────┘                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DASHBOARD (ShinyApps.io)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  URL: https://insquebec-sportsciences.shinyapps.io/saintlaurentselect_dashboard/
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────┐           │
│  │                     supabase_shiny.py                         │           │
│  ├──────────────────────────────────────────────────────────────┤           │
│  │  • Authentication (5 athletes + 1 coach)                     │           │
│  │  • Real-time queries from Supabase                           │           │
│  │  • Plotly visualizations                                     │           │
│  │  • Mobile-responsive design                                  │           │
│  │  • French UI                                                 │           │
│  └──────────────────────────────────────────────────────────────┘           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## AWS AUTOMATION ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AWS AUTOMATION (Planned)                             │
└─────────────────────────────────────────────────────────────────────────────┘

DAILY AUTOMATION (Lambda + EventBridge):
═══════════════════════════════════════

  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
  │ EventBridge  │────────▶│    Lambda    │────────▶│   Supabase   │
  │  (Cron)      │         │   (Python)   │         │  (Database)  │
  └──────────────┘         └──────┬───────┘         └──────────────┘
                                  │
  Morning: ~10 AM ET              │
  • Import new activities         │
  • Import today's wellness       ▼
  • Check weather upgrades   ┌──────────────┐
                             │   Secrets    │
  Evening: ~8 PM ET          │   Manager    │
  • Weather backfill         │ (Credentials)│
  • Secondary sync           └──────────────┘


BULK IMPORT (One-time EC2):
═══════════════════════════

  ┌──────────────────────────────────────────────────────────────┐
  │                         EC2 Instance                          │
  │                        (t3.small)                             │
  ├──────────────────────────────────────────────────────────────┤
  │                                                                │
  │   # Run ALL athletes in PARALLEL with --skip-weather:        │
  │   python intervals_hybrid_to_supabase.py \                    │
  │     --athlete "Matthew Beaudet" \                             │
  │     --oldest 2021-01-01 --newest 2024-12-31 \                 │
  │     --wellness-oldest 2021-01-01 --wellness-newest 2024-12-31 │
  │     --skip-weather &                                          │
  │   # ... repeat for all 12-15 athletes                        │
  │   wait                                                        │
  │                                                                │
  │   Strategy: PARALLEL processing (all athletes simultaneously) │
  │   Duration: ~2-4 hours (skipping weather bypasses rate limit) │
  │                                                                │
  └──────────────────────────────────────────────────────────────┘


ON-DEMAND (Refresh Button):
═══════════════════════════

  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
  │  Dashboard   │────────▶│    Lambda    │────────▶│   Supabase   │
  │   Button     │         │   (Python)   │         │  (Database)  │
  │ "Actualiser" │         │              │         │              │
  └──────────────┘         └──────────────┘         └──────────────┘
        │                                                  │
        └──────────────────────────────────────────────────┘
                    Show "Importing..." until done
```

---

## RATE LIMITS & CONSTRAINTS

### Open-Meteo Weather API
| Limit | Value |
|-------|-------|
| Per minute | 600 calls |
| Per hour | 5,000 calls |
| Per day | **10,000 calls** |
| Per month | 300,000 calls |

### Bulk Import Estimation (with --skip-weather)
| Timeframe | Activities | Time Needed |
|-----------|------------|-------------|
| 4 years (2021-2024) | ~20,000 | ~2-4 hours |
| 3 years (2023-2025) | ~15,000 | ~1.5-3 hours |
| 2 years (2024-2025) | ~10,000 | ~1-2 hours |

**Note:** Using `--skip-weather` bypasses Open-Meteo rate limits entirely. Weather will be fetched by daily cron going forward.

---

## KEY DECISIONS

### Strava vs Watch Linking
**CRITICAL:** Athletes must link watches directly to Intervals.icu, NOT through Strava.

```
❌ BAD:  Watch → Strava → Intervals.icu  (Stryd data stripped!)
✅ GOOD: Watch → Intervals.icu directly  (Full FIT data preserved)
```

### Processing Strategy
- **Bulk import:** PARALLEL with --skip-weather (all athletes simultaneously, ~2-4 hours)
- **Daily sync:** Can run in parallel (small data volume, includes weather)

### Data Priority
1. Activities + GPS records (core data)
2. Weather enrichment (cascade: archive → forecast → null)
3. Wellness data (UPSERT, idempotent)
4. TSS calculation (deferred - separate post-processing step)

---

## DEC 12, 2025 - SESSION 2 (Phase 2P)

### UI Cleanup + Questionnaire Fixes - DEPLOYED
| Task | Status | Details |
|------|--------|---------|
| **Plotly Deprecation** | ✅ FIXED | `titlefont` → `title_font` in comparison graph |
| **Lactate Card** | ✅ FIXED | Now visible to coaches + athletes |
| **Calendar Removal** | ✅ DONE | Removed year calendar for cleaner UI + mobile |
| **Activity Labels** | ✅ FIXED | Removed "(intervalles)" suffix |
| **Questionnaire** | ✅ FIXED | Uses same activity list as "Analyse de séance" |
| **Survey Filtering** | ✅ DONE | Excludes already-filled activities from dropdown |

### Working Features (Verified Dec 12)
- All graphs display full width
- Comparison graph works without warnings
- Lactate test entry works for both roles
- Questionnaire shows correct activities
- Filled surveys filtered out of dropdown
- Cleaner mobile experience (no calendar)

---

## DEC 12, 2025 - SESSION 1 (Phase 2O)

### Zone System Overhaul + Materialized Views - DEPLOYED
| Task | Status | Details |
|------|--------|---------|
| **6-Zone Config** | ✅ DONE | Real athlete-specific pace zones |
| **Materialized Views** | ✅ DONE | `activity_zone_time`, `weekly_zone_time` |
| **Auto-Refresh** | ✅ DONE | Views refresh after daily import |
| **Performance** | ✅ IMPROVED | ~60s → ~1s load time |

---

## DEC 9, 2025 - ISSUES FIXED (Phase 2N)

### UI/Display Issues - FIXED
| Issue | Status | Solution |
|-------|--------|----------|
| **Calendar Zoom** | ✅ FIXED | CSS `width: 100% !important` + `autosize=True` + JS resize triggers |
| **Zone Graph Width** | ✅ FIXED | Same CSS fix applied to all Plotly containers |
| **Zone Longitudinal Lines** | ✅ FIXED | Convert Pandas Timestamps to `YYYY-MM-DD` strings for Plotly |
| **No Data Display** | ✅ FIXED | Added error message "Aucune donnee GPS/allure pour cet athlete" |
| **Two-Workout Comparison** | ✅ FIXED | Better error handling for empty data after NaN cleaning |

---

## DEC 8, 2025 - SESSION COMPLETED

### What Was Implemented
1. **Temporal Zone Matching** - Zone calculations now use zones effective at each activity's date
   - New `fetch_zones_for_date()` function with caching
   - Modified `calculate_zone_time_by_week()` with `use_temporal_zones` parameter
   - Proper sports science accuracy - past activities use past zone configurations

2. **Fixed Zone Distribution** - "Analyse des zones d'allure" now calculates from GPS data
   - Was querying non-existent `activity_pace_zones` view
   - Now uses same logic as longitudinal graph

3. **Shared Timeframe** - Zone analysis uses same date range as CTL/ATL graphs
   - Removed separate `pace_zone_date_start/end` inputs

4. **UI Cleanup**
   - X-axis label changed from "Semaine (lundi)" to "Date"
   - Removed explanatory text from zone analysis card
   - EWM properly hides data until enough history exists

### Deployed to Production
- URL: https://insquebec-sportsciences.shinyapps.io/saintlaurentselect_dashboard/
- Status: Live but with performance issues noted above

---

## UPCOMING MILESTONES

- [x] **Dec 1:** Pre-bulk import audit complete
- [x] **Dec 2:** Bulk import optimization (parallel + --skip-weather)
- [x] **Dec 6:** Deployment fix (ShinyApps.io)
- [x] **Dec 7:** UI polish & performance optimizations
- [x] **Dec 8:** Temporal zone matching + zone analysis fixes (deployed)
- [x] **Dec 9:** Production Plotly fixes (graphs full width, zone lines visible)
- [ ] **Next:** Fix daily questionnaire dropdown
- [ ] **Next:** Fix performance issues (materialized views?)
- [ ] **TBD:** AWS infrastructure setup (Lambda, EventBridge)
- [ ] **TBD:** Execute bulk import on AWS EC2
