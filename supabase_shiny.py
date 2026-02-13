"""
INS Dashboard - Athletic Performance Analytics

Interactive Shiny dashboard for visualizing training metrics including:
- Activity time series (HR, pace, cadence, power, running dynamics)
- Weekly volume aggregation and trends
- Wellness tracking and questionnaires
- Personal records and training zones
- Multi-athlete coach view with role-based access

Stack: Shiny for Python, Plotly, Supabase PostgreSQL
"""
from __future__ import annotations
import json
import os
import time
import traceback
from datetime import date, datetime, timedelta
import functools
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter
from zoneinfo import ZoneInfo
import requests
from dotenv import load_dotenv
import plotly.graph_objects as go

from shiny import App, ui, render, reactive
# shinywidgets crashes on ShinyApps.io - using Plotly HTML rendering instead
# from shinywidgets import output_widget, render_plotly

# Import algorithme temps actif (Strava-like)
from moving_time import compute_moving_time_strava

# Import authentication utilities
from auth_utils import verify_password, generate_password_prefix


# ========== Performance Monitoring ==========

def timing_decorator(func):
    """Decorator to time function execution (logs if > 100ms)."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        if elapsed > 0.1:  # Log if > 100ms
            print(f"[TIMING] {func.__name__}: {elapsed:.3f}s")
        return result
    return wrapper

# Palette de couleurs Saint-Laurent Sélect (pie + volume hebdo)
COLORS = {
    "Run": "#D92323",        # Rouge club (course extérieure)
    "Course": "#D92323",     # Rouge club (Run+TrailRun agrégé)
    "TrailRun": "#D9CD23",   # Jaune club (trail)
    "VirtualRun": "#FF6B6B", # Rouge clair (tapis)
    "Tapis": "#FF6B6B",      # Rouge clair (same as VirtualRun)
    "Autre": "#FFA500"       # Orange (autres activités)
}

RUN_TYPES = {"run", "trailrun", "virtualrun", "treadmill"}

# Zone colors for distinct mode (consistent across sessions)
# Gradient from blue (slowest/recovery) to red (fastest)
ZONE_COLORS = {
    1: "#3B82F6",  # Blue - Zone 1 (slowest/recovery)
    2: "#06B6D4",  # Cyan - Zone 2
    3: "#22C55E",  # Green - Zone 3
    4: "#EAB308",  # Yellow - Zone 4
    5: "#F97316",  # Orange - Zone 5
    6: "#EF4444",  # Red - Zone 6 (fastest)
    7: "#DC2626",  # Darker red - Zone 7
    8: "#B91C1C",  # Even darker red - Zone 8
    9: "#991B1B",  # Dark red - Zone 9
    10: "#7F1D1D", # Darkest red - Zone 10
}
MERGED_ZONE_COLOR = "#8B5CF6"  # Purple for merged zones

# Aliases robustes pour les selects UI (labels & valeurs -> codes canoniques)
XVAR_ALIASES = {
    "moving": "moving", "Temps en mouvement (mm:ss)": "moving",
    "dist": "dist", "Distance (km)": "dist",
}
YVAR_ALIASES = {
    # Internal codes -> internal codes
    "heartrate": "heartrate",
    "cadence": "cadence",
    "pace": "pace",
    "watts": "watts",
    "vertical_oscillation": "vertical_oscillation",
    "altitude": "altitude",
    "ground_contact_time": "ground_contact_time",
    "leg_spring_stiffness": "leg_spring_stiffness",
    "none": "none",
    # French labels -> internal codes (for dropdown values)
    "Fréquence cardiaque": "heartrate",
    "Cadence": "cadence",
    "Allure (min/km)": "pace",
    "Puissance": "watts",
    "Oscillation verticale": "vertical_oscillation",
    "Altitude": "altitude",
    "Temps de contact au sol (GCT)": "ground_contact_time",
    "Leg Spring Stiffness (LSS)": "leg_spring_stiffness",
    "Aucun": "none",
}

# ========== Chargement .env & session HTTP Supabase ==========
# Try loading env files in order:
#   1. .env.dashboard.local (local development)
#   2. shiny_env.env (legacy)
#   3. .env (production - shinyapps.io)
env_files = [".env.dashboard.local", "shiny_env.env", ".env"]
script_dir = os.path.dirname(os.path.abspath(__file__))
print(f"[DEBUG] Script directory: {script_dir}")
print(f"[DEBUG] Directory contents: {os.listdir(script_dir)}")

env_loaded = False
for env_file in env_files:
    env_path = os.path.join(script_dir, env_file)
    print(f"[DEBUG] Checking: {env_path} - exists: {os.path.exists(env_path)}")
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path, override=True)  # Override shell variables
        print(f"[OK] Loaded environment from: {env_file}")
        env_loaded = True
        break

if not env_loaded:
    print("[WARN] No env file found, checking environment variables directly...")

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
print(f"[DEBUG] SUPABASE_URL set: {bool(SUPABASE_URL)}")
print(f"[DEBUG] SUPABASE_KEY set: {bool(SUPABASE_KEY)}")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(f"SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY (ou ANON) doivent être définis. script_dir={script_dir}, files={os.listdir(script_dir)}")

# Fuseau horaire local pour l'agrégation hebdo
LOCAL_TZ = os.getenv("INS_TZ", "America/Toronto")  # fuseau horaire local pour l'agrégation hebdo

# Lambda Function URL for manual refresh (optional - button hidden if not set)
LAMBDA_FUNCTION_URL = os.getenv("LAMBDA_FUNCTION_URL", "")
LAMBDA_REFRESH_TOKEN = os.getenv("LAMBDA_REFRESH_TOKEN", "")

_sess = requests.Session()
_sess.headers.update({"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
_sess.headers.update({"Accept-Encoding": "gzip, deflate"})

# ========== Memory Cache for Metadata (5-minute TTL) ==========
_metadata_cache = {}
_metadata_cache_timestamp = {}
METADATA_CACHE_TTL = 300  # 5 minutes

# Disk cache for activity time series (speeds up activity switching)
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)

def _rest_url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"

def supa_select(table: str, select="*", params: dict[str, str] | None = None,
                limit: int | None = 10000, order: str | None = None) -> pd.DataFrame:
    """
    Sélecteur générique Supabase REST → DataFrame.
    Gère automatiquement la pagination pour les grandes activités.
    """
    q = {"select": select}
    if params: q.update(params)
    if order: q["order"] = order
    
    all_data = []
    offset = 0
    page_size = min(1000, limit) if limit else 1000  # Supabase default max
    
    while True:
        q_page = q.copy()
        q_page["limit"] = str(page_size)
        q_page["offset"] = str(offset)
        
        r = _sess.get(_rest_url(table), params=q_page, timeout=30)
        r.raise_for_status()
        
        page_data = r.json() if r.content else []
        if not page_data:
            break
            
        all_data.extend(page_data)
        offset += len(page_data)
        
        # Stop if we got less than page_size (last page) or reached limit
        if len(page_data) < page_size:
            break
        if limit and offset >= limit:
            break
    
    return pd.DataFrame(all_data) if all_data else pd.DataFrame()

def supa_upsert(table: str, data: dict | list[dict], on_conflict: str | None = None) -> bool:
    """
    Upsert data to Supabase table using REST API.
    Returns True on success, False on failure.
    """
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates"
        }
        
        # Ensure data is a list
        if isinstance(data, dict):
            data = [data]
        
        r = _sess.post(_rest_url(table), json=data, headers=headers, timeout=30)
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"Error in supa_upsert: {e}")
        return False

def supa_insert(table: str, data: dict | list[dict]) -> bool:
    """
    Insert data to Supabase table using REST API (append-only, no update).
    Returns True on success, False on failure.
    """
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }

        # Ensure data is a list
        if isinstance(data, dict):
            data = [data]

        r = _sess.post(_rest_url(table), json=data, headers=headers, timeout=30)
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"Error in supa_insert: {e}")
        return False

# ========== Aides données ==========
def fetch_athletes() -> pd.DataFrame:
    """Retourne athlete_id + name triés par nom."""
    df = supa_select("athlete", select="athlete_id,name", order="name.asc", limit=20000)
    if not df.empty:
        df["athlete_id"] = df["athlete_id"].astype(str)
        df["name"] = df["name"].astype(str)
    return df

@timing_decorator
def fetch_metadata(start_iso: str, end_iso: str, athlete_ids: list[str], limit: int = 100000) -> pd.DataFrame:
    """Récupère les métadonnées d'activités d'un athlète, bornées par start/end (avec cache mémoire)."""
    # Generate cache key
    cache_key = f"{'_'.join(sorted(athlete_ids))}_{start_iso}_{end_iso}"
    now = time.time()
    
    # Check memory cache
    if cache_key in _metadata_cache:
        cache_time = _metadata_cache_timestamp.get(cache_key, 0)
        if (now - cache_time) < METADATA_CACHE_TTL:
            return _metadata_cache[cache_key].copy()
    
    # Fetch from database
    params = {
        "athlete_id": f"in.({','.join(athlete_ids)})",
        "start_time": f"gte.{start_iso}",
        "and": f"(start_time.lte.{end_iso})",
        "order": "start_time.asc",
    }
    # Select only columns that exist in activity_metadata table
    cols = ("activity_id,athlete_id,type,date,start_time,distance_m,duration_sec,avg_hr,"
            "weather_temp_c,weather_humidity_pct,weather_wind_speed_ms,weather_cloudcover_pct,air_us_aqi")
    df = supa_select("activity_metadata", select=cols, params=params, limit=limit)

    if not df.empty:
        if "start_time" in df.columns:
            df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
        df["type"] = df["type"].astype(str).str.strip()

        # Compute derived columns in Python
        df["type_lower"] = df["type"].str.lower()
        df["type_category"] = df["type_lower"].map({
            "run": "Course",
            "trailrun": "Course",
            "virtualrun": "Tapis"
        }).fillna("Autre")

        # Compute distance_km, duration_min, pace_skm (VECTORIZED - 10x faster than .apply())
        df["distance_km"] = df["distance_m"] / 1000.0
        df["duration_min"] = df["duration_sec"] / 60.0
        # Vectorized pace calculation - avoids slow row-by-row .apply()
        df["pace_skm"] = np.where(
            df["distance_m"] > 0,
            df["duration_min"] / df["distance_km"],
            np.nan
        )
    
    # Store in cache
    _metadata_cache[cache_key] = df.copy()
    _metadata_cache_timestamp[cache_key] = now
    
    return df

# Nouvelle aide: min/max de dates disponibles pour un athlète (en option, exclure VirtualRun)
def fetch_date_range(athlete_id: str, include_vrun: bool = True) -> tuple[date | None, date | None]:
    params_base = {"athlete_id": f"eq.{athlete_id}"}
    # Exclure VirtualRun si demandé (on garde toutes les autres activités)
    params_earliest = dict(params_base)
    params_latest = dict(params_base)
    if not include_vrun:
        params_earliest["type"] = "neq.VirtualRun"
        params_latest["type"] = "neq.VirtualRun"
    # Plus ancienne (Phase 2: use activity_metadata table)
    df_min = supa_select("activity_metadata", select="start_time", params={**params_earliest, "order": "start_time.asc"}, limit=1)
    # Plus récente
    df_max = supa_select("activity_metadata", select="start_time", params={**params_latest, "order": "start_time.desc"}, limit=1)
    if df_min.empty or df_max.empty:
        return None, None
    
    # Convert to datetime and handle NaT
    dmin_ts = pd.to_datetime(df_min.iloc[0]["start_time"], errors="coerce")
    dmax_ts = pd.to_datetime(df_max.iloc[0]["start_time"], errors="coerce")
    
    # Check if conversion was successful (not NaT)
    if pd.isna(dmin_ts) or pd.isna(dmax_ts):
        return None, None
    
    dmin = dmin_ts.date()
    dmax = dmax_ts.date()
    return dmin, dmax

def fetch_athlete_training_zones(athlete_id: str) -> pd.DataFrame:
    """
    Fetch the most recent pace zone configuration for an athlete.

    Returns DataFrame with columns:
    - zone_number (int): 1-6
    - pace_min_sec_per_km (float): Lower bound (faster pace)
    - pace_max_sec_per_km (float): Upper bound (slower pace)
    - zone_label (str): Human-readable label like "Z1 (>5:30/km)"

    Returns empty DataFrame if no zones configured.
    """
    params = {"athlete_id": f"eq.{athlete_id}"}
    df = supa_select("athlete_training_zones", select="*", params=params, limit=100)

    if df.empty:
        return pd.DataFrame()

    # Find most recent effective_from_date
    df["effective_from_date"] = pd.to_datetime(df["effective_from_date"])
    most_recent = df["effective_from_date"].max()
    df = df[df["effective_from_date"] == most_recent].copy()

    # Note: Do NOT filter out zones with NULL pace boundaries
    # Zone 6 (fastest) has pace_min=NULL, Zone 1 (slowest) has pace_max=NULL
    # This is by design - boundary zones have open-ended ranges

    if df.empty:
        return pd.DataFrame()

    # Add human-readable labels
    def format_pace(sec):
        if sec is None or pd.isna(sec):
            return "?"
        sec = float(sec)
        if sec >= 3600:
            return "lent"
        mins = int(sec // 60)
        secs = int(sec % 60)
        return f"{mins}:{secs:02d}"

    def make_label(row):
        zn = int(row["zone_number"])
        pmin = row["pace_min_sec_per_km"]
        pmax = row["pace_max_sec_per_km"]
        pmin_is_null = pmin is None or pd.isna(pmin)
        pmax_is_null = pmax is None or pd.isna(pmax)
        # Zone 6 (fastest): pmin is NULL, show "<X:XX/km"
        # Zone 1 (slowest): pmax is NULL, show ">X:XX/km"
        if pmin_is_null and not pmax_is_null:
            return f"Z{zn} (<{format_pace(pmax)}/km)"
        elif pmax_is_null and not pmin_is_null:
            return f"Z{zn} (>{format_pace(pmin)}/km)"
        elif pmin_is_null and pmax_is_null:
            return f"Z{zn}"
        else:
            return f"Z{zn} ({format_pace(pmin)}-{format_pace(pmax)}/km)"

    df["zone_label"] = df.apply(make_label, axis=1)

    return df.sort_values("zone_number")[["zone_number", "pace_min_sec_per_km", "pace_max_sec_per_km", "zone_label"]]


# Cache for zone lookups by (athlete_id, effective_date) to avoid repeated DB queries
_zone_by_date_cache = {}
_ZONE_BY_DATE_CACHE_TTL = 3600  # 1 hour TTL


def fetch_zones_for_date(athlete_id: str, target_date: date) -> pd.DataFrame:
    """
    Fetch training zones that were effective on a specific date.

    This finds the most recent zone configuration that was in effect on target_date,
    meaning effective_from_date <= target_date.

    Args:
        athlete_id: The athlete's ID
        target_date: The date to find effective zones for

    Returns DataFrame with columns:
    - zone_number (int): 1-6
    - pace_min_sec_per_km (float): Lower bound (faster pace)
    - pace_max_sec_per_km (float): Upper bound (slower pace)
    - zone_label (str): Human-readable label like "Z1 (>5:30/km)"
    - effective_from_date: The date these zones became effective

    Returns empty DataFrame if no zones exist for that date.
    """
    import time as _time
    now = _time.time()

    # Check cache first
    cache_key = (athlete_id, target_date.isoformat())
    if cache_key in _zone_by_date_cache:
        cached_time, cached_df = _zone_by_date_cache[cache_key]
        if now - cached_time < _ZONE_BY_DATE_CACHE_TTL:
            return cached_df.copy()

    # Query all zones for athlete where effective_from_date <= target_date
    target_str = target_date.isoformat()
    params = {
        "athlete_id": f"eq.{athlete_id}",
        "effective_from_date": f"lte.{target_str}"
    }
    df = supa_select("athlete_training_zones", select="*", params=params, limit=100)

    if df.empty:
        # No zones exist before this date - try to get earliest available zones
        params_fallback = {"athlete_id": f"eq.{athlete_id}"}
        df = supa_select("athlete_training_zones", select="*", params=params_fallback, limit=100)
        if df.empty:
            return pd.DataFrame()

    # Find most recent effective_from_date that is <= target_date
    df["effective_from_date"] = pd.to_datetime(df["effective_from_date"])

    # Filter to dates <= target_date
    df_filtered = df[df["effective_from_date"].dt.date <= target_date]

    if df_filtered.empty:
        # All zones are in the future - use earliest available
        most_recent = df["effective_from_date"].min()
    else:
        most_recent = df_filtered["effective_from_date"].max()

    df = df[df["effective_from_date"] == most_recent].copy()

    # Note: Do NOT filter out zones with NULL pace boundaries
    # Zone 6 (fastest) has pace_min=NULL, Zone 1 (slowest) has pace_max=NULL

    if df.empty:
        return pd.DataFrame()

    # Add human-readable labels
    def format_pace(sec):
        if sec is None or pd.isna(sec):
            return "?"
        sec = float(sec)
        if sec >= 3600:
            return "lent"
        mins = int(sec // 60)
        secs = int(sec % 60)
        return f"{mins}:{secs:02d}"

    def make_label(row):
        zn = int(row["zone_number"])
        pmin = row["pace_min_sec_per_km"]
        pmax = row["pace_max_sec_per_km"]
        pmin_is_null = pmin is None or pd.isna(pmin)
        pmax_is_null = pmax is None or pd.isna(pmax)
        # Zone 6 (fastest): pmin is NULL, show "<X:XX/km"
        # Zone 1 (slowest): pmax is NULL, show ">X:XX/km"
        if pmin_is_null and not pmax_is_null:
            return f"Z{zn} (<{format_pace(pmax)}/km)"
        elif pmax_is_null and not pmin_is_null:
            return f"Z{zn} (>{format_pace(pmin)}/km)"
        elif pmin_is_null and pmax_is_null:
            return f"Z{zn}"
        else:
            return f"Z{zn} ({format_pace(pmin)}-{format_pace(pmax)}/km)"

    df["zone_label"] = df.apply(make_label, axis=1)

    result = df.sort_values("zone_number")[["zone_number", "pace_min_sec_per_km", "pace_max_sec_per_km", "zone_label", "effective_from_date"]]

    # Cache the result
    _zone_by_date_cache[cache_key] = (now, result.copy())

    return result


# Cache for zone changes within date range
_zone_changes_cache = {}
_ZONE_CHANGES_CACHE_TTL = 3600  # 1 hour


def get_zone_changes_in_range(athlete_id: str, start_date: date, end_date: date) -> list[dict]:
    """
    Get list of zone configuration changes within a date range.

    Returns list of dicts with:
    - effective_from_date: Date when new zones became effective
    - zones: List of zone configs that started on that date

    Only returns dates WITHIN the range (not the initial zones before start_date).
    """
    import time as _time
    now = _time.time()

    # Check cache
    cache_key = (athlete_id, start_date.isoformat(), end_date.isoformat())
    if cache_key in _zone_changes_cache:
        cached_time, cached_result = _zone_changes_cache[cache_key]
        if now - cached_time < _ZONE_CHANGES_CACHE_TTL:
            return cached_result

    # Query zone configs where effective_from_date is WITHIN the range
    # (not including zones that were already effective before start_date)
    params = {
        "athlete_id": f"eq.{athlete_id}",
        "effective_from_date": f"gt.{start_date.isoformat()}",  # Strictly after start
    }

    df = supa_select("athlete_training_zones", select="*", params=params, limit=500)

    if df.empty:
        _zone_changes_cache[cache_key] = (now, [])
        return []

    # Filter to end_date
    df["effective_from_date"] = pd.to_datetime(df["effective_from_date"])
    df = df[df["effective_from_date"].dt.date <= end_date]

    if df.empty:
        _zone_changes_cache[cache_key] = (now, [])
        return []

    # Group by effective_from_date and collect zone changes
    result = []
    for eff_date, group in df.groupby("effective_from_date"):
        result.append({
            "effective_from_date": eff_date.date() if hasattr(eff_date, 'date') else eff_date,
            "zones": group.to_dict('records')
        })

    # Sort by date
    result = sorted(result, key=lambda x: x["effective_from_date"])

    _zone_changes_cache[cache_key] = (now, result)
    return result


# =====================================================
# RACE HELPER FUNCTIONS
# =====================================================

_races_cache = {}
_RACES_CACHE_TTL = 300  # 5 minutes cache for races


def get_athlete_races(athlete_id: str) -> list[dict]:
    """
    Fetch all races for an athlete (test_type='race'), ordered by date descending.
    Used for the race selector dropdown on "Résumé de période".
    """
    import time as _time
    now = _time.time()

    # Check cache
    cache_key = f"races_{athlete_id}"
    if cache_key in _races_cache:
        cached_time, cached_result = _races_cache[cache_key]
        if now - cached_time < _RACES_CACHE_TTL:
            return cached_result

    # Query races from lactate_tests table
    params = {
        "athlete_id": f"eq.{athlete_id}",
        "test_type": "eq.race",
        "order": "test_date.desc"
    }

    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/lactate_tests",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            },
            params=params
        )
        if response.status_code == 200:
            races = response.json()
            _races_cache[cache_key] = (now, races)
            return races
        else:
            print(f"Error fetching races: {response.text}")
            return []
    except Exception as e:
        print(f"Error fetching races: {e}")
        return []


def get_race_by_id(race_id: int) -> dict | None:
    """Fetch a single race by its ID."""
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/lactate_tests",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            },
            params={"id": f"eq.{race_id}"}
        )
        if response.status_code == 200:
            results = response.json()
            return results[0] if results else None
        return None
    except Exception as e:
        print(f"Error fetching race by id: {e}")
        return None


def invalidate_races_cache(athlete_id: str = None):
    """Invalidate races cache for an athlete or all athletes."""
    if athlete_id:
        cache_key = f"races_{athlete_id}"
        if cache_key in _races_cache:
            del _races_cache[cache_key]
    else:
        _races_cache.clear()


@timing_decorator
def _fetch_timeseries_raw(activity_id: str, limit: int = 300000) -> pd.DataFrame:
    """Récupère (et met en cache disque) la série temporelle d'une activité."""
    cols = "activity_id,ts_offset_ms,time,t_active_sec,heartrate,speed,enhanced_speed,velocity_smooth,cadence,watts,vertical_oscillation,enhanced_altitude,ground_contact_time,leg_spring_stiffness"
    params = {"activity_id": f"eq.{activity_id}", "order": "ts_offset_ms.asc"}
    cache_fp = os.path.join(CACHE_DIR, f"act_{activity_id}.parquet")

    # Try Parquet cache first
    if os.path.exists(cache_fp):
        try:
            df_cached = pd.read_parquet(cache_fp)
            return df_cached
        except Exception:
            # Cache corrompu → on le regénère
            try:
                os.remove(cache_fp)
            except Exception:
                pass
    
    # Fallback: try old CSV.gz cache and migrate to Parquet
    old_cache_fp = os.path.join(CACHE_DIR, f"act_{activity_id}.csv.gz")
    if os.path.exists(old_cache_fp):
        try:
            df_cached = pd.read_csv(
                old_cache_fp,
                dtype={
                    "activity_id": "string",
                    "ts_offset_ms": "float32",
                    "time": "float32",
                    "t_active_sec": "float32",
                    "heartrate": "float32",
                    "speed": "float32",
                    "enhanced_speed": "float32",
                    "velocity_smooth": "float32",
                    "cadence": "float32",
                    "watts": "float32",
                    "vertical_oscillation": "float32",
                    "leg_spring_stiffness": "float32",
                }
            )
            # Migrate to Parquet and remove old cache
            try:
                df_cached.to_parquet(cache_fp, compression="snappy", index=False)
                os.remove(old_cache_fp)
            except Exception:
                pass
            return df_cached
        except Exception:
            try:
                os.remove(old_cache_fp)
            except Exception:
                pass

    # Fetch from database - try with all columns first, fallback to core columns if some don't exist
    try:
        df = supa_select("activity", select=cols, params=params, limit=limit)
    except Exception as e:
        # If columns don't exist, try with core columns only
        print(f"Warning: Some columns don't exist, using core columns only: {e}")
        cols_core = "activity_id,ts_offset_ms,time,t_active_sec,heartrate,speed,enhanced_speed,velocity_smooth,cadence,watts,vertical_oscillation,leg_spring_stiffness"
        df = supa_select("activity", select=cols_core, params=params, limit=limit)
    
    if df.empty:
        return df

    # Dtypes compacts pour accélérer les calculs et réduire la taille disque
    for c in ("ts_offset_ms","time","t_active_sec","heartrate","speed","enhanced_speed","velocity_smooth","cadence","watts","vertical_oscillation","leg_spring_stiffness"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")
    if "activity_id" in df.columns:
        df["activity_id"] = df["activity_id"].astype("string")

    # Écrire en cache (Parquet avec Snappy compression)
    try:
        df.to_parquet(cache_fp, compression="snappy", index=False)
    except Exception:
        pass
    return df

# Memory cache for pre-computed timeseries data
_timeseries_cache = {}
_timeseries_cache_timestamp = {}
TIMESERIES_CACHE_TTL = 3600  # 1 hour TTL

def fetch_timeseries_cached(activity_id: str) -> pd.DataFrame:
    """Cache mémoire sur la série d'une activité avec colonnes pré-calculées."""
    now = time.time()

    # Check memory cache first
    if activity_id in _timeseries_cache:
        cache_time = _timeseries_cache_timestamp.get(activity_id, 0)
        if (now - cache_time) < TIMESERIES_CACHE_TTL:
            return _timeseries_cache[activity_id].copy()

    # Fetch raw data
    df = _fetch_timeseries_raw(activity_id)
    if df.empty:
        return df

    # PRE-COMPUTE commonly used columns (avoids recalculating on every render)
    # 1. Speed proxy (max of available speed columns) - VECTORIZED
    speed_cols = [c for c in ("speed", "enhanced_speed", "velocity_smooth") if c in df.columns]
    if speed_cols:
        speed_arrays = [pd.to_numeric(df[c], errors="coerce").fillna(0).values for c in speed_cols]
        df["speed_max"] = np.maximum.reduce(speed_arrays) if len(speed_arrays) > 1 else speed_arrays[0]
    else:
        df["speed_max"] = 0.0

    # 2. Pace in seconds per km (1000 / speed) - VECTORIZED
    df["pace_sec_km"] = np.where(
        df["speed_max"] > 0.1,  # Avoid division by zero, minimum ~0.1 m/s
        1000.0 / df["speed_max"],
        np.nan
    )

    # 3. Pre-smooth heartrate (most commonly displayed) - avoids smoothing on every render
    if "heartrate" in df.columns:
        hr_raw = pd.to_numeric(df["heartrate"], errors="coerce").to_numpy(dtype="float64")
        df["hr_smooth"] = _smooth_nan(hr_raw, 21)

    # 4. Pre-smooth pace - avoids smoothing on every render
    df["pace_smooth"] = _smooth_nan(df["pace_sec_km"].values.astype("float64"), 21)

    # 5. Cumulative distance in km (for distance-based X axis)
    if "t_active_sec" in df.columns:
        t_sec = pd.to_numeric(df["t_active_sec"], errors="coerce").fillna(0).values
        dt = np.diff(t_sec, prepend=0)
        dt = np.maximum(dt, 0)
        df["dist_cumsum_km"] = np.cumsum(df["speed_max"].values * dt) / 1000.0

    # Store in cache
    _timeseries_cache[activity_id] = df.copy()
    _timeseries_cache_timestamp[activity_id] = now

    return df

# Cache for zone time calculations (key: (athlete_id, start, end, selected_zones, use_temporal))
_zone_time_cache = {}
_zone_time_cache_timestamp = {}
_ZONE_TIME_CACHE_TTL = 3600  # 1 hour TTL

# Cache for daily zone time (used by monotony/strain calculation)
_daily_zone_cache = {}
_daily_zone_cache_timestamp = {}
_DAILY_ZONE_CACHE_TTL = 3600  # 1 hour TTL

# Cache for weekly monotony/strain (pre-calculated in database)
_monotony_strain_cache = {}
_monotony_strain_cache_timestamp = {}
_MONOTONY_STRAIN_CACHE_TTL = 3600  # 1 hour TTL


@timing_decorator
def fetch_weekly_zone_time_from_view(
    athlete_id: str,
    start_date: date,
    end_date: date
) -> pd.DataFrame:
    """
    Fetch pre-calculated weekly zone time from materialized view.

    This replaces the expensive calculate_zone_time_by_week() function by
    querying the weekly_zone_time materialized view in Supabase.

    Args:
        athlete_id: Athlete ID (e.g., 'i344978')
        start_date: Start date for the range
        end_date: End date for the range

    Returns DataFrame with columns:
        - week_start (date): Monday of each week
        - zone_1_minutes through zone_6_minutes
        - total_minutes
        - activity_count
    """
    # Query the materialized view with date range filter
    # Note: Supabase REST API doesn't allow duplicate keys, so we use 'and' syntax
    url = f"{SUPABASE_URL}/rest/v1/weekly_zone_time"
    params = {
        "athlete_id": f"eq.{athlete_id}",
        "week_start": f"gte.{start_date.isoformat()}",
        "order": "week_start.asc"
    }
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        if response.status_code != 200:
            print(f"[ZONE_VIEW] Error fetching weekly_zone_time: {response.status_code}", flush=True)
            return pd.DataFrame()

        data = response.json()
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)

        # Convert week_start to date and filter by end_date
        df["week_start"] = pd.to_datetime(df["week_start"]).dt.date
        df = df[df["week_start"] <= end_date]

        # Convert numeric columns from strings (Supabase returns NUMERIC as strings)
        numeric_cols = ["zone_1_minutes", "zone_2_minutes", "zone_3_minutes",
                       "zone_4_minutes", "zone_5_minutes", "zone_6_minutes",
                       "total_minutes"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        return df

    except Exception as e:
        print(f"[ZONE_VIEW] Exception fetching weekly_zone_time: {e}", flush=True)
        return pd.DataFrame()


def fetch_daily_zone_time(
    athlete_id: str,
    start_date: date,
    end_date: date
) -> pd.DataFrame:
    """
    Fetch daily zone time from activity_zone_time table.
    Groups multiple activities on the same day into daily totals.
    Uses memory cache with 1-hour TTL to avoid repeated database queries.

    Args:
        athlete_id: Athlete ID (e.g., 'i344978')
        start_date: Start date for the range
        end_date: End date for the range

    Returns DataFrame with columns:
        - activity_date (date): The date
        - zone_1_minutes through zone_6_minutes
        - total_minutes
    """
    # Check cache first
    cache_key = (athlete_id, start_date.isoformat(), end_date.isoformat())
    now = time.time()
    if cache_key in _daily_zone_cache:
        cache_time = _daily_zone_cache_timestamp.get(cache_key, 0)
        if (now - cache_time) < _DAILY_ZONE_CACHE_TTL:
            return _daily_zone_cache[cache_key].copy()

    url = f"{SUPABASE_URL}/rest/v1/activity_zone_time"
    params = {
        "select": "activity_date,zone_1_minutes,zone_2_minutes,zone_3_minutes,zone_4_minutes,zone_5_minutes,zone_6_minutes,total_zone_minutes",
        "athlete_id": f"eq.{athlete_id}",
        "activity_date": f"gte.{start_date.isoformat()}",
        "order": "activity_date.asc"
    }
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        if response.status_code != 200:
            print(f"[DAILY_ZONE] Error fetching activity_zone_time: {response.status_code}", flush=True)
            return pd.DataFrame()

        data = response.json()
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)

        # Convert activity_date to date and filter by end_date
        df["activity_date"] = pd.to_datetime(df["activity_date"]).dt.date
        df = df[df["activity_date"] <= end_date]

        # Convert numeric columns
        numeric_cols = ["zone_1_minutes", "zone_2_minutes", "zone_3_minutes",
                       "zone_4_minutes", "zone_5_minutes", "zone_6_minutes",
                       "total_zone_minutes"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # Group by date (sum multiple activities on same day)
        daily_df = df.groupby("activity_date")[numeric_cols].sum().reset_index()

        # Cache the result
        _daily_zone_cache[cache_key] = daily_df.copy()
        _daily_zone_cache_timestamp[cache_key] = now

        return daily_df

    except Exception as e:
        print(f"[DAILY_ZONE] Exception fetching activity_zone_time: {e}", flush=True)
        return pd.DataFrame()


def calculate_weekly_monotony_strain(
    daily_zone_df: pd.DataFrame,
    selected_zones: list,
    start_date: date,
    end_date: date
) -> pd.DataFrame:
    """
    Calculate Training Monotony and Strain per calendar week (Mon-Sun).

    Based on Carl Foster's model:
    - CV = std(daily_minutes) / mean(daily_minutes)
    - Monotony = 1 / CV (capped at 10.0)
    - Load = sum(daily_minutes) for the week
    - Strain = Load × Monotony

    Args:
        daily_zone_df: DataFrame from fetch_daily_zone_time()
        selected_zones: List of zone numbers (1-6) to include
        start_date: Start date for the analysis
        end_date: End date for the analysis

    Returns DataFrame with columns:
        - week_start (date): Monday of each week
        - load_min: Total training load in minutes
        - monotony: Training monotony (1/CV, capped at 10)
        - strain: Training strain (load × monotony)
    """
    if daily_zone_df.empty or not selected_zones:
        return pd.DataFrame()

    # Calculate total minutes for selected zones per day
    zone_cols = [f"zone_{z}_minutes" for z in selected_zones]
    available_cols = [c for c in zone_cols if c in daily_zone_df.columns]

    if not available_cols:
        return pd.DataFrame()

    daily_df = daily_zone_df.copy()
    daily_df["total_minutes"] = daily_df[available_cols].sum(axis=1)
    daily_df["activity_date"] = pd.to_datetime(daily_df["activity_date"])

    # Create week_start column (Monday of each week)
    daily_df["week_start"] = daily_df["activity_date"] - pd.to_timedelta(
        daily_df["activity_date"].dt.dayofweek, unit='D'
    )

    # Create full date range to include zero-training days
    full_dates = pd.date_range(start_date, end_date, freq='D')
    full_df = pd.DataFrame({"date": full_dates})
    full_df["week_start"] = full_df["date"] - pd.to_timedelta(
        full_df["date"].dt.dayofweek, unit='D'
    )

    # Merge with daily data (left join to keep all days)
    full_df = full_df.merge(
        daily_df[["activity_date", "total_minutes"]],
        left_on="date",
        right_on="activity_date",
        how="left"
    )
    full_df["total_minutes"] = full_df["total_minutes"].fillna(0)

    # Group by week and calculate metrics
    results = []
    for week_start, week_data in full_df.groupby("week_start"):
        daily_values = week_data["total_minutes"].values

        # Load = sum of daily minutes
        load_min = daily_values.sum()

        # Calculate CV and Monotony
        mean_val = daily_values.mean()
        std_val = daily_values.std(ddof=0)  # Population std

        if mean_val > 0 and std_val > 0:
            cv = std_val / mean_val
            monotony = min(10.0, 1.0 / cv)  # Cap at 10
        elif mean_val > 0 and std_val == 0:
            # All days identical (std=0) → CV=0 → monotony capped at 10
            monotony = 10.0
        else:
            # No training this week
            monotony = 0.0

        # Strain = Load × Monotony
        strain = load_min * monotony

        results.append({
            "week_start": week_start.date() if hasattr(week_start, 'date') else week_start,
            "load_min": load_min,
            "monotony": monotony,
            "strain": strain
        })

    return pd.DataFrame(results)


def fetch_weekly_monotony_strain_from_db(
    athlete_id: str,
    start_date: date,
    end_date: date,
    selected_zones: list
) -> pd.DataFrame:
    """
    Fetch pre-calculated weekly monotony/strain from the database.
    Aggregates per-zone metrics based on selected zones.
    Uses memory cache with 1-hour TTL.

    Args:
        athlete_id: Athlete ID (e.g., 'i344978')
        start_date: Start date for the range
        end_date: End date for the range
        selected_zones: List of zone numbers (1-6) to aggregate

    Returns DataFrame with columns:
        - week_start (date): Monday of each week
        - load_min: Aggregated load from selected zones
        - monotony: Aggregated monotony (weighted by load)
        - strain: Aggregated strain from selected zones
    """
    if not selected_zones:
        return pd.DataFrame()

    # Check cache first
    cache_key = (athlete_id, start_date.isoformat(), end_date.isoformat(), tuple(sorted(selected_zones)))
    now = time.time()
    if cache_key in _monotony_strain_cache:
        cache_time = _monotony_strain_cache_timestamp.get(cache_key, 0)
        if (now - cache_time) < _MONOTONY_STRAIN_CACHE_TTL:
            return _monotony_strain_cache[cache_key].copy()

    url = f"{SUPABASE_URL}/rest/v1/weekly_monotony_strain"

    # Build select columns based on selected zones
    select_cols = ["week_start"]
    for z in range(1, 7):
        select_cols.extend([
            f"zone_{z}_load_min",
            f"zone_{z}_monotony",
            f"zone_{z}_strain"
        ])
    select_cols.extend(["total_load_min", "total_monotony", "total_strain"])

    params = {
        "select": ",".join(select_cols),
        "athlete_id": f"eq.{athlete_id}",
        "week_start": f"gte.{start_date.isoformat()}",
        "order": "week_start.asc"
    }
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        if response.status_code != 200:
            print(f"[MONOTONY_STRAIN] Error fetching weekly_monotony_strain: {response.status_code}", flush=True)
            return pd.DataFrame()

        data = response.json()
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)

        # Convert week_start to date and filter by end_date
        df["week_start"] = pd.to_datetime(df["week_start"]).dt.date
        df = df[df["week_start"] <= end_date]

        if df.empty:
            return pd.DataFrame()

        # Convert numeric columns
        for col in df.columns:
            if col != "week_start":
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # Aggregate selected zones
        results = []
        for _, row in df.iterrows():
            # Sum load and strain from selected zones
            load_sum = sum(row.get(f"zone_{z}_load_min", 0) for z in selected_zones)
            strain_sum = sum(row.get(f"zone_{z}_strain", 0) for z in selected_zones)

            # Calculate weighted monotony (weighted by load per zone)
            weighted_monotony_sum = sum(
                row.get(f"zone_{z}_load_min", 0) * row.get(f"zone_{z}_monotony", 0)
                for z in selected_zones
            )
            monotony = weighted_monotony_sum / load_sum if load_sum > 0 else 0

            results.append({
                "week_start": row["week_start"],
                "load_min": load_sum,
                "monotony": monotony,
                "strain": strain_sum
            })

        result_df = pd.DataFrame(results)

        # Cache the result
        _monotony_strain_cache[cache_key] = result_df.copy()
        _monotony_strain_cache_timestamp[cache_key] = now

        return result_df

    except Exception as e:
        print(f"[MONOTONY_STRAIN] Exception fetching weekly_monotony_strain: {e}", flush=True)
        return pd.DataFrame()


@timing_decorator
def calculate_zone_time_by_week(
    athlete_id: str,
    zones_df: pd.DataFrame,
    start_date: date,
    end_date: date,
    selected_zones: list[int],
    use_temporal_zones: bool = True
) -> pd.DataFrame:
    """
    Calculate weekly time spent in selected pace zones.
    Uses memory cache to avoid recomputing for same parameters.

    TEMPORAL ZONE MATCHING (use_temporal_zones=True):
    Each activity uses the zones that were effective on that activity's date.
    This ensures sports science accuracy - you can't analyze past data with future test results.

    Args:
        athlete_id: Athlete ID
        zones_df: DataFrame from fetch_athlete_training_zones() - used for selected_zones reference
                  or as fallback when use_temporal_zones=False
        start_date: Analysis start date
        end_date: Analysis end date
        selected_zones: List of zone numbers (1-6) to calculate
        use_temporal_zones: If True, lookup zones per-activity date (default). If False, use zones_df for all.

    Returns DataFrame with columns:
    - week_start (date): Monday of each week
    - zone_N_minutes (float): Time in zone N in minutes
    """
    if not selected_zones:
        return pd.DataFrame()

    # For non-temporal mode, zones_df is required
    if not use_temporal_zones and zones_df.empty:
        return pd.DataFrame()

    import time as _time
    now = _time.time()

    # Build cache key - include use_temporal_zones flag
    # For temporal mode, don't include zone bounds in key since they vary by date
    if use_temporal_zones:
        cache_key = (athlete_id, start_date.isoformat(), end_date.isoformat(), tuple(sorted(selected_zones)), "temporal")
    else:
        zone_bounds_tuple = tuple(sorted([
            (int(row["zone_number"]), float(row["pace_min_sec_per_km"]), float(row["pace_max_sec_per_km"]))
            for _, row in zones_df.iterrows()
        ]))
        cache_key = (athlete_id, start_date.isoformat(), end_date.isoformat(), zone_bounds_tuple)

    # Check cache
    if cache_key in _zone_time_cache:
        cached_time, cached_df = _zone_time_cache[cache_key]
        if now - cached_time < _ZONE_TIME_CACHE_TTL:
            print(f"[ZONE_TIME] Cache hit for {athlete_id}", flush=True)
            return cached_df.copy()

    # 1. Get activity metadata for date range
    start_iso = start_date.isoformat()
    end_iso = end_date.isoformat()
    meta_df = fetch_metadata(start_iso, end_iso, [athlete_id])

    if meta_df.empty:
        return pd.DataFrame()

    # Filter to running activities only
    meta_df = meta_df[meta_df["type"].str.lower().isin(RUN_TYPES)]

    if meta_df.empty:
        return pd.DataFrame()

    # 2. Build zone boundaries lookup (for non-temporal mode)
    if not use_temporal_zones:
        zone_bounds = {}
        for _, row in zones_df.iterrows():
            zn = int(row["zone_number"])
            if zn in selected_zones:
                zone_bounds[zn] = (
                    float(row["pace_min_sec_per_km"]),
                    float(row["pace_max_sec_per_km"])
                )
        if not zone_bounds:
            return pd.DataFrame()

    # 3. Process activities and calculate zone times
    results = []
    # Cache for zones by effective date to avoid repeated lookups
    zones_by_effective_date = {}

    for _, act in meta_df.iterrows():
        activity_id = act["activity_id"]

        # Get activity date from start_time
        start_time = act.get("start_time")
        if pd.isna(start_time):
            continue
        act_date = pd.to_datetime(start_time).date()

        # Calculate week start (Monday)
        week_start = act_date - timedelta(days=act_date.weekday())

        # TEMPORAL ZONE MATCHING: Fetch zones effective on activity date
        if use_temporal_zones:
            # Check local cache first
            if act_date not in zones_by_effective_date:
                act_zones_df = fetch_zones_for_date(athlete_id, act_date)
                if act_zones_df.empty:
                    continue
                # Extract effective date for caching
                eff_date = act_zones_df["effective_from_date"].iloc[0]
                if isinstance(eff_date, pd.Timestamp):
                    eff_date = eff_date.date()
                # Build zone bounds for this effective date
                act_zone_bounds = {}
                for _, row in act_zones_df.iterrows():
                    zn = int(row["zone_number"])
                    if zn in selected_zones:
                        act_zone_bounds[zn] = (
                            float(row["pace_min_sec_per_km"]),
                            float(row["pace_max_sec_per_km"])
                        )
                zones_by_effective_date[act_date] = act_zone_bounds

            zone_bounds = zones_by_effective_date.get(act_date, {})
            if not zone_bounds:
                continue

        # Fetch cached timeseries (already has pace_sec_km pre-computed)
        ts_df = fetch_timeseries_cached(activity_id)

        if ts_df.empty or "pace_sec_km" not in ts_df.columns:
            continue

        # Get valid pace values
        pace = ts_df["pace_sec_km"].values
        valid_mask = np.isfinite(pace)

        if not np.any(valid_mask):
            continue

        pace_valid = pace[valid_mask]

        # Calculate time in each zone (each row = 1 second of data)
        row_result = {"week_start": week_start}
        for zn, (pace_min, pace_max) in zone_bounds.items():
            # pace_min = faster pace (lower seconds), pace_max = slower pace (higher seconds)
            zone_mask = (pace_valid >= pace_min) & (pace_valid < pace_max)
            # Store as minutes directly
            row_result[f"zone_{zn}_minutes"] = zone_mask.sum() / 60.0

        results.append(row_result)

    if not results:
        return pd.DataFrame()

    # 4. Aggregate by week (sum minutes across activities in same week)
    df = pd.DataFrame(results)
    zone_cols = [c for c in df.columns if c.startswith("zone_")]
    weekly = df.groupby("week_start")[zone_cols].sum().reset_index()

    # Store in cache
    _zone_time_cache[cache_key] = (now, weekly.copy())
    print(f"[ZONE_TIME] Cached result for {athlete_id} ({len(weekly)} weeks)", flush=True)

    return weekly

# ========== Numpy helpers ==========
def _np_max_cols(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    """Row-wise nanmax over existing columns, as float64 numpy array."""
    arrs = []
    for c in cols:
        if c in df.columns:
            arrs.append(pd.to_numeric(df[c], errors="coerce").to_numpy(dtype="float64"))
    if not arrs:
        return np.zeros(len(df), dtype="float64")
    
    # Stack arrays and compute max, handling all-NaN slices
    stacked = np.column_stack(arrs)
    with np.errstate(invalid='ignore'):  # Suppress warning for all-NaN slices
        M = np.nanmax(stacked, axis=1)
    
    # Replace any remaining NaN values with 0
    M = np.nan_to_num(M, nan=0.0)
    return M

def _smooth_nan(y: np.ndarray, win: int) -> np.ndarray:
    """Simple moving average (centered-ish) that ignores NaNs (no pandas)."""
    if win is None or win <= 1 or y.size == 0:
        return y
    k = np.ones(win, dtype="float64")
    data = y.copy().astype("float64")
    mask = np.isfinite(data).astype("float64")
    data[~np.isfinite(data)] = 0.0
    num = np.convolve(data, k, mode="same")
    den = np.convolve(mask, k, mode="same")
    den[den == 0] = 1.0
    return num / den

# ========== Conversions & formatages ==========
def _fmt_mmss(x, _=None):
    try: x = float(x)
    except: return ""
    if x < 0 or not np.isfinite(x): return ""
    m = int(x // 60); s = int(x % 60)
    return f"{m:02d}:{s:02d}"

def _create_empty_plotly_fig(msg: str, height: int = 480) -> go.Figure:
    """Create empty Plotly figure with centered message."""
    fig = go.Figure()
    fig.add_annotation(text=msg, xref="paper", yref="paper", x=0.5, y=0.5,
                       showarrow=False, font=dict(size=16, color="#666"))
    fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False),
                      plot_bgcolor="white", height=height)
    return fig

def _create_error_plotly_fig(error_msg: str, height: int = 480) -> go.Figure:
    """Create error Plotly figure with red message for debugging."""
    fig = go.Figure()
    fig.add_annotation(
        text=f"ERREUR: {error_msg[:200]}",  # Truncate long errors
        xref="paper", yref="paper", x=0.5, y=0.5,
        showarrow=False, font=dict(size=12, color="#dc2626")
    )
    fig.update_layout(
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        plot_bgcolor="#fee", height=height
    )
    return fig

# ========== Préparation XY selon choix X/Y ==========
def _prep_xy(df: pd.DataFrame, xvar: str, yvar: str, activity_type: str = "run", smooth_win: int = 21):
    """Optimized XY preparation using pre-computed columns from cache."""
    n = len(df)
    if n == 0:
        return np.array([]), np.array([]), "", "", None, None

    # Downsample step target (~1200 pts)
    step = max(1, n // 1200)

    # X AXIS - Use pre-computed columns when available
    if xvar == "moving":
        # Use t_active_sec from database (already calculated correctly)
        if "t_active_sec" in df.columns and df["t_active_sec"].notna().any():
            x_full = pd.to_numeric(df["t_active_sec"], errors="coerce").to_numpy(dtype="float64")
        else:
            # Fallback: recalculate client-side
            x_full = compute_moving_time_strava(df, activity_type=activity_type).values
        x_label = "Temps en mouvement (mm:ss)"
        x_fmt = FuncFormatter(_fmt_mmss)
    else:
        # Use pre-computed cumulative distance if available
        if "dist_cumsum_km" in df.columns:
            x_full = df["dist_cumsum_km"].values.astype("float64")
        else:
            # Fallback: calculate distance from speed
            if "ts_offset_ms" in df.columns and pd.to_numeric(df["ts_offset_ms"], errors="coerce").notna().any():
                t_raw = pd.to_numeric(df["ts_offset_ms"], errors="coerce").to_numpy(dtype="float64") / 1000.0
            else:
                t_raw = pd.to_numeric(df.get("time"), errors="coerce").to_numpy(dtype="float64")
            if t_raw.size:
                t_raw = t_raw - t_raw[0]
                t_raw = np.maximum(t_raw, 0.0)
            else:
                t_raw = np.zeros(n, dtype="float64")
            dt = np.diff(t_raw, prepend=t_raw[:1])
            dt = np.maximum(dt, 0.0)
            v = df["speed_max"].values if "speed_max" in df.columns else _np_max_cols(df, ["speed", "enhanced_speed", "velocity_smooth"])
            x_full = np.cumsum(np.nan_to_num(v) * dt) / 1000.0
        x_label = "Distance (km)"
        x_fmt = None

    # Y AXIS - Use pre-computed and pre-smoothed columns when available
    if yvar == "pace":
        # Use pre-smoothed pace if available (avoids smoothing every render)
        if "pace_smooth" in df.columns:
            y_full = df["pace_smooth"].values.astype("float64")
        elif "pace_sec_km" in df.columns:
            y_full = _smooth_nan(df["pace_sec_km"].values.astype("float64"), smooth_win)
        else:
            # Fallback: calculate from speed
            v = df["speed_max"].values if "speed_max" in df.columns else _np_max_cols(df, ["speed", "enhanced_speed", "velocity_smooth"])
            pace = 1000.0 / np.where(np.isfinite(v) & (v > 0), v, np.nan)
            y_full = _smooth_nan(pace, smooth_win)
        y_label = "Allure (min/km)"
        y_fmt = FuncFormatter(_fmt_mmss)
    elif yvar == "heartrate":
        # Use pre-smoothed heartrate if available
        if "hr_smooth" in df.columns:
            y_full = df["hr_smooth"].values.astype("float64")
        else:
            y_full = _smooth_nan(pd.to_numeric(df.get("heartrate"), errors="coerce").to_numpy(dtype="float64"), smooth_win)
        y_label = "Fréquence cardiaque"
        y_fmt = None
    elif yvar == "cadence":
        # Cadence from devices is often per leg - multiply by 2 for total (spm)
        y_full = _smooth_nan(2.0 * pd.to_numeric(df.get("cadence"), errors="coerce").to_numpy(dtype="float64"), smooth_win)
        y_label = "Cadence"
        y_fmt = None
    elif yvar == "watts":
        y_full = _smooth_nan(pd.to_numeric(df.get("watts"), errors="coerce").to_numpy(dtype="float64"), smooth_win)
        y_label = "Puissance"
        y_fmt = None
    elif yvar == "vertical_oscillation":
        y_full = _smooth_nan(pd.to_numeric(df.get("vertical_oscillation"), errors="coerce").to_numpy(dtype="float64"), smooth_win)
        y_label = "Oscillation verticale"
        y_fmt = None
    elif yvar == "altitude":
        y_full = _smooth_nan(pd.to_numeric(df.get("enhanced_altitude"), errors="coerce").to_numpy(dtype="float64"), smooth_win)
        y_label = "Altitude"
        y_fmt = None
    elif yvar == "ground_contact_time":
        y_full = _smooth_nan(pd.to_numeric(df.get("ground_contact_time"), errors="coerce").to_numpy(dtype="float64"), smooth_win)
        y_label = "Temps de contact au sol (GCT)"
        y_fmt = None
    elif yvar == "leg_spring_stiffness":
        y_full = _smooth_nan(pd.to_numeric(df.get("leg_spring_stiffness"), errors="coerce").to_numpy(dtype="float64"), smooth_win)
        y_label = "Leg Spring Stiffness (LSS)"
        y_fmt = None
    else:
        # Default to heartrate
        if "hr_smooth" in df.columns:
            y_full = df["hr_smooth"].values.astype("float64")
        else:
            y_full = _smooth_nan(pd.to_numeric(df.get("heartrate"), errors="coerce").to_numpy(dtype="float64"), smooth_win)
        y_label = "Fréquence cardiaque"
        y_fmt = None

    # Decimation only (smoothing already done)
    x = x_full[::step]
    y = y_full[::step]

    return x, y, x_label, y_label, x_fmt, y_fmt

# ========== UI ==========
today = date.today()
start_default = today - timedelta(days=7)

# Top bar: Athlète, Activité, Période, Toggle VirtualRun
top_bar = ui.div(
    ui.layout_columns(
        # Athlète (colonne ~33%)
        ui.column(4, 
            ui.div(
                ui.tags.label("Athlète", **{"class": "form-label"}),
                ui.input_select("athlete", "", choices=[], width="100%")
            )
        ),

        # Période (colonne ~50%) — grille 2 lignes, "à" à gauche de la 2e ligne
        ui.column(6, ui.div(
            ui.tags.label("Période", **{"class": "form-label"}),
            ui.div(
                ui.div("", class_="period-pad"),
                ui.div(ui.input_date("date_start", "", value=start_default, width="100%"), class_="period-start"),
                ui.div("à", class_="period-a"),
                ui.div(ui.input_date("date_end", "", value=today, width="100%"), class_="period-end"),
                class_="period-grid"
            ),
        )),

        # Toggle VirtualRun (colonne ~17%)
        ui.column(2, 
            ui.div(
                ui.tags.label("Options", **{"class": "form-label"}),
                ui.input_checkbox("incl_vrun", "Inclure course sur tapis", value=True)
            )
        ),
    ),
    class_="top-bar-container"
)

# Login Modal
login_modal = ui.modal(
    ui.div(
        ui.h3("Tableau de bord - Saint-Laurent Sélect", style="text-align: center; margin-bottom: 1.5rem; color: #D92323; font-size: 1.8rem;"),
        ui.input_password("login_password", "Mot de passe", placeholder="Entrer votre mot de passe"),
        ui.div(id="login_error", style="color: #dc3545; text-align: center; margin-top: 0.5rem; display: none; font-size: 1.05rem;"),
        ui.div(
            ui.input_action_button("login_submit", "Entrer", class_="btn btn-primary w-100", style="background: #D92323; border: none; padding: 0.85rem; font-weight: 600; margin-top: 1rem; font-size: 1.15rem;"),
            style="margin-top: 1rem;"
        ),
        ui.tags.script("""
            $(document).ready(function() {
                $('#login_password').on('keypress', function(e) {
                    if (e.which === 13) {  // Enter key
                        e.preventDefault();
                        var password = $(this).val();
                        if (password && password.length > 0) {
                            setTimeout(function() {
                                $('#login_submit').click();
                            }, 50);
                        }
                    }
                });
            });
        """),
    ),
    title=None,
    easy_close=False,
    footer=None,
    size="s"
)

# Tabs principaux
app_ui = ui.page_fluid(
    ui.tags.style("""
      /* Global styles */
      body { 
        background: #F2F2F2;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      }
      
      /* Enhanced form controls */
      .form-select, .form-control { 
        font-size: 1.2rem; 
        padding: 0.8rem 1.15rem;
        border: 2px solid #e1e8ed;
        border-radius: 8px;
        transition: all 0.3s ease;
        background: white;
      }
      .form-select:focus, .form-control:focus {
        border-color: #D9CD23;
        box-shadow: 0 0 0 3px rgba(217, 205, 35, 0.2);
        outline: none;
      }
      
      label { 
        font-size: 1.15rem; 
        margin-bottom: 0.5rem;
        font-weight: 600;
        color: #262626;
        letter-spacing: 0.3px;
      }
      
      /* Date inputs */
      input[type="date"].form-control { 
        min-width: 320px;
      }
      
      /* Survey form - hide ALL numbers on feeling-based sliders */
      .survey-form .irs-min,
      .survey-form .irs-max,
      .survey-form .irs-single,
      .survey-form .irs-from,
      .survey-form .irs-to {
        visibility: hidden !important;
        display: none !important;
      }

      /* Range selection sliders - hide numeric seconds, show formatted time instead */
      #range_start-label + .shiny-input-container .irs-min,
      #range_start-label + .shiny-input-container .irs-max,
      #range_start-label + .shiny-input-container .irs-single,
      #range_end-label + .shiny-input-container .irs-min,
      #range_end-label + .shiny-input-container .irs-max,
      #range_end-label + .shiny-input-container .irs-single,
      #range_start .irs-min,
      #range_start .irs-max,
      #range_start .irs-single,
      #range_end .irs-min,
      #range_end .irs-max,
      #range_end .irs-single,
      div[id*="range_start"] .irs-min,
      div[id*="range_start"] .irs-max,
      div[id*="range_start"] .irs-single,
      div[id*="range_end"] .irs-min,
      div[id*="range_end"] .irs-max,
      div[id*="range_end"] .irs-single {
        visibility: hidden !important;
      }

      /* Style the formatted time display */
      #range_start_display,
      #range_end_display {
        font-size: 1.1rem;
        font-weight: 600;
        color: #2563eb;
        margin-top: 0.5rem;
        padding: 0.4rem 0.8rem;
        background: #eff6ff;
        border-radius: 6px;
        display: inline-block;
      }
      
      /* Additional targeting for pseudo-elements */
      .survey-form .irs-from:before,
      .survey-form .irs-to:before,
      .survey-form .irs-single:before {
        display: none !important;
      }
      
      /* Hide slider descriptions and any form-text */
      .survey-form .slider-description,
      .survey-form .form-text {
        display: none !important;
      }
      
      /* Make sure the slider line is still visible */
      .survey-form .irs-line {
        display: block !important;
      }
      
      /* Make sure the handle is still visible */
      .survey-form .irs-handle {
        display: block !important;
      }

      /* Tooltip icon for questionnaire scales */
      .tooltip-trigger {
        display: inline-flex;
        width: 20px;
        height: 20px;
        background: #D92323;
        color: white;
        border-radius: 50%;
        font-size: 0.7rem;
        line-height: 20px;
        text-align: center;
        cursor: help;
        font-weight: bold;
        margin-left: 0.4rem;
        transition: all 0.2s ease;
        vertical-align: middle;
        justify-content: center;
        align-items: center;
      }

      .tooltip-trigger:hover {
        background: #b01a1a;
        transform: scale(1.15);
        box-shadow: 0 2px 8px rgba(217, 35, 35, 0.3);
      }

      /* Tooltip popup - positioned by JavaScript */
      .custom-tooltip {
        position: fixed;
        background: #333;
        color: white;
        padding: 0.75rem 1rem;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: normal;
        white-space: pre-wrap;
        word-wrap: break-word;
        max-width: 320px;
        min-width: 200px;
        z-index: 999999;
        line-height: 1.5;
        text-align: left;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        pointer-events: none;
        opacity: 0;
        transition: opacity 0.2s ease;
      }

      .custom-tooltip.visible {
        opacity: 1;
      }

      .custom-tooltip::after {
        content: '';
        position: absolute;
        top: 100%;
        left: 50%;
        transform: translateX(-50%);
        border: 7px solid transparent;
        border-top-color: #333;
      }

      /* Period grid */
      .period-grid { 
        display: grid; 
        grid-template-columns: 26px 1fr; 
        grid-template-rows: auto auto; 
        column-gap: 8px; 
        row-gap: 8px; 
        align-items: center; 
      }
      .period-grid .period-pad { grid-column: 1; grid-row: 1; }
      .period-grid .period-start { grid-column: 2; grid-row: 1; }
      .period-grid .period-a { 
        grid-column: 1; 
        grid-row: 2; 
        font-weight: 700; 
        padding-top: 0.5rem;
        color: #D92323;
        font-size: 1.1rem;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .period-grid .period-end { grid-column: 2; grid-row: 2; }
      
      /* Grid spacing */
      .bslib-grid { row-gap: 24px; column-gap: 24px; }
      
      /* Column dividers in top bar */
      .top-bar-container .bslib-grid > div:not(:last-child) {
        position: relative;
      }
      
      .top-bar-container .bslib-grid > div:not(:last-child)::after {
        content: '';
        position: absolute;
        right: -12px;
        top: 10%;
        height: 80%;
        width: 1px;
        background: linear-gradient(180deg, transparent 0%, rgba(217, 35, 35, 0.2) 20%, rgba(217, 35, 35, 0.2) 80%, transparent 100%);
      }
      
      /* Top bar container */
      .top-bar-container {
        background: linear-gradient(135deg, #ffffff 0%, #fafafa 100%);
        padding: 2rem;
        border-radius: 16px;
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.08), 0 2px 4px rgba(0, 0, 0, 0.04);
        margin-bottom: 1.5rem;
        border: 2px solid rgba(217, 35, 35, 0.1);
        position: relative;
        overflow: hidden;
      }
      
      .top-bar-container::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, #D92323 0%, #D9CD23 100%);
      }
      
      /* Enhanced form labels in top bar */
      .top-bar-container .form-label {
        font-size: 1.1rem;
        font-weight: 700;
        color: #D92323;
        margin-bottom: 0.75rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-size: 0.95rem;
      }
      
      /* Enhanced form controls in top bar */
      .top-bar-container .form-select,
      .top-bar-container .form-control {
        border: 2px solid #e5e7eb;
        border-radius: 10px;
        padding: 0.85rem 1.2rem;
        font-size: 1.15rem;
        transition: all 0.3s ease;
        background: white;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);
      }
      
      .top-bar-container .form-select:hover,
      .top-bar-container .form-control:hover {
        border-color: #D9CD23;
        box-shadow: 0 4px 8px rgba(217, 205, 35, 0.15);
        transform: translateY(-1px);
      }
      
      .top-bar-container .form-select:focus,
      .top-bar-container .form-control:focus {
        border-color: #D92323;
        box-shadow: 0 0 0 4px rgba(217, 35, 35, 0.15);
        transform: translateY(-1px);
      }
      
      /* Checkbox styling in top bar */
      .top-bar-container .form-check {
        background: white;
        padding: 0.75rem 1rem;
        border-radius: 10px;
        border: 2px solid #e5e7eb;
        transition: all 0.3s ease;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);
      }
      
      .top-bar-container .form-check:hover {
        border-color: #D9CD23;
        box-shadow: 0 4px 8px rgba(217, 205, 35, 0.15);
      }
      
      .top-bar-container .form-check-label {
        font-size: 1.05rem;
        font-weight: 500;
        color: #374151;
      }
      
      /* Enhanced cards - no transform to avoid stacking context issues with tooltips */
      .card {
        width: 100%;
        max-width: none;
        border: none;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.07), 0 1px 3px rgba(0, 0, 0, 0.06);
        transition: box-shadow 0.2s ease;
        background: white;
      }
      .card:hover {
        box-shadow: 0 8px 12px rgba(0, 0, 0, 0.1), 0 2px 4px rgba(0, 0, 0, 0.08);
      }
      
      .card-header {
        background: linear-gradient(135deg, #D92323 0%, #D92323 100%);
        color: white;
        font-weight: 700;
        font-size: 1.4rem;
        padding: 1.15rem 1.4rem;
        border-radius: 12px 12px 0 0 !important;
        letter-spacing: 0.3px;
        border: none;
      }

      .card-body {
        padding: 1.5rem;
      }
      
      /* Summary grid - full width */
      .summary-grid-full { 
        display: grid; 
        grid-template-columns: repeat(3, minmax(0, 1fr)); 
        gap: 20px; 
        align-items: stretch;
        margin-top: 20px;
        margin-bottom: 20px;
      }
      .summary-grid-full .card { height: 100%; }
      .summary-grid-full .shiny-plot-output { width: 100% !important; }
      
      /* Analysis unified layout */
      .analysis-unified {
        width: 100%;
      }
      
      /* Compact control labels in analysis tab */
      .analysis-unified label {
        font-size: 1.05rem;
        margin-bottom: 0.3rem;
        font-weight: 600;
      }
      
      .analysis-unified .form-select {
        font-size: 1.15rem;
        padding: 0.6rem 0.9rem;
      }
      
      /* Plot outputs */
      .shiny-plot-output { 
        width: 100% !important;
        border-radius: 8px;
      }
      .bslib-grid [class^="col-"] > * { width: 100%; }
      
      /* Header styling */
      h2 {
        background: linear-gradient(135deg, #D92323 0%, #D9CD23 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-weight: 800;
        font-size: 2.6rem;
        margin-bottom: 1.5rem;
        letter-spacing: -0.5px;
      }
      
      /* Tabs styling */
      .nav-tabs {
        border-bottom: 2px solid #e1e8ed;
        margin-bottom: 1.5rem;
      }
      .nav-tabs .nav-link {
        color: #5a6c7d;
        font-weight: 600;
        font-size: 1.1rem;
        padding: 0.85rem 1.6rem;
        border: none;
        border-radius: 8px 8px 0 0;
        transition: all 0.2s ease;
      }
      .nav-tabs .nav-link:hover {
        color: #D92323;
        background: rgba(217, 35, 35, 0.1);
      }
      .nav-tabs .nav-link.active {
        color: #D92323;
        background: white;
        border-bottom: 3px solid #D92323;
      }
      
      /* Checkbox styling */
      .form-check-input {
        width: 1.3rem;
        height: 1.3rem;
        border: 2px solid #e1e8ed;
        border-radius: 4px;
        cursor: pointer;
      }
      .form-check-input:checked {
        background-color: #D92323;
        border-color: #D92323;
      }
      .form-check-label {
        margin-left: 0.5rem;
        cursor: pointer;
        color: #262626;
        font-size: 1.15rem;
      }
      
      /* Radio buttons */
      .form-check-input[type="radio"] {
        border-radius: 50%;
      }
      
      /* Radio button labels */
      .form-check.form-check-inline label {
        font-size: 1.15rem;
      }
      
      /* Numeric inputs */
      input[type="number"].form-control {
        font-size: 1.2rem;
      }
      
      /* Action buttons */
      .btn {
        font-size: 1.15rem;
        padding: 0.7rem 1.3rem;
      }
      
      .btn-sm {
        font-size: 1.05rem;
        padding: 0.5rem 1rem;
      }

      /* Plotly text sizing */
      .plotly text {
        font-size: 13px !important;
      }

      .plotly .xtick text, .plotly .ytick text {
        font-size: 12px !important;
      }

      .plotly .gtitle {
        font-size: 16px !important;
        font-weight: 600 !important;
      }

      /* Hide leaked Plotly documentation text - comprehensive targeting */
      .plotly-notifier,
      [class*="plotly-notifier"],
      .js-plotly-plot .plotly .modebar-container ~ div:not(.svg-container):not(.legend):not(.infolayer):not(.hoverlayer) {
        display: none !important;
        visibility: hidden !important;
      }

      /* Hide any text containing Plotly parameter documentation patterns */
      /* This uses a parent selector approach for elements containing doc text */
      .shinywidgets-container > div > div:not(.js-plotly-plot):not(.plotly) {
        display: none !important;
      }

      /* Fix tooltip/popover/dropdown z-index - ensure they appear above everything */
      .tooltip, .popover, [data-bs-toggle="tooltip"], [data-bs-toggle="popover"],
      .bs-tooltip-auto, .bs-popover-auto, .tooltip-inner,
      div[role="tooltip"], .shiny-input-container .tooltip,
      .selectize-dropdown, .dropdown-menu, .bslib-popover {
        z-index: 99999 !important;
      }

      /* Specifically for validation tooltips (red circles with info) */
      .form-group .tooltip, .shiny-input-container .tooltip,
      .bslib-tooltip-wrapper, [data-bslib-tooltip],
      .bslib-tooltip-wrapper > .bslib-tooltip {
        z-index: 99999 !important;
      }

      /* Ensure all popovers render above cards (card transform creates stacking context) */
      .bslib-tooltip, .bslib-popover, [data-tippy-root],
      .tippy-box, .tippy-content, .tippy-arrow {
        z-index: 99999 !important;
      }

      /* User info and logout styling */
      .user-info-container {
        display: flex;
        align-items: center;
        gap: 1rem;
        padding: 0.5rem;
      }
      
      .user-info-container span {
        font-size: 1.3rem !important;
        font-weight: 600;
        color: #262626;
        padding: 0.6rem 1.2rem;
        background: linear-gradient(135deg, #fff 0%, #f9fafb 100%);
        border-radius: 10px;
        border: 2px solid rgba(217, 35, 35, 0.15);
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
      }
      
      .user-info-container .btn {
        font-size: 1rem !important;
        padding: 0.5rem 1rem !important;
        font-weight: 600;
        border-radius: 8px;
        transition: all 0.2s ease;
      }

      .user-info-container .btn-primary {
        background-color: #3b82f6;
        border: none !important;
        color: white;
      }

      .user-info-container .btn-primary:hover {
        background-color: #2563eb;
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
      }

      .user-info-container .btn-light {
        background-color: #f3f4f6;
        border: none !important;
        color: #374151;
      }

      .user-info-container .btn-light:hover {
        background-color: #e5e7eb;
        transform: translateY(-1px);
      }

      .user-info-container .btn:focus {
        outline: none !important;
        box-shadow: none !important;
      }
      
      /* Responsive design - Progressive stacking for better readability */
      @media (max-width: 1400px) {
        .summary-grid-full { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      }

      @media (max-width: 992px) {
        .summary-grid-full { grid-template-columns: 1fr; }
        .bslib-grid .col-4 { grid-column: span 12 !important; }
        .bslib-grid .col-6 { grid-column: span 12 !important; }
        h2 { font-size: 2.1rem; }
      }

      @media (max-width: 768px) {
        .summary-grid-full { grid-template-columns: 1fr; }
        h2 { font-size: 1.8rem; }

        /* === MOBILE TAB RESTRICTION === */
        /* Hide desktop-only tab buttons */
        #tabs .nav-tabs .nav-item:has([data-value="Résumé de période"]),
        #tabs .nav-tabs .nav-item:has([data-value="Analyse de séance"]),
        #tabs .nav-tabs .nav-item:has([data-value="Comparaison de séances"]) {
          display: none !important;
        }

        /* Fallback for browsers without :has() support */
        .nav-link[data-value="Résumé de période"],
        .nav-link[data-value="Analyse de séance"],
        .nav-link[data-value="Comparaison de séances"] {
          display: none !important;
        }

        /* Hide content panels for hidden tabs */
        .tab-pane[data-value="Résumé de période"],
        .tab-pane[data-value="Analyse de séance"],
        .tab-pane[data-value="Comparaison de séances"] {
          display: none !important;
        }
      }
      
      /* Animations */
      @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
      }
      .card {
        animation: fadeIn 0.4s ease-out;
      }

      /* Hide Plotly internal documentation text that sometimes leaks through */
      .plotly-notifier,
      .plotly .plotly-notifier,
      [class*="plotly"] .modebar-container ~ div:not(.plot-container):not(.main-svg),
      .js-plotly-plot .plotly .user-select-none.svg-container ~ div:not(.modebar-container) {
        display: none !important;
      }

      /* Hide any spurious text rendered outside of plot containers */
      .shinywidgets-container > :not(div):not(script) {
        display: none !important;
      }

      /* Hide leaked Plotly documentation text - target specific text patterns */
      /* This targets text nodes that appear as siblings to plotly containers */
      .widget-container > .widget-subarea ~ :not(.widget-subarea) {
        display: none !important;
      }

      /* === PLOTLY RESPONSIVENESS FIX FOR SHINYAPPS.IO === */
      /* Ensure shinywidgets containers expand to full width */
      .shinywidgets-container,
      .widget-container,
      .widget-subarea,
      .jupyter-widgets {
        width: 100% !important;
        max-width: 100% !important;
      }

      /* Make Plotly figures fill their containers */
      .js-plotly-plot,
      .plotly,
      .plot-container {
        width: 100% !important;
      }

      /* Ensure the main SVG container is responsive */
      .js-plotly-plot .plotly .main-svg {
        width: 100% !important;
      }

      /* Fix for card-body containing Plotly figures */
      .card-body > div:has(.js-plotly-plot) {
        width: 100% !important;
      }

      /* Ensure output_widget renders at full width */
      [id*="_heatmap"],
      [id*="_trend"],
      [id*="_plot"],
      [id*="_scatter"],
      [id*="_volume"],
      [id*="comparison_plot"],
      [id*="zone_time"],
      [id*="pie_types"] {
        width: 100% !important;
        min-width: 100% !important;
      }

      /* Force Plotly to recalculate on container resize */
      .card .plotly-graph-div {
        width: 100% !important;
      }
    """),
    # Custom tooltip JavaScript - positions tooltips above triggers using fixed positioning
    ui.tags.script("""
        $(document).ready(function() {
            // Create tooltip element once
            var $tooltip = $('<div class="custom-tooltip"></div>').appendTo('body');

            // Handle tooltip show on hover
            $(document).on('mouseenter', '.tooltip-trigger', function(e) {
                var text = $(this).data('tooltip');
                if (!text) return;

                $tooltip.text(text);

                // Get trigger position
                var rect = this.getBoundingClientRect();
                var tooltipWidth = $tooltip.outerWidth();
                var tooltipHeight = $tooltip.outerHeight();

                // Position above the trigger, centered
                var left = rect.left + (rect.width / 2) - (tooltipWidth / 2);
                var top = rect.top - tooltipHeight - 10;

                // Keep within viewport
                if (left < 10) left = 10;
                if (left + tooltipWidth > window.innerWidth - 10) {
                    left = window.innerWidth - tooltipWidth - 10;
                }
                if (top < 10) top = rect.bottom + 10; // Show below if no room above

                $tooltip.css({
                    left: left + 'px',
                    top: top + 'px'
                }).addClass('visible');
            });

            // Handle tooltip hide
            $(document).on('mouseleave', '.tooltip-trigger', function() {
                $tooltip.removeClass('visible');
            });
        });
    """),
    # Load flatpickr CSS
    ui.tags.link(rel="stylesheet", href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css"),
    # Load Font Awesome for icons
    ui.tags.link(rel="stylesheet", href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css"),
    # Load flatpickr JS
    ui.tags.script(src="https://cdn.jsdelivr.net/npm/flatpickr"),
    # Load flatpickr French locale
    ui.tags.script(src="https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/fr.js"),
    ui.tags.script("""
        // Global variables for data date range (will be set by Shiny)
        window.dataMinDate = null;
        window.dataMaxDate = null;

        // Initialize flatpickr for all date inputs with French locale and date restrictions
        function initializeFrenchDatePickers() {
            if (typeof flatpickr === 'undefined') {
                setTimeout(initializeFrenchDatePickers, 100);
                return;
            }

            // Configure flatpickr for all date inputs
            $('input[type="date"]').each(function() {
                // Check if already initialized
                if (this._flatpickr) {
                    this._flatpickr.destroy();
                }

                // Get the current value
                var currentValue = $(this).val();

                // Build flatpickr config with date restrictions
                var config = {
                    locale: 'fr',
                    dateFormat: 'Y-m-d',
                    defaultDate: currentValue || null,
                    allowInput: true,
                    onChange: function(selectedDates, dateStr, instance) {
                        // Trigger Shiny input change
                        $(instance.input).trigger('change');
                    }
                };

                // Add min/max date restrictions if available
                if (window.dataMinDate) {
                    config.minDate = window.dataMinDate;
                }
                if (window.dataMaxDate) {
                    config.maxDate = window.dataMaxDate;
                }

                // Initialize flatpickr with config
                flatpickr(this, config);
            });
        }

        $(document).ready(function() {
            // Wait for Shiny to initialize
            $(document).on('shiny:connected', function() {
                initializeFrenchDatePickers();
            });

            // Re-initialize for any dynamically created date inputs
            var observer = new MutationObserver(function(mutations) {
                mutations.forEach(function(mutation) {
                    if (mutation.addedNodes.length) {
                        mutation.addedNodes.forEach(function(node) {
                            if (node.nodeType === 1) {
                                var dateInputs = $(node).find('input[type="date"]').addBack('input[type="date"]');
                                if (dateInputs.length > 0) {
                                    setTimeout(initializeFrenchDatePickers, 100);
                                }
                            }
                        });
                    }
                });
            });

            observer.observe(document.body, {
                childList: true,
                subtree: true
            });

            // Hide leaked Plotly documentation text
            function hideLeakedPlotlyText() {
                // Find and hide text nodes containing Plotly parameter documentation
                var walker = document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_TEXT,
                    null,
                    false
                );
                while(walker.nextNode()) {
                    var text = walker.currentNode.textContent.trim();
                    // Only match very specific Plotly documentation patterns (avoid false positives)
                    var isPlotlyDocs = (
                        (text.includes('rangemode') && text.includes('tozero')) ||
                        (text.includes('extrema of the input data') && text.includes('range')) ||
                        (text.includes('extends to 0, regardless') && text.includes('input data')) ||
                        (text.includes('Applies only to linear axes') && text.includes('scaleanchor'))
                    );

                    if (isPlotlyDocs && text.length > 50) {  // Only long doc strings
                        var parent = walker.currentNode.parentNode;
                        // Only hide the immediate parent, don't walk up the tree
                        if (parent && parent.style && !parent.classList.contains('js-plotly-plot') &&
                            !parent.classList.contains('plotly') && !parent.classList.contains('svg-container')) {
                            parent.style.display = 'none';
                            parent.style.visibility = 'hidden';
                        }
                    }
                }
            }

            // Run on load and periodically (less aggressive)
            setTimeout(hideLeakedPlotlyText, 2000);
            setTimeout(hideLeakedPlotlyText, 5000);

            // === PLOTLY RESPONSIVE FIX FOR SHINYAPPS.IO ===
            // Force Plotly charts to resize to container width
            function resizePlotlyCharts() {
                var plots = document.querySelectorAll('.js-plotly-plot');
                plots.forEach(function(plot) {
                    if (plot && typeof Plotly !== 'undefined') {
                        try {
                            Plotly.Plots.resize(plot);
                        } catch(e) {
                            // Ignore resize errors
                        }
                    }
                });
            }

            // Trigger resize on load and after a delay
            setTimeout(resizePlotlyCharts, 500);
            setTimeout(resizePlotlyCharts, 1500);
            setTimeout(resizePlotlyCharts, 3000);

            // Resize on window resize
            var resizeTimer;
            window.addEventListener('resize', function() {
                clearTimeout(resizeTimer);
                resizeTimer = setTimeout(resizePlotlyCharts, 250);
            });

            // Also resize when Shiny outputs update
            $(document).on('shiny:value', function(event) {
                setTimeout(resizePlotlyCharts, 100);
            });

            // Resize when tabs change (for hidden plots)
            $(document).on('shown.bs.tab', function(e) {
                setTimeout(resizePlotlyCharts, 100);
            });

            // === MOBILE TAB RESTRICTION ===
            (function() {
                var MOBILE_BREAKPOINT = 768;
                var ALLOWED_TABS = ['Questionnaires', 'Entrée de données manuelle'];
                var DEFAULT_TAB = 'Questionnaires';

                function isMobile() {
                    return window.innerWidth < MOBILE_BREAKPOINT;
                }

                function getCurrentTab() {
                    var active = document.querySelector('#tabs .nav-link.active');
                    return active ? active.getAttribute('data-value') : null;
                }

                function switchToDefault() {
                    var tab = document.querySelector('#tabs .nav-link[data-value="' + DEFAULT_TAB + '"]');
                    if (tab && !tab.classList.contains('active')) tab.click();
                }

                function enforce() {
                    if (!isMobile()) return;
                    var current = getCurrentTab();
                    if (current && ALLOWED_TABS.indexOf(current) === -1) {
                        switchToDefault();
                    }
                }

                // On Shiny connect
                $(document).on('shiny:connected', function() {
                    setTimeout(enforce, 100);
                });

                // On window resize
                var mobileTimer;
                window.addEventListener('resize', function() {
                    clearTimeout(mobileTimer);
                    mobileTimer = setTimeout(enforce, 250);
                });

                // Block navigation to hidden tabs
                $(document).on('show.bs.tab', function(e) {
                    if (!isMobile()) return;
                    var target = e.target.getAttribute('data-value');
                    if (ALLOWED_TABS.indexOf(target) === -1) {
                        e.preventDefault();
                        switchToDefault();
                    }
                });
            })();
        });
    """),
    # Main dashboard content (conditionally shown after authentication)
    ui.output_ui("dashboard_content")
)

# ========== HELPER FUNCTIONS FOR UI ==========
def scale_with_tooltip(label_text, input_element, tooltip_text=""):
    """
    Creates a scale input with an optional informational tooltip icon.

    Args:
        label_text: The label text for the scale
        input_element: The Shiny input element (slider, radio buttons, etc.)
        tooltip_text: The text to display in the tooltip on hover. If empty, no tooltip icon is shown.

    Returns:
        A ui.div containing the label (with optional tooltip icon) and the input element
    """
    # Only show the red triangle if there's tooltip text to display
    label_children = [label_text]
    if tooltip_text:
        label_children.append(
            ui.tags.span(
                "▲",
                **{"class": "tooltip-trigger", "data-tooltip": tooltip_text}
            )
        )

    return ui.div(
        ui.tags.label(
            *label_children,
            style="font-weight: 600; margin-bottom: 0.5rem; display: inline-flex; align-items: center;"
        ),
        input_element,
        style="margin-bottom: 1.25rem;"
    )

# Dashboard content (to be rendered after authentication)
def dashboard_content_ui():
    return ui.div(
        ui.div(
            ui.layout_columns(
                ui.h2("Dashboard - Saint-Laurent Sélect", style="margin: 0;"),
                ui.div(
                    ui.output_ui("user_info_display"),
                    ui.input_action_button("refresh_data_btn", "Sync", class_="btn btn-primary", style="font-weight: 600; font-size: 1rem; padding: 0.4rem 0.8rem;"),
                    ui.output_ui("refresh_status_display"),
                    ui.input_action_button("logout_btn", "Logout", class_="btn btn-light", style="font-weight: 600; font-size: 1rem; padding: 0.4rem 0.8rem; border: 1px solid #d1d5db; outline: none; box-shadow: none;"),
                    class_="user-info-container",
                    style="text-align: right; justify-content: flex-end; gap: 0.5rem; display: flex; align-items: center;"
                ),
                col_widths=[8, 4]
            ),
            style="padding: 1.5rem 0;"
        ),

    top_bar,
    ui.br(),
    ui.navset_tab(
        ui.nav_panel("Résumé de période",
            # Trend card with integrated controls - full width
            ui.card(
                ui.card_header("Tendance course — moyenne mobile exponentielle"),
                ui.div(
                    ui.layout_columns(
                        ui.input_radio_buttons(
                            "run_metric",
                            "Base de calcul",
                            {
                                "time": "Temps de course (minutes)",
                                "dist": "Distance (km)",
                            },
                            selected="time",
                            inline=True
                        ),
                        ui.input_numeric(
                            "ctl_days",
                            "CTL - Mésocycle (jours)",
                            value=28,
                            min=7,
                            max=90,
                            width="180px"
                        ),
                        ui.input_numeric(
                            "atl_days",
                            "ATL - Microcycle (jours)",
                            value=7,
                            min=1,
                            max=30,
                            width="180px"
                        ),
                        col_widths=[4, 4, 4],
                    ),
                    ui.div(ui.output_ui("run_duration_trend"), style="margin-top: 1rem;"),
                    # Zone time longitudinal graph - same section, shares CTL/ATL controls
                    ui.div(
                        ui.tags.label("Zones d'allure", style="font-weight: 600; color: #374151; margin-top: 1.5rem; margin-bottom: 0.5rem; display: block;"),
                        ui.output_ui("zone_time_checkboxes"),
                        ui.div(
                            ui.input_radio_buttons(
                                "zone_display_mode",
                                "",
                                choices={"distinct": "Distinct", "merge": "Fusionner"},
                                selected="distinct",
                                inline=True
                            ),
                            ui.input_checkbox(
                                "show_acl_atl",
                                "ACL - ATL",
                                value=False
                            ),
                            ui.input_checkbox(
                                "show_monotony",
                                "Monotonie",
                                value=False
                            ),
                            ui.input_checkbox(
                                "show_strain",
                                "Strain",
                                value=False
                            ),
                            style="margin-top: 0.5rem; display: flex; align-items: center; gap: 1.5rem;"
                        ),
                        style="margin-top: 1rem;"
                    ),
                    # Race marker controls
                    ui.div(
                        ui.tags.label("Marqueur de course", style="font-weight: 600; color: #374151; margin-top: 1.5rem; margin-bottom: 0.5rem; display: block;"),
                        ui.div(
                            ui.output_ui("race_selector_dropdown"),
                            ui.input_checkbox(
                                "show_simulated_race",
                                "Simuler une date alternative",
                                value=False
                            ),
                            ui.output_ui("simulated_race_date_input"),
                            style="display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;"
                        ),
                        style="margin-top: 0.5rem; padding: 0.75rem; background: #fef3c7; border-radius: 8px; border: 1px solid #f59e0b;"
                    ),
                    ui.output_ui("zone_change_banner"),
                    ui.div(ui.output_ui("zone_time_longitudinal"), style="margin-top: 1rem;"),
                    class_="analysis-unified"
                ),
            ),
            # Pace zone analysis - right under Tendance course (uses shared date range)
            ui.card(
                ui.card_header("Analyse des zones d'allure"),
                ui.output_ui("pace_zone_analysis"),
            ),
            # Three graphs in grid - full width
            ui.div({"class": "summary-grid-full"},
                ui.card(
                    ui.card_header("Repartition des types (temps total)"),
                    ui.output_ui("pie_types"),
                ),
                ui.card(
                    ui.card_header("Allure vs Frequence cardiaque — par mois"),
                    ui.input_checkbox("show_pace_hr_dots", "Afficher les points", value=True),
                    ui.output_ui("pace_hr_scatter"),
                ),
                ui.card(
                    ui.card_header("Volume hebdomadaire"),
                    ui.output_ui("weekly_volume"),
                ),
            ),
        ),
        ui.nav_panel("Analyse de séance",
            ui.card(
                ui.card_header("Analyse X/Y dynamique"),
                ui.div(
                    # Top controls row: Activity selector + X/Y axis selectors
                    ui.layout_columns(
                        ui.input_select("activity_sel", "Activité", choices=[], width="100%"),
                        ui.input_select(
                            "xvar", "Axe X",
                            choices={"Temps en mouvement": "Temps", "Distance (km)": "Distance"},
                            selected="moving", width="100%"
                        ),
                        ui.input_select(
                            "yvar", "Axe Y (Principal)",
                            choices={
                                "Fréquence cardiaque": "Fréquence cardiaque",
                                "Cadence": "Cadence",
                                "Allure (min/km)": "Allure (min/km)"
                            },
                            selected="Fréquence cardiaque", width="100%"
                        ),
                        ui.input_select(
                            "yvar2", "Axe Y (Secondaire)",
                            choices={
                                "Aucun": "Aucun",
                                "Fréquence cardiaque": "Fréquence cardiaque",
                                "Cadence": "Cadence",
                                "Allure (min/km)": "Allure (min/km)"
                            },
                            selected="none", width="100%"
                        ),
                        col_widths=[4, 2, 3, 3]
                    ),
                    # Plot
                    ui.div(ui.output_ui("plot_xy"), style="margin-top: 1rem;"),
                    
                    # Range selection controls
                    ui.div(
                        ui.output_ui("range_selector_ui"),
                        style="margin-top: 1rem;"
                    ),
                    
                    # Summary statistics card
                    ui.div(
                        ui.output_ui("zoom_summary_card"),
                        style="margin-top: 0.5rem;"
                    ),
                    class_="analysis-unified"
                ),
            )
        ),
        
        # New tab: Workout Comparison
        ui.nav_panel("Comparaison de séances",
                ui.card(
                    ui.card_header("Comparaison de deux séances"),
                    ui.div(
                        # Comparison mode toggle
                        ui.input_switch("comparison_enabled", "Activer la comparaison", value=False),
                        
                        # Activity selection row
                        ui.layout_columns(
                            # Activity 1
                            ui.div(
                                ui.input_select(
                                    "comp_activity_1",
                                    "Activité 1",
                                    choices={},
                                    width="100%"
                                ),
                                style="padding: 1rem; background: #fef2f2; border-radius: 10px; border: 2px solid rgba(217, 35, 35, 0.2);"
                            ),
                            # Activity 2
                            ui.panel_conditional(
                                "input.comparison_enabled",
                                ui.div(
                                    ui.input_select(
                                        "comp_activity_2",
                                        "Activité 2",
                                        choices={},
                                        width="100%"
                                    ),
                                    style="padding: 1rem; background: #fff5f5; border-radius: 10px; border: 2px solid rgba(255, 107, 107, 0.2);"
                                )
                            ),
                            col_widths=[6, 6]
                        ),
                        
                        # Cropping controls (collapsible)
                        ui.panel_conditional(
                            "input.comparison_enabled",
                            ui.div(
                                ui.tags.h4("Découpage des séances", style="color: #D92323; margin-top: 1.5rem;"),
                                ui.layout_columns(
                                    # Crop controls for Activity 1
                                    ui.output_ui("crop_controls_1"),
                                    # Crop controls for Activity 2
                                    ui.output_ui("crop_controls_2"),
                                    col_widths=[6, 6]
                                ),
                                style="margin-top: 1rem;"
                            )
                        ),
                        
                        # Axis selection (shared)
                        ui.div(
                            ui.tags.h4("Axes de comparaison", style="color: #D92323; margin-top: 1.5rem;"),
                            ui.layout_columns(
                                ui.input_select("comp_xvar", "Axe X", 
                                    choices={"moving": "Temps en mouvement", "dist": "Distance"},
                                    selected="moving", width="100%"),
                                ui.input_select("comp_yvar", "Axe Y (Principal)",
                                    choices={
                                        "Fréquence cardiaque": "Fréquence cardiaque",
                                        "Cadence": "Cadence",
                                        "Allure (min/km)": "Allure (min/km)",
                                        "Altitude": "Altitude"
                                    },
                                    selected="Fréquence cardiaque", width="100%"),
                                ui.input_select("comp_yvar2", "Axe Y (Secondaire)",
                                    choices={
                                        "none": "Aucun",
                                        "Fréquence cardiaque": "Fréquence cardiaque",
                                        "Cadence": "Cadence",
                                        "Allure (min/km)": "Allure (min/km)"
                                    },
                                    selected="none", width="100%"),
                                col_widths=[4, 4, 4]
                            ),
                            style="margin-top: 1rem;"
                        ),
                        
                        # Comparison graph
                        ui.div(
                            ui.output_ui("comparison_plot"),
                            style="margin-top: 1.5rem;"
                        ),
                        
                        # Comparison statistics card
                        ui.div(
                            ui.output_ui("comparison_stats_card"),
                            style="margin-top: 1.5rem;"
                        ),
                        
                        class_="analysis-unified"
                    )
                )
        ),
        
# Questionnaire Tab - Daily & Weekly Surveys (Manager's Specifications)
        ui.nav_panel("Questionnaires",
            ui.navset_pill(
                # ============================================================
                # DAILY POST-WORKOUT QUESTIONNAIRE (≤45 seconds)
                # ============================================================
                ui.nav_panel("Questionnaire Journalier",
                    ui.card(
                        ui.card_header("Questionnaire Post-Entraînement"),
                        ui.div(
                            {"class": "survey-form", "style": "width: 100%; padding: 2rem;"},

                            # Activity selector + already filled notice
                            ui.div(
                                ui.tags.h5("Sélectionner l'entraînement", style="color: #D92323; margin-bottom: 0.75rem;"),
                                ui.output_ui("daily_activity_selector"),
                                ui.output_ui("daily_already_filled_notice"),
                                style="margin-bottom: 2rem; padding: 1.25rem; background: #fef2f2; border-radius: 8px; border-left: 4px solid #D92323;"
                            ),

                            # S2: Effort perçu et atteinte des objectifs
                            ui.div(
                                ui.tags.h4("Effort et Objectifs", style="color: #D92323; margin-bottom: 0.75rem; border-bottom: 2px solid #D92323; padding-bottom: 0.5rem;"),

                                scale_with_tooltip(
                                    "RPE - Perception de l'effort (CR10)",
                                    ui.input_slider("daily_rpe_cr10", "", min=0, max=10, value=5, step=1, width="100%"),
                                    "0 = Rien du tout\n1 = Très, très léger (juste perceptible)\n2 = Très léger\n3 = Léger\n4 = Modéré\n5 = Fort\n6 = Plus fort\n7 = Très fort (intense)\n8 = \n9 = Très, très fort (presque max)\n10 = Maximal"
                                ),

                                scale_with_tooltip(
                                    "Atteinte des objectifs",
                                    ui.input_slider("daily_atteinte_obj", "", min=0, max=10, value=7, step=1, width="100%"),
                                    ""  # Placeholder - description to be added later
                                ),

                                style="margin-bottom: 1.5rem; padding: 1.25rem; background: #f9f9f9; border-radius: 8px;"
                            ),

                            # S3: Douleur/Inconfort
                            ui.div(
                                ui.tags.h4("Douleur / Inconfort", style="color: #D92323; margin-bottom: 0.75rem; border-bottom: 2px solid #D92323; padding-bottom: 0.5rem;"),

                                ui.div(
                                    ui.tags.label("Avez-vous ressenti un inconfort ou douleur durant la séance ?", style="font-weight: 600; margin-bottom: 0.5rem; display: block;"),
                                    ui.input_radio_buttons("daily_douleur_oui", "", choices=["Non", "Oui"], selected="Non", inline=True),
                                    style="margin-bottom: 1rem;"
                                ),

                                ui.panel_conditional(
                                    "input.daily_douleur_oui === 'Oui'",
                                    ui.div(
                                        # Dual body picker (front + back)
                                        ui.tags.label("Zones de douleur (cliquez pour selectionner, plusieurs zones possibles)", style="font-weight: 600; margin-bottom: 0.5rem; display: block;"),
                                        ui.HTML('''
                                            <div id="daily-body-picker" style="display: flex; gap: 1.5rem; justify-content: center; flex-wrap: wrap; margin-bottom: 1rem;">
                                                <style>
                                                    .daily-bp { fill: #e5e7eb; stroke: #9ca3af; stroke-width: 1; cursor: pointer; transition: all 0.2s; }
                                                    .daily-bp:hover { fill: #d1d5db; stroke: #6b7280; }
                                                    .daily-bp.bp-selected { stroke-width: 2.5; }
                                                    .daily-bp.sev-1 { fill: #86efac; stroke: #22c55e; }
                                                    .daily-bp.sev-2 { fill: #fde047; stroke: #eab308; }
                                                    .daily-bp.sev-3 { fill: #fca5a5; stroke: #ef4444; }
                                                    #daily-selected-list { margin-top: 0.5rem; }
                                                    .daily-sel-item { display: inline-flex; align-items: center; gap: 0.3rem; background: #f3f4f6; border: 1px solid #d1d5db; border-radius: 20px; padding: 0.25rem 0.75rem; margin: 0.25rem; font-size: 0.85rem; }
                                                    .daily-sel-item .remove-btn { cursor: pointer; color: #ef4444; font-weight: bold; margin-left: 0.25rem; }
                                                    .daily-sel-item select { border: none; background: transparent; font-size: 0.8rem; padding: 0; }
                                                </style>
                                                <!-- FRONT VIEW -->
                                                <div data-view="front" style="text-align: center;">
                                                    <div style="font-size: 0.85rem; font-weight: 600; margin-bottom: 0.3rem; color: #555;">Vue avant</div>
                                                    <svg viewBox="0 0 200 400" width="160" height="320" style="max-width: 100%;">
                                                        <ellipse class="daily-bp" data-part="head" cx="100" cy="30" rx="25" ry="28"/>
                                                        <rect class="daily-bp" data-part="neck" x="90" y="58" width="20" height="15" rx="3"/>
                                                        <ellipse class="daily-bp" data-part="left_shoulder" cx="60" cy="85" rx="18" ry="12"/>
                                                        <ellipse class="daily-bp" data-part="right_shoulder" cx="140" cy="85" rx="18" ry="12"/>
                                                        <rect class="daily-bp" data-part="left_arm" x="35" y="95" width="18" height="55" rx="8"/>
                                                        <rect class="daily-bp" data-part="right_arm" x="147" y="95" width="18" height="55" rx="8"/>
                                                        <rect class="daily-bp" data-part="chest" x="70" y="75" width="60" height="45" rx="5"/>
                                                        <rect class="daily-bp" data-part="abdomen" x="75" y="120" width="50" height="35" rx="3"/>
                                                        <ellipse class="daily-bp" data-part="left_hip" cx="75" cy="165" rx="20" ry="15"/>
                                                        <ellipse class="daily-bp" data-part="right_hip" cx="125" cy="165" rx="20" ry="15"/>
                                                        <rect class="daily-bp" data-part="left_quad" x="60" y="178" width="28" height="60" rx="10"/>
                                                        <rect class="daily-bp" data-part="right_quad" x="112" y="178" width="28" height="60" rx="10"/>
                                                        <ellipse class="daily-bp" data-part="left_knee" cx="74" cy="248" rx="14" ry="12"/>
                                                        <ellipse class="daily-bp" data-part="right_knee" cx="126" cy="248" rx="14" ry="12"/>
                                                        <rect class="daily-bp" data-part="left_shin" x="65" y="260" width="18" height="55" rx="6"/>
                                                        <rect class="daily-bp" data-part="right_shin" x="117" y="260" width="18" height="55" rx="6"/>
                                                        <ellipse class="daily-bp" data-part="left_ankle" cx="74" cy="322" rx="10" ry="8"/>
                                                        <ellipse class="daily-bp" data-part="right_ankle" cx="126" cy="322" rx="10" ry="8"/>
                                                        <ellipse class="daily-bp" data-part="left_foot" cx="74" cy="345" rx="14" ry="20"/>
                                                        <ellipse class="daily-bp" data-part="right_foot" cx="126" cy="345" rx="14" ry="20"/>
                                                    </svg>
                                                </div>
                                                <!-- BACK VIEW -->
                                                <div data-view="back" style="text-align: center;">
                                                    <div style="font-size: 0.85rem; font-weight: 600; margin-bottom: 0.3rem; color: #555;">Vue arriere</div>
                                                    <svg viewBox="0 0 200 400" width="160" height="320" style="max-width: 100%;">
                                                        <ellipse class="daily-bp" data-part="head" cx="100" cy="30" rx="25" ry="28"/>
                                                        <rect class="daily-bp" data-part="neck" x="90" y="58" width="20" height="15" rx="3"/>
                                                        <ellipse class="daily-bp" data-part="left_shoulder" cx="60" cy="85" rx="18" ry="12"/>
                                                        <ellipse class="daily-bp" data-part="right_shoulder" cx="140" cy="85" rx="18" ry="12"/>
                                                        <rect class="daily-bp" data-part="left_arm" x="35" y="95" width="18" height="55" rx="8"/>
                                                        <rect class="daily-bp" data-part="right_arm" x="147" y="95" width="18" height="55" rx="8"/>
                                                        <rect class="daily-bp" data-part="upper_back" x="70" y="75" width="60" height="45" rx="5"/>
                                                        <rect class="daily-bp" data-part="lower_back" x="75" y="120" width="50" height="35" rx="3"/>
                                                        <ellipse class="daily-bp" data-part="left_glute" cx="75" cy="165" rx="20" ry="15"/>
                                                        <ellipse class="daily-bp" data-part="right_glute" cx="125" cy="165" rx="20" ry="15"/>
                                                        <rect class="daily-bp" data-part="left_hamstring" x="60" y="178" width="28" height="60" rx="10"/>
                                                        <rect class="daily-bp" data-part="right_hamstring" x="112" y="178" width="28" height="60" rx="10"/>
                                                        <ellipse class="daily-bp" data-part="left_knee" cx="74" cy="248" rx="14" ry="12"/>
                                                        <ellipse class="daily-bp" data-part="right_knee" cx="126" cy="248" rx="14" ry="12"/>
                                                        <rect class="daily-bp" data-part="left_calf" x="65" y="260" width="18" height="55" rx="6"/>
                                                        <rect class="daily-bp" data-part="right_calf" x="117" y="260" width="18" height="55" rx="6"/>
                                                        <ellipse class="daily-bp" data-part="left_ankle" cx="74" cy="322" rx="10" ry="8"/>
                                                        <ellipse class="daily-bp" data-part="right_ankle" cx="126" cy="322" rx="10" ry="8"/>
                                                        <ellipse class="daily-bp" data-part="left_foot" cx="74" cy="345" rx="14" ry="20"/>
                                                        <ellipse class="daily-bp" data-part="right_foot" cx="126" cy="345" rx="14" ry="20"/>
                                                    </svg>
                                                </div>
                                            </div>
                                            <!-- Selected parts list -->
                                            <div id="daily-selected-list"></div>
                                        '''),
                                        ui.tags.script("""
                                            (function() {
                                                if (window._dailyBPInitialized) return;
                                                window._dailyBPInitialized = true;

                                                const LABELS = {
                                                    head:"Tete",neck:"Cou",left_shoulder:"Epaule G",right_shoulder:"Epaule D",
                                                    left_arm:"Bras G",right_arm:"Bras D",chest:"Poitrine",abdomen:"Abdomen",
                                                    upper_back:"Haut du dos",lower_back:"Bas du dos",
                                                    left_hip:"Hanche G",right_hip:"Hanche D",
                                                    left_quad:"Quadriceps G",right_quad:"Quadriceps D",
                                                    left_hamstring:"Ischio-jambier G",right_hamstring:"Ischio-jambier D",
                                                    left_glute:"Fessier G",right_glute:"Fessier D",
                                                    left_knee:"Genou G",right_knee:"Genou D",
                                                    left_shin:"Tibia G",right_shin:"Tibia D",
                                                    left_calf:"Mollet G",right_calf:"Mollet D",
                                                    left_ankle:"Cheville G",right_ankle:"Cheville D",
                                                    left_foot:"Pied G",right_foot:"Pied D"
                                                };
                                                var selections = {};

                                                function render() {
                                                    document.querySelectorAll('.daily-bp').forEach(function(el) {
                                                        var partId = el.dataset.part;
                                                        var viewEl = el.closest('[data-view]');
                                                        var view = viewEl ? viewEl.dataset.view : 'front';
                                                        var key = view + ':' + partId;
                                                        el.classList.remove('bp-selected','sev-1','sev-2','sev-3');
                                                        if (selections[key]) {
                                                            el.classList.add('bp-selected','sev-'+selections[key].severity);
                                                        }
                                                    });
                                                    var listEl = document.getElementById('daily-selected-list');
                                                    if (!listEl) return;
                                                    if (Object.keys(selections).length === 0) {
                                                        listEl.innerHTML = '<p style="color:#999;font-size:0.85rem;margin:0;">Aucune zone selectionnee</p>';
                                                    } else {
                                                        var html = '';
                                                        for (var compositeKey in selections) {
                                                            var info = selections[compositeKey];
                                                            var parts = compositeKey.split(':');
                                                            var partId = parts.length > 1 ? parts[1] : parts[0];
                                                            var lbl = LABELS[partId] || partId;
                                                            var viewLbl = info.view === 'front' ? 'av.' : 'arr.';
                                                            html += '<span class="daily-sel-item">' +
                                                                lbl + ' (' + viewLbl + ') ' +
                                                                '<select onchange="window._dailyBPSetSev(\\''+compositeKey+'\\',this.value)">' +
                                                                '<option value="1"'+(info.severity==1?' selected':'')+'>1-Legere</option>' +
                                                                '<option value="2"'+(info.severity==2?' selected':'')+'>2-Moderee</option>' +
                                                                '<option value="3"'+(info.severity==3?' selected':'')+'>3-Severe</option>' +
                                                                '</select>' +
                                                                '<span class="remove-btn" onclick="window._dailyBPRemove(\\''+compositeKey+'\\')">x</span>' +
                                                                '</span>';
                                                        }
                                                        listEl.innerHTML = html;
                                                    }
                                                    if (window.Shiny) {
                                                        Shiny.setInputValue('daily_pain_selections', JSON.stringify(selections));
                                                    }
                                                }

                                                window._dailyBPSetSev = function(key, sev) {
                                                    if (selections[key]) { selections[key].severity = parseInt(sev); render(); }
                                                };
                                                window._dailyBPRemove = function(key) {
                                                    delete selections[key]; render();
                                                };

                                                document.addEventListener('click', function(e) {
                                                    var el = e.target.closest('.daily-bp');
                                                    if (!el) return;
                                                    var partId = el.dataset.part;
                                                    var viewEl = el.closest('[data-view]');
                                                    if (!viewEl) return;
                                                    var view = viewEl.dataset.view;
                                                    var key = view + ':' + partId;
                                                    if (selections[key]) {
                                                        delete selections[key];
                                                    } else {
                                                        selections[key] = {view: view, severity: 1};
                                                    }
                                                    render();
                                                });
                                                render();
                                            })();
                                        """),


                                        # Capacity to execute training (0-3 scale)
                                        ui.div(
                                            ui.tags.label("Capacite d'execution de l'entrainement", style="font-weight: 600; margin-bottom: 0.5rem; display: block;"),
                                            ui.input_radio_buttons(
                                                "daily_capacite_execution",
                                                "",
                                                choices={
                                                    "0": "0 - Non complete",
                                                    "1": "1 - Fortement limite",
                                                    "2": "2 - Partiellement limite",
                                                    "3": "3 - Pleine capacite"
                                                },
                                                selected="3",
                                                inline=True
                                            ),
                                            style="margin-bottom: 1rem;"
                                        ),

                                        ui.div(
                                            ui.tags.label("La douleur a-t-elle reduit votre participation ou performance ?", style="font-weight: 600; margin-bottom: 0.5rem; display: block;"),
                                            ui.input_radio_buttons("daily_douleur_impact", "", choices=["Non", "Oui"], selected="Non", inline=True),
                                            style="margin-bottom: 1rem;"
                                        ),

                                        style="padding-left: 1.5rem; border-left: 3px solid #D92323; margin-top: 1rem;"
                                    )
                                ),

                                style="margin-bottom: 1.5rem; padding: 1.25rem; background: #f9f9f9; border-radius: 8px;"
                            ),

                            # S4: Contexte
                            ui.div(
                                ui.tags.h4("Contexte", style="color: #D92323; margin-bottom: 0.75rem; border-bottom: 2px solid #D92323; padding-bottom: 0.5rem;"),

                                ui.div(
                                    ui.tags.label("Séance en groupe ?", style="font-weight: 600; margin-bottom: 0.5rem; display: block;"),
                                    ui.input_radio_buttons("daily_en_groupe", "", choices=["Non", "Oui"], selected="Non", inline=True),
                                    style="margin-bottom: 1rem;"
                                ),

                                style="margin-bottom: 1.5rem;"
                            ),

                            # S5: Détails
                            ui.div(
                                ui.tags.h4("Détails de la Séance", style="color: #D92323; margin-bottom: 0.75rem; border-bottom: 2px solid #D92323; padding-bottom: 0.5rem;"),

                                ui.div(
                                    ui.tags.label("Allures / détails techniques", style="font-weight: 600; margin-bottom: 0.5rem; display: block;"),
                                    ui.input_text("daily_allures", "", placeholder="Ex: 10×400m à 76–74s, récup 1'"),
                                    style="margin-bottom: 1rem;"
                                ),

                                ui.div(
                                    ui.tags.label("Commentaires", style="font-weight: 600; margin-bottom: 0.5rem; display: block;"),
                                    ui.input_text_area("daily_commentaires", "", placeholder="Sensations, météo, matériel...", rows=3),
                                    style="margin-bottom: 1rem;"
                                ),

                                ui.div(
                                    ui.tags.label("Avez-vous modifié l'entraînement ?", style="font-weight: 600; margin-bottom: 0.5rem; display: block;"),
                                    ui.input_radio_buttons("daily_modifs_oui", "", choices=["Non", "Oui"], selected="Non", inline=True),
                                    style="margin-bottom: 1rem;"
                                ),

                                ui.panel_conditional(
                                    "input.daily_modifs_oui === 'Oui'",
                                    ui.div(
                                        ui.tags.label("Quelles modifications ?", style="font-weight: 600; margin-bottom: 0.5rem; display: block;"),
                                        ui.input_text("daily_modifs_details", "", placeholder="Décrivez les modifications"),
                                        style="padding-left: 1.5rem; border-left: 3px solid #D92323; margin-top: 1rem;"
                                    )
                                ),

                                style="margin-bottom: 1.5rem; padding: 1.25rem; background: #f9f9f9; border-radius: 8px;"
                            ),

                            # Submit
                            ui.div(
                                ui.input_action_button("submit_daily_survey", "Envoyer",
                                    class_="btn btn-primary",
                                    style="background: #D92323; border: none; padding: 0.75rem 2rem; font-weight: 600; font-size: 1.1rem; width: 100%;"),
                                style="margin-top: 2rem;"
                            ),

                            ui.div(
                                ui.output_ui("daily_survey_result"),
                                style="margin-top: 2rem;"
                            )
                        )
                    )
                ),

                # ============================================================
                # WEEKLY WELLNESS QUESTIONNAIRE (≤1 minute)
                # ============================================================
                ui.nav_panel("Questionnaire Hebdomadaire",
                    ui.card(
                        ui.card_header("Questionnaire Bien-être Hebdomadaire"),
                        ui.div(
                            {"class": "survey-form", "style": "width: 100%; padding: 2rem; max-width: 1200px;"},

                            # Week selector
                            ui.div(
                                ui.tags.h5("Sélectionner la semaine", style="color: #D92323; margin-bottom: 0.75rem;"),
                                ui.output_ui("weekly_week_selector"),
                                ui.output_ui("weekly_already_filled_notice"),
                                style="margin-bottom: 2rem; padding: 1.25rem; background: #fef2f2; border-radius: 8px; border-left: 4px solid #D92323;"
                            ),

                            # S1: Bien-être
                            ui.div(
                                ui.tags.h4("1. Bien-être Général", style="color: #D92323; margin-bottom: 0.75rem; border-bottom: 2px solid #D92323; padding-bottom: 0.5rem;"),
                                ui.tags.p("0=aucun | 5=modéré | 10=extrême", style="font-size: 0.9rem; color: #666; margin-bottom: 1rem; font-style: italic;"),

                                ui.layout_columns(
                                    scale_with_tooltip("Fatigue",
                                                      ui.input_slider("weekly_fatigue", "", min=0, max=10, value=5, step=1, width="100%"),
                                                      ""),  # Placeholder
                                    scale_with_tooltip("Douleurs musculaires",
                                                      ui.input_slider("weekly_doms", "", min=0, max=10, value=5, step=1, width="100%"),
                                                      ""),  # Placeholder
                                    col_widths=[6, 6]
                                ),

                                ui.layout_columns(
                                    scale_with_tooltip("Stress global",
                                                      ui.input_slider("weekly_stress_global", "", min=0, max=10, value=5, step=1, width="100%"),
                                                      ""),  # Placeholder
                                    scale_with_tooltip("Humeur générale",
                                                      ui.input_slider("weekly_humeur_globale", "", min=0, max=10, value=5, step=1, width="100%"),
                                                      ""),  # Placeholder
                                    col_widths=[6, 6]
                                ),

                                scale_with_tooltip("Disposition à s'entraîner",
                                                  ui.input_slider("weekly_readiness", "", min=0, max=10, value=5, step=1, width="100%"),
                                                  ""),  # Placeholder

                                style="margin-bottom: 1.5rem; padding: 1.25rem; background: #f9f9f9; border-radius: 8px;"
                            ),

                            # S2: BRUMS
                            ui.div(
                                ui.tags.h4("2. État Psychologique (BRUMS)", style="color: #D92323; margin-bottom: 0.75rem; border-bottom: 2px solid #D92323; padding-bottom: 0.5rem;"),
                                ui.tags.p("0=pas du tout | 2=modérément | 4=extrêmement", style="font-size: 0.9rem; color: #666; margin-bottom: 1rem; font-style: italic;"),

                                ui.layout_columns(
                                    ui.div(ui.tags.label("Tension", style="font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;"),
                                           ui.input_radio_buttons("weekly_brums_tension", "", choices=["0", "1", "2", "3", "4"], selected="0", inline=True)),
                                    ui.div(ui.tags.label("Dépression", style="font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;"),
                                           ui.input_radio_buttons("weekly_brums_depression", "", choices=["0", "1", "2", "3", "4"], selected="0", inline=True)),
                                    ui.div(ui.tags.label("Colère", style="font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;"),
                                           ui.input_radio_buttons("weekly_brums_colere", "", choices=["0", "1", "2", "3", "4"], selected="0", inline=True)),
                                    col_widths=[4, 4, 4]
                                ),

                                ui.layout_columns(
                                    ui.div(ui.tags.label("Vigueur", style="font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;"),
                                           ui.input_radio_buttons("weekly_brums_vigueur", "", choices=["0", "1", "2", "3", "4"], selected="2", inline=True)),
                                    ui.div(ui.tags.label("Fatigue mentale", style="font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;"),
                                           ui.input_radio_buttons("weekly_brums_fatigue", "", choices=["0", "1", "2", "3", "4"], selected="1", inline=True)),
                                    ui.div(ui.tags.label("Confusion", style="font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;"),
                                           ui.input_radio_buttons("weekly_brums_confusion", "", choices=["0", "1", "2", "3", "4"], selected="0", inline=True)),
                                    col_widths=[4, 4, 4]
                                ),

                                style="margin-bottom: 1.5rem; padding: 1.25rem; background: #fff3e0; border-radius: 8px;"
                            ),

                            # S3: REST-Q
                            ui.div(
                                ui.tags.h4("3. Stress & Récupération", style="color: #D92323; margin-bottom: 0.75rem; border-bottom: 2px solid #D92323; padding-bottom: 0.5rem;"),
                                ui.tags.p("0=jamais | 2=parfois | 4=toujours", style="font-size: 0.9rem; color: #666; margin-bottom: 1rem; font-style: italic;"),

                                ui.layout_columns(
                                    ui.div(ui.tags.label("Stress émotionnel", style="font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;"),
                                           ui.input_radio_buttons("weekly_restq_emotion", "", choices=["0", "1", "2", "3", "4"], selected="1", inline=True)),
                                    ui.div(ui.tags.label("Stress physique", style="font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;"),
                                           ui.input_radio_buttons("weekly_restq_physique", "", choices=["0", "1", "2", "3", "4"], selected="1", inline=True)),
                                    ui.div(ui.tags.label("Sommeil réparateur", style="font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;"),
                                           ui.input_radio_buttons("weekly_restq_sommeil", "", choices=["0", "1", "2", "3", "4"], selected="2", inline=True)),
                                    col_widths=[4, 4, 4]
                                ),

                                ui.layout_columns(
                                    ui.div(ui.tags.label("Récup. physique", style="font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;"),
                                           ui.input_radio_buttons("weekly_restq_recup_phys", "", choices=["0", "1", "2", "3", "4"], selected="2", inline=True)),
                                    ui.div(ui.tags.label("Récup. sociale", style="font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;"),
                                           ui.input_radio_buttons("weekly_restq_social", "", choices=["0", "1", "2", "3", "4"], selected="2", inline=True)),
                                    ui.div(ui.tags.label("Relaxation", style="font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;"),
                                           ui.input_radio_buttons("weekly_restq_relax", "", choices=["0", "1", "2", "3", "4"], selected="2", inline=True)),
                                    col_widths=[4, 4, 4]
                                ),

                                style="margin-bottom: 1.5rem; padding: 1.25rem; background: #e8f5e9; border-radius: 8px;"
                            ),

                            # S4: OSLO
                            ui.div(
                                ui.tags.h4("4. Blessures / Maladies (OSLO)", style="color: #D92323; margin-bottom: 0.75rem; border-bottom: 2px solid #D92323; padding-bottom: 0.5rem;"),

                                ui.layout_columns(
                                    ui.div(ui.tags.label("Participation réduite ?", style="font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;"),
                                           ui.input_radio_buttons("weekly_oslo_participation", "", choices=["Non", "Oui"], selected="Non", inline=True)),
                                    ui.div(ui.tags.label("Volume diminué ?", style="font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;"),
                                           ui.input_radio_buttons("weekly_oslo_volume", "", choices=["Non", "Oui"], selected="Non", inline=True)),
                                    col_widths=[6, 6]
                                ),

                                ui.layout_columns(
                                    ui.div(ui.tags.label("Performance affectée ?", style="font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;"),
                                           ui.input_radio_buttons("weekly_oslo_performance", "", choices=["Non", "Oui"], selected="Non", inline=True)),
                                    ui.div(ui.tags.label("Blessure ou maladie ?", style="font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;"),
                                           ui.input_radio_buttons("weekly_oslo_symptomes", "", choices=["Non", "Oui"], selected="Non", inline=True)),
                                    col_widths=[6, 6]
                                ),

                                ui.panel_conditional(
                                    "input.weekly_oslo_symptomes === 'Oui'",
                                    ui.div(
                                        scale_with_tooltip("Intensité (1-10)",
                                                          ui.input_slider("weekly_douleur_intensite", "", min=1, max=10, value=5, step=1, width="100%"),
                                                          ""),  # Placeholder

                                        ui.div(ui.tags.label("Type et zone", style="font-weight: 600; display: block; margin-bottom: 0.5rem;"),
                                               ui.input_text("weekly_douleur_description", "", placeholder="Ex: tendinopathie achille droite"),
                                               style="margin-bottom: 1rem;"),

                                        ui.div(ui.tags.label("Entraînements modifiés/arrêtés ?", style="font-weight: 600; display: block; margin-bottom: 0.5rem;"),
                                               ui.input_radio_buttons("weekly_douleur_modif", "", choices=["Non", "Oui"], selected="Non", inline=True)),

                                        style="padding: 1rem; background: #fff3cd; border-left: 3px solid #D92323; margin-top: 1rem; border-radius: 4px;"
                                    )
                                ),

                                style="margin-bottom: 1.5rem; padding: 1.25rem; background: #ffebee; border-radius: 8px;"
                            ),

                            # S5: Sommeil, alimentation, charge, poids
                            ui.div(
                                ui.tags.h4("5. Sommeil, Alimentation, Charge & Poids", style="color: #D92323; margin-bottom: 0.75rem; border-bottom: 2px solid #D92323; padding-bottom: 0.5rem;"),

                                ui.layout_columns(
                                    scale_with_tooltip("Qualité sommeil (1-10)",
                                                      ui.input_slider("weekly_sommeil_qualite", "", min=1, max=10, value=7, step=1, width="100%"),
                                                      ""),  # Placeholder
                                    scale_with_tooltip("Qualité alimentation (1-10)",
                                                      ui.input_slider("weekly_alimentation_qualite", "", min=1, max=10, value=7, step=1, width="100%"),
                                                      ""),  # Placeholder
                                    col_widths=[6, 6]
                                ),

                                ui.layout_columns(
                                    scale_with_tooltip("Charge académique/pro (0-10)",
                                                      ui.input_slider("weekly_charge_acad_pro", "", min=0, max=10, value=5, step=1, width="100%"),
                                                      ""),  # Placeholder
                                    ui.div(ui.tags.label("Poids (kg, optionnel)", style="font-weight: 600; display: block; margin-bottom: 0.5rem; font-size: 0.95rem;"),
                                           ui.input_numeric("weekly_poids", "", value=None, min=30, max=150, step=0.1, width="150px")),
                                    col_widths=[6, 6]
                                ),

                                style="margin-bottom: 1.5rem; padding: 1.25rem; background: #f9f9f9; border-radius: 8px;"
                            ),

                            # Submit
                            ui.div(
                                ui.input_action_button("submit_weekly_survey", "Envoyer",
                                    class_="btn btn-primary",
                                    style="background: #D92323; border: none; padding: 0.75rem 2rem; font-weight: 600; font-size: 1.1rem; width: 100%;"),
                                style="margin-top: 2rem;"
                            ),

                            ui.div(
                                ui.output_ui("weekly_survey_result"),
                                style="margin-top: 2rem;"
                            )
                        )
                    )
                ),

                id="questionnaire_tabs"
            )
        ),
        
        # New tab: Manual Data Entry for Personal Records
        ui.nav_panel("Entrée de données manuelle",
            ui.output_ui("manual_entry_content")
        ),
        
        # Phase 1.5: Intervals visualization - REMOVED (to be implemented later)
        id="tabs"
    )
    )  # Close dashboard_content_ui div

# ========== SERVER ==========
def server(input, output, session):

    # ========== AUTHENTICATION ==========
    is_authenticated = reactive.Value(False)
    user_role = reactive.Value(None)  # 'athlete' or 'coach'
    user_athlete_id = reactive.Value(None)  # athlete_id for athletes, None for coach
    user_name = reactive.Value(None)

    # ========== DATA REFRESH ==========
    refresh_status = reactive.Value("")  # "", "loading", "success", "error"
    refresh_message = reactive.Value("")

    # Show login modal on startup
    ui.modal_show(login_modal)
    
    # Login handler
    @reactive.Effect
    @reactive.event(input.login_submit)
    def handle_login():
        password = input.login_password()
        if not password:
            ui.insert_ui(
                ui.HTML('<script>document.getElementById("login_error").style.display="block"; document.getElementById("login_error").innerText="Veuillez entrer votre mot de passe";</script>'),
                selector="body",
                where="beforeEnd"
            )
            return

        try:
            # Generate password prefix for fast lookup (O(1) instead of O(n))
            prefix = generate_password_prefix(password)

            # Query users by prefix - instant indexed lookup
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/users?password_prefix=eq.{prefix}&select=*",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json"
                }
            )
            matching_users = response.json()

            # Verify bcrypt for matching users (usually just 1)
            authenticated_user = None
            for user in matching_users:
                if verify_password(password, user['password_hash']):
                    authenticated_user = user
                    break

            if authenticated_user is not None:
                # Successful login
                is_authenticated.set(True)
                user_role.set(authenticated_user['role'])
                user_athlete_id.set(authenticated_user['athlete_id'])
                user_name.set(authenticated_user['name'])

                # Close modal and clear password
                ui.modal_remove()
                ui.update_text("login_password", value="")

                print(f"Login successful: {authenticated_user['name']} ({authenticated_user['role']})")
            else:
                # Failed login
                ui.insert_ui(
                    ui.HTML('<script>document.getElementById("login_error").style.display="block"; document.getElementById("login_error").innerText="Mot de passe invalide. Veuillez réessayer.";</script>'),
                    selector="body",
                    where="beforeEnd"
                )
                ui.update_text("login_password", value="")
        except Exception as e:
            print(f"Login error: {e}")
            ui.insert_ui(
                ui.HTML(f'<script>document.getElementById("login_error").style.display="block"; document.getElementById("login_error").innerText="Erreur de connexion. Veuillez réessayer.";</script>'),
                selector="body",
                where="beforeEnd"
            )
    
    # Logout handler
    @reactive.Effect
    @reactive.event(input.logout_btn)
    def handle_logout():
        is_authenticated.set(False)
        user_role.set(None)
        user_athlete_id.set(None)
        user_name.set(None)
        ui.modal_show(login_modal)

    # Data refresh handler (triggers Lambda)
    @reactive.Effect
    @reactive.event(input.refresh_data_btn)
    async def handle_refresh_data():
        if not LAMBDA_FUNCTION_URL or not LAMBDA_REFRESH_TOKEN:
            refresh_status.set("error")
            refresh_message.set("Refresh non configure")
            return

        # Check rate limit (3 per day)
        try:
            check_resp = _sess.get(
                f"{SUPABASE_URL}/rest/v1/rpc/check_sync_allowed",
                timeout=10
            )
            if check_resp.status_code == 200:
                result = check_resp.json()
                if result and len(result) > 0:
                    if not result[0].get("allowed", True):
                        refresh_status.set("error")
                        refresh_message.set(f"Limite atteinte ({result[0].get('count_today', 3)}/3 aujourd'hui)")
                        return
        except Exception as e:
            print(f"[WARN] Could not check sync limit: {e}")
            # Continue anyway if check fails

        refresh_status.set("loading")
        role = user_role.get()
        if role == "coach":
            refresh_message.set("Synchronisation de tous les athletes en cours...")
        else:
            refresh_message.set("Synchronisation de vos donnees en cours...")

        # Log sync start
        current_user = user_name.get() or "unknown"
        try:
            _sess.post(
                f"{SUPABASE_URL}/rest/v1/sync_log",
                json={"triggered_by": current_user, "status": "started"},
                timeout=10
            )
        except Exception as e:
            print(f"[WARN] Could not log sync start: {e}")

        try:
            import asyncio
            # Run HTTP request in background to not block UI
            # Athletes sync only their own data; coaches sync everyone
            sync_body = {}
            if role != "coach":
                sync_athlete_name = user_name.get()
                if sync_athlete_name:
                    sync_body = {"athlete_name": sync_athlete_name}

            def do_request():
                return requests.post(
                    LAMBDA_FUNCTION_URL,
                    headers={
                        "Authorization": f"Bearer {LAMBDA_REFRESH_TOKEN}",
                        "Content-Type": "application/json"
                    },
                    json=sync_body,
                    timeout=900  # 15 minutes max
                )

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, do_request)

            if response.status_code == 200 or response.status_code == 207:
                data = response.json()
                msg = data.get("message", "Synchronisation terminee")
                refresh_status.set("success")
                refresh_message.set(msg)
            elif response.status_code == 401:
                refresh_status.set("error")
                refresh_message.set("Erreur d'authentification")
            else:
                refresh_status.set("error")
                refresh_message.set(f"Erreur: {response.status_code}")

        except requests.exceptions.Timeout:
            refresh_status.set("warning")
            refresh_message.set("Synchronisation peut encore etre en cours...")
        except Exception as e:
            refresh_status.set("error")
            refresh_message.set(f"Erreur: {str(e)[:50]}")

    # Refresh status display
    @output
    @render.ui
    def refresh_status_display():
        status = refresh_status.get()
        message = refresh_message.get()

        if not status:
            return ui.div()

        if status == "loading":
            return ui.span(
                ui.tags.i(class_="fa fa-spinner fa-spin", style="margin-right: 0.5rem;"),
                message,
                style="color: #3b82f6; font-size: 0.9rem; margin-right: 0.75rem;"
            )
        elif status == "success":
            return ui.span(
                ui.tags.i(class_="fa fa-check", style="margin-right: 0.5rem;"),
                message,
                style="color: #22c55e; font-size: 0.9rem; margin-right: 0.75rem;"
            )
        elif status == "warning":
            return ui.span(
                ui.tags.i(class_="fa fa-clock", style="margin-right: 0.5rem;"),
                message,
                style="color: #f59e0b; font-size: 0.9rem; margin-right: 0.75rem;"
            )
        else:  # error
            return ui.span(
                ui.tags.i(class_="fa fa-times", style="margin-right: 0.5rem;"),
                message,
                style="color: #ef4444; font-size: 0.9rem; margin-right: 0.75rem;"
            )

    # Render dashboard content conditionally
    @output
    @render.ui
    def dashboard_content():
        if not is_authenticated.get():
            return ui.div()  # Empty div when not authenticated
        # Return the full dashboard UI
        print("[DEBUG] dashboard_content returning FULL UI", flush=True)
        return dashboard_content_ui()
    
    # Render user info
    @output
    @render.ui
    def user_info_display():
        if not is_authenticated.get():
            return ui.div()
        name = user_name.get()
        role = user_role.get()
        # For coach, just show "Coach", for athletes show their name
        display_text = "Coach" if role == "coach" else name
        return ui.tags.button(display_text, class_="btn btn-light", style="font-weight: 600; font-size: 1.1rem; cursor: default;", disabled=True)

    # TEST: Simple matplotlib plot to see if non-Plotly graphs work
    @output
    @render.plot
    def test_matplotlib_plot():
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot([1, 2, 3, 4], [1, 4, 2, 3], 'b-o')
        ax.set_title("Test Matplotlib Plot")
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        return fig

    # Helper function to render Plotly as HTML (workaround for shinywidgets crash on ShinyApps.io)
    # Track if plotly.js has been included already to avoid duplicates
    _plotly_js_included = {"value": False}

    def plotly_to_html(fig):
        """Convert a Plotly figure to HTML for rendering without shinywidgets."""
        # Only include plotly.js on first graph, then use 'cdn' for rest
        if not _plotly_js_included["value"]:
            _plotly_js_included["value"] = True
            include_js = True  # First graph: embed full JS
        else:
            include_js = 'cdn'  # Subsequent: use CDN (JS already loaded)

        html_str = fig.to_html(
            full_html=False,
            include_plotlyjs=include_js,
            config={'responsive': True, 'displayModeBar': True}
        )
        return ui.HTML(html_str)

    # Helper function to get effective athlete_id for filtering
    def get_effective_athlete_id():
        """Returns the athlete_id to use for filtering data based on role and selection."""
        if not is_authenticated.get():
            return None
        
        role = user_role.get()
        if role == "athlete":
            # Athletes always see only their own data
            return user_athlete_id.get()
        elif role == "coach":
            # Coach uses the athlete dropdown selection
            try:
                sel_name = input.athlete()
                if sel_name:
                    return name_to_id.get(sel_name)
            except:
                pass
            return None  # No selection or error
        return None

    # --- Athlètes (id <-> nom)
    athletes_df = fetch_athletes()
    name_to_id = {r["name"]: r["athlete_id"] for _, r in athletes_df.iterrows()}
    id_to_name = {r["athlete_id"]: r["name"] for _, r in athletes_df.iterrows()}
    
    # Update athlete selector based on role
    @reactive.Effect
    @reactive.event(is_authenticated, user_role)
    def update_athlete_selector():
        if not is_authenticated.get():
            return
        
        role = user_role.get()
        if role == "athlete":
            # Athletes see only their own name (locked)
            athlete_id = user_athlete_id.get()
            athlete_name = id_to_name.get(athlete_id, "Unknown")
            ui.update_select("athlete", choices=[athlete_name], selected=athlete_name)
        else:
            # Coach sees all athletes
            ui.update_select("athlete", choices=athletes_df["name"].tolist(),
                           selected=(athletes_df["name"].iloc[0] if not athletes_df.empty else None))

    # --- Réactifs
    meta_df_all = reactive.Value(pd.DataFrame())     # meta complètes (avant toggle VirtualRun)
    meta_df = reactive.Value(pd.DataFrame())         # meta filtrées sur période + athlète (+ toggle vrun)
    act_label_to_id = reactive.Value({})             # libellé -> activity_id (pour Run/TrailRun)
    id_to_info = reactive.Value({})                  # activity_id -> infos (type, date_str)

    # Data date range (for restricting date pickers)
    data_min_date = reactive.Value(None)  # Earliest date with data
    data_max_date = reactive.Value(None)  # Latest date with data

    # Activity by date mapping (used for activity selection)
    activities_by_date = reactive.Value({})  # date_str -> list of {activity_id, label}

    # ========== COMPARISON TAB STATE ==========
    comparison_activity_id_1 = reactive.Value(None)
    comparison_activity_id_2 = reactive.Value(None)
    comparison_calendar_year_1 = reactive.Value(date.today().year)
    comparison_calendar_year_2 = reactive.Value(date.today().year)
    crop_range_1 = reactive.Value([0, 0])
    crop_range_2 = reactive.Value([0, 0])

    # Set date range for flatpickr restrictions
    @reactive.Effect
    @reactive.event(data_min_date, data_max_date)
    def _update_date_range():
        min_date = data_min_date.get()
        max_date = data_max_date.get()

        if min_date and max_date:
            # Convert to ISO format strings for JavaScript
            min_str = min_date.isoformat()
            max_str = max_date.isoformat()

            # Inject JavaScript to update date range and reinitialize date pickers
            js_code = f"""
                window.dataMinDate = '{min_str}';
                window.dataMaxDate = '{max_str}';
                // Reinitialize all date pickers with new limits
                if (typeof initializeFrenchDatePickers === 'function') {{
                    initializeFrenchDatePickers();
                }}
            """
            ui.insert_ui(
                ui.tags.script(js_code),
                selector="body",
                where="beforeEnd"
            )

    def _range_iso() -> tuple[str, str]:
        sd = pd.to_datetime(input.date_start() or date.today()).date()
        ed = pd.to_datetime(input.date_end() or date.today()).date()
        return f"{sd.isoformat()}T00:00:00Z", f"{ed.isoformat()}T23:59:59Z"

    def _apply_vrun_toggle(df: pd.DataFrame) -> pd.DataFrame:
        """Applique le toggle VirtualRun sur le *Résumé* (et la liste d'activités si on veut exclure VRUN)."""
        if df.empty: return df
        inc = bool(input.incl_vrun())
        if inc: return df
        # Exclure VirtualRun si toggle OFF
        return df.loc[df["type"].str.lower() != "virtualrun"].copy()

    def _update_activity_choices(df: pd.DataFrame):
        """Alimente le select 'activity_sel' avec toutes les activités de course (Run/TrailRun/VirtualRun)."""
        labels_map, info_map = {}, {}

        # Mapping des types de course en français
        type_labels = {
            "run": "Course extérieur",
            "trailrun": "Course en sentier",
            "virtualrun": "Course sur tapis"
        }

        if not df.empty and "type" in df.columns:
            # Inclure toutes les activités de course
            m = df["type"].str.lower().isin(["run", "trailrun", "virtualrun"])
            dfr = df.loc[m].copy()
            if "start_time" in dfr.columns and not dfr.empty:
                dfr = dfr.sort_values("start_time", ascending=False)  # Plus récent en premier
                dfr["date_str"] = pd.to_datetime(dfr["start_time"]).dt.date.astype(str)

                # Vectorized date formatting using pandas operations
                mois_fr = ["janvier", "février", "mars", "avril", "mai", "juin",
                           "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

                # Parse all dates at once
                dates = pd.to_datetime(dfr["start_time"])
                dfr["jour"] = dates.dt.day
                dfr["mois_nom"] = dates.dt.month.apply(lambda m: mois_fr[m - 1])
                dfr["annee"] = dates.dt.year

                # Format time strings vectorized
                duration_min = dfr["duration_min"].fillna(0)
                total_seconds = (duration_min * 60).astype(int)
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60

                # Conditional time formatting
                dfr["time_str"] = np.where(
                    hours > 0,
                    hours.astype(str) + ":" + minutes.astype(str).str.zfill(2) + ":" + seconds.astype(str).str.zfill(2),
                    minutes.astype(str) + ":" + seconds.astype(str).str.zfill(2)
                )

                # Format distance
                dfr["dist_str"] = dfr["distance_km"].fillna(0).apply(lambda x: f"{x:.2f}")

                # Map type labels
                dfr["type_fr"] = dfr["type"].str.lower().map(type_labels).fillna(dfr["type"])

                # Build labels vectorized (without intervals tag)
                dfr["label"] = (
                    dfr["type_fr"] + " - " +
                    dfr["jour"].astype(str) + " " + dfr["mois_nom"] + " " + dfr["annee"].astype(str) + " - " +
                    dfr["time_str"] + " - " +
                    dfr["dist_str"] + " km"
                )

                # OPTIMIZATION 3: Build dictionaries using vectorized operations instead of iterrows
                labels_map = dict(zip(dfr["label"], dfr["activity_id"].astype(str)))
                info_map = dict(
                    zip(
                        dfr["activity_id"].astype(str),
                        [{"type": str(t), "date_str": d} for t, d in zip(dfr["type"], dfr["date_str"])]
                    )
                )

                # OPTIMIZATION 4: Group by date using pandas groupby (much faster than manual loop)
                grouped = dfr.groupby("date_str")
                by_date = {
                    date_key: [
                        {"activity_id": str(row["activity_id"]), "label": row["label"]}
                        for _, row in group[["activity_id", "label"]].iterrows()
                    ]
                    for date_key, group in grouped
                }

                activities_by_date.set(by_date)

        act_label_to_id.set(labels_map)
        id_to_info.set(info_map)
        ui.update_select("activity_sel", choices=list(labels_map.keys()),
                         selected=(next(iter(labels_map)) if labels_map else None))

    # Rechargement des métadonnées quand athlète/période/toggle changent
    @reactive.Effect
    @reactive.event(input.athlete, input.date_start, input.date_end, input.incl_vrun)
    def _reload_meta():
        print("[DEBUG] _reload_meta called", flush=True)
        try:
            # Get the effective athlete_id based on role and selection
            athlete_id = get_effective_athlete_id()
            
            # If no athlete_id (shouldn't happen), skip
            if not athlete_id:
                meta_df.set(pd.DataFrame())
                _update_activity_choices(pd.DataFrame())
                return
            
            sd = pd.to_datetime(input.date_start() or date.today()).date()
            ed = pd.to_datetime(input.date_end() or date.today()).date()
            _, end_iso = _range_iso()
            lookback_days = 90
            calc_start = (sd - timedelta(days=lookback_days))
            calc_start_iso = f"{calc_start.isoformat()}T00:00:00Z"
            df_calc = fetch_metadata(calc_start_iso, end_iso, [athlete_id])
            # Ajouter le nom
            if not df_calc.empty and "athlete_id" in df_calc.columns:
                df_calc["athlete"] = df_calc["athlete_id"].map(id_to_name).fillna(df_calc["athlete_id"])
                st_utc = pd.to_datetime(df_calc.get("start_time"), utc=True, errors="coerce")
                st_local = st_utc.dt.tz_convert(ZoneInfo(LOCAL_TZ))
                df_calc["start_time_local"] = st_local
                df_calc["date_local"] = st_local.dt.tz_localize(None).dt.normalize()
                df_calc["duration_min"] = pd.to_numeric(df_calc.get("duration_sec"), errors="coerce") / 60.0
                df_calc["distance_km"] = pd.to_numeric(df_calc.get("distance_m"), errors="coerce") / 1000.0
                df_calc["type_lower"] = df_calc.get("type", pd.Series(dtype=str)).astype(str).str.lower()

                # Calculate data date range for date picker restrictions
                if "date_local" in df_calc.columns and not df_calc.empty:
                    dates = df_calc["date_local"].dt.date
                    data_min_date.set(dates.min())
                    data_max_date.set(dates.max())

            meta_df_all.set(df_calc.copy())
            df_view = df_calc.copy()
            if not df_view.empty:
                dates_local = df_view["date_local"].dt.date if "date_local" in df_view else pd.to_datetime(df_view["start_time"], utc=True, errors="coerce").dt.tz_convert(ZoneInfo(LOCAL_TZ)).dt.date
                mask_period = (dates_local >= sd) & (dates_local <= ed)
                df_view = df_view.loc[mask_period].copy()
            # Appliquer le toggle VirtualRun pour **Résumé**
            df_summary = _apply_vrun_toggle(df_view)
            meta_df.set(df_summary)
            # Liste d’activités d’analyse (on respecte aussi le toggle: si OFF, on exclut VRUN du choix)
            _update_activity_choices(df_summary)
        except Exception as e:
            print(f"ERROR in _reload_meta: {e}")
            import traceback
            traceback.print_exc()
            meta_df.set(pd.DataFrame())
            _update_activity_choices(pd.DataFrame())

    # ----------------- Résumé de période -----------------
    @output
    @render.ui
    def run_duration_trend():
        """
        Temps de course moyen avec CTL/ATL configurables pour Run/Trail/Tapis.
        CTL = Chronic Training Load (mésocycle, défaut 28j)
        ATL = Acute Training Load (microcycle, défaut 7j)
        TSB = Training Stress Balance (CTL - ATL)
        """
        print("[RUN_TREND] Starting run_duration_trend render...", flush=True)
        df_all = meta_df_all.get().copy()
        print(f"[RUN_TREND] meta_df_all has {len(df_all)} rows", flush=True)

        if df_all.empty:
            print("[RUN_TREND] No data, returning empty fig", flush=True)
            return plotly_to_html(_create_empty_plotly_fig("Aucune activité", height=360))

        try:
            start_date = pd.to_datetime(input.date_start()).date()
            end_date = pd.to_datetime(input.date_end()).date()
        except Exception:
            return plotly_to_html(_create_empty_plotly_fig("Sélectionnez une période valide", height=360))

        if start_date > end_date:
            start_date, end_date = end_date, start_date

        metric_mode = input.run_metric() or "time"
        type_series = df_all.get("type_lower")
        if type_series is None:
            type_series = df_all.get("type", pd.Series(dtype=str)).astype(str).str.lower()
        m_run = type_series.isin(RUN_TYPES)
        if not m_run.any():
            return plotly_to_html(_create_empty_plotly_fig("Aucune sortie de course sur cette période", height=360))

        metric_col = "duration_min" if metric_mode == "time" else "distance_km"
        if metric_col not in df_all.columns:
            return plotly_to_html(_create_empty_plotly_fig("Mesure indisponible pour ces activités", height=360))

        d_all = df_all.loc[m_run].dropna(subset=["date_local"])
        if d_all.empty:
            return plotly_to_html(_create_empty_plotly_fig("Aucune donnée exploitable", height=360))

        daily = d_all.groupby("date_local", as_index=True)[metric_col].sum().astype(float)
        daily = daily.sort_index()
        full_index = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
        daily = daily.reindex(full_index, fill_value=0.0)
        daily.index = full_index

        # Get CTL and ATL periods from inputs
        ctl_days = int(input.ctl_days() or 28)
        atl_days = int(input.atl_days() or 7)
        
        daily_values = daily
        if metric_mode == "dist":
            y_label = "Kilomètres par jour"
            legend_ctl = f"CTL {ctl_days} j (km)"
            legend_atl = f"ATL {atl_days} j (km)"
            legend_tsb = "TSB (km)"
        else:
            y_label = "Minutes par jour"
            legend_ctl = f"CTL {ctl_days} j (min)"
            legend_atl = f"ATL {atl_days} j (min)"
            legend_tsb = "TSB (min)"

        if not np.isfinite(daily_values).any() or np.isclose(daily_values.sum(), 0.0):
            return plotly_to_html(_create_empty_plotly_fig("Valeurs nulles sur cette période", height=360))

        # Dynamic min_periods: start calculating as soon as we have data
        # Use minimum of 1 day to allow immediate calculation with available data
        # This prevents gaps when database doesn't have full history
        ctl_min_periods = max(1, min(ctl_days, len(daily_values)))
        atl_min_periods = max(1, min(atl_days, len(daily_values)))

        ctl = daily_values.ewm(span=ctl_days, min_periods=ctl_min_periods, adjust=False).mean()
        atl = daily_values.ewm(span=atl_days, min_periods=atl_min_periods, adjust=False).mean()
        tsb = ctl - atl

        mask = ctl.notna()
        if not mask.any():
            return plotly_to_html(_create_empty_plotly_fig(f"Aucune donnée disponible pour le calcul.", height=360))

        available_idx = ctl.index[mask]
        disp_start = max(start_date, available_idx.min().date())
        disp_end = min(end_date, available_idx.max().date())
        if disp_start > disp_end:
            return plotly_to_html(_create_empty_plotly_fig("Aucune donnée dans la plage sélectionnée", height=360))
        display_mask = mask & (ctl.index.date >= disp_start) & (ctl.index.date <= disp_end)
        if not display_mask.any():
            return plotly_to_html(_create_empty_plotly_fig("Aucune donnée dans la plage sélectionnée", height=360))

        idx = ctl.index[display_mask].to_pydatetime()  # Convert to Python datetime for Plotly
        ctl_vals = ctl.loc[display_mask]
        atl_vals = atl.loc[display_mask]
        tsb_vals = tsb.loc[display_mask]

        # Calculate Y-axis range to fit all data (CTL, ATL, TSB)
        # TSB can be negative, so don't clamp to 0
        all_values = pd.concat([ctl_vals, atl_vals, tsb_vals])
        y_min = all_values.min()
        y_max = all_values.max()
        y_padding = (y_max - y_min) * 0.15  # 15% padding for better visibility
        y_range = [y_min - y_padding, y_max + y_padding]

        # Saint-Laurent Sélect colors
        color28 = "#D92323"  # Red for CTL
        color7 = "#D9CD23"   # Yellow for ATL
        color_tsb = "#FF6B6B" if metric_mode != "dist" else "#FFA500"

        fig = go.Figure()
        
        # Fill area under CTL
        fig.add_trace(go.Scatter(
            x=idx, y=ctl_vals.values,
            fill='tozeroy',
            fillcolor=f'rgba(217, 35, 35, 0.15)',
            line=dict(color=color28, width=3),
            name=legend_ctl,
            mode='lines',
            hovertemplate=legend_ctl + "<br>%{x|%d %b %Y}<br>%{y:.1f}<extra></extra>"
        ))
        
        # ATL line
        fig.add_trace(go.Scatter(
            x=idx, y=atl_vals.values,
            line=dict(color=color7, width=2.5),
            name=legend_atl,
            mode='lines',
            hovertemplate=legend_atl + "<br>%{x|%d %b %Y}<br>%{y:.1f}<extra></extra>"
        ))
        
        # TSB line (dotted)
        fig.add_trace(go.Scatter(
            x=idx, y=tsb_vals.values,
            line=dict(color=color_tsb, width=2, dash='dot'),
            name=legend_tsb,
            mode='lines',
            hovertemplate=legend_tsb + "<br>%{x|%d %b %Y}<br>%{y:.1f}<extra></extra>"
        ))
        
        fig.update_layout(
            autosize=True,  # Responsive sizing for production
            title=dict(text="Moyenne pondérée exponentiellement — CTL / ATL / TSB", font=dict(size=16, color='#262626')),
            xaxis=dict(
                title=dict(text="Date", font=dict(size=14)),
                type='date',
                tickformat='%d %b',  # Format: "15 Nov", "20 Nov", etc.
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)',
                tickfont=dict(size=12),
                autorange=True  # Ensure proper range
            ),
            yaxis=dict(
                title=dict(text=y_label, font=dict(size=14)),
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)',
                range=y_range,
                tickfont=dict(size=12)
            ),
            plot_bgcolor='white',
            height=400,
            hovermode='x unified',
            legend=dict(x=0, y=1, bgcolor='rgba(255,255,255,0.9)', font=dict(size=13)),
            margin=dict(l=70, r=30, t=70, b=70)
        )

        # Add race markers (vertical lines) - same as zone_time_longitudinal
        try:
            # Safely get selected_race - might not exist if dropdown wasn't rendered
            try:
                selected_race_id = input.selected_race()
            except Exception:
                selected_race_id = None
            if selected_race_id and selected_race_id != "":
                race = get_race_by_id(int(selected_race_id))
                if race:
                    race_date = race.get('test_date')
                    race_date_str = str(race_date) if race_date else None
                    distance_m = race.get('distance_m', 0)

                    if race_date_str:
                        if distance_m >= 1000:
                            dist_display = f"{distance_m / 1000:.1f}km"
                        else:
                            dist_display = f"{distance_m}m"

                        fig.add_vline(
                            x=race_date_str,
                            line_dash="solid",
                            line_color="#F59E0B",
                            line_width=2.5,
                            annotation_text=f"Course: {dist_display}",
                            annotation_position="top right",
                            annotation_font_size=10,
                            annotation_font_color="#F59E0B"
                        )

                        try:
                            show_sim = input.show_simulated_race()
                        except Exception:
                            show_sim = False
                        if show_sim:
                            try:
                                sim_date = input.simulated_race_date()
                            except Exception:
                                sim_date = None
                            if sim_date:
                                sim_date_str = sim_date.strftime('%Y-%m-%d') if hasattr(sim_date, 'strftime') else str(sim_date)
                                fig.add_vline(
                                    x=sim_date_str,
                                    line_dash="dash",
                                    line_color="#8B5CF6",
                                    line_width=2,
                                    annotation_text=f"Simulation: {dist_display}",
                                    annotation_position="top left",
                                    annotation_font_size=10,
                                    annotation_font_color="#8B5CF6"
                                )
        except Exception as e:
            print(f"Error adding race markers to trend graph: {e}")

        return plotly_to_html(fig)

    @output
    @render.ui
    def pie_types():
        df = meta_df.get()

        if df.empty:
            return plotly_to_html(_create_empty_plotly_fig("Aucune activité", height=500))

        # Grouper types → "Course" (Run+TrailRun combined), "Tapis" (VirtualRun), "Autre" (cross-training)
        type_map = {"run": "Course", "trailrun": "Course", "virtualrun": "Tapis"}
        df_lower = df.copy()
        df_lower["type_lower"] = df_lower["type"].str.lower()
        df_lower["_grp"] = df_lower["type_lower"].map(type_map)
        # Map all non-running activities to "Autre" (cross-training)
        df_lower.loc[df_lower["_grp"].isna(), "_grp"] = "Autre"
        g = df_lower.copy()
        if g.empty:
            return plotly_to_html(_create_empty_plotly_fig("Aucune activité", height=500))
        s = pd.to_numeric(g["duration_sec"], errors="coerce").fillna(0).groupby(g["_grp"]).sum().sort_values(ascending=False)
        if s.sum() <= 0:
            return plotly_to_html(_create_empty_plotly_fig("Aucune durée disponible", height=500))

        labels = s.index.tolist()
        sizes = s.values
        pie_colors = [COLORS.get(lbl, "#999999") for lbl in labels]
        
        # Fonction pour formater le temps en hh:mm:ss
        def format_time(seconds):
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        
        # Créer des labels personnalisés avec nom et temps
        custom_labels = [f"{label}<br>{format_time(size)}" for label, size in zip(labels, sizes)]
        
        fig = go.Figure(data=[go.Pie(
            labels=custom_labels,
            values=sizes,
            marker=dict(colors=pie_colors),
            textposition='auto',
            textinfo='percent',
            hovertemplate='<b>%{label}</b><br>%{percent}<extra></extra>'
        )])
        
        fig.update_layout(
            autosize=True,  # Responsive sizing for production
            title=dict(text="Répartition du temps (période sélectionnée)", font=dict(size=16, color='#262626')),
            height=500,
            showlegend=True,
            legend=dict(orientation="v", x=1.0, y=0.5, font=dict(size=13)),
            margin=dict(l=20, r=20, t=70, b=20),
            font=dict(size=14)
        )
        return plotly_to_html(fig)


    @output
    @render.ui
    def pace_hr_scatter():
        """
        Nuage de points : 1 point par activité (pas d'agrégation par bins)
        - X = allure moyenne par activité (sec/km → min/km)
        - Y = FC moyenne par activité (avg_hr)
        - Couleur = mois (YYYY-MM)
        Bornes:
        - X : 3:30 à 5:00 min/km (210s .. 300s)
        - Y : 110 à 180 bpm (fixed for all athletes)
        """
        df = meta_df.get().copy()

        if df.empty:
            return plotly_to_html(_create_empty_plotly_fig("Aucune activité", height=480))

        # Prépare les colonnes nécessaires
        df["dist_km"] = pd.to_numeric(df.get("distance_m"), errors="coerce") / 1000.0
        df["dur_s"] = pd.to_numeric(df.get("duration_sec"), errors="coerce")
        df["avg_hr"] = pd.to_numeric(df.get("avg_hr"), errors="coerce")
        st = pd.to_datetime(df.get("start_time"), utc=True, errors="coerce")
        st = st.dt.tz_convert("UTC").dt.tz_localize(None)
        df["start_time_naive"] = st

        # Un point par activité : garder celles avec distance, durée et FC valides
        m_valid = (df["dist_km"] > 0) & (df["dur_s"] > 0) & df["avg_hr"].notna() & df["start_time_naive"].notna()
        d = df.loc[m_valid].copy()
        if d.empty:
            return plotly_to_html(_create_empty_plotly_fig("Aucune donnée exploitable (pace/FC)", height=480))

        # Allure moyenne par activité (sec/km)
        d["pace_skm"] = d["dur_s"] / d["dist_km"]

        # Mois (YYYY-MM) pour la couleur
        d["month"] = d["start_time_naive"].dt.to_period("M").astype(str)

        # Filtrer plage d'allures demandée : 3:30..5:00 min/km (210..300 s/km)
        d = d[(d["pace_skm"] >= 210) & (d["pace_skm"] <= 300)].copy()

        if d.empty:
            return plotly_to_html(_create_empty_plotly_fig("Aucun point dans la plage d'allure 3:30–5:00", height=480))

        # Helper for formatting pace
        def format_pace(sec_per_km):
            mins = int(sec_per_km // 60)
            secs = int(sec_per_km % 60)
            return f"{mins}:{secs:02d}"

        # Scatter : un nuage par mois pour une légende claire
        months = sorted(d["month"].unique())
        # Saint-Laurent Sélect color palette - reds, yellows, and warm tones
        colors_club = ['#D92323', '#D9CD23', '#FF6B6B', '#FFB347', '#E63946', '#F4A261',
                       '#DC2626', '#FCD34D', '#EF4444', '#FDE047', '#B91C1C', '#FBBF24',
                       '#991B1B', '#F59E0B', '#7C2D12', '#D97706', '#EA580C', '#FB923C',
                       '#C2410C', '#FDBA74']
        
        fig = go.Figure()
        show_dots = input.show_pace_hr_dots()

        for i, m in enumerate(months):
            gd = d[d["month"] == m]
            color = colors_club[i % len(colors_club)]

            # Scatter points (toggled by checkbox)
            if show_dots:
                fig.add_trace(go.Scatter(
                    x=gd["pace_skm"].values,
                    y=gd["avg_hr"].values,
                    mode='markers',
                    marker=dict(size=8, color=color, opacity=0.85),
                    name=m,
                    customdata=[[format_pace(p)] for p in gd["pace_skm"].values],
                    hovertemplate='<b>%{fullData.name}</b><br>Allure: %{customdata[0]}<br>FC: %{y:.0f} bpm<extra></extra>'
                ))

            # Ligne de tendance par mois
            gdl = gd.dropna(subset=["pace_skm", "avg_hr"]).copy()
            if not gdl.empty:
                gdl["bin"] = (np.floor(gdl["pace_skm"] / 5) * 5).astype(int)
                gdl = gdl[(gdl["bin"] >= 210) & (gdl["bin"] <= 300)]
                if not gdl.empty:
                    b = gdl.groupby("bin", as_index=False)["avg_hr"].mean().sort_values("bin")
                    b["avg_hr"] = b["avg_hr"].rolling(3, center=True, min_periods=1).mean()
                    fig.add_trace(go.Scatter(
                        x=b["bin"].values,
                        y=b["avg_hr"].values,
                        mode='lines',
                        line=dict(color=color, width=2),
                        showlegend=not show_dots,
                        name=m if not show_dots else None,
                        hoverinfo='skip'
                    ))

        # Format X axis ticks (3:30 to 5:00 = 210 to 300 seconds/km)
        tick_vals = [210, 220, 230, 240, 250, 260, 270, 280, 290, 300]
        tick_text = [format_pace(v) for v in tick_vals]
        
        fig.update_layout(
            autosize=True,  # Responsive sizing for production
            xaxis=dict(
                title=dict(text="Allure (min/km)", font=dict(size=14)),
                range=[210, 300],
                tickmode='array',
                tickvals=tick_vals,
                ticktext=tick_text,
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)',
                tickfont=dict(size=12)
            ),
            yaxis=dict(
                title=dict(text="Fréquence cardiaque (bpm)", font=dict(size=14)),
                range=[110, 180],  # Fixed range for consistent comparison across athletes
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)',
                tickfont=dict(size=12)
            ),
            plot_bgcolor='white',
            height=500,
            hovermode='closest',
            legend=dict(title=dict(text="Mois", font=dict(size=13)), orientation="v", x=1.0, y=0.5, font=dict(size=12)),
            margin=dict(l=70, r=120, t=50, b=70)
        )
        return plotly_to_html(fig)

    @output
    @render.ui
    def weekly_volume():
        """Aires empilées hebdomadaires en kilomètres, séparées par type (Run, TrailRun, VirtualRun).
        Semaine calée sur LUNDI dans le fuseau LOCAL_TZ et index complet basé sur un calendrier (sans trous).
        """
        df = meta_df.get()

        if df.empty:
            return plotly_to_html(_create_empty_plotly_fig("Aucune activité", height=480))

        d = df.copy()

        # Convertir en timezone locale pour déterminer correctement les semaines (lundi local)
        st_aware = pd.to_datetime(d.get("start_time"), utc=True, errors="coerce").dt.tz_convert(ZoneInfo(LOCAL_TZ))

        d = d.assign(
            start_time_local=st_aware,
            distance_km=pd.to_numeric(d.get("distance_m"), errors="coerce").fillna(0) / 1000.0,
            _cat=d["type"].astype(str).str.strip().map(lambda t: (
                "TrailRun" if t.lower()=="trailrun" else ("VirtualRun" if t.lower()=="virtualrun" else ("Run" if t.lower()=="run" else None))
            ))
        ).dropna(subset=["start_time_local", "_cat"])  # uniquement les 3 types de course
        if d.empty:
            return plotly_to_html(_create_empty_plotly_fig("Aucune donnée de course", height=480))

        # Lundi local = normaliser à minuit local puis soustraire le weekday (0=lundi)
        wk_start = (d["start_time_local"].dt.floor("D") - pd.to_timedelta(d["start_time_local"].dt.weekday, unit="D"))
        # Rendre naïf (sans tz) pour l'affichage
        d["week_start"] = wk_start.dt.tz_localize(None)

        # Agréger distance par semaine/type
        tmp = d.groupby(["week_start", "_cat"], as_index=False)["distance_km"].sum()
        pivot = tmp.pivot(index="week_start", columns="_cat", values="distance_km").fillna(0.0)

        # Construire un calendrier hebdo complet (tous les lundis) pour éviter les semaines manquantes
        if not pivot.empty:
            first = pivot.index.min()
            last = pivot.index.max()
            full_idx = pd.date_range(first, last, freq="W-MON")
            pivot = pivot.reindex(full_idx, fill_value=0.0)

        cats = ["Run", "TrailRun", "VirtualRun"]
        for c in cats:
            if c not in pivot.columns:
                pivot[c] = 0.0
        pivot = pivot[cats]

        weeks = pivot.index.to_pydatetime()  # Convert to Python datetime objects for Plotly
        if len(weeks) == 0:
            return empty_fig("Aucune semaine disponible")

        # Create stacked area chart - ordered: Tapis (bottom), Trail (middle), Run (top)
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=weeks, y=pivot["VirtualRun"].values,
            name="Tapis",
            mode='lines',
            stackgroup='one',
            fillcolor=COLORS.get("VirtualRun"),
            line=dict(width=0.5, color=COLORS.get("VirtualRun")),
            hovertemplate='<b>Tapis</b><br>%{y:.1f} km<extra></extra>'
        ))
        
        fig.add_trace(go.Scatter(
            x=weeks, y=pivot["TrailRun"].values,
            name="Trail",
            mode='lines',
            stackgroup='one',
            fillcolor=COLORS.get("TrailRun"),
            line=dict(width=0.5, color=COLORS.get("TrailRun")),
            hovertemplate='<b>Trail</b><br>%{y:.1f} km<extra></extra>'
        ))
        
        fig.add_trace(go.Scatter(
            x=weeks, y=pivot["Run"].values,
            name="Run",
            mode='lines',
            stackgroup='one',
            fillcolor=COLORS.get("Run"),
            line=dict(width=0.5, color=COLORS.get("Run")),
            hovertemplate='<b>Run</b><br>%{y:.1f} km<extra></extra>'
        ))
        
        fig.update_layout(
            autosize=True,  # Responsive sizing for production
            title=dict(text="Volume hebdomadaire par type (km)", font=dict(size=16, color='#262626')),
            xaxis=dict(
                title="",
                type='date',
                tickformat='%d %b',  # Format: "15 Nov", "20 Nov", etc.
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)',
                tickfont=dict(size=12),
                autorange=True  # Ensure proper range
            ),
            yaxis=dict(
                title=dict(text="Distance hebdomadaire (km)", font=dict(size=14)),
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)',
                rangemode='tozero',
                tickfont=dict(size=12)
            ),
            plot_bgcolor='white',
            height=500,
            hovermode='x unified',
            legend=dict(x=0, y=1, bgcolor='rgba(255,255,255,0.9)', font=dict(size=13)),
            margin=dict(l=70, r=30, t=70, b=70)
        )
        return plotly_to_html(fig)

    # Pace zone analysis (uses shared date range from date_start/date_end)
    @output
    @render.ui
    @reactive.event(input.date_start, input.date_end, input.athlete, input.incl_vrun)
    def pace_zone_analysis():
        """Display time spent in each pace zone for the selected period using athlete's training zones"""
        # Use shared date range (same as CTL/ATL and other summary graphs)
        pace_start = pd.to_datetime(input.date_start() or date.today()).date()
        pace_end = pd.to_datetime(input.date_end() or date.today()).date()

        # Get athlete's training zones
        zones = zone_time_available_zones.get()
        if not zones:
            return ui.div(
                ui.tags.p("Configurez les zones d'allure pour cet athlete.",
                         style="padding: 2rem; text-align: center; color: #666;")
            )

        # Get athlete ID
        role = user_role.get()
        if role == "coach":
            athlete_name = input.athlete()
            athlete_id = name_to_id.get(athlete_name)
        else:
            athlete_id = user_athlete_id.get()

        if not athlete_id:
            return ui.div(
                ui.tags.p("Aucun athlete selectionne.",
                         style="padding: 2rem; text-align: center; color: #666;")
            )

        # Get all zone numbers
        all_zone_nums = sorted([z["zone_number"] for z in zones])

        # Fetch pre-calculated zone times from materialized view (much faster!)
        weekly_df = fetch_weekly_zone_time_from_view(athlete_id, pace_start, pace_end)

        if weekly_df.empty:
            return ui.div(
                ui.tags.p("Aucune donnée d'allure disponible pour cette période.",
                         style="padding: 2rem; text-align: center; color: #666;")
            )

        # Sum all weeks to get total time per zone
        zone_cols = [c for c in weekly_df.columns if c.startswith("zone_") and c.endswith("_minutes")]
        zone_totals = {}
        total_time_min = 0
        for col in zone_cols:
            zone_num = int(col.replace("zone_", "").replace("_minutes", ""))
            total_min = weekly_df[col].sum()
            zone_totals[zone_num] = total_min
            total_time_min += total_min

        if total_time_min == 0:
            return ui.div(
                ui.tags.p("Aucune donnée d'allure disponible pour cette période.",
                         style="padding: 2rem; text-align: center; color: #666;")
            )

        # Build zone_data with labels from training zones
        zone_data = []
        for zone_info in zones:
            zn = zone_info["zone_number"]
            time_min = zone_totals.get(zn, 0)
            percentage = (time_min / total_time_min) * 100 if total_time_min > 0 else 0
            zone_data.append({
                "zone": zone_info["label"],
                "zone_number": zn,
                "time_min": time_min,
                "percentage": percentage
            })
        
        # Zone colors (matching longitudinal graph)
        zone_colors = {
            1: "#2E86AB",  # Blue - Recovery
            2: "#28A745",  # Green - Aerobic
            3: "#FFC107",  # Yellow - Tempo
            4: "#FD7E14",  # Orange - Threshold
            5: "#DC3545",  # Red - VO2max
        }

        # Create visual bars
        rows = []
        max_time = max([z["time_min"] for z in zone_data]) if zone_data else 1

        for data in zone_data:
            if data["time_min"] < 0.1:  # Skip zones with less than 6 seconds
                continue

            # Calculate bar width percentage
            bar_width = (data["time_min"] / max_time * 100) if max_time > 0 else 0

            # Use zone-specific colors
            color = zone_colors.get(data["zone_number"], "#666")

            rows.append(
                ui.div(
                    ui.layout_columns(
                        ui.div(
                            ui.tags.strong(data["zone"], style="font-size: 1.1rem;"),
                            style="text-align: right; padding-right: 1rem;"
                        ),
                        ui.div(
                            ui.div(
                                style=f"background: {color}; height: 30px; width: {bar_width}%; border-radius: 4px; display: inline-block;"
                            ),
                            ui.tags.span(
                                f"{data['time_min']:.1f} min ({data['percentage']:.1f}%)",
                                style="margin-left: 0.5rem; font-weight: 600; color: #374151;"
                            ),
                            style="display: flex; align-items: center;"
                        ),
                        col_widths=[3, 9]
                    ),
                    style="padding: 0.5rem 0; border-bottom: 1px solid #e5e7eb;"
                )
            )

        # Number of weeks in the data
        num_weeks = len(weekly_df)

        return ui.div(
            ui.div(
                ui.tags.p(
                    f"Temps total analyse: {total_time_min:.1f} minutes ({num_weeks} semaines)",
                    style="font-size: 1.1rem; color: #666; margin-bottom: 1.5rem; text-align: center;"
                )
            ),
            ui.div(
                *rows,
                style="padding: 1rem;"
            )
        )

    # ----------------- Longitudinal Zone Time Graph -----------------
    # Reactive value to store available zones for current athlete
    zone_time_available_zones = reactive.Value([])

    @reactive.Effect
    @reactive.event(input.athlete, user_athlete_id)
    def _update_zone_time_zones():
        """Load available pace zones when athlete changes."""
        print("[DEBUG] _update_zone_time_zones called", flush=True)
        role = user_role.get()
        if role == "coach":
            # input.athlete() returns athlete NAME, convert to athlete_id
            athlete_name = input.athlete()
            athlete_id = name_to_id.get(athlete_name)
        else:
            athlete_id = user_athlete_id.get()

        if not athlete_id:
            zone_time_available_zones.set([])
            return

        zones_df = fetch_athlete_training_zones(athlete_id)
        print(f"[ZONE_EFFECT] zones_df rows = {len(zones_df)}", flush=True)
        if zones_df.empty:
            zone_time_available_zones.set([])
            return

        # Build list for UI
        zones_list = []
        for _, row in zones_df.iterrows():
            pmin = row["pace_min_sec_per_km"]
            pmax = row["pace_max_sec_per_km"]
            zones_list.append({
                "zone_number": int(row["zone_number"]),
                "label": row["zone_label"],
                "pace_min": None if pd.isna(pmin) else float(pmin),
                "pace_max": None if pd.isna(pmax) else float(pmax)
            })
        zone_time_available_zones.set(zones_list)

    @output
    @render.ui
    def zone_time_checkboxes():
        """Dynamically render zone multi-select checkboxes."""
        zones = zone_time_available_zones.get()
        if not zones:
            return ui.div(
                ui.tags.p("Aucune zone d'allure configuree pour cet athlete.",
                         style="color: #666; font-style: italic; padding: 0.5rem;")
            )

        # Build checkbox choices - allow 1 to all zones
        choices = {str(z["zone_number"]): z["label"] for z in zones}

        # Default: select all zones
        default_selected = [str(z["zone_number"]) for z in zones]

        return ui.input_checkbox_group(
            "zone_time_zones",
            "",
            choices=choices,
            selected=default_selected,
            inline=True
        )

    # Race selector dropdown for "Résumé de période"
    @render.ui
    def race_selector_dropdown():
        """Render race selector dropdown based on current athlete."""
        print("[DEBUG] race_selector_dropdown called", flush=True)
        try:
            role = user_role.get()
            if role == "coach":
                try:
                    athlete_name = input.athlete()
                except Exception:
                    athlete_name = None
                athlete_id = name_to_id.get(athlete_name) if athlete_name else None
            else:
                athlete_id = user_athlete_id.get()

            if not athlete_id:
                return ui.p("Sélectionnez un athlète", style="color: #666; font-style: italic; margin: 0;")

            races = get_athlete_races(athlete_id)

            if not races:
                return ui.p("Aucune course enregistrée", style="color: #666; font-style: italic; margin: 0;")
        except Exception as e:
            print(f"Error in race_selector_dropdown: {e}")
            return ui.p("Erreur de chargement", style="color: #666; font-style: italic; margin: 0;")

        # Build choices dict
        choices = {"": "-- Sélectionner une course --"}
        for race in races:
            race_id = str(race.get("id", ""))
            test_date = race.get("test_date", "")
            distance_m = race.get("distance_m", 0)
            race_time = race.get("race_time_seconds")

            # Format label: "2025-03-15 - 10000m (42:30)"
            label = f"{test_date} - {distance_m}m"
            if race_time:
                time_str = format_time_from_seconds(race_time)
                label += f" ({time_str})"

            choices[race_id] = label

        return ui.input_select(
            "selected_race",
            "",
            choices=choices,
            width="250px"
        )

    # Simulated race date input (shown only when checkbox is checked)
    @render.ui
    def simulated_race_date_input():
        """Render date input for race simulation."""
        try:
            show_sim = input.show_simulated_race()
        except Exception:
            show_sim = False
        if not show_sim:
            return ui.div()  # Hidden when checkbox unchecked

        return ui.input_date(
            "simulated_race_date",
            "Date simulée:",
            value=str(datetime.now().date()),
            width="150px"
        )

    @render.ui
    def zone_change_banner():
        """Show info banner when zone configuration changed within selected date range."""
        print("[DEBUG] zone_change_banner called", flush=True)
        try:
            start_date = pd.to_datetime(input.date_start()).date()
            end_date = pd.to_datetime(input.date_end()).date()
        except Exception:
            return None

        if start_date > end_date:
            start_date, end_date = end_date, start_date

        # Get athlete ID
        role = user_role.get()
        if role == "coach":
            athlete_name = input.athlete()
            athlete_id = name_to_id.get(athlete_name)
        else:
            athlete_id = user_athlete_id.get()

        if not athlete_id:
            return None

        # Check for zone changes
        zone_changes = get_zone_changes_in_range(athlete_id, start_date, end_date)

        if not zone_changes:
            return None

        # Build banner message
        if len(zone_changes) == 1:
            change_date = zone_changes[0]["effective_from_date"]
            date_str = change_date.strftime("%d %B %Y") if hasattr(change_date, 'strftime') else str(change_date)
            msg = f"Les zones d'entrainement ont change le {date_str}. Les activites avant cette date utilisent des limites differentes."
        else:
            dates = [c["effective_from_date"].strftime("%d %b") if hasattr(c["effective_from_date"], 'strftime') else str(c["effective_from_date"]) for c in zone_changes]
            msg = f"Les zones d'entrainement ont change {len(zone_changes)} fois ({', '.join(dates)}). Chaque activite utilise les zones en vigueur a sa date."

        # Return styled banner
        return ui.div(
            ui.tags.span("Info:", style="font-weight: 600; margin-right: 0.5rem;"),
            msg,
            style="background-color: #e0f2fe; border: 1px solid #7dd3fc; border-radius: 6px; padding: 0.75rem 1rem; margin-bottom: 0.5rem; color: #0369a1; font-size: 0.9rem;"
        )

    @output
    @render.ui
    def zone_time_longitudinal():
        """Render longitudinal zone time chart with multi-zone support and merge/distinct modes."""
        print("[ZONE_LONG] Starting zone_time_longitudinal render...", flush=True)
        zones = zone_time_available_zones.get()
        print(f"[ZONE_LONG] Got zones: {len(zones) if zones else 0}", flush=True)
        if not zones:
            return plotly_to_html(_create_empty_plotly_fig("Configurez les zones d'allure pour cet athlete", height=360))

        # Get selected zones (now multiple from checkbox group)
        selected = input.zone_time_zones()
        print(f"[ZONE_LONG] Selected zones: {selected}", flush=True)
        if not selected or len(selected) == 0:
            return plotly_to_html(_create_empty_plotly_fig("Selectionnez au moins une zone", height=360))

        # Convert to list of integers
        selected_zones = sorted([int(z) for z in selected])

        # Get display mode (merge or distinct)
        display_mode = input.zone_display_mode() or "distinct"

        # Get date range (use same as CTL/ATL graph)
        try:
            start_date = pd.to_datetime(input.date_start()).date()
            end_date = pd.to_datetime(input.date_end()).date()
        except Exception:
            return plotly_to_html(_create_empty_plotly_fig("Selectionnez une periode valide", height=360))

        if start_date > end_date:
            start_date, end_date = end_date, start_date

        # Get athlete ID
        role = user_role.get()
        if role == "coach":
            athlete_name = input.athlete()
            athlete_id = name_to_id.get(athlete_name)
        else:
            athlete_id = user_athlete_id.get()

        if not athlete_id:
            return plotly_to_html(_create_empty_plotly_fig("Aucun athlete selectionne", height=360))

        # Fetch pre-calculated zone times from materialized view
        weekly_df = fetch_weekly_zone_time_from_view(athlete_id, start_date, end_date)

        if weekly_df.empty:
            return plotly_to_html(_create_empty_plotly_fig("Aucune donnee pour cette periode", height=360))

        # Fill missing weeks with 0
        weekly_df["week_start"] = pd.to_datetime(weekly_df["week_start"])

        # Create full week range (Monday to Monday)
        first_week = start_date - timedelta(days=start_date.weekday())
        last_week = end_date - timedelta(days=end_date.weekday())
        full_weeks = pd.date_range(first_week, last_week, freq="W-MON")

        # Drop non-numeric columns before reindex (fill_value=0 fails on string cols like athlete_id)
        non_numeric_cols = weekly_df.select_dtypes(exclude='number').columns.difference(["week_start"])
        weekly_df = weekly_df.drop(columns=non_numeric_cols, errors="ignore")
        weekly_df = weekly_df.set_index("week_start").reindex(full_weeks, fill_value=0).reset_index()
        weekly_df = weekly_df.rename(columns={"index": "week_start"})

        # Get MA window from ATL input (simpler: just one EWM line per zone)
        atl_days = int(input.atl_days() or 7)
        atl_weeks = max(1.0, atl_days / 7.0)  # Use float for finer granularity

        fig = go.Figure()

        if display_mode == "merge":
            # MERGE MODE: Stacked bar chart showing each zone as a segment
            zone_cols = [f"zone_{z}_minutes" for z in selected_zones if f"zone_{z}_minutes" in weekly_df.columns]
            if not zone_cols:
                return plotly_to_html(_create_empty_plotly_fig("Aucune donnee pour les zones selectionnees", height=360))

            # Apply EWM smoothing to each zone individually
            smoothed_data = {}
            for zn in selected_zones:
                col_raw = f"zone_{zn}_minutes"
                if col_raw in weekly_df.columns:
                    smoothed_data[zn] = weekly_df[col_raw].ewm(
                        span=atl_weeks, min_periods=max(1, int(atl_weeks)), adjust=False
                    ).mean()

            # Filter valid data (where smoothing has enough history)
            valid_mask = pd.Series(True, index=weekly_df.index)
            for zn in smoothed_data:
                valid_mask &= smoothed_data[zn].notna()

            display_df = weekly_df[valid_mask].copy()

            if display_df.empty:
                return plotly_to_html(_create_empty_plotly_fig("Pas assez d'historique pour la moyenne mobile", height=360))

            # Check if all values are zero
            total_sum = sum(smoothed_data[zn][valid_mask].sum() for zn in smoothed_data)
            if total_sum < 0.1:
                return plotly_to_html(_create_empty_plotly_fig("Aucune donnee GPS/allure pour cet athlete", height=360))

            # Convert x-axis dates to strings for Plotly
            x_dates = [d.strftime('%Y-%m-%d') for d in display_df["week_start"]]

            # Create stacked bar chart - Z1 at bottom, higher zones stacked on top
            for zn in sorted(selected_zones):
                if zn not in smoothed_data:
                    continue

                y_values = smoothed_data[zn][valid_mask].tolist()

                # Get zone label
                zone_info = next((z for z in zones if z["zone_number"] == zn), None)
                label = zone_info["label"] if zone_info else f"Zone {zn}"

                fig.add_trace(go.Bar(
                    x=x_dates,
                    y=y_values,
                    name=label,
                    marker_color=ZONE_COLORS.get(zn, "#888888"),
                    hovertemplate=f"{label}<br>Sem. %{{x|%d %b}}<br>%{{y:.1f}} min<extra></extra>"
                ))

            # Group bars side-by-side within each week
            fig.update_layout(
                barmode='group',
                bargap=0.15,        # Gap between weeks
                bargroupgap=0.05    # Gap between bars within same week
            )

            # Title
            zone_labels = ", ".join([f"Z{z}" for z in selected_zones])
            title_text = f"Temps par zone ({zone_labels}) — MA {atl_weeks}sem"

        else:
            # DISTINCT MODE: Separate line per zone
            has_data = False

            for zn in selected_zones:
                col_raw = f"zone_{zn}_minutes"
                if col_raw not in weekly_df.columns:
                    continue

                # Apply EWM smoothing
                col_ewm = f"zone_{zn}_ewm"
                weekly_df[col_ewm] = weekly_df[col_raw].ewm(
                    span=atl_weeks, min_periods=max(1, int(atl_weeks)), adjust=False
                ).mean()

                # Filter valid data
                display_df = weekly_df[weekly_df[col_ewm].notna()].copy()

                if display_df.empty or display_df[col_ewm].max() < 0.1:
                    continue

                has_data = True

                # Get zone label
                zone_info = next((z for z in zones if z["zone_number"] == zn), None)
                label = zone_info["label"] if zone_info else f"Zone {zn}"

                # Get color for this zone
                zone_color = ZONE_COLORS.get(zn, "#888888")

                # Convert for Plotly
                x_dates = [d.strftime('%Y-%m-%d') for d in display_df["week_start"]]
                y_values = display_df[col_ewm].tolist()

                # Add trace for this zone
                fig.add_trace(go.Scatter(
                    x=x_dates,
                    y=y_values,
                    name=label,
                    line=dict(color=zone_color, width=2.5),
                    mode='lines',
                    hovertemplate=f"{label}<br>Sem. %{{x|%d %b}}<br>%{{y:.1f}} min<extra></extra>"
                ))

            if not has_data:
                return plotly_to_html(_create_empty_plotly_fig("Aucune donnee GPS/allure pour les zones selectionnees", height=360))

            # Title for distinct mode
            if len(selected_zones) == 1:
                zone_info = next((z for z in zones if z["zone_number"] == selected_zones[0]), None)
                title_text = f"Temps en {zone_info['label'] if zone_info else f'Zone {selected_zones[0]}'} — MA {atl_weeks}sem"
            else:
                title_text = f"Temps par zone — MA {atl_weeks}sem"

        # ACL/ATL overlay lines (works in both modes)
        if input.show_acl_atl():
            # Calculate total minutes across all selected zones
            zone_cols = [f"zone_{z}_minutes" for z in selected_zones if f"zone_{z}_minutes" in weekly_df.columns]
            if zone_cols:
                weekly_df["total_selected_minutes"] = weekly_df[zone_cols].sum(axis=1)

                # Get CTL days for chronic load
                ctl_days = int(input.ctl_days() or 28)
                ctl_weeks = max(1.0, ctl_days / 7.0)  # Use float for finer granularity

                # ACL (Acute) - short-term using atl_weeks
                acl_values = weekly_df["total_selected_minutes"].ewm(
                    span=atl_weeks, min_periods=max(1, int(atl_weeks)), adjust=False
                ).mean()

                # ATL (Chronic) - long-term using ctl_weeks
                atl_values = weekly_df["total_selected_minutes"].ewm(
                    span=ctl_weeks, min_periods=max(1, int(ctl_weeks)), adjust=False
                ).mean()

                # Filter to valid data (where both have enough history)
                valid_mask = acl_values.notna() & atl_values.notna()
                if valid_mask.any():
                    acl_display = weekly_df[valid_mask].copy()
                    x_acl_dates = [d.strftime('%Y-%m-%d') for d in acl_display["week_start"]]

                    # Add ACL line (dashed, red)
                    fig.add_trace(go.Scatter(
                        x=x_acl_dates,
                        y=acl_values[valid_mask].tolist(),
                        name=f"ACL ({atl_days}j)",
                        line=dict(color="#E63946", width=2, dash="dash"),
                        mode='lines',
                        hovertemplate="ACL<br>Sem. %{x|%d %b}<br>%{y:.1f} min<extra></extra>"
                    ))

                    # Add ATL line (solid, navy)
                    fig.add_trace(go.Scatter(
                        x=x_acl_dates,
                        y=atl_values[valid_mask].tolist(),
                        name=f"ATL ({ctl_days}j)",
                        line=dict(color="#1D3557", width=2.5),
                        mode='lines',
                        hovertemplate="ATL<br>Sem. %{x|%d %b}<br>%{y:.1f} min<extra></extra>"
                    ))

        # Monotony and Strain overlay lines (Phase 2Y)
        if input.show_monotony() or input.show_strain():
            # Fetch pre-calculated data
            ms_result_df = fetch_weekly_monotony_strain_from_db(
                athlete_id, start_date, end_date, selected_zones
            )
            # Fallback to on-the-fly calculation if no pre-calculated data
            if ms_result_df.empty:
                daily_df = fetch_daily_zone_time(athlete_id, start_date, end_date)
                if not daily_df.empty:
                    ms_result_df = calculate_weekly_monotony_strain(
                        daily_df, selected_zones, start_date, end_date
                    )

            if not ms_result_df.empty:
                x_ms_dates = [d.strftime('%Y-%m-%d') for d in ms_result_df["week_start"]]

                # Monotony overlay (purple dotted, yaxis2)
                if input.show_monotony():
                    y_monotony = ms_result_df["monotony"].tolist()
                    fig.add_trace(go.Scatter(
                        x=x_ms_dates,
                        y=y_monotony,
                        name="Monotonie",
                        line=dict(color="#8B5CF6", width=2, dash="dot"),
                        mode='lines',
                        yaxis='y2',
                        hovertemplate="Monotonie<br>Sem. %{x|%d %b}<br>%{y:.2f}<extra></extra>"
                    ))

                # Strain overlay (red dash-dot, yaxis3)
                if input.show_strain():
                    y_strain = ms_result_df["strain"].tolist()
                    fig.add_trace(go.Scatter(
                        x=x_ms_dates,
                        y=y_strain,
                        name="Strain",
                        line=dict(color="#EF4444", width=2, dash="dashdot"),
                        mode='lines',
                        yaxis='y3',
                        hovertemplate="Strain<br>Sem. %{x|%d %b}<br>%{y:.0f}<extra></extra>"
                    ))

        # Set X-axis range
        if 'x_dates' in locals() and x_dates:
            x_range = [x_dates[0], x_dates[-1]]
        else:
            x_range = [first_week.strftime('%Y-%m-%d'), last_week.strftime('%Y-%m-%d')]

        # Add vertical lines for zone configuration changes
        zone_changes = get_zone_changes_in_range(athlete_id, start_date, end_date)
        for change in zone_changes:
            change_date = change["effective_from_date"]
            date_str = change_date.strftime('%Y-%m-%d') if hasattr(change_date, 'strftime') else str(change_date)
            fig.add_vline(
                x=date_str,
                line_dash="dash",
                line_color="#6b7280",
                line_width=1.5,
                annotation_text="Zones modifiees",
                annotation_position="top",
                annotation_font_size=10,
                annotation_font_color="#6b7280"
            )

        # Add race markers (vertical lines)
        try:
            # Safely get selected_race - might not exist if dropdown wasn't rendered
            try:
                selected_race_id = input.selected_race()
            except Exception:
                selected_race_id = None
            if selected_race_id and selected_race_id != "":
                race = get_race_by_id(int(selected_race_id))
                if race:
                    # Real race marker (gold/amber color)
                    race_date = race.get('test_date')
                    race_date_str = str(race_date) if race_date else None
                    distance_m = race.get('distance_m', 0)

                    if race_date_str:
                        # Format distance for display
                        if distance_m >= 1000:
                            dist_display = f"{distance_m / 1000:.1f}km"
                        else:
                            dist_display = f"{distance_m}m"

                        fig.add_vline(
                            x=race_date_str,
                            line_dash="solid",
                            line_color="#F59E0B",
                            line_width=2.5,
                            annotation_text=f"Course: {dist_display}",
                            annotation_position="top right",
                            annotation_font_size=10,
                            annotation_font_color="#F59E0B"
                        )

                        # Simulated race marker (if enabled)
                        try:
                            show_sim = input.show_simulated_race()
                        except Exception:
                            show_sim = False
                        if show_sim:
                            try:
                                sim_date = input.simulated_race_date()
                            except Exception:
                                sim_date = None
                            if sim_date:
                                sim_date_str = sim_date.strftime('%Y-%m-%d') if hasattr(sim_date, 'strftime') else str(sim_date)
                                fig.add_vline(
                                    x=sim_date_str,
                                    line_dash="dash",
                                    line_color="#8B5CF6",
                                    line_width=2,
                                    annotation_text=f"Simulation: {dist_display}",
                                    annotation_position="top left",
                                    annotation_font_size=10,
                                    annotation_font_color="#8B5CF6"
                                )
        except Exception as e:
            print(f"Error adding race markers: {e}")

        # Build layout configuration
        layout_config = dict(
            autosize=True,
            title=dict(
                text=title_text,
                font=dict(size=16, color='#262626')
            ),
            xaxis=dict(
                title="Date",
                type='date',
                tickformat='%d %b',
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)',
                dtick="M1",
                range=x_range
            ),
            yaxis=dict(
                title="Minutes par semaine",
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)',
                rangemode='tozero'
            ),
            plot_bgcolor='white',
            height=400,
            hovermode='x unified',
            legend=dict(
                x=0, y=1,
                bgcolor='rgba(255,255,255,0.9)',
                font=dict(size=11),
                orientation='h'
            ),
            margin=dict(l=70, r=30, t=70, b=70)
        )

        # Add secondary Y-axis for Monotony (purple, right side)
        if input.show_monotony():
            layout_config['yaxis2'] = dict(
                title=dict(text="Monotonie", font=dict(color="#8B5CF6")),
                tickfont=dict(color="#8B5CF6"),
                overlaying='y',
                side='right',
                showgrid=False,
                rangemode='tozero'
            )

        # Add third Y-axis for Strain (red, far right with offset)
        if input.show_strain():
            layout_config['yaxis3'] = dict(
                title=dict(text="Strain", font=dict(color="#EF4444")),
                tickfont=dict(color="#EF4444"),
                overlaying='y',
                side='right',
                position=0.95,
                showgrid=False,
                rangemode='tozero'
            )
            # Adjust right margin and x-axis domain to make room for third axis
            layout_config['margin'] = dict(l=70, r=80, t=70, b=70)
            layout_config['xaxis']['domain'] = [0, 0.9]

        fig.update_layout(**layout_config)

        return plotly_to_html(fig)

    # ----------------- Analyse de séance (X/Y dynamiques) -----------------
    @reactive.Calc
    def current_activity_id() -> str | None:
        """Get current activity ID from dropdown selection."""
        mapping = act_label_to_id.get() or {}
        sel = input.activity_sel()
        return mapping.get(sel, sel) if sel else None
    
    @reactive.Effect
    @reactive.event(input.activity_sel)
    def _update_yvar_choices():
        """Update Y-axis choices based on available data in selected activity."""
        act_id = current_activity_id()
        if not act_id:
            return
        
        try:
            df = fetch_timeseries_cached(str(act_id))
            if df.empty:
                return
        except:
            return
        
        # Build choices based on available data - check all 7 metrics
        # Using French labels as BOTH label and value (matching initial UI setup)
        choices = {}
        
        # 1. Fréquence cardiaque (always available if heartrate exists)
        if "heartrate" in df.columns and df["heartrate"].notna().any():
            choices["Fréquence cardiaque"] = "Fréquence cardiaque"
        
        # 2. Cadence (always available if cadence exists)
        if "cadence" in df.columns and df["cadence"].notna().any():
            choices["Cadence"] = "Cadence"
        
        # 3. Allure/Pace (always available if speed exists)
        if any(col in df.columns for col in ["speed", "enhanced_speed", "velocity_smooth"]):
            choices["Allure (min/km)"] = "Allure (min/km)"
        
        # 4. Altitude
        if "enhanced_altitude" in df.columns and df["enhanced_altitude"].notna().any():
            choices["Altitude"] = "Altitude"
        
        # 5. Puissance
        if "watts" in df.columns and df["watts"].notna().any():
            choices["Puissance"] = "Puissance"
        
        # 6. Oscillation verticale
        if "vertical_oscillation" in df.columns and df["vertical_oscillation"].notna().any():
            choices["Oscillation verticale"] = "Oscillation verticale"
        
        # 7. Temps de contact au sol (GCT)
        if "ground_contact_time" in df.columns and df["ground_contact_time"].notna().any():
            choices["Temps de contact au sol (GCT)"] = "Temps de contact au sol (GCT)"

        # 8. Leg Spring Stiffness (LSS)
        if "leg_spring_stiffness" in df.columns and df["leg_spring_stiffness"].notna().any():
            choices["Leg Spring Stiffness (LSS)"] = "Leg Spring Stiffness (LSS)"

        # Update both primary and secondary Y-axis selects with SAME choices
        current_selection_y1 = input.yvar()
        current_selection_y2 = input.yvar2()
        
        # Secondary choices include "Aucun" option + all same metrics
        choices_y2 = {"Aucun": "none"}
        choices_y2.update(choices)
        
        # Ensure selected value is valid, otherwise default to French labels
        selected_y1 = current_selection_y1 if current_selection_y1 in choices.values() else "Fréquence cardiaque"
        selected_y2 = current_selection_y2 if current_selection_y2 in choices_y2.values() else "none"
        
        # Debug: Print choices to verify format
        print(f"Updating yvar choices: {choices}")
        print(f"Updating yvar2 choices: {choices_y2}")
        print(f"Selected y1: {selected_y1}, Selected y2: {selected_y2}")
        
        # Update dropdowns with standard Shiny method
        # Since values are now French labels, selectize will display them correctly
        try:
            ui.update_select("yvar", choices=choices, selected=selected_y1)
            ui.update_select("yvar2", choices=choices_y2, selected=selected_y2)
            print("Dropdowns updated successfully")
            print(f"Final selections: y1={selected_y1}, y2={selected_y2}")
        except Exception as e:
            print(f"Error updating dropdowns: {e}")

    @reactive.Calc
    def xy_data():
        """Prépare (x, y, labels, formatters) en fonction de xvar/yvar et de l’activité sélectionnée.
        Ajoute un mémo en mémoire pour éviter de recalculer quand on revient sur la même activité/axes.
        """
        act_id = current_activity_id()
        if not act_id:
            return None
        raw_x = (input.xvar() or "moving")
        raw_y = (input.yvar() or "heartrate")
        xvar = XVAR_ALIASES.get(raw_x, "moving")
        yvar = YVAR_ALIASES.get(raw_y, "heartrate")

        # Tiny memo cache by (act_id, xvar, yvar)
        if not hasattr(xy_data, "_memo"):
            xy_data._memo = {}
        key = (str(act_id), xvar, yvar)
        memo = xy_data._memo.get(key)
        if memo is not None:
            return memo

        df = fetch_timeseries_cached(str(act_id)).copy()
        if df.empty:
            return None

        # Récupérer le type d'activité pour l'algorithme Strava
        info = (id_to_info.get() or {}).get(str(act_id), {})
        activity_type = (info.get("type") or "run").lower()

        x, y, x_label, y_label, x_fmt, y_fmt = _prep_xy(df, xvar=xvar, yvar=yvar, activity_type=activity_type, smooth_win=21)
        res = {"x":x, "y":y, "x_label":x_label, "y_label":y_label, "x_fmt":x_fmt, "y_fmt":y_fmt, "act_id":str(act_id)}
        xy_data._memo[key] = res
        return res

    @output
    @render.ui
    def plot_xy():
        d = xy_data()

        if not d:
            # Return empty figure with message
            fig = go.Figure()
            fig.add_annotation(
                text="Sélectionnez une activité",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=20, color="#666")
            )
            fig.update_layout(
                xaxis=dict(visible=False),
                yaxis=dict(visible=False),
                height=560,
                plot_bgcolor="white"
            )
            return plotly_to_html(fig)

        # Check if secondary Y-axis is requested
        try:
            raw_y2 = (input.yvar2() or "none")
        except:
            raw_y2 = "none"

        yvar2 = YVAR_ALIASES.get(raw_y2, "none")
        raw_y1 = input.yvar() or "heartrate"
        yvar1 = YVAR_ALIASES.get(raw_y1, "heartrate")
        has_secondary = yvar2 != "none" and yvar2 != yvar1

        # Get info for activity metadata
        info = (id_to_info.get() or {}).get(d["act_id"], {})

        # Initialize secondary Y variables
        y2 = None
        y2_label = ""
        y2_fmt = None

        if has_secondary:
            # Prepare secondary Y data
            try:
                act_id = current_activity_id()
                df = fetch_timeseries_cached(act_id)
                activity_type = (info.get("type") or "run").lower()
                raw_x = (input.xvar() or "moving")
                xvar = XVAR_ALIASES.get(raw_x, "moving")
                _, y2, _, y2_label, _, y2_fmt = _prep_xy(df, xvar=xvar, yvar=yvar2, activity_type=activity_type, smooth_win=21)
            except Exception as e:
                print(f"Error preparing secondary Y-axis: {e}")
                import traceback
                traceback.print_exc()
                has_secondary = False

        # Get FULL x values for reference (before filtering)
        x_values_full = d["x"]
        x_is_time = d["x_fmt"] is not None

        # Apply range filter from sliders
        # Store unfiltered y2 for fallback
        y2_full = y2.copy() if (has_secondary and y2 is not None) else None

        try:
            range_start = input.range_start()
            range_end = input.range_end()
            # Create mask to filter data to selected range
            mask = (x_values_full >= range_start) & (x_values_full <= range_end)
            x_values = x_values_full[mask]
            y_values = d["y"][mask]
            if has_secondary and y2 is not None:
                y2 = y2[mask]
            # If filtering resulted in empty data, fall back to full data
            if len(x_values) == 0:
                x_values = x_values_full
                y_values = d["y"]
                if has_secondary and y2_full is not None:
                    y2 = y2_full
        except:
            # Sliders not initialized yet, use full data
            x_values = x_values_full
            y_values = d["y"]
            if has_secondary and y2_full is not None:
                y2 = y2_full
        
        # Helper function to format seconds to hh:mm:ss or mm:ss
        def format_time(seconds):
            if np.isnan(seconds):
                return "N/A"
            total_sec = int(seconds)
            hours = total_sec // 3600
            minutes = (total_sec % 3600) // 60
            secs = total_sec % 60
            if hours > 0:
                return f"{hours}:{minutes:02d}:{secs:02d}"
            else:
                return f"{minutes}:{secs:02d}"
        
        if x_is_time:
            x_hover = [format_time(val) for val in x_values]
        else:
            x_hover = x_values

        # Format y-axis values if needed (for pace, or float metrics)
        # Note: y_values is already filtered above via range sliders
        y_is_time = d["y_fmt"] is not None

        # Rounding rules for float metrics in hover display
        _hover_format = {
            "vertical_oscillation": ".1f",
            "leg_spring_stiffness": ".2f",
        }

        if y_is_time:
            y_hover = [format_time(val) for val in y_values]
        elif yvar1 in _hover_format:
            fmt = _hover_format[yvar1]
            y_hover = [f"{v:{fmt}}" if not np.isnan(v) else "N/A" for v in y_values]
        else:
            y_hover = y_values
        
        # Create the figure (with or without secondary Y-axis)
        if has_secondary:
            from plotly.subplots import make_subplots
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            # Primary Y-axis trace
            fig.add_trace(
                go.Scatter(
                    x=x_values,
                    y=y_values,
                    mode='lines',
                    line=dict(color='#D92323', width=2.5),
                    hovertemplate='<b>' + d["x_label"] + ':</b> %{customdata[0]}<br>' +
                                 '<b>' + d["y_label"] + ':</b> %{customdata[1]}<br>' +
                                 '<extra></extra>',
                    customdata=list(zip(x_hover, y_hover)),
                    name=d["y_label"]
                ),
                secondary_y=False
            )
            
            # Secondary Y-axis trace (only if y2 data exists)
            if y2 is not None and len(y2) > 0:
                y2_is_time = y2_fmt is not None
                if y2_is_time:
                    y2_hover = [format_time(val) for val in y2]
                elif yvar2 in _hover_format:
                    fmt = _hover_format[yvar2]
                    y2_hover = [f"{v:{fmt}}" if not np.isnan(v) else "N/A" for v in y2]
                else:
                    y2_hover = y2
                
                fig.add_trace(
                    go.Scatter(
                        x=x_values,
                        y=y2,
                        mode='lines',
                        line=dict(color='#D9CD23', width=2.5, dash='dash'),
                        hovertemplate='<b>' + d["x_label"] + ':</b> %{customdata[0]}<br>' +
                                     '<b>' + y2_label + ':</b> %{customdata[1]}<br>' +
                                     '<extra></extra>',
                        customdata=list(zip(x_hover, y2_hover)),
                        name=y2_label
                    ),
                    secondary_y=True
                )
        else:
            fig = go.Figure()
            
            fig.add_trace(go.Scatter(
                x=x_values,
                y=y_values,
                mode='lines',
                line=dict(color='#D92323', width=2.5),
                hovertemplate='<b>' + d["x_label"] + ':</b> %{customdata[0]}<br>' +
                             '<b>' + d["y_label"] + ':</b> %{customdata[1]}<br>' +
                             '<extra></extra>',
                customdata=list(zip(x_hover, y_hover)),
                name=''
            ))
        
        # Build X-axis configuration
        xaxis_config = dict(
            title=d["x_label"],
            showgrid=True,
            gridcolor='rgba(128, 128, 128, 0.2)',
            zeroline=False,
            autorange=True  # Ensure proper range, prevents compression
        )
        
        # Add custom tick formatting for time-based X-axis
        if x_is_time:
            # Create tick values at reasonable intervals
            x_min, x_max = x_values.min(), x_values.max()
            x_range = x_max - x_min
            
            # Determine tick interval based on range
            if x_range <= 300:  # <= 5 minutes
                tick_interval = 30  # 30 seconds
            elif x_range <= 900:  # <= 15 minutes
                tick_interval = 60  # 1 minute
            elif x_range <= 1800:  # <= 30 minutes
                tick_interval = 120  # 2 minutes
            elif x_range <= 3600:  # <= 1 hour
                tick_interval = 300  # 5 minutes
            else:
                tick_interval = 600  # 10 minutes
            
            # Generate tick values starting from x_min (rounded down to nearest tick)
            tick_start = (int(x_min) // tick_interval) * tick_interval
            tick_vals = np.arange(tick_start, x_max + tick_interval, tick_interval)
            tick_vals = tick_vals[(tick_vals >= x_min) & (tick_vals <= x_max)]
            
            # Format tick labels
            tick_text = [format_time(val) for val in tick_vals]
            
            xaxis_config['tickmode'] = 'array'
            xaxis_config['tickvals'] = tick_vals
            xaxis_config['ticktext'] = tick_text
        
        # Build Y-axis configuration
        yaxis_config = dict(
            title=d["y_label"],
            showgrid=True,
            gridcolor='rgba(128, 128, 128, 0.2)',
            zeroline=False
        )
        
        # Add custom tick formatting for pace Y-axis
        if y_is_time:
            # Reverse the axis for pace (faster at top, slower at bottom)
            yaxis_config['autorange'] = 'reversed'
            
            # Create tick values for pace
            y_min_clean = np.nanmin(y_values)
            y_max_clean = np.nanmax(y_values)
            
            if not np.isnan(y_min_clean) and not np.isnan(y_max_clean):
                # Generate reasonable pace tick values (e.g., 4:00, 4:30, 5:00, etc.)
                y_min_minutes = int(y_min_clean // 60)
                y_max_minutes = int(y_max_clean // 60) + 1
                
                pace_ticks = []
                for minute in range(y_min_minutes, y_max_minutes + 1):
                    pace_ticks.append(minute * 60)  # On the minute
                    if minute < y_max_minutes:
                        pace_ticks.append(minute * 60 + 30)  # Half minute
                
                pace_ticks = [t for t in pace_ticks if y_min_clean <= t <= y_max_clean]
                pace_labels = [format_time(t) for t in pace_ticks]
                
                yaxis_config['tickmode'] = 'array'
                yaxis_config['tickvals'] = pace_ticks
                yaxis_config['ticktext'] = pace_labels
        
        # Update layout (different approach for single vs dual Y-axis)
        if has_secondary:
            # Use update_xaxes and update_yaxes for subplots
            fig.update_xaxes(**xaxis_config)
            
            # Primary Y-axis configuration
            primary_y_config = dict(title_text=d["y_label"], showgrid=True, gridcolor='rgba(128, 128, 128, 0.2)')
            if y_is_time:  # Reverse if pace
                primary_y_config['autorange'] = 'reversed'
            fig.update_yaxes(**primary_y_config, secondary_y=False)
            
            # Secondary Y-axis configuration
            secondary_y_config = dict(title_text=y2_label, showgrid=False)

            # Add pace formatting for secondary Y-axis if it's pace (min/km)
            if yvar2 == "pace" and y2 is not None and len(y2) > 0:
                # Get min/max of y2 values (excluding NaN)
                y2_clean = y2[np.isfinite(y2)]
                if len(y2_clean) > 0:
                    y2_min = np.nanmin(y2_clean)
                    y2_max = np.nanmax(y2_clean)

                    # Generate pace tick values (e.g., 3:00, 3:30, 4:00, etc.)
                    y2_min_minutes = int(y2_min // 60)
                    y2_max_minutes = int(y2_max // 60) + 1

                    pace_ticks = []
                    for minute in range(y2_min_minutes, y2_max_minutes + 1):
                        pace_ticks.append(minute * 60)  # On the minute
                        if minute < y2_max_minutes:
                            pace_ticks.append(minute * 60 + 30)  # Half minute

                    pace_ticks = [t for t in pace_ticks if y2_min <= t <= y2_max]

                    # Format pace labels as MM:SS
                    def format_pace_label(seconds):
                        minutes = int(seconds // 60)
                        secs = int(seconds % 60)
                        return f"{minutes}:{secs:02d}"

                    pace_labels = [format_pace_label(t) for t in pace_ticks]

                    secondary_y_config['tickmode'] = 'array'
                    secondary_y_config['tickvals'] = pace_ticks
                    secondary_y_config['ticktext'] = pace_labels
                    # NO reversal - slower pace (high value like 9:00) at top, faster (low value like 3:00) at bottom
                    # This matches intuition: when pace line goes DOWN, runner is going FASTER

            fig.update_yaxes(**secondary_y_config, secondary_y=True)
            
            fig.update_layout(
                autosize=True,  # Responsive sizing for production
                plot_bgcolor='white',
                height=600,
                hovermode='x unified',
                margin=dict(l=70, r=70, t=50, b=70),
                legend=dict(x=0.01, y=0.99, bgcolor='rgba(255,255,255,0.9)', font=dict(size=13)),
                font=dict(size=13)
            )
        else:
            # Single Y-axis layout
            fig.update_layout(
                autosize=True,  # Responsive sizing for production
                xaxis=xaxis_config,
                yaxis=yaxis_config,
                plot_bgcolor='white',
                height=600,
                hovermode='x unified',
                margin=dict(l=70, r=70, t=50, b=70),
                font=dict(size=13)
            )

        return plotly_to_html(fig)

    # ========== RANGE SELECTION & SUMMARY STATISTICS ==========
    
    # Reactive values for range selection
    analysis_range_start = reactive.Value(0.0)
    analysis_range_end = reactive.Value(100.0)
    
    @output
    @render.ui
    def range_selector_ui():
        """Dynamic range selector based on current activity data"""
        d = xy_data()
        if not d:
            return ui.div()  # No activity selected
        
        x_min = float(d["x"].min())
        x_max = float(d["x"].max())
        x_is_time = d["x_fmt"] is not None
        
        # Format labels
        if x_is_time:
            def format_time_label(seconds):
                total_sec = int(seconds)
                hours = total_sec // 3600
                minutes = (total_sec % 3600) // 60
                secs = total_sec % 60
                if hours > 0:
                    return f"{hours}:{minutes:02d}:{secs:02d}"
                else:
                    return f"{minutes}:{secs:02d}"
            start_label = format_time_label(x_min)
            end_label = format_time_label(x_max)
            unit = "temps"
        else:
            start_label = f"{x_min:.2f} km"
            end_label = f"{x_max:.2f} km"
            unit = "distance"
        
        return ui.card(
            ui.card_header(
                ui.div(
                    ui.span("Sélection de plage pour analyse", style="font-weight: bold; font-size: 1.05rem;"),
                    ui.input_action_button("reset_range", "Réinitialiser", class_="btn btn-sm btn-outline-secondary", style="margin-left: 1rem;"),
                    style="display: flex; align-items: center; justify-content: space-between;"
                )
            ),
            ui.div(
                ui.layout_columns(
                    ui.div(
                        ui.tags.label(f"Début ({unit})", style="font-weight: 600; margin-bottom: 0.5rem; display: block;"),
                        ui.input_slider(
                            "range_start",
                            "",
                            min=x_min,
                            max=x_max,
                            value=x_min,
                            step=(x_max - x_min) / 1000,
                            width="100%"
                        ),
                        ui.output_text("range_start_display"),
                        style="padding: 0.5rem;"
                    ),
                    ui.div(
                        ui.tags.label(f"Fin ({unit})", style="font-weight: 600; margin-bottom: 0.5rem; display: block;"),
                        ui.input_slider(
                            "range_end",
                            "",
                            min=x_min,
                            max=x_max,
                            value=x_max,
                            step=(x_max - x_min) / 1000,
                            width="100%"
                        ),
                        ui.output_text("range_end_display"),
                        style="padding: 0.5rem;"
                    ),
                    col_widths=[6, 6]
                ),
                style="padding: 1rem;"
            ),
            style="background: #f9fafb; border: 1px solid #e5e7eb;"
        )
    
    @output
    @render.text
    def range_start_display():
        """Display formatted start value"""
        d = xy_data()
        if not d:
            return ""
        
        try:
            val = input.range_start()
            x_is_time = d["x_fmt"] is not None
            
            if x_is_time:
                total_sec = int(val)
                hours = total_sec // 3600
                minutes = (total_sec % 3600) // 60
                secs = total_sec % 60
                if hours > 0:
                    return f"Sélectionné: {hours}:{minutes:02d}:{secs:02d}"
                else:
                    return f"Sélectionné: {minutes}:{secs:02d}"
            else:
                return f"Sélectionné: {val:.2f} km"
        except:
            return ""
    
    @output
    @render.text
    def range_end_display():
        """Display formatted end value"""
        d = xy_data()
        if not d:
            return ""
        
        try:
            val = input.range_end()
            x_is_time = d["x_fmt"] is not None
            
            if x_is_time:
                total_sec = int(val)
                hours = total_sec // 3600
                minutes = (total_sec % 3600) // 60
                secs = total_sec % 60
                if hours > 0:
                    return f"Sélectionné: {hours}:{minutes:02d}:{secs:02d}"
                else:
                    return f"Sélectionné: {minutes}:{secs:02d}"
            else:
                return f"Sélectionné: {val:.2f} km"
        except:
            return ""
    
    @reactive.Effect
    @reactive.event(input.reset_range)
    def reset_range_handler():
        """Reset range to full activity"""
        d = xy_data()
        if d:
            x_min = float(d["x"].min())
            x_max = float(d["x"].max())
            ui.update_slider("range_start", value=x_min)
            ui.update_slider("range_end", value=x_max)
    
    @output
    @render.ui
    def zoom_summary_card():
        """Display summary statistics for ALL metrics in the selected range"""
        d = xy_data()
        if not d:
            return ui.div()  # No activity selected

        try:
            x_min = input.range_start()
            x_max = input.range_end()
        except:
            # Sliders not initialized yet
            x_min = d["x"].min()
            x_max = d["x"].max()

        # Ensure valid range
        if x_min >= x_max:
            return ui.div(
                ui.card(
                    ui.card_header("Plage invalide"),
                    ui.div("La valeur de début doit être inférieure à la valeur de fin.", style="padding: 1rem; color: #dc2626;")
                )
            )

        # Get full dataframe to calculate stats for all metrics
        act_id = current_activity_id()
        if not act_id:
            return ui.div()

        df_full = fetch_timeseries_cached(str(act_id))
        if df_full.empty:
            return ui.div()

        # Determine X variable type and filter dataframe
        raw_x = (input.xvar() or "moving")
        xvar = XVAR_ALIASES.get(raw_x, "moving")

        # Get the X column for filtering
        if xvar == "moving":
            x_col = "t_active_sec"
        elif xvar == "distance":
            x_col = "distance"
        else:
            x_col = "t_active_sec"

        if x_col not in df_full.columns:
            return ui.div()

        # Filter dataframe to selected range
        mask = (df_full[x_col] >= x_min) & (df_full[x_col] <= x_max)
        df_range = df_full[mask]

        if len(df_range) == 0:
            return ui.div(
                ui.card(
                    ui.card_header("Aucune donnée"),
                    ui.div("Aucune donnée dans la plage sélectionnée.", style="padding: 1rem; color: #dc2626;")
                )
            )

        # Format X range
        x_is_time = xvar == "moving"
        if x_is_time:
            def format_time_range(seconds):
                total_sec = int(seconds)
                hours = total_sec // 3600
                minutes = (total_sec % 3600) // 60
                secs = total_sec % 60
                if hours > 0:
                    return f"{hours}:{minutes:02d}:{secs:02d}"
                else:
                    return f"{minutes}:{secs:02d}"
            x_range_str = f"{format_time_range(x_min)} → {format_time_range(x_max)}"
        else:
            x_range_str = f"{x_min/1000:.2f} → {x_max/1000:.2f} km"

        # Determine if analyzing partial or full range
        full_range = df_full[x_col].max() - df_full[x_col].min()
        selected_range = x_max - x_min
        is_partial = selected_range < full_range * 0.98

        range_indicator = "Analyse de plage sélectionnée" if is_partial else "Analyse complète"

        # Helper function to format pace
        def format_pace(pace_min_km):
            """Format pace as min:sec/km"""
            if pd.isna(pace_min_km):
                return "N/A"
            minutes = int(pace_min_km)
            seconds = int((pace_min_km - minutes) * 60)
            return f"{minutes}:{seconds:02d}"

        # Define metrics to display (similar to comparison stats)
        metrics = [
            {'name': 'Fréquence cardiaque', 'col': 'heartrate', 'unit': 'bpm', 'format': lambda x: f"{x:.0f}"},
            {'name': 'Cadence', 'col': 'cadence', 'unit': 'spm', 'format': lambda x: f"{x:.0f}"},
            {'name': 'Puissance', 'col': 'watts', 'unit': 'W', 'format': lambda x: f"{x:.0f}"},
            {'name': 'Oscillation verticale', 'col': 'vertical_oscillation', 'unit': 'mm', 'format': lambda x: f"{x:.1f}"},
            {'name': 'Temps de contact (GCT)', 'col': 'ground_contact_time', 'unit': 'ms', 'format': lambda x: f"{x:.0f}"},
            {'name': 'Leg Spring Stiffness (LSS)', 'col': 'leg_spring_stiffness', 'unit': 'kN/m', 'format': lambda x: f"{x:.1f}"},
        ]

        # Build metric rows
        metric_rows = []
        for metric in metrics:
            col = metric['col']
            if col not in df_range.columns:
                continue

            # Get data and remove NaNs
            data = df_range[col].dropna()
            if len(data) == 0:
                continue

            # Calculate statistics
            mean_val = np.mean(data)
            median_val = np.median(data)
            min_val = np.min(data)
            max_val = np.max(data)

            # Format values
            mean_str = metric['format'](mean_val)
            median_str = metric['format'](median_val)
            min_str = metric['format'](min_val)
            max_str = metric['format'](max_val)

            # Create row
            metric_rows.append(
                ui.div(
                    ui.div(
                        ui.span(metric.get('icon', ''), style="margin-right: 0.5rem; font-size: 1.2rem;"),
                        ui.span(metric['name'], style="font-weight: 600; font-size: 0.95rem;"),
                        style="display: flex; align-items: center; margin-bottom: 0.75rem;"
                    ),
                    ui.layout_columns(
                        ui.div(
                            ui.tags.div("Moyenne", style="font-size: 0.75rem; color: #666; margin-bottom: 0.25rem;"),
                            ui.tags.div(mean_str, style="font-size: 1.3rem; font-weight: bold; color: #D92323;"),
                            ui.tags.div(metric['unit'], style="font-size: 0.7rem; color: #666; margin-top: 0.1rem;"),
                            style="text-align: center; padding: 0.5rem; background: white; border-radius: 6px;"
                        ),
                        ui.div(
                            ui.tags.div("Médiane", style="font-size: 0.75rem; color: #666; margin-bottom: 0.25rem;"),
                            ui.tags.div(median_str, style="font-size: 1.3rem; font-weight: bold; color: #D92323;"),
                            ui.tags.div(metric['unit'], style="font-size: 0.7rem; color: #666; margin-top: 0.1rem;"),
                            style="text-align: center; padding: 0.5rem; background: white; border-radius: 6px;"
                        ),
                        ui.div(
                            ui.tags.div("Minimum", style="font-size: 0.75rem; color: #666; margin-bottom: 0.25rem;"),
                            ui.tags.div(min_str, style="font-size: 1.3rem; font-weight: bold; color: #2563eb;"),
                            ui.tags.div(metric['unit'], style="font-size: 0.7rem; color: #666; margin-top: 0.1rem;"),
                            style="text-align: center; padding: 0.5rem; background: white; border-radius: 6px;"
                        ),
                        ui.div(
                            ui.tags.div("Maximum", style="font-size: 0.75rem; color: #666; margin-bottom: 0.25rem;"),
                            ui.tags.div(max_str, style="font-size: 1.3rem; font-weight: bold; color: #dc2626;"),
                            ui.tags.div(metric['unit'], style="font-size: 0.7rem; color: #666; margin-top: 0.1rem;"),
                            style="text-align: center; padding: 0.5rem; background: white; border-radius: 6px;"
                        ),
                        col_widths=[3, 3, 3, 3]
                    ),
                    style="padding: 0.75rem 1rem; border-bottom: 1px solid #e5e7eb;"
                )
            )

        if not metric_rows:
            return ui.div(
                ui.card(
                    ui.card_header("Aucune métrique disponible"),
                    ui.div("Aucune métrique de performance disponible pour cette plage.", style="padding: 1rem; color: #dc2626;")
                )
            )

        return ui.card(
            ui.card_header(
                ui.div(
                    ui.span(range_indicator, style="font-weight: bold; font-size: 1.05rem;"),
                    ui.span(f"Plage: {x_range_str}", style="margin-left: 1rem; color: #666; font-size: 0.95rem;"),
                    style="display: flex; align-items: center;"
                )
            ),
            ui.div(
                ui.tags.h5("Statistiques de la plage", style="color: #D92323; margin-bottom: 1rem; text-align: center;"),
                *metric_rows,
                style="padding: 0.5rem 0;"
            ),
            style="background: #fef2f2; border: 1px solid rgba(217, 35, 35, 0.2);"
        )

    # ========== COMPARISON TAB FUNCTIONS ==========
    
    # Helper functions
    def format_time_comp(seconds):
        """Convert seconds to mm:ss or hh:mm:ss"""
        if pd.isna(seconds) or seconds is None:
            return "00:00"
        total_sec = int(seconds)
        hours = total_sec // 3600
        minutes = (total_sec % 3600) // 60
        secs = total_sec % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"
    
    def parse_time_to_seconds(time_str):
        """Parse time string (mm:ss or h:mm:ss) to seconds"""
        try:
            parts = time_str.strip().split(':')
            if len(parts) == 2:  # mm:ss
                minutes, seconds = int(parts[0]), int(parts[1])
                return minutes * 60 + seconds
            elif len(parts) == 3:  # h:mm:ss
                hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
                return hours * 3600 + minutes * 60 + seconds
            else:
                return None
        except:
            return None
    
    def crop_timeseries(df, mode, start_val, end_val):
        """Crop timeseries data based on t_active_sec (moving time)"""
        if df.empty:
            return df
        
        # Use t_active_sec for cropping
        if mode == "time" and 't_active_sec' in df.columns:
            mask = (df['t_active_sec'] >= start_val) & (df['t_active_sec'] <= end_val)
            cropped = df[mask].copy()
            if not cropped.empty:
                # Reset t_active_sec to start at 0
                time_offset = cropped['t_active_sec'].iloc[0]
                cropped['t_active_sec'] = cropped['t_active_sec'] - time_offset
        elif mode == "dist" and 'distance' in df.columns:
            start_m = start_val * 1000
            end_m = end_val * 1000
            mask = (df['distance'] >= start_m) & (df['distance'] <= end_m)
            cropped = df[mask].copy()
            if not cropped.empty:
                dist_offset = cropped['distance'].iloc[0]
                cropped['distance'] = cropped['distance'] - dist_offset
        else:
            # If can't crop, return full dataframe
            cropped = df.copy()
        
        return cropped
    
    # Update comparison activity dropdowns when activities change
    @reactive.Effect
    @reactive.event(act_label_to_id)
    def update_comparison_dropdowns():
        """Update comparison activity selectors with same choices as main analysis"""
        label_to_id = act_label_to_id.get()
        if label_to_id:
            choices = list(label_to_id.keys())
            ui.update_select("comp_activity_1", choices=choices)
            ui.update_select("comp_activity_2", choices=choices)
    
    # Track selected activities for comparison
    @reactive.Effect
    @reactive.event(input.comp_activity_1)
    def update_comp_activity_1():
        """Update comparison_activity_id_1 when dropdown changes"""
        label = input.comp_activity_1()
        if label:
            label_to_id = act_label_to_id.get()
            act_id = label_to_id.get(label)
            if act_id:
                comparison_activity_id_1.set(act_id)
    
    @reactive.Effect
    @reactive.event(input.comp_activity_2)
    def update_comp_activity_2():
        """Update comparison_activity_id_2 when dropdown changes"""
        label = input.comp_activity_2()
        if label:
            label_to_id = act_label_to_id.get()
            act_id = label_to_id.get(label)
            if act_id:
                comparison_activity_id_2.set(act_id)
    
    # Initialize crop ranges when activities change (separate from render to avoid state warnings)
    @reactive.Effect
    @reactive.event(comparison_activity_id_1)
    def init_crop_range_1():
        """Initialize crop range for Activity 1 when activity changes"""
        act_id_1 = comparison_activity_id_1.get()
        if not act_id_1:
            return
        try:
            df1 = fetch_timeseries_cached(act_id_1)
            if df1.empty or 't_active_sec' not in df1.columns:
                return
            max_time_1 = df1['t_active_sec'].max()
            crop_range_1.set([0, max_time_1])
        except:
            pass

    # Crop controls
    @output
    @render.ui
    def crop_controls_1():
        act_id_1 = comparison_activity_id_1.get()
        if not act_id_1:
            return ui.div()
        try:
            df1 = fetch_timeseries_cached(act_id_1)
            if df1.empty:
                return ui.div()

            # Use t_active_sec column for duration (moving time)
            if 't_active_sec' not in df1.columns:
                return ui.div("Données de temps en mouvement non disponibles", style="color: #999; padding: 1rem;")

            # Get max moving time for this activity only
            max_time_1 = df1['t_active_sec'].max()

            # Get current crop range (initialized by init_crop_range_1 effect)
            # Use reactive.isolate() to prevent this UI from re-rendering when crop_range_1 changes
            # This prevents infinite loops when slider is moved quickly
            with reactive.isolate():
                current_crop = crop_range_1.get()
            if current_crop == [0, 0] or current_crop[1] == 0:
                current_crop = [0, max_time_1]  # Use local default, don't set reactive value here
            
            # JavaScript to format slider values as time (optimized to prevent flashing)
            slider_js = f"""
            <script>
            (function() {{
                var slider1Initialized = false;
                function initSlider1() {{
                    if (slider1Initialized) return;
                    var slider = $("#crop_slider_1").data("ionRangeSlider");
                    if (slider) {{
                        slider1Initialized = true;
                        slider.update({{
                            prettify: function(num) {{
                                var h = Math.floor(num / 3600);
                                var m = Math.floor((num % 3600) / 60);
                                var s = Math.floor(num % 60);
                                if (h > 0) {{
                                    return h + ":" + (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
                                }} else {{
                                    return m + ":" + (s < 10 ? "0" : "") + s;
                                }}
                            }}
                        }});
                    }}
                }}
                $(document).ready(function() {{
                    setTimeout(initSlider1, 100);
                }});
            }})();
            </script>
            """
            
            return ui.div(
                ui.tags.label("Découpage Activité 1", style="font-weight: 700; color: #D92323;"),
                ui.input_slider(
                    "crop_slider_1", 
                    "Sélection", 
                    min=0, 
                    max=max_time_1, 
                    value=current_crop, 
                    step=1
                ),
                ui.HTML(slider_js),
                ui.div(
                    ui.tags.label("Ajustement manuel:", style="font-size: 0.9rem; color: #666; font-weight: 600; margin-bottom: 0.5rem; display: block;"),
                    ui.layout_columns(
                        ui.div(
                            ui.tags.label("Début:", style="font-size: 0.85rem; color: #666; margin-bottom: 0.25rem; display: block;"),
                            ui.div(
                                ui.input_numeric("manual_start_h_1", "", value=int(current_crop[0] // 3600), min=0, max=23, step=1, width="80px"),
                                ui.tags.span("h", style="margin: 0 0.5rem; font-weight: 600; font-size: 1rem;"),
                                ui.input_numeric("manual_start_m_1", "", value=int((current_crop[0] % 3600) // 60), min=0, max=59, step=1, width="80px"),
                                ui.tags.span("m", style="margin: 0 0.5rem; font-weight: 600; font-size: 1rem;"),
                                ui.input_numeric("manual_start_s_1", "", value=int(current_crop[0] % 60), min=0, max=59, step=1, width="80px"),
                                ui.tags.span("s", style="margin-left: 0.5rem; font-weight: 600; font-size: 1rem;"),
                                style="display: flex; align-items: center; font-size: 1.1rem;"
                            )
                        ),
                        ui.div(
                            ui.tags.label("Fin:", style="font-size: 0.85rem; color: #666; margin-bottom: 0.25rem; display: block;"),
                            ui.div(
                                ui.input_numeric("manual_end_h_1", "", value=int(current_crop[1] // 3600), min=0, max=23, step=1, width="80px"),
                                ui.tags.span("h", style="margin: 0 0.5rem; font-weight: 600; font-size: 1rem;"),
                                ui.input_numeric("manual_end_m_1", "", value=int((current_crop[1] % 3600) // 60), min=0, max=59, step=1, width="80px"),
                                ui.tags.span("m", style="margin: 0 0.5rem; font-weight: 600; font-size: 1rem;"),
                                ui.input_numeric("manual_end_s_1", "", value=int(current_crop[1] % 60), min=0, max=59, step=1, width="80px"),
                                ui.tags.span("s", style="margin-left: 0.5rem; font-weight: 600; font-size: 1rem;"),
                                style="display: flex; align-items: center; font-size: 1.1rem;"
                            )
                        ),
                        col_widths=[6, 6]
                    ),
                    style="margin-top: 0.75rem; padding: 0.5rem; background: #fff; border-radius: 4px; border: 1px solid #e5e5e5;"
                ),
                ui.div(f"Segment: {format_time_comp(current_crop[0])} → {format_time_comp(current_crop[1])}", 
                      style="color: #666; font-size: 0.9rem; margin-top: 0.5rem;"),
                ui.div(
                    ui.input_action_button("preset_full_1", "Complet", class_="btn btn-sm btn-outline-primary"),
                    style="margin-top: 0.5rem;"
                ),
                style="padding: 1rem; background: #fef2f2; border-radius: 8px; border: 2px solid rgba(217, 35, 35, 0.2);"
            )
        except Exception as e:
            return ui.div(f"Erreur: {str(e)}", style="color: #dc2626; padding: 1rem;")
    
    @reactive.Effect
    @reactive.event(comparison_activity_id_2)
    def init_crop_range_2():
        """Initialize crop range for Activity 2 when activity changes"""
        act_id_2 = comparison_activity_id_2.get()
        if not act_id_2:
            return
        try:
            df2 = fetch_timeseries_cached(act_id_2)
            if df2.empty or 't_active_sec' not in df2.columns:
                return
            max_time_2 = df2['t_active_sec'].max()
            crop_range_2.set([0, max_time_2])
        except:
            pass

    @output
    @render.ui
    def crop_controls_2():
        act_id_2 = comparison_activity_id_2.get()
        if not act_id_2:
            return ui.div()
        try:
            df2 = fetch_timeseries_cached(act_id_2)
            if df2.empty:
                return ui.div()

            # Use t_active_sec column for duration (moving time)
            if 't_active_sec' not in df2.columns:
                return ui.div("Données de temps en mouvement non disponibles", style="color: #999; padding: 1rem;")

            # Get max moving time for this activity only
            max_time_2 = df2['t_active_sec'].max()

            # Get current crop range (initialized by init_crop_range_2 effect)
            # Use reactive.isolate() to prevent this UI from re-rendering when crop_range_2 changes
            # This prevents infinite loops when slider is moved quickly
            with reactive.isolate():
                current_crop = crop_range_2.get()
            if current_crop == [0, 0] or current_crop[1] == 0:
                current_crop = [0, max_time_2]  # Use local default, don't set reactive value here
            
            # JavaScript to format slider values as time (optimized to prevent flashing)
            slider_js = f"""
            <script>
            (function() {{
                var slider2Initialized = false;
                function initSlider2() {{
                    if (slider2Initialized) return;
                    var slider = $("#crop_slider_2").data("ionRangeSlider");
                    if (slider) {{
                        slider2Initialized = true;
                        slider.update({{
                            prettify: function(num) {{
                                var h = Math.floor(num / 3600);
                                var m = Math.floor((num % 3600) / 60);
                                var s = Math.floor(num % 60);
                                if (h > 0) {{
                                    return h + ":" + (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
                                }} else {{
                                    return m + ":" + (s < 10 ? "0" : "") + s;
                                }}
                            }}
                        }});
                    }}
                }}
                $(document).ready(function() {{
                    setTimeout(initSlider2, 100);
                }});
            }})();
            </script>
            """
            
            return ui.div(
                ui.tags.label("Découpage Activité 2", style="font-weight: 700; color: #FF6B6B;"),
                ui.input_slider(
                    "crop_slider_2", 
                    "Sélection", 
                    min=0, 
                    max=max_time_2, 
                    value=current_crop, 
                    step=1
                ),
                ui.HTML(slider_js),
                ui.div(
                    ui.tags.label("Ajustement manuel:", style="font-size: 0.9rem; color: #666; font-weight: 600; margin-bottom: 0.5rem; display: block;"),
                    ui.layout_columns(
                        ui.div(
                            ui.tags.label("Début:", style="font-size: 0.85rem; color: #666; margin-bottom: 0.25rem; display: block;"),
                            ui.div(
                                ui.input_numeric("manual_start_h_2", "", value=int(current_crop[0] // 3600), min=0, max=23, step=1, width="80px"),
                                ui.tags.span("h", style="margin: 0 0.5rem; font-weight: 600; font-size: 1rem;"),
                                ui.input_numeric("manual_start_m_2", "", value=int((current_crop[0] % 3600) // 60), min=0, max=59, step=1, width="80px"),
                                ui.tags.span("m", style="margin: 0 0.5rem; font-weight: 600; font-size: 1rem;"),
                                ui.input_numeric("manual_start_s_2", "", value=int(current_crop[0] % 60), min=0, max=59, step=1, width="80px"),
                                ui.tags.span("s", style="margin-left: 0.5rem; font-weight: 600; font-size: 1rem;"),
                                style="display: flex; align-items: center; font-size: 1.1rem;"
                            )
                        ),
                        ui.div(
                            ui.tags.label("Fin:", style="font-size: 0.85rem; color: #666; margin-bottom: 0.25rem; display: block;"),
                            ui.div(
                                ui.input_numeric("manual_end_h_2", "", value=int(current_crop[1] // 3600), min=0, max=23, step=1, width="80px"),
                                ui.tags.span("h", style="margin: 0 0.5rem; font-weight: 600; font-size: 1rem;"),
                                ui.input_numeric("manual_end_m_2", "", value=int((current_crop[1] % 3600) // 60), min=0, max=59, step=1, width="80px"),
                                ui.tags.span("m", style="margin: 0 0.5rem; font-weight: 600; font-size: 1rem;"),
                                ui.input_numeric("manual_end_s_2", "", value=int(current_crop[1] % 60), min=0, max=59, step=1, width="80px"),
                                ui.tags.span("s", style="margin-left: 0.5rem; font-weight: 600; font-size: 1rem;"),
                                style="display: flex; align-items: center; font-size: 1.1rem;"
                            )
                        ),
                        col_widths=[6, 6]
                    ),
                    style="margin-top: 0.75rem; padding: 0.5rem; background: #fff; border-radius: 4px; border: 1px solid #e5e5e5;"
                ),
                ui.div(f"Segment: {format_time_comp(current_crop[0])} → {format_time_comp(current_crop[1])}", 
                      style="color: #666; font-size: 0.9rem; margin-top: 0.5rem;"),
                ui.div(
                    ui.input_action_button("preset_full_2", "Complet", class_="btn btn-sm btn-outline-primary"),
                    style="margin-top: 0.5rem;"
                ),
                style="padding: 1rem; background: #fff5f5; border-radius: 8px; border: 2px solid rgba(255, 107, 107, 0.2);"
            )
        except Exception as e:
            return ui.div(f"Erreur: {str(e)}", style="color: #dc2626; padding: 1rem;")
    
    # Sync sliders - with debouncing to prevent infinite loops on fast movement
    # Track last update times for debouncing
    import time as _time_module
    _last_slider_update_1 = reactive.Value(0.0)
    _last_slider_update_2 = reactive.Value(0.0)
    _SLIDER_DEBOUNCE_MS = 50  # Minimum milliseconds between updates

    @reactive.Effect
    @reactive.event(input.crop_slider_1)
    def update_crop_1():
        val = input.crop_slider_1()
        if val:
            current_time = _time_module.time() * 1000  # ms
            last_update = _last_slider_update_1.get()
            # Only update if enough time has passed (debouncing)
            if current_time - last_update > _SLIDER_DEBOUNCE_MS:
                # Check if value actually changed (prevent loops)
                current = crop_range_1.get()
                if current != list(val):
                    _last_slider_update_1.set(current_time)
                    crop_range_1.set(list(val))

    @reactive.Effect
    @reactive.event(input.crop_slider_2)
    def update_crop_2():
        val = input.crop_slider_2()
        if val:
            current_time = _time_module.time() * 1000  # ms
            last_update = _last_slider_update_2.get()
            # Only update if enough time has passed (debouncing)
            if current_time - last_update > _SLIDER_DEBOUNCE_MS:
                # Check if value actually changed (prevent loops)
                current = crop_range_2.get()
                if current != list(val):
                    _last_slider_update_2.set(current_time)
                    crop_range_2.set(list(val))
    
    # Sync manual input fields when slider changes (without re-rendering entire UI)
    # Only sync when inputs exist (i.e., comparison tab is active and activity selected)
    @reactive.Effect
    @reactive.event(crop_range_1)
    def sync_manual_inputs_1():
        """Update manual time inputs when crop_range_1 changes from slider"""
        # Only run if comparison is enabled and activity 1 is selected
        # This ensures the manual inputs exist in the DOM
        if not input.comparison_enabled():
            return
        if not comparison_activity_id_1.get():
            return
        crop = crop_range_1.get()
        if crop and len(crop) == 2 and crop != [0, 0]:
            start_sec = crop[0]
            end_sec = crop[1]
            # Update start time inputs
            ui.update_numeric("manual_start_h_1", value=int(start_sec // 3600))
            ui.update_numeric("manual_start_m_1", value=int((start_sec % 3600) // 60))
            ui.update_numeric("manual_start_s_1", value=int(start_sec % 60))
            # Update end time inputs
            ui.update_numeric("manual_end_h_1", value=int(end_sec // 3600))
            ui.update_numeric("manual_end_m_1", value=int((end_sec % 3600) // 60))
            ui.update_numeric("manual_end_s_1", value=int(end_sec % 60))

    @reactive.Effect
    @reactive.event(crop_range_2)
    def sync_manual_inputs_2():
        """Update manual time inputs when crop_range_2 changes from slider"""
        # Only run if comparison is enabled and activity 2 is selected
        # This ensures the manual inputs exist in the DOM
        if not input.comparison_enabled():
            return
        if not comparison_activity_id_2.get():
            return
        crop = crop_range_2.get()
        if crop and len(crop) == 2 and crop != [0, 0]:
            start_sec = crop[0]
            end_sec = crop[1]
            # Update start time inputs
            ui.update_numeric("manual_start_h_2", value=int(start_sec // 3600))
            ui.update_numeric("manual_start_m_2", value=int((start_sec % 3600) // 60))
            ui.update_numeric("manual_start_s_2", value=int(start_sec % 60))
            # Update end time inputs
            ui.update_numeric("manual_end_h_2", value=int(end_sec // 3600))
            ui.update_numeric("manual_end_m_2", value=int((end_sec % 3600) // 60))
            ui.update_numeric("manual_end_s_2", value=int(end_sec % 60))

    # Preset handlers - "Complet" button to reset to full workout
    @reactive.Effect
    @reactive.event(input.preset_full_1)
    def apply_full_1():
        act_id = comparison_activity_id_1.get()
        if act_id:
            df = fetch_timeseries_cached(act_id)
            if not df.empty and 't_active_sec' in df.columns:
                max_time = df['t_active_sec'].max()
                new_range = [0, max_time]
                crop_range_1.set(new_range)
                ui.update_slider("crop_slider_1", value=new_range)
    
    @reactive.Effect
    @reactive.event(input.preset_full_2)
    def apply_full_2():
        act_id = comparison_activity_id_2.get()
        if act_id:
            df = fetch_timeseries_cached(act_id)
            if not df.empty and 't_active_sec' in df.columns:
                max_time = df['t_active_sec'].max()
                new_range = [0, max_time]
                crop_range_2.set(new_range)
                ui.update_slider("crop_slider_2", value=new_range)
    
    # Tracking values to prevent loops from UI re-renders
    last_manual_update_1_start = reactive.Value(0)
    last_manual_update_1_end = reactive.Value(0)
    last_manual_update_2_start = reactive.Value(0)
    last_manual_update_2_end = reactive.Value(0)
    
    # Manual time input handlers - separate to prevent cross-triggering
    # Activity 1 - Start time
    @reactive.Effect
    @reactive.event(input.manual_start_h_1)
    def update_manual_start_h_1():
        try:
            with reactive.isolate():
                h = input.manual_start_h_1() or 0
                m = input.manual_start_m_1() or 0
                s = input.manual_start_s_1() or 0
                total_seconds = s + (m * 60) + (h * 3600)
                last_value = last_manual_update_1_start.get()
                # Only update if value changed from last manual update (not from UI re-render)
                if abs(last_value - total_seconds) > 1:
                    current = crop_range_1.get()
                    if current and len(current) == 2:
                        crop_range_1.set([total_seconds, current[1]])
                        last_manual_update_1_start.set(total_seconds)
        except:
            pass
    
    @reactive.Effect
    @reactive.event(input.manual_start_m_1)
    def update_manual_start_m_1():
        try:
            with reactive.isolate():
                h = input.manual_start_h_1() or 0
                m = input.manual_start_m_1() or 0
                s = input.manual_start_s_1() or 0
                total_seconds = s + (m * 60) + (h * 3600)
                last_value = last_manual_update_1_start.get()
                # Only update if value changed from last manual update
                if abs(last_value - total_seconds) > 1:
                    current = crop_range_1.get()
                    if current and len(current) == 2:
                        crop_range_1.set([total_seconds, current[1]])
                        last_manual_update_1_start.set(total_seconds)
        except:
            pass
    
    @reactive.Effect
    @reactive.event(input.manual_start_s_1)
    def update_manual_start_s_1():
        try:
            with reactive.isolate():
                h = input.manual_start_h_1() or 0
                m = input.manual_start_m_1() or 0
                s = input.manual_start_s_1() or 0
                total_seconds = s + (m * 60) + (h * 3600)
                last_value = last_manual_update_1_start.get()
                # Only update if value changed from last manual update
                if abs(last_value - total_seconds) > 1:
                    current = crop_range_1.get()
                    if current and len(current) == 2:
                        crop_range_1.set([total_seconds, current[1]])
                        last_manual_update_1_start.set(total_seconds)
        except:
            pass
    
    # Activity 1 - End time
    @reactive.Effect
    @reactive.event(input.manual_end_h_1)
    def update_manual_end_h_1():
        try:
            with reactive.isolate():
                h = input.manual_end_h_1() or 0
                m = input.manual_end_m_1() or 0
                s = input.manual_end_s_1() or 0
                total_seconds = s + (m * 60) + (h * 3600)
                last_value = last_manual_update_1_end.get()
                if abs(last_value - total_seconds) > 1:
                    current = crop_range_1.get()
                    if current and len(current) == 2:
                        crop_range_1.set([current[0], total_seconds])
                        last_manual_update_1_end.set(total_seconds)
        except:
            pass
    
    @reactive.Effect
    @reactive.event(input.manual_end_m_1)
    def update_manual_end_m_1():
        try:
            with reactive.isolate():
                h = input.manual_end_h_1() or 0
                m = input.manual_end_m_1() or 0
                s = input.manual_end_s_1() or 0
                total_seconds = s + (m * 60) + (h * 3600)
                last_value = last_manual_update_1_end.get()
                if abs(last_value - total_seconds) > 1:
                    current = crop_range_1.get()
                    if current and len(current) == 2:
                        crop_range_1.set([current[0], total_seconds])
                        last_manual_update_1_end.set(total_seconds)
        except:
            pass
    
    @reactive.Effect
    @reactive.event(input.manual_end_s_1)
    def update_manual_end_s_1():
        try:
            with reactive.isolate():
                h = input.manual_end_h_1() or 0
                m = input.manual_end_m_1() or 0
                s = input.manual_end_s_1() or 0
                total_seconds = s + (m * 60) + (h * 3600)
                last_value = last_manual_update_1_end.get()
                if abs(last_value - total_seconds) > 1:
                    current = crop_range_1.get()
                    if current and len(current) == 2:
                        crop_range_1.set([current[0], total_seconds])
                        last_manual_update_1_end.set(total_seconds)
        except:
            pass
    
    # Activity 2 - Start time
    @reactive.Effect
    @reactive.event(input.manual_start_h_2)
    def update_manual_start_h_2():
        try:
            with reactive.isolate():
                h = input.manual_start_h_2() or 0
                m = input.manual_start_m_2() or 0
                s = input.manual_start_s_2() or 0
                total_seconds = s + (m * 60) + (h * 3600)
                last_value = last_manual_update_2_start.get()
                if abs(last_value - total_seconds) > 1:
                    current = crop_range_2.get()
                    if current and len(current) == 2:
                        crop_range_2.set([total_seconds, current[1]])
                        last_manual_update_2_start.set(total_seconds)
        except:
            pass
    
    @reactive.Effect
    @reactive.event(input.manual_start_m_2)
    def update_manual_start_m_2():
        try:
            with reactive.isolate():
                h = input.manual_start_h_2() or 0
                m = input.manual_start_m_2() or 0
                s = input.manual_start_s_2() or 0
                total_seconds = s + (m * 60) + (h * 3600)
                last_value = last_manual_update_2_start.get()
                if abs(last_value - total_seconds) > 1:
                    current = crop_range_2.get()
                    if current and len(current) == 2:
                        crop_range_2.set([total_seconds, current[1]])
                        last_manual_update_2_start.set(total_seconds)
        except:
            pass
    
    @reactive.Effect
    @reactive.event(input.manual_start_s_2)
    def update_manual_start_s_2():
        try:
            with reactive.isolate():
                h = input.manual_start_h_2() or 0
                m = input.manual_start_m_2() or 0
                s = input.manual_start_s_2() or 0
                total_seconds = s + (m * 60) + (h * 3600)
                last_value = last_manual_update_2_start.get()
                if abs(last_value - total_seconds) > 1:
                    current = crop_range_2.get()
                    if current and len(current) == 2:
                        crop_range_2.set([total_seconds, current[1]])
                        last_manual_update_2_start.set(total_seconds)
        except:
            pass
    
    # Activity 2 - End time
    @reactive.Effect
    @reactive.event(input.manual_end_h_2)
    def update_manual_end_h_2():
        try:
            with reactive.isolate():
                h = input.manual_end_h_2() or 0
                m = input.manual_end_m_2() or 0
                s = input.manual_end_s_2() or 0
                total_seconds = s + (m * 60) + (h * 3600)
                last_value = last_manual_update_2_end.get()
                if abs(last_value - total_seconds) > 1:
                    current = crop_range_2.get()
                    if current and len(current) == 2:
                        crop_range_2.set([current[0], total_seconds])
                        last_manual_update_2_end.set(total_seconds)
        except:
            pass
    
    @reactive.Effect
    @reactive.event(input.manual_end_m_2)
    def update_manual_end_m_2():
        try:
            with reactive.isolate():
                h = input.manual_end_h_2() or 0
                m = input.manual_end_m_2() or 0
                s = input.manual_end_s_2() or 0
                total_seconds = s + (m * 60) + (h * 3600)
                last_value = last_manual_update_2_end.get()
                if abs(last_value - total_seconds) > 1:
                    current = crop_range_2.get()
                    if current and len(current) == 2:
                        crop_range_2.set([current[0], total_seconds])
                        last_manual_update_2_end.set(total_seconds)
        except:
            pass
    
    @reactive.Effect
    @reactive.event(input.manual_end_s_2)
    def update_manual_end_s_2():
        try:
            with reactive.isolate():
                h = input.manual_end_h_2() or 0
                m = input.manual_end_m_2() or 0
                s = input.manual_end_s_2() or 0
                total_seconds = s + (m * 60) + (h * 3600)
                last_value = last_manual_update_2_end.get()
                if abs(last_value - total_seconds) > 1:
                    current = crop_range_2.get()
                    if current and len(current) == 2:
                        crop_range_2.set([current[0], total_seconds])
                        last_manual_update_2_end.set(total_seconds)
        except:
            pass
    
    # Main comparison plot
    @output
    @render.ui
    def comparison_plot():
        if not input.comparison_enabled():
            fig = go.Figure()
            fig.add_annotation(text="Activez la comparaison", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font=dict(size=18, color="#666"))
            fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False), height=600, plot_bgcolor="white")
            return plotly_to_html(fig)

        act_id_1 = comparison_activity_id_1.get()
        if not act_id_1:
            fig = go.Figure()
            fig.add_annotation(text="Sélectionnez l'Activité 1", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font=dict(size=18, color="#D92323"))
            fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False), height=600, plot_bgcolor="white")
            return plotly_to_html(fig)

        try:
            df1 = fetch_timeseries_cached(act_id_1)
            if df1.empty:
                fig = go.Figure()
                fig.add_annotation(text="Activité 1 sans données", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font=dict(size=18, color="#D92323"))
                fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False), height=600, plot_bgcolor="white")
                return plotly_to_html(fig)

            # Get crop range - don't modify reactive values here to avoid circular reactivity
            if 't_active_sec' not in df1.columns:
                fig = go.Figure()
                fig.add_annotation(text="Colonne t_active_sec manquante", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font=dict(size=18, color="#dc2626"))
                fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False), height=600, plot_bgcolor="white")
                return plotly_to_html(fig)
            
            crop1 = crop_range_1.get()
            max_time_1 = df1['t_active_sec'].max()
            print(f"[DEBUG comparison_plot] crop1: {crop1}, max_time_1: {max_time_1}")

            # Use full range if crop not initialized or invalid
            if crop1 == [0, 0] or crop1[1] == 0 or crop1[1] > max_time_1:
                crop1 = [0, max_time_1]
                print(f"[DEBUG comparison_plot] Using full range: {crop1}")

            # Ensure we have valid crop range
            if max_time_1 <= 0 or np.isnan(max_time_1):
                fig = go.Figure()
                fig.add_annotation(text="Donnees de temps invalides pour l'Activite 1", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font=dict(size=18, color="#D92323"))
                fig.update_layout(autosize=True, xaxis=dict(visible=False), yaxis=dict(visible=False), height=600, plot_bgcolor="white")
                return plotly_to_html(fig)

            df1_cropped = crop_timeseries(df1, "time", crop1[0], crop1[1])
            print(f"[DEBUG comparison_plot] df1_cropped rows: {len(df1_cropped)}")

            # Check if cropped data is empty
            if df1_cropped.empty:
                fig = go.Figure()
                fig.add_annotation(text="Aucune donnee dans la plage selectionnee", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font=dict(size=18, color="#D92323"))
                fig.update_layout(autosize=True, xaxis=dict(visible=False), yaxis=dict(visible=False), height=600, plot_bgcolor="white")
                return plotly_to_html(fig)

            xvar = XVAR_ALIASES.get(input.comp_xvar() or "moving", "moving")
            yvar = YVAR_ALIASES.get(input.comp_yvar() or "Fréquence cardiaque", "heartrate")
            yvar2_input = input.comp_yvar2() or "none"
            yvar2 = YVAR_ALIASES.get(yvar2_input, None) if yvar2_input != "none" else None

            info1 = id_to_info.get().get(act_id_1, {})
            activity_type1 = (info1.get("type") or "run").lower()

            x1, y1, x1_label, y1_label, _, _ = _prep_xy(df1_cropped, xvar, yvar, activity_type1, smooth_win=21)

            # Debug: Print data info
            print(f"[DEBUG comparison_plot] x1 type: {type(x1)}, len: {len(x1) if hasattr(x1, '__len__') else 'N/A'}")
            print(f"[DEBUG comparison_plot] y1 type: {type(y1)}, len: {len(y1) if hasattr(y1, '__len__') else 'N/A'}")
            if len(x1) > 0:
                print(f"[DEBUG comparison_plot] x1 sample: {x1[:5]}, y1 sample: {y1[:5]}")

            # Calculate max_x BEFORE converting to lists (numpy arrays have .max(), lists don't)
            max_x = x1.max() if len(x1) > 0 else 0

            # Convert numpy arrays to lists for Plotly compatibility
            x1 = x1.tolist() if hasattr(x1, 'tolist') else list(x1)
            y1 = y1.tolist() if hasattr(y1, 'tolist') else list(y1)

            # Remove NaN values which can cause rendering issues
            valid_mask = [not (np.isnan(xi) if isinstance(xi, (float, np.floating)) else False or
                              np.isnan(yi) if isinstance(yi, (float, np.floating)) else False)
                          for xi, yi in zip(x1, y1)]
            x1 = [x for x, v in zip(x1, valid_mask) if v]
            y1 = [y for y, v in zip(y1, valid_mask) if v]

            print(f"[DEBUG comparison_plot] After cleaning - x1 len: {len(x1)}, y1 len: {len(y1)}")

            # Check if we have data after cleaning
            if len(x1) == 0 or len(y1) == 0:
                fig = go.Figure()
                fig.add_annotation(text="Aucune donnee valide pour l'Activite 1", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font=dict(size=18, color="#D92323"))
                fig.update_layout(autosize=True, xaxis=dict(visible=False), yaxis=dict(visible=False), height=600, plot_bgcolor="white")
                return plotly_to_html(fig)

            # Helper function to format seconds to mm:ss or hh:mm:ss
            def format_seconds_to_time(seconds):
                """Convert seconds to hh:mm:ss format"""
                h = int(seconds // 3600)
                m = int((seconds % 3600) // 60)
                s = int(seconds % 60)
                if h > 0:
                    return f"{h}:{m:02d}:{s:02d}"
                else:
                    return f"{m}:{s:02d}"

            # Helper function to format pace (sec/km) to mm:ss
            def format_pace(pace_sec):
                """Convert pace in seconds/km to M:SS format"""
                if pd.isna(pace_sec) or pace_sec <= 0:
                    return "--:--"
                m = int(pace_sec // 60)
                s = int(pace_sec % 60)
                return f"{m}:{s:02d}"

            # Check if Y-axis is pace (needs MM:SS formatting)
            is_pace_y1 = yvar == "pace" or "Allure" in y1_label

            # Rounding rules for float metrics in hover display
            _comp_hover_format = {
                "vertical_oscillation": ".1f",
                "leg_spring_stiffness": ".2f",
            }

            def _fmt_hover_vals(values, is_pace, var_name):
                if is_pace:
                    return [format_pace(p) for p in values]
                fmt = _comp_hover_format.get(var_name, ".1f")
                return [f"{v:{fmt}}" for v in values]

            # Create formatted time labels for hover
            x1_formatted = [format_seconds_to_time(t) for t in x1]
            # Create formatted Y values for pace
            y1_formatted = _fmt_hover_vals(y1, is_pace_y1, yvar)

            fig = go.Figure()
            # Primary Y-axis trace for Activity 1 (solid red)
            # Use list of tuples for customdata: (time_formatted, y_formatted)
            customdata_1 = list(zip(x1_formatted, y1_formatted))
            fig.add_trace(go.Scatter(
                x=x1, y=y1, mode='lines',
                line=dict(color='#D92323', width=2.5),
                name=f"Activité 1 - {y1_label}",
                yaxis='y',
                customdata=customdata_1,
                hovertemplate='<b>Activité 1</b><br>Temps: %{customdata[0]}<br>' + y1_label + ': %{customdata[1]}<extra></extra>'
            ))
            
            # Secondary Y-axis trace for Activity 1 (dashed red) if selected
            if yvar2:
                x1_y2, y1_y2, _, y1_y2_label, _, _ = _prep_xy(df1_cropped, xvar, yvar2, activity_type1, smooth_win=21)
                # Convert to lists and clean NaN
                x1_y2 = x1_y2.tolist() if hasattr(x1_y2, 'tolist') else list(x1_y2)
                y1_y2 = y1_y2.tolist() if hasattr(y1_y2, 'tolist') else list(y1_y2)
                valid_mask = [not (np.isnan(xi) if isinstance(xi, (float, np.floating)) else False or
                                  np.isnan(yi) if isinstance(yi, (float, np.floating)) else False)
                              for xi, yi in zip(x1_y2, y1_y2)]
                x1_y2 = [x for x, v in zip(x1_y2, valid_mask) if v]
                y1_y2 = [y for y, v in zip(y1_y2, valid_mask) if v]
                x1_y2_formatted = [format_seconds_to_time(t) for t in x1_y2]
                # Check if secondary Y-axis is pace
                is_pace_y2 = yvar2 == "pace" or "Allure" in y1_y2_label
                y1_y2_formatted = _fmt_hover_vals(y1_y2, is_pace_y2, yvar2)
                if len(x1_y2) > 0:  # Only add trace if there's data
                    customdata_1_y2 = list(zip(x1_y2_formatted, y1_y2_formatted))
                    fig.add_trace(go.Scatter(
                        x=x1_y2, y=y1_y2, mode='lines',
                        line=dict(color='#D92323', width=2.5, dash='dash'),
                        name=f"Activité 1 - {y1_y2_label}",
                        yaxis='y2',
                        customdata=customdata_1_y2,
                        hovertemplate='<b>Activité 1</b><br>Temps: %{customdata[0]}<br>' + y1_y2_label + ': %{customdata[1]}<extra></extra>'
                    ))
            
            act_id_2 = comparison_activity_id_2.get()
            if act_id_2:
                df2 = fetch_timeseries_cached(act_id_2)
                if not df2.empty and 't_active_sec' in df2.columns:
                    # Get crop range - don't modify reactive values here to avoid circular reactivity
                    crop2 = crop_range_2.get()
                    # Use full range if crop not initialized
                    if crop2 == [0, 0] or crop2[1] == 0:
                        crop2 = [0, df2['t_active_sec'].max()]
                    
                    df2_cropped = crop_timeseries(df2, "time", crop2[0], crop2[1])
                    info2 = id_to_info.get().get(act_id_2, {})
                    activity_type2 = (info2.get("type") or "run").lower()
                    x2, y2, _, _, _, _ = _prep_xy(df2_cropped, xvar, yvar, activity_type2, smooth_win=21)

                    # Use the longest workout for X-axis max (before converting to list)
                    max_x = max(max_x, x2.max() if len(x2) > 0 else 0)

                    # Convert to lists and clean NaN
                    x2 = x2.tolist() if hasattr(x2, 'tolist') else list(x2)
                    y2 = y2.tolist() if hasattr(y2, 'tolist') else list(y2)
                    valid_mask = [not (np.isnan(xi) if isinstance(xi, (float, np.floating)) else False or
                                      np.isnan(yi) if isinstance(yi, (float, np.floating)) else False)
                                  for xi, yi in zip(x2, y2)]
                    x2 = [x for x, v in zip(x2, valid_mask) if v]
                    y2 = [y for y, v in zip(y2, valid_mask) if v]

                    print(f"[DEBUG comparison_plot] Activity 2 - x2 len: {len(x2)}, y2 len: {len(y2)}")

                    # Create formatted time labels for Activity 2
                    x2_formatted = [format_seconds_to_time(t) for t in x2]
                    # Format Y values for Activity 2 (use same is_pace_y1 since same metric)
                    y2_formatted = _fmt_hover_vals(y2, is_pace_y1, yvar)

                    # Primary Y-axis trace for Activity 2 (solid yellow/orange)
                    if len(x2) > 0:  # Only add trace if there's data
                        customdata_2 = list(zip(x2_formatted, y2_formatted))
                        fig.add_trace(go.Scatter(
                            x=x2, y=y2, mode='lines',
                            line=dict(color='#F59E0B', width=2.5),  # Amber/orange color
                            name=f"Activité 2 - {y1_label}",
                            yaxis='y',
                            customdata=customdata_2,
                            hovertemplate='<b>Activité 2</b><br>Temps: %{customdata[0]}<br>' + y1_label + ': %{customdata[1]}<extra></extra>'
                        ))

                    # Secondary Y-axis trace for Activity 2 (dashed yellow/orange) if selected
                    if yvar2:
                        x2_y2, y2_y2, _, y2_y2_label, _, _ = _prep_xy(df2_cropped, xvar, yvar2, activity_type2, smooth_win=21)
                        # Convert to lists and clean NaN
                        x2_y2 = x2_y2.tolist() if hasattr(x2_y2, 'tolist') else list(x2_y2)
                        y2_y2 = y2_y2.tolist() if hasattr(y2_y2, 'tolist') else list(y2_y2)
                        valid_mask = [not (np.isnan(xi) if isinstance(xi, (float, np.floating)) else False or
                                          np.isnan(yi) if isinstance(yi, (float, np.floating)) else False)
                                      for xi, yi in zip(x2_y2, y2_y2)]
                        x2_y2 = [x for x, v in zip(x2_y2, valid_mask) if v]
                        y2_y2 = [y for y, v in zip(y2_y2, valid_mask) if v]
                        x2_y2_formatted = [format_seconds_to_time(t) for t in x2_y2]
                        # Check if secondary Y-axis is pace for Activity 2
                        is_pace_y2_act2 = yvar2 == "pace" or "Allure" in y2_y2_label
                        y2_y2_formatted = _fmt_hover_vals(y2_y2, is_pace_y2_act2, yvar2)
                        if len(x2_y2) > 0:  # Only add trace if there's data
                            customdata_2_y2 = list(zip(x2_y2_formatted, y2_y2_formatted))
                            fig.add_trace(go.Scatter(
                                x=x2_y2, y=y2_y2, mode='lines',
                                line=dict(color='#F59E0B', width=2.5, dash='dash'),
                                name=f"Activité 2 - {y2_y2_label}",
                                yaxis='y2',
                                customdata=customdata_2_y2,
                                hovertemplate='<b>Activité 2</b><br>Temps: %{customdata[0]}<br>' + y2_y2_label + ': %{customdata[1]}<extra></extra>'
                            ))
            
            # Create custom tick values and labels
            if max_x > 0:
                # Create ticks every 5 minutes (300s) or appropriate interval
                if max_x <= 1800:  # <= 30 min
                    tick_interval = 300  # 5 min
                elif max_x <= 3600:  # <= 1 hour
                    tick_interval = 600  # 10 min
                else:
                    tick_interval = 900  # 15 min
                
                tick_vals = list(range(0, int(max_x) + tick_interval, tick_interval))
                tick_text = [format_seconds_to_time(t) for t in tick_vals]
            else:
                tick_vals = [0]
                tick_text = ["0:00"]
            
            # Build layout with secondary Y-axis if needed
            layout_config = dict(
                autosize=True,  # Responsive sizing for production
                xaxis=dict(
                    title="Temps",
                    showgrid=True,
                    gridcolor='rgba(128, 128, 128, 0.2)',
                    tickfont=dict(size=12),
                    tickmode='array',
                    tickvals=tick_vals,
                    ticktext=tick_text,
                    range=[0, max_x * 1.02]  # Add 2% padding
                ),
                yaxis=dict(
                    title=y1_label,
                    showgrid=True,
                    gridcolor='rgba(128, 128, 128, 0.2)',
                    tickfont=dict(size=12),
                    title_font=dict(color='#D92323')
                ),
                plot_bgcolor='white',
                height=600, 
                hovermode='x unified',
                legend=dict(x=0.01, y=0.99, bgcolor='rgba(255,255,255,0.9)', font=dict(size=11)),
                margin=dict(l=70, r=70, t=50, b=70), 
                font=dict(size=13)
            )
            
            # Add secondary Y-axis if selected
            if yvar2:
                yaxis2_config = dict(
                    title=y1_y2_label if 'y1_y2_label' in locals() else yvar2_input,
                    overlaying='y',
                    side='right',
                    showgrid=False,
                    tickfont=dict(size=12),
                    title_font=dict(color='#666')
                )

                # Add pace formatting for secondary Y-axis if it's pace (min/km)
                if yvar2 == "pace":
                    # Collect all y2 values to determine range
                    # Filter to realistic running paces: 2:00/km to 10:00/km (120-600 sec/km)
                    MIN_PACE = 120  # 2:00/km (very fast sprint)
                    MAX_PACE = 600  # 10:00/km (slow jog/walk)

                    all_y2_values = []
                    if 'y1_y2' in locals() and y1_y2 is not None:
                        all_y2_values.extend([v for v in y1_y2 if v is not None and not np.isnan(v) and MIN_PACE <= v <= MAX_PACE])
                    if 'y2_y2' in locals() and y2_y2 is not None:
                        all_y2_values.extend([v for v in y2_y2 if v is not None and not np.isnan(v) and MIN_PACE <= v <= MAX_PACE])

                    if all_y2_values:
                        y2_min = min(all_y2_values)
                        y2_max = max(all_y2_values)

                        # Add some padding (10% on each side)
                        y2_padding = (y2_max - y2_min) * 0.1
                        y2_min = max(MIN_PACE, y2_min - y2_padding)
                        y2_max = min(MAX_PACE, y2_max + y2_padding)

                        # Generate pace tick values - only full minutes for cleaner display
                        y2_min_minutes = int(y2_min // 60)
                        y2_max_minutes = int(y2_max // 60) + 1

                        # Choose tick interval based on range (aim for 4-6 ticks)
                        num_minutes = y2_max_minutes - y2_min_minutes
                        if num_minutes <= 4:
                            tick_interval = 1  # Every minute
                        elif num_minutes <= 8:
                            tick_interval = 2  # Every 2 minutes
                        else:
                            tick_interval = max(1, num_minutes // 4)  # ~4 ticks

                        pace_ticks = []
                        for minute in range(y2_min_minutes, y2_max_minutes + 1, tick_interval):
                            pace_ticks.append(minute * 60)

                        # Format pace labels as M:SS
                        def format_pace_label(seconds):
                            minutes = int(seconds // 60)
                            secs = int(seconds % 60)
                            return f"{minutes}:{secs:02d}"

                        pace_labels = [format_pace_label(t) for t in pace_ticks]

                        yaxis2_config['tickmode'] = 'array'
                        yaxis2_config['tickvals'] = pace_ticks
                        yaxis2_config['ticktext'] = pace_labels
                        yaxis2_config['range'] = [y2_min, y2_max]  # Set explicit range to filter outliers
                        # NO reversal - slower pace (high value) at top, faster (low value) at bottom

                layout_config['yaxis2'] = yaxis2_config
                layout_config['margin'] = dict(l=70, r=90, t=50, b=70)  # More space for right axis
            
            fig.update_layout(**layout_config)

            # Debug: Print figure info before returning
            print(f"[DEBUG comparison_plot] Figure has {len(fig.data)} traces")
            for i, trace in enumerate(fig.data):
                print(f"[DEBUG comparison_plot] Trace {i}: name='{trace.name}', x_len={len(trace.x) if trace.x is not None else 0}, y_len={len(trace.y) if trace.y is not None else 0}")

            return plotly_to_html(fig)
        except Exception as e:
            print(f"[DEBUG comparison_plot] Exception: {str(e)}")
            import traceback
            traceback.print_exc()
            fig = go.Figure()
            # Sanitize error message - truncate and remove Plotly documentation text
            error_msg = str(e)
            # Truncate very long error messages (likely contain Plotly docs)
            if len(error_msg) > 150:
                error_msg = error_msg[:147] + "..."
            # Remove common Plotly documentation patterns
            doc_patterns = ["rangebreaks", "rangemode", "scaleanchor", "extrema of the input data", "tozero", "nonnegative"]
            if any(pattern in error_msg.lower() for pattern in doc_patterns):
                error_msg = "Erreur de configuration du graphique. Veuillez reessayer."
            fig.add_annotation(text=f"Erreur: {error_msg}", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font=dict(size=16, color="#dc2626"))
            fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False), height=600, plot_bgcolor="white")
            return plotly_to_html(fig)
    
    # Comparison statistics card
    @output
    @render.ui
    def comparison_stats_card():
        """Display detailed statistics comparison for both workouts"""
        if not input.comparison_enabled():
            return ui.div()  # Comparison not enabled
        
        act_id_1 = comparison_activity_id_1.get()
        if not act_id_1:
            return ui.div()  # No activity 1 selected
        
        try:
            # Fetch and crop Activity 1 data
            df1 = fetch_timeseries_cached(act_id_1)
            if df1.empty or 't_active_sec' not in df1.columns:
                return ui.div()
            
            crop1 = crop_range_1.get()
            if crop1 == [0, 0] or crop1[1] == 0:
                crop1 = [0, df1['t_active_sec'].max()]
            df1_cropped = crop_timeseries(df1, "time", crop1[0], crop1[1])
            
            # Get Activity 1 info
            info1 = id_to_info.get().get(act_id_1, {})
            activity_type1 = (info1.get("type") or "run").lower()
            
            # Calculate statistics for Activity 1
            stats1 = calculate_workout_stats(df1_cropped, activity_type1)
            
            # Fetch and crop Activity 2 data (if enabled)
            stats2 = None
            info2 = None
            act_id_2 = comparison_activity_id_2.get()
            if act_id_2:
                df2 = fetch_timeseries_cached(act_id_2)
                if not df2.empty and 't_active_sec' in df2.columns:
                    crop2 = crop_range_2.get()
                    if crop2 == [0, 0] or crop2[1] == 0:
                        crop2 = [0, df2['t_active_sec'].max()]
                    df2_cropped = crop_timeseries(df2, "time", crop2[0], crop2[1])
                    
                    info2 = id_to_info.get().get(act_id_2, {})
                    activity_type2 = (info2.get("type") or "run").lower()
                    stats2 = calculate_workout_stats(df2_cropped, activity_type2)
            
            # Build the comparison card
            return build_comparison_stats_ui(stats1, stats2, crop1, crop2 if stats2 else None, info1, info2)
            
        except Exception as e:
            print(f"Error in comparison_stats_card: {e}")
            import traceback
            traceback.print_exc()
            return ui.div(
                ui.card(
                    ui.card_header("Erreur"),
                    ui.div(f"Erreur lors du calcul des statistiques: {str(e)}", style="padding: 1rem; color: #dc2626;")
                )
            )
    
    def calculate_workout_stats(df, activity_type):
        """Calculate comprehensive statistics for a workout segment"""
        stats = {}
        
        # Heart Rate
        if 'heartrate' in df.columns:
            hr_data = df['heartrate'].dropna()
            if len(hr_data) > 0:
                stats['hr_avg'] = np.mean(hr_data)
                stats['hr_min'] = np.min(hr_data)
                stats['hr_max'] = np.max(hr_data)
        
        # Cadence
        if 'cadence' in df.columns:
            cad_data = df['cadence'].dropna()
            if len(cad_data) > 0:
                stats['cadence_avg'] = np.mean(cad_data)
                stats['cadence_min'] = np.min(cad_data)
                stats['cadence_max'] = np.max(cad_data)
        
        # Speed/Pace (calculate from distance and time)
        if 'distance' in df.columns and 't_active_sec' in df.columns and len(df) > 1:
            # Calculate speed in m/s, then convert to pace (min/km)
            total_distance_m = df['distance'].iloc[-1] - df['distance'].iloc[0]
            total_time_s = df['t_active_sec'].iloc[-1] - df['t_active_sec'].iloc[0]
            
            if total_time_s > 0 and total_distance_m > 0:
                speed_ms = total_distance_m / total_time_s
                pace_min_per_km = (1000 / speed_ms) / 60  # Convert to min/km
                stats['pace_avg'] = pace_min_per_km
                
                # Calculate instantaneous pace for min/max
                df_copy = df.copy()
                df_copy['speed_ms'] = df_copy['distance'].diff() / df_copy['t_active_sec'].diff()
                df_copy['pace_min_km'] = (1000 / df_copy['speed_ms']) / 60
                
                # Filter out unrealistic pace values (< 2 min/km or > 15 min/km)
                valid_pace = df_copy['pace_min_km'][(df_copy['pace_min_km'] >= 2) & (df_copy['pace_min_km'] <= 15)]
                if len(valid_pace) > 0:
                    stats['pace_min'] = np.min(valid_pace)
                    stats['pace_max'] = np.max(valid_pace)
        
        # Vertical Oscillation
        if 'vertical_oscillation' in df.columns:
            vo_data = df['vertical_oscillation'].dropna()
            if len(vo_data) > 0:
                stats['vo_avg'] = np.mean(vo_data)
                stats['vo_min'] = np.min(vo_data)
                stats['vo_max'] = np.max(vo_data)
        
        # Ground Contact Time (GCT)
        if 'ground_contact_time' in df.columns:
            gct_data = df['ground_contact_time'].dropna()
            if len(gct_data) > 0:
                stats['gct_avg'] = np.mean(gct_data)
                stats['gct_min'] = np.min(gct_data)
                stats['gct_max'] = np.max(gct_data)

        # Leg Spring Stiffness (LSS)
        if 'leg_spring_stiffness' in df.columns:
            lss_data = df['leg_spring_stiffness'].dropna()
            if len(lss_data) > 0:
                stats['lss_avg'] = np.mean(lss_data)
                stats['lss_min'] = np.min(lss_data)
                stats['lss_max'] = np.max(lss_data)

        # Power
        if 'watts' in df.columns:
            power_data = df['watts'].dropna()
            if len(power_data) > 0:
                stats['power_avg'] = np.mean(power_data)
                stats['power_min'] = np.min(power_data)
                stats['power_max'] = np.max(power_data)
        
        return stats
    
    def build_comparison_stats_ui(stats1, stats2, crop1, crop2, info1, info2):
        """Build the UI for comparison statistics"""
        
        def format_date(date_str):
            """Format date string to 'DD Month YYYY' in French"""
            if not date_str:
                return ""
            try:
                from datetime import datetime
                # Parse the date string (assuming format like "2025-09-30")
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                # French month names
                months_fr = ["janvier", "février", "mars", "avril", "mai", "juin",
                           "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
                return f"{dt.day} {months_fr[dt.month - 1]} {dt.year}"
            except:
                return date_str
        
        def format_time_range(crop_range):
            """Format crop range as time string"""
            if not crop_range:
                return "N/A"
            start, end = crop_range
            def fmt(seconds):
                h = int(seconds // 3600)
                m = int((seconds % 3600) // 60)
                s = int(seconds % 60)
                if h > 0:
                    return f"{h}:{m:02d}:{s:02d}"
                return f"{m}:{s:02d}"
            return f"{fmt(start)} → {fmt(end)}"
        
        def format_pace(pace_min_km):
            """Format pace as min:sec/km"""
            if pd.isna(pace_min_km):
                return "N/A"
            minutes = int(pace_min_km)
            seconds = int((pace_min_km - minutes) * 60)
            return f"{minutes}:{seconds:02d}"
        
        # Metrics to display
        metrics = [
            {
                'name': 'Fréquence cardiaque',
                'key': 'hr',
                'unit': 'bpm',
                'format': lambda x: f"{x:.0f}",
                'icon': ''
            },
            {
                'name': 'Cadence',
                'key': 'cadence',
                'unit': 'spm',
                'format': lambda x: f"{x:.0f}",
                'icon': ''
            },
            {
                'name': 'Allure',
                'key': 'pace',
                'unit': 'min/km',
                'format': format_pace,
            },
            {
                'name': 'Oscillation verticale',
                'key': 'vo',
                'unit': 'mm',
                'format': lambda x: f"{x:.1f}",
                'icon': ''
            },
            {
                'name': 'Temps de contact (GCT)',
                'key': 'gct',
                'unit': 'ms',
                'format': lambda x: f"{x:.0f}"
            },
            {
                'name': 'Leg Spring Stiffness (LSS)',
                'key': 'lss',
                'unit': 'kN/m',
                'format': lambda x: f"{x:.1f}",
                'icon': ''
            },
            {
                'name': 'Puissance',
                'key': 'power',
                'unit': 'W',
                'format': lambda x: f"{x:.0f}",
            }
        ]
        
        # Build metric rows
        metric_rows = []
        for metric in metrics:
            key = metric['key']
            avg_key = f"{key}_avg"
            
            # Check if metric is available in either workout
            has_metric_1 = avg_key in stats1
            has_metric_2 = avg_key in stats2 if stats2 else False
            
            if not has_metric_1 and not has_metric_2:
                continue  # Skip if metric not available in either workout
            
            # Get values for Activity 1
            val1_avg = metric['format'](stats1.get(avg_key, np.nan)) if has_metric_1 else "—"
            
            # Get values for Activity 2
            val2_avg = metric['format'](stats2.get(avg_key, np.nan)) if has_metric_2 else "—"
            
            # Calculate difference if both have the metric
            diff_str = ""
            if has_metric_1 and has_metric_2 and key != 'pace':  # Don't show diff for pace (complex)
                val1 = stats1.get(avg_key)
                val2 = stats2.get(avg_key)
                if not pd.isna(val1) and not pd.isna(val2):
                    diff = val2 - val1
                    diff_pct = (diff / val1 * 100) if val1 != 0 else 0
                    sign = "+" if diff > 0 else ""
                    diff_color = "#16a34a" if diff < 0 and key == 'hr' else "#16a34a" if diff > 0 else "#dc2626"
                    diff_str = f"{sign}{diff:.1f} ({sign}{diff_pct:.1f}%)"
            
            metric_rows.append(
                ui.div(
                    ui.layout_columns(
                        ui.div(
                            ui.span(metric.get('icon', ''), style="margin-right: 0.5rem;"),
                            ui.span(metric['name'], style="font-weight: 600;"),
                            style="display: flex; align-items: center;"
                        ),
                        ui.div(
                            ui.div(val1_avg, style="font-size: 1.3rem; font-weight: bold; color: #D92323;"),
                            ui.div(metric['unit'], style="font-size: 0.75rem; color: #666;"),
                            style="text-align: center;"
                        ),
                        ui.div(
                            ui.div(val2_avg if stats2 else "—", style="font-size: 1.3rem; font-weight: bold; color: #F59E0B;"),
                            ui.div(metric['unit'], style="font-size: 0.75rem; color: #666;"),
                            style="text-align: center;"
                        ),
                        ui.div(
                            diff_str,
                            style=f"text-align: center; font-size: 0.9rem; color: {diff_color if diff_str else '#666'}; font-weight: 600;"
                        ) if stats2 else ui.div(),
                        col_widths=[4, 2, 2, 4] if stats2 else [6, 3, 3]
                    ),
                    style="padding: 0.75rem; border-bottom: 1px solid #e5e7eb;"
                )
            )
        
        # Build header with dates
        date1 = format_date(info1.get("date_str", "")) if info1 else ""
        activity1_label = f"Activité 1 - {date1}" if date1 else "Activité 1"
        
        header_cols = [
            ui.div("Métrique", style="font-weight: 700; color: #374151;"),
            ui.div(activity1_label, style="font-weight: 700; color: #D92323; text-align: center;"),
        ]
        
        if stats2:
            date2 = format_date(info2.get("date_str", "")) if info2 else ""
            activity2_label = f"Activité 2 - {date2}" if date2 else "Activité 2"
            header_cols.extend([
                ui.div(activity2_label, style="font-weight: 700; color: #F59E0B; text-align: center;"),
                ui.div("Différence", style="font-weight: 700; color: #374151; text-align: center;")
            ])
        else:
            header_cols.append(ui.div())
        
        return ui.card(
            ui.card_header(
                ui.div(
                    ui.span("Statistiques comparatives", style="font-weight: bold; font-size: 1.1rem;"),
                    style="display: flex; align-items: center;"
                )
            ),
            ui.div(
                # Time ranges
                ui.div(
                    ui.layout_columns(
                        ui.div("Plage analysée:", style="font-weight: 600; color: #666;"),
                        ui.div(format_time_range(crop1), style="color: #D92323; font-weight: 600; text-align: center;"),
                        ui.div(format_time_range(crop2) if stats2 else "—", style="color: #F59E0B; font-weight: 600; text-align: center;"),
                        ui.div(),
                        col_widths=[4, 2, 2, 4] if stats2 else [6, 3, 3]
                    ),
                    style="padding: 1rem; background: #f9fafb; border-bottom: 2px solid #e5e7eb; margin-bottom: 0.5rem;"
                ),
                
                # Header row
                ui.div(
                    ui.layout_columns(
                        *header_cols,
                        col_widths=[4, 2, 2, 4] if stats2 else [6, 3, 3]
                    ),
                    style="padding: 0.75rem; background: #f3f4f6; border-bottom: 2px solid #d1d5db;"
                ),
                
                # Metric rows
                *metric_rows,
                
                style="padding: 0;"
            ),
            style="background: white; border: 1px solid #e5e7eb;"
        )

    # ========== SURVEY FORM HANDLERS ==========
    
    # Reactive value to store survey data
    survey_data = reactive.Value(None)
    
    # Generate dynamic training perception sections (one per workout)
    @output
    @render.ui
    @reactive.event(input.survey_date)
    def survey_training_perception_sections():
        # Check authentication
        athlete_id = user_athlete_id.get()
        role = user_role.get()
        
        if not athlete_id or role == "coach":
            return ui.div()
        
        # Get selected date
        selected_date = input.survey_date()
        if not selected_date:
            return ui.div()
        
        try:
            # Query workouts for this date
            params = {
                "athlete_id": f"eq.{athlete_id}",
                "date": f"eq.{selected_date.isoformat()}"
            }
            
            df_date = supa_select(
                "activity_metadata",
                select="activity_id,athlete_id,type,date,start_time,distance_m,duration_sec,avg_hr",
                params=params,
                limit=100
            )
            
            # Filter for running activities
            if not df_date.empty and "type" in df_date.columns:
                m = df_date["type"].str.lower().isin(["run", "trailrun", "virtualrun"])
                df_date = df_date.loc[m].copy()
            
            # Calculate duration_min and distance_km
            if "duration_min" not in df_date.columns and "duration_sec" in df_date.columns:
                df_date["duration_min"] = pd.to_numeric(df_date["duration_sec"], errors="coerce") / 60.0
            if "distance_km" not in df_date.columns and "distance_m" in df_date.columns:
                df_date["distance_km"] = pd.to_numeric(df_date["distance_m"], errors="coerce") / 1000.0
            
            # Sort by start_time
            if "start_time" in df_date.columns:
                df_date = df_date.sort_values("start_time", ascending=True)
            
            workout_count = len(df_date)
            
            # If no workouts, show message
            if workout_count == 0:
                return ui.div(
                    ui.tags.h4("2. Perception de l'entraînement", 
                        style="color: #D92323; margin-bottom: 1rem; border-bottom: 2px solid #D92323; padding-bottom: 0.5rem;"),
                    ui.tags.p("Aucun entraînement trouvé pour cette date.", 
                        style="color: #6b7280; font-style: italic; padding: 1.5rem;"),
                    style="margin-bottom: 2rem; padding: 1.5rem; background: #f9f9f9; border-radius: 8px;"
                )
            
            # Type labels
            type_labels = {
                "run": "Course extérieur",
                "trailrun": "Course en sentier",
                "virtualrun": "Course sur tapis"
            }
            
            # French month names
            mois_fr = ["janvier", "février", "mars", "avril", "mai", "juin", 
                       "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
            
            # Build sections - one per workout
            sections = []
            
            for idx, (_, row) in enumerate(df_date.iterrows(), start=1):
                # Build workout label
                type_fr = type_labels.get(str(row.get("type", "")).lower(), "Activité")
                date_obj = pd.to_datetime(row["start_time"])
                date_str = f"{date_obj.day} {mois_fr[date_obj.month - 1]} {date_obj.year}"
                
                duration_min = row.get("duration_min", 0)
                if pd.isna(duration_min) or duration_min == 0:
                    time_str = "0:00"
                else:
                    total_seconds = int(duration_min * 60)
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60
                    if hours > 0:
                        time_str = f"{hours}:{minutes:02d}:{seconds:02d}"
                    else:
                        time_str = f"{minutes}:{seconds:02d}"
                
                distance_km = row.get("distance_km", 0)
                dist_str = f"{distance_km:.2f}" if not pd.isna(distance_km) else "0.00"
                
                workout_label = f"{type_fr} - {date_str} - {time_str} - {dist_str} km"
                
                # Section header
                if workout_count == 1:
                    header_text = "2. Perception de l'entraînement"
                else:
                    header_text = f"2{chr(96+idx)}. Perception - Entraînement {idx}"
                
                # Create section
                section = ui.div(
                    ui.tags.h4(header_text, 
                        style="color: #D92323; margin-bottom: 1rem; border-bottom: 2px solid #D92323; padding-bottom: 0.5rem;"),
                    
                    # Workout info
                    ui.tags.p(workout_label, 
                        style="font-weight: 600; color: #333; margin-bottom: 1rem; font-size: 0.95rem;"),
                    
                    # Difficulty
                    ui.div(
                        ui.tags.label(
                            "Difficulté de l'entraînement",
                            style="font-weight: 600; display: block; margin-bottom: 0.5rem;"
                        ),
                        ui.input_slider(f"workout_difficulty_{idx}", "", min=1, max=10, value=5, step=1, width="100%"),
                        style="margin-bottom: 1.5rem;"
                    ),

                    # Motivation
                    ui.div(
                        ui.tags.label(
                            "Niveau de motivation",
                            style="font-weight: 600; display: block; margin-bottom: 0.5rem;"
                        ),
                        ui.input_slider(f"motivation_level_{idx}", "", min=1, max=10, value=5, step=1, width="100%"),
                        style="margin-bottom: 1.5rem;"
                    ),

                    # Satisfaction
                    ui.div(
                        ui.tags.label(
                            "Satisfaction générale",
                            style="font-weight: 600; display: block; margin-bottom: 0.5rem;"
                        ),
                        ui.input_slider(f"satisfaction_rating_{idx}", "", min=1, max=5, value=3, step=1, width="100%"),
                        style="margin-bottom: 1.5rem;"
                    ),
                    
                    style="margin-bottom: 2rem; padding: 1.5rem; background: #f9f9f9; border-radius: 8px;"
                )
                
                sections.append(section)
            
            return ui.div(*sections)
            
        except Exception as e:
            print(f"[ERROR] Training perception sections: {e}")
            import traceback
            traceback.print_exc()
            return ui.div(
                ui.tags.p("Erreur lors du chargement des entraînements", 
                    style="color: #ef4444; margin-bottom: 1.5rem;")
            )
    
    # Display workout selector based on selected date (DEPRECATED - keeping for reference)
    @output
    @render.ui
    @reactive.event(input.survey_date)  # Reactive to date changes
    def survey_workout_selector():
        # Check authentication
        athlete_id = user_athlete_id.get()
        role = user_role.get()
        
        if not athlete_id:
            return ui.div()
        
        # If coach, show message
        if role == "coach":
            return ui.div(
                ui.tags.p("Les questionnaires sont réservés aux athlètes. Connectez-vous en tant qu'athlète pour remplir un questionnaire.", 
                    style="color: #6b7280; font-style: italic; margin-bottom: 1.5rem;")
            )
        
        # Get selected date
        selected_date = input.survey_date()
        if not selected_date:
            return ui.div()  # No date selected, show nothing
        
        try:
            # Query activity_metadata by date column
            params = {
                "athlete_id": f"eq.{athlete_id}",
                "date": f"eq.{selected_date.isoformat()}"
            }
            
            # Query activity_metadata table
            df_date = supa_select(
                "activity_metadata",
                select="activity_id,athlete_id,type,date,start_time,distance_m,duration_sec,avg_hr",
                params=params,
                limit=100
            )
            
            if df_date.empty:
                return ui.div(
                    ui.tags.p("Aucun entraînement trouvé pour cette date.", 
                        style="color: #6b7280; font-style: italic; margin-bottom: 1.5rem;")
                )
            
            # Filter for running activities only
            if "type" in df_date.columns:
                m = df_date["type"].str.lower().isin(["run", "trailrun", "virtualrun"])
                df_date = df_date.loc[m].copy()
            
            if df_date.empty:
                return ui.div(
                    ui.tags.p("Aucun entraînement de course trouvé pour cette date.", 
                        style="color: #6b7280; font-style: italic; margin-bottom: 1.5rem;")
                )
            
            # Ensure we have duration_min and distance_km
            if "duration_min" not in df_date.columns and "duration_sec" in df_date.columns:
                df_date["duration_min"] = pd.to_numeric(df_date["duration_sec"], errors="coerce") / 60.0
            if "distance_km" not in df_date.columns and "distance_m" in df_date.columns:
                df_date["distance_km"] = pd.to_numeric(df_date["distance_m"], errors="coerce") / 1000.0
            
            # Sort by start_time
            if "start_time" in df_date.columns:
                df_date = df_date.sort_values("start_time", ascending=True)
            
            # Type labels mapping (same as Analyse de séance)
            type_labels = {
                "run": "Course extérieur",
                "trailrun": "Course en sentier",
                "virtualrun": "Course sur tapis"
            }
            
            # French month names
            mois_fr = ["janvier", "février", "mars", "avril", "mai", "juin", 
                       "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
            
            # Build dropdown choices using EXACT same make_label logic
            choices = {"none": "Aucun entraînement sélectionné"}
            
            for _, row in df_date.iterrows():
                # Type in French
                type_fr = type_labels.get(str(row.get("type", "")).lower(), str(row.get("type", "Activité")))
                
                # Date in French format (e.g., "2 juillet 2025")
                date_obj = pd.to_datetime(row["start_time"])
                date_str = f"{date_obj.day} {mois_fr[date_obj.month - 1]} {date_obj.year}"
                
                # Duration in mm:ss or h:mm:ss format
                duration_min = row.get("duration_min", 0)
                if pd.isna(duration_min) or duration_min == 0:
                    time_str = "0:00"
                else:
                    total_seconds = int(duration_min * 60)
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60
                    
                    if hours > 0:
                        time_str = f"{hours}:{minutes:02d}:{seconds:02d}"
                    else:
                        time_str = f"{minutes}:{seconds:02d}"
                
                # Distance in km
                distance_km = row.get("distance_km", 0)
                if pd.isna(distance_km):
                    dist_str = "0.00"
                else:
                    dist_str = f"{distance_km:.2f}"
                
                # Build label - EXACT format: "Type - Date - Duration - Distance km"
                # Note: Skipping intervals check for performance (can add back if needed)
                label = f"{type_fr} - {date_str} - {time_str} - {dist_str} km"
                
                choices[str(row["activity_id"])] = label
            
            return ui.div(
                ui.input_select(
                    "survey_activity_id",
                    "Entraînement associé (optionnel)",
                    choices=choices,
                    selected="none",
                    width="100%"
                ),
                style="margin-bottom: 1.5rem;"
            )
            
        except Exception as e:
            print(f"[ERROR] Survey workout selector: {e}")
            import traceback
            traceback.print_exc()
            return ui.div(
                ui.tags.p("Erreur lors du chargement des entraînements",
                    style="color: #ef4444; margin-bottom: 1.5rem;")
            )

    # ========== NEW QUESTIONNAIRES - DAILY & WEEKLY ==========

    # DAILY QUESTIONNAIRE: Activity Selector
    selected_daily_activity = reactive.Value(None)

    @output
    @render.ui
    def daily_activity_selector():
        """Activity selector for daily post-workout questionnaire - uses same list as Analyse de séance"""
        # Explicitly depend on authentication state to re-render on login
        _ = is_authenticated.get()
        athlete_id = user_athlete_id.get()
        role = user_role.get()

        # For coach, show message (coaches can't fill questionnaires)
        if role == "coach":
            return ui.div(
                ui.tags.p("Les questionnaires sont reserves aux athletes.",
                    style="color: #666; font-style: italic;")
            )

        if not athlete_id:
            return ui.div(
                ui.tags.p("Veuillez vous connecter pour voir vos entrainements.",
                    style="color: #666; font-style: italic;")
            )

        # Use the same activity list as "Analyse de séance" (act_label_to_id)
        labels_map = act_label_to_id.get()

        if not labels_map:
            return ui.div(
                ui.tags.p("Aucun entrainement dans la periode selectionnee. Ajustez les dates ci-dessus.",
                    style="color: #666; font-style: italic;"),
                style="padding: 1rem; background: #fff3cd; border-radius: 4px;"
            )

        # Get activity IDs that already have surveys filled
        filled_activity_ids = set()
        try:
            all_activity_ids = list(labels_map.values())
            if all_activity_ids:
                surveys_df = supa_select(
                    "daily_workout_surveys",
                    select="activity_id",
                    params={
                        "athlete_id": f"eq.{athlete_id}",
                        "activity_id": f"in.({','.join(str(aid) for aid in all_activity_ids)})"
                    },
                    limit=1000
                )
                if not surveys_df.empty:
                    filled_activity_ids = set(surveys_df["activity_id"].astype(str).tolist())
        except Exception as e:
            print(f"Warning: Could not check filled surveys: {e}")

        # Build choices excluding already filled activities
        choices = {
            activity_id: label
            for label, activity_id in labels_map.items()
            if str(activity_id) not in filled_activity_ids
        }

        if not choices:
            return ui.div(
                ui.tags.p("Tous les questionnaires de la periode ont ete remplis!",
                    style="color: #16a34a; font-style: italic;"),
                style="padding: 1rem; background: #f0fdf4; border-radius: 4px; border: 1px solid #16a34a;"
            )

        return ui.input_select(
            "daily_selected_activity",
            "Choisir l'entrainement:",
            choices=choices,
            width="100%"
        )

    # DAILY QUESTIONNAIRE: Already Filled Check
    @output
    @render.ui
    def daily_already_filled_notice():
        """Check if daily survey already filled for selected activity"""
        athlete_id = user_athlete_id.get()
        if not athlete_id:
            return ui.div()

        try:
            # Get selected activity, return empty if not available yet
            try:
                activity_id = input.daily_selected_activity()
            except:
                return ui.div()

            if not activity_id:
                return ui.div()

            # Store selected activity in reactive value
            selected_daily_activity.set(activity_id)

            # Check if survey exists for this activity
            params = {
                "athlete_id": f"eq.{athlete_id}",
                "activity_id": f"eq.{activity_id}"
            }

            df = supa_select(
                "daily_workout_surveys",
                select="id,submitted_at,rpe_cr10,atteinte_obj",
                params=params,
                limit=1
            )

            if not df.empty:
                # Survey already exists
                submitted_at = df.iloc[0]["submitted_at"]
                rpe = df.iloc[0]["rpe_cr10"]
                atteinte = df.iloc[0]["atteinte_obj"]

                return ui.div(
                    ui.tags.p(
                        ui.tags.strong("Questionnaire déjà rempli"),
                        style="color: #059669; font-size: 1.1rem; margin-bottom: 0.5rem;"
                    ),
                    ui.tags.p(
                        f"Soumis le: {submitted_at}",
                        style="color: #666; font-size: 0.9rem; margin-bottom: 0.25rem;"
                    ),
                    ui.tags.p(
                        f"RPE: {rpe}/10 | Atteinte objectifs: {atteinte}/10",
                        style="color: #666; font-size: 0.9rem;"
                    ),
                    ui.tags.p(
                        "Vous ne pouvez pas modifier ce questionnaire.",
                        style="color: #666; font-size: 0.9rem; font-style: italic; margin-top: 0.5rem;"
                    ),
                    style="padding: 1.25rem; background: #d1fae5; border: 2px solid #059669; border-radius: 8px; margin-top: 1rem;"
                )
            else:
                # No survey yet - show green light
                return ui.div(
                    ui.tags.p(
                        "Questionnaire non rempli - Vous pouvez le compléter ci-dessous",
                        style="color: #059669; font-weight: 600;"
                    ),
                    style="padding: 1rem; background: #ecfdf5; border-left: 4px solid #059669; border-radius: 4px; margin-top: 1rem;"
                )

        except Exception as e:
            print(f"Error checking daily survey status: {e}")
            traceback.print_exc()
            return ui.div()

    # WEEKLY QUESTIONNAIRE: Week Selector
    selected_weekly_date = reactive.Value(None)

    @output
    @render.ui
    def weekly_week_selector():
        """Date picker to select Monday of the week for weekly wellness questionnaire"""
        from datetime import date, timedelta

        # Get current date
        today = date.today()

        # Find the Monday of current week
        days_since_monday = today.weekday()  # Monday = 0, Sunday = 6
        current_monday = today - timedelta(days=days_since_monday)

        # Minimum date (data starts August 17, 2024)
        min_date = date(2024, 8, 17)
        # Find Monday of the week containing min_date
        days_to_monday = min_date.weekday()
        min_monday = min_date - timedelta(days=days_to_monday)

        # Generate list of weeks (Mondays) from current week back to first week with data
        weeks = []
        monday = current_monday
        while monday >= min_monday:
            weeks.append(monday)
            monday = monday - timedelta(weeks=1)

        # Build choices
        choices = {}
        for monday in weeks:
            # Format: "Semaine du 14 novembre 2025"
            mois_fr = ["janvier", "février", "mars", "avril", "mai", "juin",
                       "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
            label = f"Semaine du {monday.day} {mois_fr[monday.month - 1]} {monday.year}"
            choices[monday.isoformat()] = label

        return ui.input_select(
            "weekly_selected_week",
            "Choisir la semaine (lundi):",
            choices=choices,
            selected=current_monday.isoformat(),
            width="100%"
        )

    # WEEKLY QUESTIONNAIRE: Already Filled Check
    @output
    @render.ui
    def weekly_already_filled_notice():
        """Check if weekly survey already filled for selected week"""
        athlete_id = user_athlete_id.get()
        if not athlete_id:
            return ui.div()

        try:
            # Safely get selected week
            week_start = None
            try:
                week_start = input.weekly_selected_week()
            except:
                pass

            if not week_start:
                return ui.div()

            # Store selected week in reactive value
            selected_weekly_date.set(week_start)

            # Check if survey exists for this week
            params = {
                "athlete_id": f"eq.{athlete_id}",
                "week_start_date": f"eq.{week_start}"
            }

            df = supa_select(
                "weekly_wellness_surveys",
                select="id,submitted_at,fatigue,stress_global,humeur_globale",
                params=params,
                limit=1
            )

            if not df.empty:
                # Survey already exists
                submitted_at = df.iloc[0]["submitted_at"]
                fatigue = df.iloc[0].get("fatigue", "N/A")
                stress = df.iloc[0].get("stress_global", "N/A")
                humeur = df.iloc[0].get("humeur_globale", "N/A")

                return ui.div(
                    ui.tags.p(
                        ui.tags.strong("Questionnaire hebdomadaire déjà rempli"),
                        style="color: #059669; font-size: 1.1rem; margin-bottom: 0.5rem;"
                    ),
                    ui.tags.p(
                        f"Soumis le: {submitted_at}",
                        style="color: #666; font-size: 0.9rem; margin-bottom: 0.25rem;"
                    ),
                    ui.tags.p(
                        f"Fatigue: {fatigue}/10 | Stress: {stress}/10 | Humeur: {humeur}/10",
                        style="color: #666; font-size: 0.9rem;"
                    ),
                    ui.tags.p(
                        "Vous ne pouvez pas modifier ce questionnaire.",
                        style="color: #666; font-size: 0.9rem; font-style: italic; margin-top: 0.5rem;"
                    ),
                    style="padding: 1.25rem; background: #d1fae5; border: 2px solid #059669; border-radius: 8px; margin-top: 1rem;"
                )
            else:
                # No survey yet - show green light
                return ui.div(
                    ui.tags.p(
                        "Questionnaire non rempli - Vous pouvez le compléter ci-dessous",
                        style="color: #059669; font-weight: 600;"
                    ),
                    style="padding: 1rem; background: #ecfdf5; border-left: 4px solid #059669; border-radius: 4px; margin-top: 1rem;"
                )

        except Exception as e:
            print(f"Error checking weekly survey status: {e}")
            traceback.print_exc()
            return ui.div()

    # ========== DAILY SURVEY SUBMISSION ==========

    # Reactive value for daily survey save status
    daily_survey_save_status = reactive.Value(None)

    @reactive.Effect
    @reactive.event(input.submit_daily_survey)
    def handle_daily_survey_submit():
        """Handle daily workout survey submission to database"""
        try:
            athlete_id = user_athlete_id.get()
            if not athlete_id:
                daily_survey_save_status.set({"success": False, "message": "Athlete ID manquant"})
                return

            # Get selected activity
            activity_id = input.daily_selected_activity() if hasattr(input, 'daily_selected_activity') and input.daily_selected_activity() else None
            if not activity_id:
                daily_survey_save_status.set({"success": False, "message": "Veuillez sélectionner un entraînement"})
                return

            # Get activity date from activity_metadata
            activity_params = {"activity_id": f"eq.{activity_id}"}
            activity_df = supa_select("activity_metadata", select="date,duration_sec", params=activity_params, limit=1)

            if activity_df.empty:
                daily_survey_save_status.set({"success": False, "message": "Entraînement introuvable"})
                return

            date_seance = activity_df.iloc[0]["date"]
            duree_min = int(activity_df.iloc[0]["duration_sec"] / 60) if activity_df.iloc[0]["duration_sec"] else None

            # Collect form data
            douleur_oui = input.daily_douleur_oui() == "Oui"
            modifs_oui = input.daily_modifs_oui() == "Oui"

            # Parse pain selections from body picker (JSON string from JS)
            pain_selections = {}
            if douleur_oui:
                try:
                    pain_json = input.daily_pain_selections()
                    if pain_json and str(pain_json).strip():
                        pain_selections = json.loads(str(pain_json))
                except Exception:
                    pass

            # Parse capacite_execution
            capacite_val = None
            if douleur_oui:
                try:
                    cap_raw = input.daily_capacite_execution()
                    if cap_raw is not None and str(cap_raw).strip():
                        capacite_val = int(cap_raw)
                except Exception:
                    pass

            data = {
                "athlete_id": athlete_id,
                "activity_id": activity_id,
                "date_seance": date_seance,
                "duree_min": duree_min,

                # S2: RPE and goal achievement
                "rpe_cr10": int(input.daily_rpe_cr10()),
                "atteinte_obj": int(input.daily_atteinte_obj()),

                # S3: Pain/discomfort
                "douleur_oui": douleur_oui,
                "douleur_intensite": None,
                "douleur_type_zone": None,
                "douleur_impact": input.daily_douleur_impact() == "Oui" if douleur_oui else None,
                "capacite_execution": capacite_val,

                # S4: Context
                "en_groupe": input.daily_en_groupe() == "Oui",

                # S5: Details
                "allures": input.daily_allures() if input.daily_allures() else None,
                "commentaires": input.daily_commentaires() if input.daily_commentaires() else None,
                "modifs_oui": modifs_oui,
                "modifs_details": input.daily_modifs_details() if modifs_oui and input.daily_modifs_details() else None
            }

            # Insert into database - use return=representation to get back the UUID
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/daily_workout_surveys",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation"
                },
                json=data
            )

            if response.status_code in [200, 201]:
                # Insert pain entries into workout_pain_entries if any selected
                survey_id = None
                try:
                    resp_data = response.json()
                    if isinstance(resp_data, list) and len(resp_data) > 0:
                        survey_id = resp_data[0].get("id")
                except Exception:
                    pass

                if survey_id and pain_selections:
                    pain_entries = []
                    for composite_key, part_info in pain_selections.items():
                        # Keys are "view:partId" (e.g. "front:left_knee")
                        if ':' in composite_key:
                            _, body_part = composite_key.split(':', 1)
                        else:
                            body_part = composite_key
                        entry = {
                            "survey_id": survey_id,
                            "body_part": body_part,
                            "body_view": part_info.get("view", "front"),
                            "severity": int(part_info.get("severity", 1))
                        }
                        pain_entries.append(entry)

                    if pain_entries:
                        try:
                            pain_resp = requests.post(
                                f"{SUPABASE_URL}/rest/v1/workout_pain_entries",
                                headers={
                                    "apikey": SUPABASE_KEY,
                                    "Authorization": f"Bearer {SUPABASE_KEY}",
                                    "Content-Type": "application/json",
                                    "Prefer": "return=minimal"
                                },
                                json=pain_entries
                            )
                            if pain_resp.status_code not in [200, 201]:
                                print(f"Warning: Failed to insert pain entries: {pain_resp.text}")
                        except Exception as pe:
                            print(f"Warning: Error inserting pain entries: {pe}")

                pain_count = len(pain_selections)
                pain_msg = f" | {pain_count} zone(s) de douleur enregistrée(s)" if pain_count > 0 else ""
                daily_survey_save_status.set({
                    "success": True,
                    "message": f"Questionnaire enregistré avec succès!{pain_msg}",
                    "data": data
                })
            else:
                error_msg = response.text
                daily_survey_save_status.set({
                    "success": False,
                    "message": f"Erreur lors de l'enregistrement: {error_msg}"
                })

        except Exception as e:
            print(f"Error submitting daily survey: {e}")
            traceback.print_exc()
            daily_survey_save_status.set({
                "success": False,
                "message": f"Erreur: {str(e)}"
            })

    @output
    @render.ui
    def daily_survey_result():
        """Display daily survey save result"""
        status = daily_survey_save_status.get()

        if not status:
            return ui.div()

        if status["success"]:
            data = status.get("data", {})
            return ui.div(
                ui.tags.div(
                    ui.tags.h4("Questionnaire enregistré!", style="color: #16a34a; margin-bottom: 1rem;"),
                    ui.tags.p(
                        f"RPE: {data.get('rpe_cr10', 'N/A')}/10 | Objectifs: {data.get('atteinte_obj', 'N/A')}/10",
                        style="color: #666; font-size: 1rem; margin-bottom: 0.5rem;"
                    ),
                    ui.tags.p(
                        "Les données ont été enregistrées dans la base de données.",
                        style="color: #666; font-size: 0.9rem;"
                    ),
                    style="padding: 1.5rem; background: #f0fdf4; border: 2px solid #16a34a; border-radius: 8px; margin-top: 1rem;"
                )
            )
        else:
            return ui.div(
                ui.tags.div(
                    ui.tags.h4("Erreur", style="color: #dc2626; margin-bottom: 1rem;"),
                    ui.tags.p(status.get("message", "Une erreur est survenue"), style="color: #666;"),
                    style="padding: 1.5rem; background: #fee; border: 2px solid #dc2626; border-radius: 8px; margin-top: 1rem;"
                )
            )

    # ========== WEEKLY SURVEY SUBMISSION ==========

    # Reactive value for weekly survey save status
    weekly_survey_save_status = reactive.Value(None)

    def get_athlete_typical_weight(athlete_id: int) -> tuple:
        """Fetch athlete's typical weight from previous entries.

        Returns:
            tuple: (typical_weight, entry_count) where typical_weight is the median of previous entries
        """
        try:
            # Query previous weight entries for this athlete
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/weekly_wellness_surveys",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json"
                },
                params={
                    "athlete_id": f"eq.{athlete_id}",
                    "poids": "not.is.null",
                    "select": "poids",
                    "order": "week_start_date.desc",
                    "limit": 20  # Use last 20 entries to calculate typical weight
                }
            )

            if response.status_code == 200:
                entries = response.json()
                if entries and len(entries) > 0:
                    weights = [e["poids"] for e in entries if e.get("poids")]
                    if weights:
                        # Use median for robustness against outliers
                        import statistics
                        return (statistics.median(weights), len(weights))
            return (None, 0)
        except Exception as e:
            print(f"Error fetching typical weight: {e}")
            return (None, 0)

    @reactive.Effect
    @reactive.event(input.submit_weekly_survey)
    def handle_weekly_survey_submit():
        """Handle weekly wellness survey submission to database"""
        try:
            athlete_id = user_athlete_id.get()
            if not athlete_id:
                weekly_survey_save_status.set({"success": False, "message": "Athlete ID manquant"})
                return

            # Get selected week
            week_start = input.weekly_selected_week() if hasattr(input, 'weekly_selected_week') and input.weekly_selected_week() else None
            if not week_start:
                weekly_survey_save_status.set({"success": False, "message": "Veuillez sélectionner une semaine"})
                return

            # ===== WEIGHT VALIDATION (30% threshold) =====
            new_weight = float(input.weekly_poids()) if input.weekly_poids() else None
            if new_weight is not None:
                typical_weight, entry_count = get_athlete_typical_weight(athlete_id)

                if typical_weight is not None and entry_count >= 1:
                    # Calculate 30% threshold
                    lower_bound = typical_weight * 0.70  # 30% lower
                    upper_bound = typical_weight * 1.30  # 30% higher

                    if new_weight < lower_bound or new_weight > upper_bound:
                        # Weight is outside acceptable range - likely lbs/kg confusion
                        if new_weight < lower_bound:
                            error_msg = (
                                f"Poids invalide: {new_weight:.1f} kg est trop bas. "
                                f"Votre poids habituel est ~{typical_weight:.1f} kg. "
                                f"Avez-vous entré le poids en livres (lbs) par erreur?"
                            )
                        else:
                            error_msg = (
                                f"Poids invalide: {new_weight:.1f} kg est trop élevé. "
                                f"Votre poids habituel est ~{typical_weight:.1f} kg. "
                                f"Avez-vous entré le poids en livres (lbs) par erreur?"
                            )
                        weekly_survey_save_status.set({"success": False, "message": error_msg})
                        return

            # Collect form data
            oslo_symptomes = input.weekly_oslo_symptomes() == "Oui"

            data = {
                "athlete_id": athlete_id,
                "week_start_date": week_start,

                # S1: General well-being (0-10 sliders)
                "fatigue": int(input.weekly_fatigue()),
                "doms": int(input.weekly_doms()),
                "stress_global": int(input.weekly_stress_global()),
                "humeur_globale": int(input.weekly_humeur_globale()),
                "readiness": int(input.weekly_readiness()),

                # S2: BRUMS (0-4 Likert)
                "brums_tension": int(input.weekly_brums_tension()),
                "brums_depression": int(input.weekly_brums_depression()),
                "brums_colere": int(input.weekly_brums_colere()),
                "brums_vigueur": int(input.weekly_brums_vigueur()),
                "brums_fatigue": int(input.weekly_brums_fatigue()),
                "brums_confusion": int(input.weekly_brums_confusion()),

                # S3: REST-Q (0-4 Likert)
                "restq_emotion": int(input.weekly_restq_emotion()),
                "restq_physique": int(input.weekly_restq_physique()),
                "restq_sommeil": int(input.weekly_restq_sommeil()),
                "restq_recup_phys": int(input.weekly_restq_recup_phys()),
                "restq_social": int(input.weekly_restq_social()),
                "restq_relax": int(input.weekly_restq_relax()),

                # S4: OSLO
                "oslo_participation": input.weekly_oslo_participation() == "Oui",
                "oslo_volume": input.weekly_oslo_volume() == "Oui",
                "oslo_performance": input.weekly_oslo_performance() == "Oui",
                "oslo_symptomes": oslo_symptomes,
                "douleur_intensite": int(input.weekly_douleur_intensite()) if oslo_symptomes else None,
                "douleur_description": input.weekly_douleur_description() if oslo_symptomes and input.weekly_douleur_description() else None,
                "douleur_modif": input.weekly_douleur_modif() == "Oui" if oslo_symptomes else None,

                # S5: Sleep, nutrition, load, weight
                "sommeil_qualite": int(input.weekly_sommeil_qualite()),
                "alimentation_qualite": int(input.weekly_alimentation_qualite()),
                "charge_acad_pro": int(input.weekly_charge_acad_pro()),
                "poids": float(input.weekly_poids()) if input.weekly_poids() else None
            }

            # Insert into database
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/weekly_wellness_surveys",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal"
                },
                json=data
            )

            if response.status_code in [200, 201]:
                weekly_survey_save_status.set({
                    "success": True,
                    "message": "Questionnaire enregistré avec succès!",
                    "data": data
                })
            else:
                error_msg = response.text
                weekly_survey_save_status.set({
                    "success": False,
                    "message": f"Erreur lors de l'enregistrement: {error_msg}"
                })

        except Exception as e:
            print(f"Error submitting weekly survey: {e}")
            traceback.print_exc()
            weekly_survey_save_status.set({
                "success": False,
                "message": f"Erreur: {str(e)}"
            })

    @output
    @render.ui
    def weekly_survey_result():
        """Display weekly survey save result"""
        status = weekly_survey_save_status.get()

        if not status:
            return ui.div()

        if status["success"]:
            data = status.get("data", {})
            return ui.div(
                ui.tags.div(
                    ui.tags.h4("Questionnaire hebdomadaire enregistré!", style="color: #16a34a; margin-bottom: 1rem;"),
                    ui.tags.p(
                        f"Fatigue: {data.get('fatigue', 'N/A')}/10 | Stress: {data.get('stress_global', 'N/A')}/10 | Humeur: {data.get('humeur_globale', 'N/A')}/10",
                        style="color: #666; font-size: 1rem; margin-bottom: 0.5rem;"
                    ),
                    ui.tags.p(
                        "Les données ont été enregistrées dans la base de données.",
                        style="color: #666; font-size: 0.9rem;"
                    ),
                    style="padding: 1.5rem; background: #f0fdf4; border: 2px solid #16a34a; border-radius: 8px; margin-top: 1rem;"
                )
            )
        else:
            return ui.div(
                ui.tags.div(
                    ui.tags.h4("Erreur", style="color: #dc2626; margin-bottom: 1rem;"),
                    ui.tags.p(status.get("message", "Une erreur est survenue"), style="color: #666;"),
                    style="padding: 1.5rem; background: #fee; border: 2px solid #dc2626; border-radius: 8px; margin-top: 1rem;"
                )
            )

    # Handle survey submission (OLD - will be replaced)
    @reactive.Effect
    @reactive.event(input.submit_survey)
    def handle_survey_submit():
        try:
            # Collect all form data
            # Get selected activity (if any)
            activity_id = None
            try:
                if hasattr(input, 'survey_activity_id') and input.survey_activity_id():
                    selected = input.survey_activity_id()
                    activity_id = selected if selected != "none" else None
            except:
                pass
            
            data = {
                "date": str(input.survey_date()) if input.survey_date() else None,
                "activity_id": activity_id,
                "athlete_id": user_athlete_id.get(),
                "athlete_name": user_name.get(),
                "physical_condition": {
                    "sleep_quality": input.sleep_quality(),
                    "fatigue_level": input.fatigue_level(),
                    "muscle_soreness": input.muscle_soreness() == "yes",
                    "soreness_severity": input.soreness_severity() if input.muscle_soreness() == "yes" else None,
                    "injury_notes": input.injury_notes() if input.injury_notes() else None
                },
                "training_perception": {
                    "workout_difficulty": input.workout_difficulty(),
                    "motivation_level": input.motivation_level(),
                    "satisfaction_rating": input.satisfaction_rating()
                },
                "additional_notes": {
                    "mood": input.mood(),
                    "comments": input.comments() if input.comments() else None
                },
                "submitted_at": datetime.now().isoformat()
            }
            
            # Store in reactive value for display
            survey_data.set(data)
            
        except Exception as e:
            print(f"Error collecting survey data: {e}")
            survey_data.set({"error": str(e)})
    
    # Display survey results
    @output
    @render.ui
    def survey_result():
        data = survey_data.get()
        
        if not data:
            return ui.div()
        
        if "error" in data:
            return ui.div(
                ui.tags.div(
                    ui.tags.h4("Erreur", style="color: #dc2626; margin-bottom: 1rem;"),
                    ui.tags.p(f"Une erreur est survenue: {data['error']}", style="color: #666;"),
                    style="padding: 1.5rem; background: #fee; border: 2px solid #dc2626; border-radius: 8px;"
                )
            )
        
        # Format data for display
        import json
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        
        return ui.div(
            ui.tags.div(
                ui.tags.h4("Questionnaire reçu (Mode test)", style="color: #16a34a; margin-bottom: 1rem;"),
                ui.tags.p("Les données suivantes ont été collectées (elles ne sont pas encore enregistrées dans Supabase):", 
                    style="color: #666; margin-bottom: 1rem;"),
                
                # Display formatted data
                ui.tags.div(
                    ui.tags.h5("Données collectées:", style="margin-bottom: 0.5rem; color: #D92323;"),
                    ui.tags.div(
                        ui.tags.p(f"Date: {data.get('date', 'Non spécifiée')}", style="margin: 0.5rem 0;"),
                        ui.tags.p(f"Athlète: {data.get('athlete_name', 'Inconnu')}", style="margin: 0.5rem 0;"),
                        ui.tags.p(f"Entraînement: {data.get('activity_id', 'Aucun')}", style="margin: 0.5rem 0;"),
                        ui.tags.hr(style="margin: 1rem 0;"),
                        ui.tags.p(f"Sommeil: {data['physical_condition']['sleep_quality']}/5", style="margin: 0.5rem 0;"),
                        ui.tags.p(f"Fatigue: {data['physical_condition']['fatigue_level']}/10", style="margin: 0.5rem 0;"),
                        ui.tags.p(f"Douleurs: {'Oui' if data['physical_condition']['muscle_soreness'] else 'Non'}", style="margin: 0.5rem 0;"),
                        ui.tags.p(f"Difficulté: {data['training_perception']['workout_difficulty']}/10", style="margin: 0.5rem 0;"),
                        ui.tags.p(f"Motivation: {data['training_perception']['motivation_level']}/10", style="margin: 0.5rem 0;"),
                        ui.tags.p(f"Satisfaction: {data['training_perception']['satisfaction_rating']}/5", style="margin: 0.5rem 0;"),
                        ui.tags.p(f"Humeur: {data['additional_notes']['mood']}", style="margin: 0.5rem 0;"),
                        style="padding: 1rem; background: #f9f9f9; border-radius: 6px; margin-bottom: 1rem;"
                    ),
                    
                    # JSON preview for database structure
                    ui.tags.details(
                        ui.tags.summary("Voir la structure JSON (pour Supabase)", style="cursor: pointer; font-weight: 600; margin-bottom: 0.5rem;"),
                        ui.tags.pre(
                            json_str,
                            style="background: #1e1e1e; color: #d4d4d4; padding: 1rem; border-radius: 6px; overflow-x: auto; font-size: 0.85rem; margin-top: 0.5rem;"
                        ),
                        style="margin-top: 1rem;"
                    )
                ),
                
                style="padding: 1.5rem; background: #f0fdf4; border: 2px solid #16a34a; border-radius: 8px;"
            )
        )

    # ========== MANUAL DATA ENTRY - PERSONAL RECORDS ==========

    # Reactive values for manual entry
    pr_data = reactive.Value({})  # Current PRs from database
    pr_save_status = reactive.Value(None)  # Save status message

    # Training zones reactive values
    zones_data = reactive.Value([])  # Current zones from database
    zones_save_status = reactive.Value(None)  # Save status message for zones
    zones_selected_athlete = reactive.Value(None)  # Selected athlete for zone configuration (coach only)

    # Lactate tests reactive values
    lactate_tests_data = reactive.Value([])  # Current lactate tests from database
    lactate_tests_save_status = reactive.Value(None)  # Save status message for lactate tests

    # Distance definitions
    DISTANCES = [
        {"key": "400m", "label": "400 mètres", "format": "short"},
        {"key": "800m", "label": "800 mètres", "format": "short"},
        {"key": "1000m", "label": "1000 mètres", "format": "short"},
        {"key": "1500m", "label": "1500 mètres", "format": "short"},
        {"key": "1mile", "label": "1 Mile / 1609m", "format": "short"},
        {"key": "2000m", "label": "2000 mètres", "format": "short"},
        {"key": "3000m", "label": "3000 mètres", "format": "short"},
        {"key": "2000m_steeple", "label": "2000m steeple", "format": "short"},
        {"key": "3000m_steeple", "label": "3000m steeple", "format": "short"},
        {"key": "5000m", "label": "5000 mètres", "format": "long"},
        {"key": "10000m", "label": "10 000 mètres", "format": "long"},
        {"key": "5km", "label": "5 km (route)", "format": "long"},
        {"key": "10km", "label": "10 km (route)", "format": "long"},
        {"key": "half_marathon", "label": "Semi-marathon 21.1km", "format": "long"},
        {"key": "marathon", "label": "Marathon 42.2km", "format": "long"}
    ]
    
    def format_time_from_seconds(seconds, format_type="short"):
        """Convert seconds to MM:SS, HH:MM:SS, or with milliseconds if present"""
        if not seconds or seconds <= 0:
            return ""

        # Check if there are milliseconds
        has_ms = (seconds % 1) > 0.0001  # Small tolerance for float precision
        total_sec = int(seconds)
        ms = int(round((seconds - total_sec) * 1000)) if has_ms else 0

        hours = total_sec // 3600
        minutes = (total_sec % 3600) // 60
        secs = total_sec % 60

        if format_type == "long" or hours > 0:
            base = f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            base = f"{minutes}:{secs:02d}"

        if has_ms and ms > 0:
            return f"{base}:{ms:02d}"  # Display 2 digits for centiseconds
        else:
            return base
    
    def parse_time_to_seconds(time_str):
        """Parse MM:SS, HH:MM:SS, MM:SS:ms, or HH:MM:SS:ms to total seconds (with decimals)"""
        if not time_str or time_str.strip() == "":
            return None

        try:
            parts = time_str.strip().split(':')
            if len(parts) == 2:  # MM:SS
                minutes, seconds = int(parts[0]), int(parts[1])
                if seconds >= 60:
                    return None  # Invalid
                return float(minutes * 60 + seconds)
            elif len(parts) == 3:
                # Could be HH:MM:SS or MM:SS:ms
                first, second, third = parts[0], parts[1], parts[2]
                # If third part is > 59 or has leading zeros with length < 2, treat as milliseconds
                if len(third) <= 2 and int(third) <= 59:
                    # HH:MM:SS format
                    hours, minutes, seconds = int(first), int(second), int(third)
                    if minutes >= 60 or seconds >= 60:
                        return None  # Invalid
                    return float(hours * 3600 + minutes * 60 + seconds)
                else:
                    # MM:SS:ms format (milliseconds can be 1-3 digits)
                    minutes, seconds = int(first), int(second)
                    ms = int(third)
                    # Normalize milliseconds to 3 digits
                    if len(third) == 1:
                        ms = ms * 100  # 1 -> 100ms
                    elif len(third) == 2:
                        ms = ms * 10   # 12 -> 120ms
                    # else 3 digits, use as-is
                    if seconds >= 60:
                        return None  # Invalid
                    return float(minutes * 60 + seconds) + (ms / 1000.0)
            elif len(parts) == 4:  # HH:MM:SS:ms
                hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
                ms = int(parts[3])
                # Normalize milliseconds
                if len(parts[3]) == 1:
                    ms = ms * 100
                elif len(parts[3]) == 2:
                    ms = ms * 10
                if minutes >= 60 or seconds >= 60:
                    return None  # Invalid
                return float(hours * 3600 + minutes * 60 + seconds) + (ms / 1000.0)
            else:
                return None
        except:
            return None
    
    def calculate_pace(distance_key, time_seconds):
        """Calculate pace in min/km"""
        distance_map = {
            "400m": 0.4,
            "800m": 0.8,
            "1000m": 1.0,
            "1500m": 1.5,
            "1mile": 1.609,
            "2000m": 2.0,
            "3000m": 3.0,
            "2000m_steeple": 2.0,
            "3000m_steeple": 3.0,
            "5000m": 5.0,
            "10000m": 10.0,
            "5km": 5.0,
            "10km": 10.0,
            "half_marathon": 21.1,
            "marathon": 42.195
        }

        distance_km = distance_map.get(distance_key)
        if not distance_km or not time_seconds:
            return None

        pace_seconds_per_km = time_seconds / distance_km
        pace_minutes = int(pace_seconds_per_km // 60)
        pace_seconds = int(pace_seconds_per_km % 60)
        return f"{pace_minutes}:{pace_seconds:02d}"

    # Helper functions for training zones pace conversion
    def pace_seconds_to_mmss(seconds_per_km):
        """Convert pace from seconds per km to MM:SS format for display"""
        if seconds_per_km is None or seconds_per_km <= 0:
            return ""

        total_sec = int(seconds_per_km)
        minutes = total_sec // 60
        secs = total_sec % 60
        return f"{minutes}:{secs:02d}"

    def pace_mmss_to_seconds(pace_str):
        """Convert pace from MM:SS format to seconds per km for storage"""
        if not pace_str or pace_str.strip() == "":
            return None

        try:
            parts = pace_str.strip().split(':')
            if len(parts) != 2:
                return None

            minutes, seconds = int(parts[0]), int(parts[1])
            if seconds >= 60:
                return None  # Invalid

            return float(minutes * 60 + seconds)
        except:
            return None

    @output
    @render.ui
    def manual_entry_content():
        """Render manual data entry form - Events, Training Zones, and Personal Records"""
        # Check authentication
        if not is_authenticated.get():
            return ui.div()

        # Build content - all cards available to all users
        cards = []

        # 1. Events Card (TOP) - lactate tests, races, and injuries
        cards.append(lactate_tests_card())

        # 2. Training Zones Card (MIDDLE)
        cards.append(training_zones_card())

        # 3. Personal Records Card (BOTTOM) - now available to all users
        cards.append(personal_records_card())

        return ui.div(*cards)

    def personal_records_card():
        """Build Personal Records card for athletes"""
        # Load current PRs
        athlete_id = user_athlete_id.get()
        current_prs = pr_data.get()

        # Build table rows
        table_rows = []
        for dist in DISTANCES:
            key = dist["key"]
            label = dist["label"]
            format_type = dist["format"]

            # Current PR
            current_pr = current_prs.get(key, {})
            current_time_sec = current_pr.get("time_seconds")
            current_time_str = format_time_from_seconds(current_time_sec, format_type) if current_time_sec else "Aucun"
            current_pace = calculate_pace(key, current_time_sec) if current_time_sec else "—"
            current_date = current_pr.get("record_date", "")
            current_priority = current_pr.get("race_priority", "")

            # Input IDs
            time_id = f"pr_time_{key}"
            date_id = f"pr_date_{key}"
            priority_id = f"pr_priority_{key}"
            notes_id = f"pr_notes_{key}"

            # Placeholder - supports HH:MM:SS or HH:MM:SS:ms
            time_placeholder = "HH:MM:SS:ms"

            table_rows.append(
                ui.tags.tr(
                    ui.tags.td(
                        ui.tags.strong(label),
                        style="padding: 1rem; vertical-align: middle;"
                    ),
                    ui.tags.td(
                        ui.div(
                            ui.tags.div(current_time_str, style="font-size: 1.2rem; font-weight: 600; color: #D92323;"),
                            ui.tags.div(f"Allure: {current_pace}/km", style="font-size: 0.85rem; color: #666; margin-top: 0.25rem;") if current_time_sec else ui.div(),
                            style="text-align: center;"
                        ),
                        style="padding: 1rem; background: #fef2f2; vertical-align: middle;"
                    ),
                    ui.tags.td(
                        ui.input_text(time_id, "", placeholder=time_placeholder, width="140px"),
                        style="padding: 1rem; vertical-align: middle;"
                    ),
                    ui.tags.td(
                        ui.input_date(date_id, "", value=current_date if current_date else None, width="150px"),
                        style="padding: 1rem; vertical-align: middle;"
                    ),
                    ui.tags.td(
                        ui.input_select(
                            priority_id,
                            "",
                            choices={"": "—", "A": "A", "B": "B", "C": "C"},
                            selected=current_priority if current_priority else "",
                            width="80px"
                        ),
                        style="padding: 1rem; vertical-align: middle;"
                    ),
                    ui.tags.td(
                        ui.input_text(notes_id, "", placeholder="Course, conditions...", width="200px"),
                        style="padding: 1rem; vertical-align: middle;"
                    )
                )
            )

        return ui.card(
            ui.card_header(
                ui.div(
                    ui.tags.h3("Records personnels", style="margin: 0; color: #D92323;"),
                    ui.tags.p("Entrez vos meilleurs temps pour chaque distance",
                             style="margin: 0.5rem 0 0 0; color: white; font-size: 1rem;"),
                    style="padding: 0.5rem 0;"
                )
            ),
            ui.div(
                # Status message
                ui.div(
                    ui.output_ui("pr_status_message"),
                    style="margin-bottom: 1rem;"
                ),

                # Table
                ui.tags.table(
                    ui.tags.thead(
                        ui.tags.tr(
                            ui.tags.th("Distance", style="padding: 0.75rem; background: #f3f4f6; font-weight: 700; border-bottom: 2px solid #D92323;"),
                            ui.tags.th("Temps actuel", style="padding: 0.75rem; background: #f3f4f6; font-weight: 700; text-align: center; border-bottom: 2px solid #D92323;"),
                            ui.tags.th("Nouveau temps", style="padding: 0.75rem; background: #f3f4f6; font-weight: 700; border-bottom: 2px solid #D92323;"),
                            ui.tags.th("Date", style="padding: 0.75rem; background: #f3f4f6; font-weight: 700; border-bottom: 2px solid #D92323;"),
                            ui.tags.th("Priorité", style="padding: 0.75rem; background: #f3f4f6; font-weight: 700; border-bottom: 2px solid #D92323;"),
                            ui.tags.th("Notes", style="padding: 0.75rem; background: #f3f4f6; font-weight: 700; border-bottom: 2px solid #D92323;")
                        )
                    ),
                    ui.tags.tbody(*table_rows),
                    style="width: 100%; border-collapse: collapse; border: 1px solid #e5e7eb;"
                ),

                # Submit button
                ui.div(
                    ui.input_action_button(
                        "save_personal_records",
                        "Enregistrer les records",
                        class_="btn btn-primary",
                        style="background: #D92323; border: none; padding: 0.75rem 2rem; font-weight: 600; font-size: 1.15rem; width: 100%;"
                    ),
                    style="margin-top: 2rem;"
                ),

                style="padding: 1.5rem;"
            ),
            style="margin-bottom: 2rem;"
        )

    def lactate_tests_card():
        """Build Lactate Tests data entry card for athletes and coaches"""
        role = user_role.get()

        # Determine target athlete (same logic as training zones)
        if role == "coach":
            target_athlete_id = zones_selected_athlete.get()
        else:
            target_athlete_id = user_athlete_id.get()

        current_tests = lactate_tests_data.get()

        # Athlete selector (coach only) - reuse zones_selected_athlete
        athlete_selector = ui.div()
        if role == "coach":
            athlete_choices = {row["athlete_id"]: row["name"] for _, row in athletes_df.iterrows()}
            athlete_selector = ui.div(
                ui.input_select(
                    "lactate_athlete_select",
                    "Selectionner un athlete:",
                    choices={"": "-- Choisir un athlete --", **athlete_choices},
                    selected=target_athlete_id if target_athlete_id else "",
                    width="100%"
                ),
                style="margin-bottom: 1.5rem; padding: 1rem; background: #f9fafb; border-radius: 8px;"
            )

        # Body part labels for injury display
        body_part_labels = {
            "head": "Tête", "neck": "Cou",
            "left_shoulder": "Épaule gauche", "right_shoulder": "Épaule droite",
            "left_arm": "Bras gauche", "right_arm": "Bras droit",
            "chest": "Poitrine", "upper_back": "Dos haut", "lower_back": "Dos bas",
            "left_hip": "Hanche gauche", "right_hip": "Hanche droite",
            "left_thigh": "Cuisse gauche", "right_thigh": "Cuisse droite",
            "left_knee": "Genou gauche", "right_knee": "Genou droit",
            "left_calf": "Mollet gauche", "right_calf": "Mollet droit",
            "left_shin": "Tibia gauche", "right_shin": "Tibia droit",
            "left_ankle": "Cheville gauche", "right_ankle": "Cheville droite",
            "left_foot": "Pied gauche", "right_foot": "Pied droit",
            "other": "Autre"
        }

        # Build table rows for existing tests/events
        table_rows = []
        for test in current_tests:
            test_date = test.get("test_date", "")
            distance_m = test.get("distance_m", "")
            lactate = test.get("lactate_mmol", "")
            test_type = test.get("test_type", "lactate")
            race_time = test.get("race_time_seconds", None)
            test_id = test.get("id", "")
            injury_location = test.get("injury_location", "")
            injury_severity = test.get("injury_severity", 1)
            injury_status = test.get("injury_status", "")

            # Format type display and color based on type
            if test_type == "race":
                type_display = "Course"
                type_color = "#F59E0B"  # Gold/Orange
            elif test_type == "injury":
                # Color based on severity for injuries
                severity_colors = {"1": "#22c55e", "2": "#eab308", "3": "#ef4444"}  # Green, Yellow, Red
                type_color = severity_colors.get(str(injury_severity), "#ef4444")
                severity_labels = {"1": "Légère", "2": "Modérée", "3": "Sévère"}
                type_display = severity_labels.get(str(injury_severity), "Douleur")
            elif test_type == "speed_test":
                type_display = "Vitesse"
                type_color = "#10b981"  # Green
            else:
                type_display = "Lactate"
                type_color = "#3B82F6"  # Blue

            # Format value/info column based on type
            if test_type == "speed_test":
                speed_val = test.get("speed_ms")
                if speed_val:
                    value_display = f"{float(speed_val):.2f} m/s"
                elif race_time and distance_m:
                    value_display = f"{distance_m / race_time:.2f} m/s"
                else:
                    value_display = "-"
                distance_display = f"{distance_m} m" if distance_m else "-"
            elif test_type == "race" and race_time:
                value_display = format_time_from_seconds(race_time)
                distance_display = f"{distance_m} m" if distance_m else "-"
            elif test_type == "injury":
                location_label = body_part_labels.get(injury_location, injury_location)
                status_labels = {"active": "Active", "recovering": "Récup.", "resolved": "Résolue"}
                status_label = status_labels.get(injury_status, "")
                value_display = f"{location_label}"
                if status_label:
                    value_display += f" ({status_label})"
                distance_display = "-"
            elif lactate:
                value_display = f"{lactate} mmol/L"
                distance_display = f"{distance_m} m" if distance_m else "-"
            else:
                value_display = "-"
                distance_display = f"{distance_m} m" if distance_m else "-"

            table_rows.append(
                ui.tags.tr(
                    ui.tags.td(
                        ui.tags.span(type_display, style=f"background: {type_color}; color: white; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.8rem;"),
                        style="padding: 0.75rem; border-bottom: 1px solid #e5e7eb;"
                    ),
                    ui.tags.td(str(test_date), style="padding: 0.75rem; border-bottom: 1px solid #e5e7eb;"),
                    ui.tags.td(distance_display, style="padding: 0.75rem; border-bottom: 1px solid #e5e7eb; text-align: center;"),
                    ui.tags.td(value_display, style="padding: 0.75rem; border-bottom: 1px solid #e5e7eb; text-align: center;"),
                    ui.tags.td(
                        ui.input_action_button(
                            f"delete_lactate_{test_id}",
                            "Supprimer",
                            class_="btn btn-sm btn-outline-danger",
                            style="padding: 0.25rem 0.5rem; font-size: 0.8rem;"
                        ),
                        style="padding: 0.75rem; border-bottom: 1px solid #e5e7eb; text-align: center;"
                    )
                )
            )

        # Empty state if no events
        if not table_rows:
            table_rows.append(
                ui.tags.tr(
                    ui.tags.td(
                        "Aucun événement enregistré",
                        colspan=5,
                        style="padding: 2rem; text-align: center; color: #666; font-style: italic;"
                    )
                )
            )

        return ui.card(
            ui.card_header(
                ui.div(
                    ui.tags.h3("Événements", style="margin: 0; color: #D92323;"),
                    ui.tags.p("Enregistrez vos tests de lactate, courses ou douleurs/blessures",
                             style="margin: 0.5rem 0 0 0; color: white; font-size: 1rem;"),
                    style="padding: 0.5rem 0;"
                )
            ),
            ui.div(
                # Athlete selector (coach only)
                athlete_selector,

                # Status message
                ui.div(
                    ui.output_ui("lactate_status_message"),
                    style="margin-bottom: 1rem;"
                ),

                # New test entry form
                ui.div(
                    ui.tags.h4("Nouvelle entrée", style="margin-bottom: 1rem; color: #333;"),

                    # Type selector (radio buttons) - now includes injury
                    ui.div(
                        ui.tags.label("Type", style="font-weight: 600; display: block; margin-bottom: 0.5rem;"),
                        ui.input_radio_buttons(
                            "lactate_test_type",
                            "",
                            choices={"lactate": "Test de lactate", "race": "Course", "speed_test": "Test de vitesse max"},
                            selected="lactate",
                            inline=True
                        ),
                        style="margin-bottom: 1rem;"
                    ),

                    # Date (always shown)
                    ui.div(
                        ui.tags.label("Date", style="font-weight: 600; display: block; margin-bottom: 0.5rem;"),
                        ui.input_date("lactate_test_date", "", value=str(datetime.now().date()), width="100%"),
                        style="margin-bottom: 1rem;"
                    ),

                    # Conditional fields (rendered dynamically based on type)
                    ui.output_ui("lactate_conditional_fields"),

                    # Notes field (always shown)
                    ui.div(
                        ui.tags.label("Notes (optionnel)", style="font-weight: 600; display: block; margin-bottom: 0.5rem;"),
                        ui.input_text_area("lactate_notes", "", placeholder="Conditions, sensations, équipement...", width="100%", rows=2),
                        style="margin-top: 1rem;"
                    ),

                    ui.div(
                        ui.input_action_button(
                            "save_lactate_test",
                            "Enregistrer",
                            class_="btn btn-primary",
                            style="background: #D92323; border: none; padding: 0.75rem 2rem; font-weight: 600; margin-top: 1rem;"
                        ),
                        style="text-align: right;"
                    ),
                    style="background: #f9fafb; padding: 1.5rem; border-radius: 8px; margin-bottom: 2rem;"
                ),

                # Existing tests table
                ui.tags.h4("Historique", style="margin-bottom: 1rem; color: #333;"),
                ui.tags.table(
                    ui.tags.thead(
                        ui.tags.tr(
                            ui.tags.th("Type", style="padding: 0.75rem; background: #f3f4f6; font-weight: 700; border-bottom: 2px solid #D92323;"),
                            ui.tags.th("Date", style="padding: 0.75rem; background: #f3f4f6; font-weight: 700; border-bottom: 2px solid #D92323;"),
                            ui.tags.th("Distance", style="padding: 0.75rem; background: #f3f4f6; font-weight: 700; text-align: center; border-bottom: 2px solid #D92323;"),
                            ui.tags.th("Info", style="padding: 0.75rem; background: #f3f4f6; font-weight: 700; text-align: center; border-bottom: 2px solid #D92323;"),
                            ui.tags.th("Actions", style="padding: 0.75rem; background: #f3f4f6; font-weight: 700; text-align: center; border-bottom: 2px solid #D92323;")
                        )
                    ),
                    ui.tags.tbody(*table_rows),
                    style="width: 100%; border-collapse: collapse; border: 1px solid #e5e7eb;"
                ),

                style="padding: 1.5rem;"
            ),
            style="margin-bottom: 2rem;"
        )

    def training_zones_card():
        """Build Training Zones configuration card"""
        role = user_role.get()

        # Determine target athlete
        if role == "coach":
            target_athlete_id = zones_selected_athlete.get()
        else:
            target_athlete_id = user_athlete_id.get()

        # Get current zones for initial num_zones value
        current_zones = zones_data.get()
        num_zones = len(current_zones) if current_zones else 5  # Default to 5 zones
        effective_date = current_zones[0].get("effective_from_date") if current_zones else None

        # Athlete selector (coach only)
        athlete_selector = ui.div()
        if role == "coach":
            # Get list of coached athletes from athletes_df (defined in server scope)
            athlete_choices = {row["athlete_id"]: row["name"] for _, row in athletes_df.iterrows()}

            athlete_selector = ui.div(
                ui.input_select(
                    "zones_athlete_select",
                    "Selectionner un athlete:",
                    choices={"": "-- Choisir un athlete --", **athlete_choices},
                    selected=target_athlete_id if target_athlete_id else "",
                    width="100%"
                ),
                style="margin-bottom: 1.5rem; padding: 1rem; background: #f9fafb; border-radius: 8px;"
            )

        return ui.card(
            ui.card_header(
                ui.div(
                    ui.tags.h3("Zones d'entrainement", style="margin: 0; color: #D92323;"),
                    ui.tags.p("Configuration des zones d'entrainement (FC, Allure, Lactate)",
                             style="margin: 0.5rem 0 0 0; color: white; font-size: 1rem;"),
                    style="padding: 0.5rem 0;"
                )
            ),
            ui.div(
                # Athlete selector (coach only)
                athlete_selector,

                # Status message
                ui.div(
                    ui.output_ui("zones_status_message"),
                    style="margin-bottom: 1rem;"
                ),

                # Configuration controls
                ui.div(
                    ui.row(
                        ui.column(
                            6,
                            ui.input_date(
                                "zones_effective_date",
                                "Date d'entree en vigueur:",
                                value=effective_date if effective_date else None,
                                width="100%"
                            )
                        ),
                        ui.column(
                            6,
                            ui.input_select(
                                "zones_num_zones",
                                "Nombre de zones:",
                                choices={str(i): str(i) for i in range(1, 11)},
                                selected=str(num_zones),
                                width="100%"
                            )
                        )
                    ),
                    style="margin-bottom: 1.5rem; padding: 1rem; background: #f9fafb; border-radius: 8px;"
                ),

                # Zones table - DYNAMIC via output_ui
                ui.tags.div(
                    ui.output_ui("zones_table_dynamic"),
                    style="overflow-x: auto;"
                ),

                # Submit button
                ui.div(
                    ui.input_action_button(
                        "save_training_zones",
                        "Enregistrer les zones",
                        class_="btn btn-primary",
                        style="background: #D92323; border: none; padding: 0.75rem 2rem; font-weight: 600; font-size: 1.15rem; width: 100%;"
                    ),
                    style="margin-top: 2rem;"
                ),

                style="padding: 1.5rem;"
            ),
            style="margin-bottom: 2rem;"
        )

    @output
    @render.ui
    def zones_table_dynamic():
        """Dynamically render zone table rows based on zones_num_zones selection"""
        # Get number of zones from input (reactive!)
        try:
            num_zones = int(input.zones_num_zones() or 5)
        except:
            num_zones = 5

        # Get current zones data
        current_zones = zones_data.get()

        # Build zone input rows (only show zones 1 to num_zones)
        zone_rows = []
        for zone_num in range(1, num_zones + 1):
            # Find current zone data
            zone_data = next((z for z in current_zones if z.get("zone_number") == zone_num), {}) if current_zones else {}

            # Get current values (handle NaN from database)
            def safe_numeric(val):
                """Convert database value to numeric, handling NaN"""
                if val is None or val == "":
                    return None
                try:
                    if pd.isna(val):
                        return None
                    return float(val)
                except (ValueError, TypeError):
                    return None

            hr_min = safe_numeric(zone_data.get("hr_min"))
            hr_max = safe_numeric(zone_data.get("hr_max"))
            pace_min_sec = safe_numeric(zone_data.get("pace_min_sec_per_km"))
            pace_max_sec = safe_numeric(zone_data.get("pace_max_sec_per_km"))
            pace_min = pace_seconds_to_mmss(pace_min_sec) if pace_min_sec else ""
            pace_max = pace_seconds_to_mmss(pace_max_sec) if pace_max_sec else ""
            lactate_min = safe_numeric(zone_data.get("lactate_min"))
            lactate_max = safe_numeric(zone_data.get("lactate_max"))

            # Input width - larger for visibility
            input_width = "100px"

            zone_rows.append(
                ui.tags.tr(
                    # Zone number
                    ui.tags.td(
                        ui.tags.strong(f"Zone {zone_num}"),
                        style="padding: 0.75rem; vertical-align: middle; font-weight: 600; text-align: center;"
                    ),
                    # HR Min (numeric only, integers)
                    ui.tags.td(
                        ui.input_numeric(f"zone_{zone_num}_hr_min", "", value=hr_min if hr_min else None, min=0, max=250, step=1, width=input_width),
                        style="padding: 0.5rem; vertical-align: middle;"
                    ),
                    # HR Max (numeric only, integers)
                    ui.tags.td(
                        ui.input_numeric(f"zone_{zone_num}_hr_max", "", value=hr_max if hr_max else None, min=0, max=250, step=1, width=input_width),
                        style="padding: 0.5rem; vertical-align: middle;"
                    ),
                    # Pace Min (MM:SS format)
                    ui.tags.td(
                        ui.input_text(f"zone_{zone_num}_pace_min", "", value=pace_min, placeholder="M:SS", width=input_width),
                        style="padding: 0.5rem; vertical-align: middle;"
                    ),
                    # Pace Max (MM:SS format)
                    ui.tags.td(
                        ui.input_text(f"zone_{zone_num}_pace_max", "", value=pace_max, placeholder="M:SS", width=input_width),
                        style="padding: 0.5rem; vertical-align: middle;"
                    ),
                    # Lactate Min (numeric with decimals)
                    ui.tags.td(
                        ui.input_numeric(f"zone_{zone_num}_lactate_min", "", value=lactate_min if lactate_min else None, min=0, max=30, step=0.1, width=input_width),
                        style="padding: 0.5rem; vertical-align: middle;"
                    ),
                    # Lactate Max (numeric with decimals)
                    ui.tags.td(
                        ui.input_numeric(f"zone_{zone_num}_lactate_max", "", value=lactate_max if lactate_max else None, min=0, max=30, step=0.1, width=input_width),
                        style="padding: 0.5rem; vertical-align: middle;"
                    )
                )
            )

        return ui.tags.table(
            ui.tags.thead(
                ui.tags.tr(
                    ui.tags.th("Zone", style="padding: 0.75rem; background: #f3f4f6; font-weight: 700; border-bottom: 2px solid #D92323; text-align: center;", rowspan="2"),
                    ui.tags.th("Frequence cardiaque (bpm)", style="padding: 0.75rem; background: #f3f4f6; font-weight: 700; text-align: center; border-bottom: 2px solid #D92323;", colspan="2"),
                    ui.tags.th("Allure (min/km)", style="padding: 0.75rem; background: #f3f4f6; font-weight: 700; text-align: center; border-bottom: 2px solid #D92323;", colspan="2"),
                    ui.tags.th("Lactate (mmol/L)", style="padding: 0.75rem; background: #f3f4f6; font-weight: 700; text-align: center; border-bottom: 2px solid #D92323;", colspan="2")
                ),
                ui.tags.tr(
                    ui.tags.th("Min", style="padding: 0.5rem; background: #f9fafb; font-weight: 600; font-size: 0.85rem; border-bottom: 1px solid #D92323; text-align: center;"),
                    ui.tags.th("Max", style="padding: 0.5rem; background: #f9fafb; font-weight: 600; font-size: 0.85rem; border-bottom: 1px solid #D92323; text-align: center;"),
                    ui.tags.th("Min", style="padding: 0.5rem; background: #f9fafb; font-weight: 600; font-size: 0.85rem; border-bottom: 1px solid #D92323; text-align: center;"),
                    ui.tags.th("Max", style="padding: 0.5rem; background: #f9fafb; font-weight: 600; font-size: 0.85rem; border-bottom: 1px solid #D92323; text-align: center;"),
                    ui.tags.th("Min", style="padding: 0.5rem; background: #f9fafb; font-weight: 600; font-size: 0.85rem; border-bottom: 1px solid #D92323; text-align: center;"),
                    ui.tags.th("Max", style="padding: 0.5rem; background: #f9fafb; font-weight: 600; font-size: 0.85rem; border-bottom: 1px solid #D92323; text-align: center;")
                )
            ),
            ui.tags.tbody(*zone_rows),
            style="width: 100%; border-collapse: collapse; border: 1px solid #e5e7eb;"
        )
    
    # Load PRs when tab is accessed
    @reactive.Effect
    @reactive.event(is_authenticated)
    def load_personal_records():
        """Load current personal records from database"""
        print("[DEBUG] load_personal_records called", flush=True)
        if not is_authenticated.get() or user_role.get() != "athlete":
            return
        
        athlete_id = user_athlete_id.get()
        if not athlete_id:
            return
        
        try:
            # Query personal records using supa_select
            params = {"athlete_id": f"eq.{athlete_id}"}
            df = supa_select("personal_records", select="*", params=params, limit=100)
            
            # Convert to dict keyed by distance_type
            prs = {}
            if not df.empty:
                for _, row in df.iterrows():
                    prs[row["distance_type"]] = row.to_dict()
            
            pr_data.set(prs)
        except Exception as e:
            print(f"Error loading personal records: {e}")
            pr_data.set({})
    
    # Status message display
    @output
    @render.ui
    def pr_status_message():
        """Display save status message"""
        status = pr_save_status.get()
        if not status:
            return ui.div()
        
        if status["type"] == "success":
            return ui.div(
                ui.tags.div(
                    ui.tags.h4("" + status["title"], style="color: #16a34a; margin-bottom: 0.5rem;"),
                    ui.tags.p(status["message"], style="color: #666; margin: 0;"),
                    style="padding: 1rem; background: #f0fdf4; border: 2px solid #16a34a; border-radius: 8px;"
                )
            )
        elif status["type"] == "error":
            return ui.div(
                ui.tags.div(
                    ui.tags.h4("" + status["title"], style="color: #dc2626; margin-bottom: 0.5rem;"),
                    ui.tags.p(status["message"], style="color: #666; margin: 0;"),
                    style="padding: 1rem; background: #fee; border: 2px solid #dc2626; border-radius: 8px;"
                )
            )
        elif status["type"] == "warning":
            return ui.div(
                ui.tags.div(
                    ui.tags.h4("Attention: " + status["title"], style="color: #f59e0b; margin-bottom: 0.5rem;"),
                    ui.tags.p(status["message"], style="color: #666; margin: 0;"),
                    style="padding: 1rem; background: #fffbeb; border: 2px solid #f59e0b; border-radius: 8px;"
                )
            )

        return ui.div()

    # Status message display for training zones
    @output
    @render.ui
    def zones_status_message():
        """Display zones save status message"""
        status = zones_save_status.get()
        if not status:
            return ui.div()

        if status["type"] == "success":
            return ui.div(
                ui.tags.div(
                    ui.tags.h4(status["title"], style="color: #16a34a; margin-bottom: 0.5rem;"),
                    ui.tags.p(status["message"], style="color: #666; margin: 0;"),
                    style="padding: 1rem; background: #f0fdf4; border: 2px solid #16a34a; border-radius: 8px;"
                )
            )
        elif status["type"] == "error":
            return ui.div(
                ui.tags.div(
                    ui.tags.h4(status["title"], style="color: #dc2626; margin-bottom: 0.5rem;"),
                    ui.tags.p(status["message"], style="color: #666; margin: 0;"),
                    style="padding: 1rem; background: #fee; border: 2px solid #dc2626; border-radius: 8px;"
                )
            )
        elif status["type"] == "warning":
            return ui.div(
                ui.tags.div(
                    ui.tags.h4("Attention: " + status["title"], style="color: #f59e0b; margin-bottom: 0.5rem;"),
                    ui.tags.p(status["message"], style="color: #666; margin: 0;"),
                    style="padding: 1rem; background: #fffbeb; border: 2px solid #f59e0b; border-radius: 8px;"
                )
            )

        return ui.div()

    # ========== LACTATE TESTS HANDLERS ==========

    # Handle lactate athlete selection (coach only)
    @reactive.Effect
    @reactive.event(input.lactate_athlete_select)
    def handle_lactate_athlete_select():
        """Update zones_selected_athlete when coach selects athlete in lactate card"""
        selected = input.lactate_athlete_select()
        if selected and selected != "":
            zones_selected_athlete.set(selected)
            # Reload lactate tests for the selected athlete
            load_lactate_tests_for_athlete(selected)

    def load_lactate_tests_for_athlete(athlete_id):
        """Load lactate tests for a specific athlete"""
        if not athlete_id:
            lactate_tests_data.set([])
            return

        try:
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/lactate_tests",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json"
                },
                params={
                    "athlete_id": f"eq.{athlete_id}",
                    "select": "*",
                    "order": "test_date.desc,distance_m.asc"
                }
            )

            if response.status_code == 200:
                tests = response.json()
                lactate_tests_data.set(tests)
            else:
                print(f"Error loading lactate tests: {response.text}")
                lactate_tests_data.set([])
        except Exception as e:
            print(f"Error loading lactate tests: {e}")
            lactate_tests_data.set([])

    # Load lactate tests when authenticated
    @reactive.Effect
    @reactive.event(is_authenticated)
    def load_lactate_tests():
        """Load current lactate tests from database"""
        print("[DEBUG] load_lactate_tests called", flush=True)
        if not is_authenticated.get():
            return

        role = user_role.get()
        if role == "coach":
            # Coach: use selected athlete from zones_selected_athlete
            athlete_id = zones_selected_athlete.get()
        else:
            # Athlete: use own ID
            athlete_id = user_athlete_id.get()

        if not athlete_id:
            return

        try:
            # Query lactate tests using requests
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/lactate_tests",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json"
                },
                params={
                    "athlete_id": f"eq.{athlete_id}",
                    "select": "*",
                    "order": "test_date.desc,distance_m.asc"
                }
            )

            if response.status_code == 200:
                tests = response.json()
                lactate_tests_data.set(tests)
            else:
                print(f"Error loading lactate tests: {response.text}")
                lactate_tests_data.set([])
        except Exception as e:
            print(f"Error loading lactate tests: {e}")
            lactate_tests_data.set([])

    # Conditional fields for event type (lactate vs race vs injury)
    @output
    @render.ui
    def lactate_conditional_fields():
        """Render fields based on selected event type (lactate, race, or injury)"""
        test_type = input.lactate_test_type() if hasattr(input, 'lactate_test_type') else "lactate"

        if test_type == "race":
            # Show distance and race time inputs for races
            return ui.row(
                ui.column(6,
                    ui.tags.label("Distance (mètres)", style="font-weight: 600; display: block; margin-bottom: 0.5rem;"),
                    ui.input_numeric("lactate_distance_m", "", value=None, min=100, max=50000, step=100, width="100%")
                ),
                ui.column(6,
                    ui.tags.label("Temps de course (HH:MM:SS ou MM:SS)", style="font-weight: 600; display: block; margin-bottom: 0.5rem;"),
                    ui.input_text("lactate_race_time", "", placeholder="ex: 42:30 ou 1:23:45", width="100%")
                ),
                style="margin-top: 1rem;"
            )
        elif test_type == "speed_test":
            # Show distance, time, and auto-calculated speed for speed tests
            return ui.div(
                ui.row(
                    ui.column(4,
                        ui.tags.label("Distance (metres)", style="font-weight: 600; display: block; margin-bottom: 0.5rem;"),
                        ui.input_numeric("lactate_distance_m", "", value=None, min=10, max=1000, step=10, width="100%")
                    ),
                    ui.column(4,
                        ui.tags.label("Temps (MM:SS:MS ou SS)", style="font-weight: 600; display: block; margin-bottom: 0.5rem;"),
                        ui.input_text("speed_test_time", "", placeholder="ex: 0:05:23 ou 5.2", width="100%")
                    ),
                    ui.column(4,
                        ui.tags.label("Vitesse (m/s)", style="font-weight: 600; display: block; margin-bottom: 0.5rem;"),
                        ui.output_ui("speed_test_calculated"),
                    ),
                ),
                style="margin-top: 1rem;"
            )
        else:
            # Show lactate and distance inputs for lactate tests
            return ui.row(
                ui.column(6,
                    ui.tags.label("Lactate (mmol/L)", style="font-weight: 600; display: block; margin-bottom: 0.5rem;"),
                    ui.input_numeric("lactate_mmol", "", value=None, min=0.0, max=30.0, step=0.1, width="100%")
                ),
                ui.column(6,
                    ui.tags.label("Distance (mètres)", style="font-weight: 600; display: block; margin-bottom: 0.5rem;"),
                    ui.input_numeric("lactate_distance_m", "", value=None, min=100, max=50000, step=100, width="100%")
                ),
                style="margin-top: 1rem;"
            )

    # Auto-calculated speed for speed tests
    @output
    @render.ui
    def speed_test_calculated():
        """Reactively compute speed (m/s) from distance and time inputs."""
        try:
            dist = input.lactate_distance_m()
            time_str = input.speed_test_time()
            if dist and time_str and str(time_str).strip():
                time_str = str(time_str).strip()
                # Try parse as MM:SS first, then as raw seconds
                time_seconds = parse_time_to_seconds(time_str)
                if time_seconds is None:
                    # Try parsing as raw seconds (e.g., "5.2")
                    try:
                        time_seconds = float(time_str)
                    except ValueError:
                        pass
                if time_seconds and time_seconds > 0:
                    speed = dist / time_seconds
                    return ui.div(
                        ui.tags.span(f"{speed:.2f} m/s", style="font-size: 1.2rem; font-weight: 700; color: #16a34a;"),
                        style="padding-top: 0.3rem;"
                    )
        except Exception:
            pass
        return ui.div(
            ui.tags.span("--", style="font-size: 1.2rem; color: #999;"),
            style="padding-top: 0.3rem;"
        )

    # Status message display for lactate tests
    @output
    @render.ui
    def lactate_status_message():
        """Display lactate tests save status message"""
        status = lactate_tests_save_status.get()
        if not status:
            return ui.div()

        if status["type"] == "success":
            return ui.div(
                ui.tags.div(
                    ui.tags.h4(status["title"], style="color: #16a34a; margin-bottom: 0.5rem;"),
                    ui.tags.p(status["message"], style="color: #666; margin: 0;"),
                    style="padding: 1rem; background: #f0fdf4; border: 2px solid #16a34a; border-radius: 8px;"
                )
            )
        elif status["type"] == "error":
            return ui.div(
                ui.tags.div(
                    ui.tags.h4(status["title"], style="color: #dc2626; margin-bottom: 0.5rem;"),
                    ui.tags.p(status["message"], style="color: #666; margin: 0;"),
                    style="padding: 1rem; background: #fee; border: 2px solid #dc2626; border-radius: 8px;"
                )
            )

        return ui.div()

    # Handle save lactate test or race
    @reactive.Effect
    @reactive.event(input.save_lactate_test)
    def handle_save_lactate_test():
        """Save new lactate test or race result to database"""
        # Determine target athlete (coach uses selected athlete, athlete uses own ID)
        role = user_role.get()
        if role == "coach":
            athlete_id = zones_selected_athlete.get()
            if not athlete_id:
                lactate_tests_save_status.set({"type": "error", "title": "Erreur", "message": "Veuillez sélectionner un athlète"})
                return
        else:
            athlete_id = user_athlete_id.get()
            if not athlete_id:
                lactate_tests_save_status.set({"type": "error", "title": "Erreur", "message": "Athlète non identifié"})
                return

        try:
            # Get form values
            test_type = input.lactate_test_type() if hasattr(input, 'lactate_test_type') else "lactate"
            test_date = input.lactate_test_date()
            distance_m = input.lactate_distance_m()
            notes = input.lactate_notes() if hasattr(input, 'lactate_notes') else ""

            # Validate required fields (common to all types)
            if not test_date:
                lactate_tests_save_status.set({"type": "error", "title": "Erreur", "message": "Veuillez sélectionner une date"})
                return

            # Build base record
            record = {
                "athlete_id": athlete_id,
                "test_date": str(test_date),
                "test_type": test_type,
                "notes": notes.strip() if notes else None
            }

            # Type-specific validation and fields
            if test_type == "lactate":
                # Lactate test - require lactate value and distance
                if not distance_m:
                    lactate_tests_save_status.set({"type": "error", "title": "Erreur", "message": "Veuillez entrer une distance"})
                    return
                lactate_mmol = input.lactate_mmol() if hasattr(input, 'lactate_mmol') else None
                if lactate_mmol is None:
                    lactate_tests_save_status.set({"type": "error", "title": "Erreur", "message": "Veuillez entrer une valeur de lactate"})
                    return
                record["distance_m"] = int(distance_m)
                record["lactate_mmol"] = float(lactate_mmol)
                record["race_time_seconds"] = None
                success_msg = f"Test du {test_date}: {distance_m}m - {lactate_mmol} mmol/L"

            elif test_type == "race":
                # Race - require distance, parse race time (optional but recommended)
                if not distance_m:
                    lactate_tests_save_status.set({"type": "error", "title": "Erreur", "message": "Veuillez entrer une distance"})
                    return
                race_time_str = input.lactate_race_time() if hasattr(input, 'lactate_race_time') else ""
                race_time_seconds = None
                if race_time_str and race_time_str.strip():
                    race_time_seconds = parse_time_to_seconds(race_time_str.strip())
                    if race_time_seconds is None:
                        lactate_tests_save_status.set({"type": "error", "title": "Erreur", "message": "Format de temps invalide. Utilisez HH:MM:SS ou MM:SS"})
                        return
                record["distance_m"] = int(distance_m)
                record["lactate_mmol"] = None
                record["race_time_seconds"] = race_time_seconds
                if race_time_seconds:
                    time_display = format_time_from_seconds(race_time_seconds)
                    success_msg = f"Course du {test_date}: {distance_m}m en {time_display}"
                else:
                    success_msg = f"Course du {test_date}: {distance_m}m"

            elif test_type == "speed_test":
                # Speed test - require distance and time
                if not distance_m:
                    lactate_tests_save_status.set({"type": "error", "title": "Erreur", "message": "Veuillez entrer une distance"})
                    return
                time_str = input.speed_test_time() if hasattr(input, 'speed_test_time') else ""
                if not time_str or not str(time_str).strip():
                    lactate_tests_save_status.set({"type": "error", "title": "Erreur", "message": "Veuillez entrer un temps"})
                    return
                time_str = str(time_str).strip()
                # Parse as MM:SS first, then as raw seconds
                time_seconds = parse_time_to_seconds(time_str)
                if time_seconds is None:
                    try:
                        time_seconds = float(time_str)
                    except ValueError:
                        time_seconds = None
                if time_seconds is None or time_seconds <= 0:
                    lactate_tests_save_status.set({"type": "error", "title": "Erreur", "message": "Format de temps invalide. Utilisez MM:SS ou des secondes (ex: 5.2)"})
                    return
                speed_ms = distance_m / time_seconds
                record["distance_m"] = int(distance_m)
                record["lactate_mmol"] = None
                record["race_time_seconds"] = round(time_seconds, 2)
                record["speed_ms"] = round(speed_ms, 3)
                time_display = format_time_from_seconds(time_seconds)
                success_msg = f"Test de vitesse du {test_date}: {distance_m}m en {time_display} ({speed_ms:.2f} m/s)"

            else:
                lactate_tests_save_status.set({"type": "error", "title": "Erreur", "message": "Type d'événement non reconnu"})
                return

            # Insert into database
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/lactate_tests",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal"
                },
                json=record
            )

            if response.status_code in [200, 201]:
                if test_type == "race":
                    title = "Course enregistrée"
                else:
                    title = "Test enregistré"
                lactate_tests_save_status.set({
                    "type": "success",
                    "title": title,
                    "message": success_msg
                })
                # Reload tests
                load_lactate_tests()
            else:
                error_msg = response.text
                if "unique_lactate_test" in error_msg:
                    lactate_tests_save_status.set({
                        "type": "error",
                        "title": "Erreur",
                        "message": "Une entrée avec cette date et distance existe déjà"
                    })
                else:
                    lactate_tests_save_status.set({
                        "type": "error",
                        "title": "Erreur",
                        "message": f"Erreur lors de l'enregistrement: {error_msg}"
                    })

        except Exception as e:
            print(f"Error saving lactate test: {e}")
            traceback.print_exc()
            lactate_tests_save_status.set({
                "type": "error",
                "title": "Erreur",
                "message": f"Erreur: {str(e)}"
            })

    # Handle save
    @reactive.Effect
    @reactive.event(input.save_personal_records)
    def handle_save_personal_records():
        """Save personal records to database"""
        athlete_id = user_athlete_id.get()
        if not athlete_id:
            pr_save_status.set({"type": "error", "title": "Erreur", "message": "Athlète non identifié"})
            return
        
        try:
            updates = []
            improvements = []
            errors = []
            
            # Collect all inputs
            for dist in DISTANCES:
                key = dist["key"]
                time_id = f"pr_time_{key}"
                date_id = f"pr_date_{key}"
                priority_id = f"pr_priority_{key}"
                notes_id = f"pr_notes_{key}"

                # Get input values
                time_str = input[time_id]()
                date_val = input[date_id]()
                priority_val = input[priority_id]()
                notes_val = input[notes_id]()
                
                # Skip if no time entered
                if not time_str or time_str.strip() == "":
                    continue
                
                # Parse time
                time_seconds = parse_time_to_seconds(time_str)
                if time_seconds is None:
                    errors.append(f"{dist['label']}: Format de temps invalide (utilisez MM:SS ou HH:MM:SS)")
                    continue
                
                # Check if it's an improvement
                current_prs = pr_data.get()
                current_pr = current_prs.get(key, {})
                current_time = current_pr.get("time_seconds")
                
                if current_time and time_seconds < current_time:
                    improvement_sec = current_time - time_seconds
                    improvements.append(f"{dist['label']}: Nouveau record! ({improvement_sec}s plus rapide)")
                elif current_time and time_seconds > current_time:
                    # Slower time - still allow but note it
                    pass
                
                # Prepare record
                record = {
                    "athlete_id": athlete_id,
                    "distance_type": key,
                    "time_seconds": time_seconds,
                    "record_date": str(date_val) if date_val else None,
                    "race_priority": priority_val if priority_val and priority_val.strip() and priority_val != "—" else None,
                    "notes": notes_val if notes_val and notes_val.strip() else None
                }
                
                updates.append(record)
            
            # Validation
            if errors:
                pr_save_status.set({
                    "type": "error",
                    "title": "Erreurs de validation",
                    "message": " | ".join(errors)
                })
                return
            
            if not updates:
                pr_save_status.set({
                    "type": "warning",
                    "title": "Aucune donnée",
                    "message": "Veuillez entrer au moins un temps avant d'enregistrer."
                })
                return
            
            # Save to database (upsert)
            for record in updates:
                success = supa_upsert("personal_records", record)
                if not success:
                    errors.append(f"Erreur pour {record['distance_type']}")
            
            if errors:
                pr_save_status.set({
                    "type": "error",
                    "title": "Erreur d'enregistrement",
                    "message": " | ".join(errors)
                })
                return
            
            # Success!
            success_msg = f"{len(updates)} record(s) enregistré(s) avec succès!"
            if improvements:
                success_msg += " " + " ".join(improvements)
            
            pr_save_status.set({
                "type": "success",
                "title": "Enregistrement réussi",
                "message": success_msg
            })
            
            # Reload PRs
            load_personal_records()
            
            # Clear inputs
            for dist in DISTANCES:
                key = dist["key"]
                ui.update_text(f"pr_time_{key}", value="")
                ui.update_text(f"pr_notes_{key}", value="")
            
        except Exception as e:
            print(f"Error saving personal records: {e}")
            import traceback
            traceback.print_exc()
            pr_save_status.set({
                "type": "error",
                "title": "Erreur système",
                "message": f"Une erreur est survenue: {str(e)}"
            })

    # ========== TRAINING ZONES HANDLERS ==========

    # Load training zones for the current/selected athlete
    @reactive.Effect
    @reactive.event(is_authenticated, zones_selected_athlete)
    def load_training_zones():
        """Load most recent training zones from database"""
        print("[DEBUG] load_training_zones called", flush=True)
        if not is_authenticated.get():
            return

        role = user_role.get()

        # Determine target athlete
        if role == "coach":
            target_athlete_id = zones_selected_athlete.get()
        else:
            target_athlete_id = user_athlete_id.get()

        if not target_athlete_id:
            zones_data.set([])
            return

        try:
            # Query zones using supa_select - get most recent configuration
            params = {"athlete_id": f"eq.{target_athlete_id}"}
            df = supa_select("athlete_training_zones", select="*", params=params, limit=1000)

            if df.empty:
                zones_data.set([])
                return

            # Find the most recent effective_from_date
            most_recent_date = df["effective_from_date"].max()

            # Filter zones for most recent configuration
            recent_zones_df = df[df["effective_from_date"] == most_recent_date]

            # Convert to list of dicts
            zones = recent_zones_df.to_dict("records")

            zones_data.set(zones)
        except Exception as e:
            print(f"Error loading training zones: {e}")
            import traceback
            traceback.print_exc()
            zones_data.set([])

    # Handle athlete selection change (coach only)
    @reactive.Effect
    @reactive.event(input.zones_athlete_select)
    def handle_zones_athlete_change():
        """Update selected athlete for zones configuration"""
        if user_role.get() != "coach":
            return

        selected = input.zones_athlete_select()
        if selected and selected != "":
            zones_selected_athlete.set(selected)
        else:
            zones_selected_athlete.set(None)

    # Handle save training zones
    @reactive.Effect
    @reactive.event(input.save_training_zones)
    def handle_save_training_zones():
        """Save training zones to database"""
        role = user_role.get()

        # Determine target athlete
        if role == "coach":
            target_athlete_id = zones_selected_athlete.get()
        else:
            target_athlete_id = user_athlete_id.get()

        if not target_athlete_id:
            zones_save_status.set({
                "type": "error",
                "title": "Erreur",
                "message": "Veuillez sélectionner un athlète."
            })
            return

        try:
            # Get configuration
            effective_date = input.zones_effective_date()
            num_zones = int(input.zones_num_zones())

            if not effective_date:
                zones_save_status.set({
                    "type": "error",
                    "title": "Date requise",
                    "message": "Veuillez sélectionner une date d'entrée en vigueur."
                })
                return

            # Collect zone data
            zones_to_save = []
            errors = []

            for zone_num in range(1, 11):
                # Get all values for this zone
                hr_min = input[f"zone_{zone_num}_hr_min"]()
                hr_max = input[f"zone_{zone_num}_hr_max"]()
                pace_min_str = input[f"zone_{zone_num}_pace_min"]()
                pace_max_str = input[f"zone_{zone_num}_pace_max"]()
                lactate_min = input[f"zone_{zone_num}_lactate_min"]()
                lactate_max = input[f"zone_{zone_num}_lactate_max"]()

                # Convert pace strings to seconds
                pace_min_sec = pace_mmss_to_seconds(pace_min_str) if pace_min_str else None
                pace_max_sec = pace_mmss_to_seconds(pace_max_str) if pace_max_str else None

                # Validate pace format
                if pace_min_str and pace_min_str.strip() and pace_min_sec is None:
                    errors.append(f"Zone {zone_num}: Format d'allure min invalide (utilisez MM:SS)")
                if pace_max_str and pace_max_str.strip() and pace_max_sec is None:
                    errors.append(f"Zone {zone_num}: Format d'allure max invalide (utilisez MM:SS)")

                # Validate ranges
                if hr_min is not None and hr_max is not None and hr_min > hr_max:
                    errors.append(f"Zone {zone_num}: FC min doit être ≤ FC max")
                if pace_min_sec is not None and pace_max_sec is not None and pace_min_sec < pace_max_sec:
                    errors.append(f"Zone {zone_num}: Allure min doit être ≥ Allure max (plus lent = plus grand)")
                if lactate_min is not None and lactate_max is not None and lactate_min > lactate_max:
                    errors.append(f"Zone {zone_num}: Lactate min doit être ≤ Lactate max")

                # Prepare zone record
                zone_record = {
                    "athlete_id": target_athlete_id,
                    "effective_from_date": str(effective_date),
                    "num_zones": num_zones,
                    "zone_number": zone_num,
                    "hr_min": float(hr_min) if hr_min is not None else None,
                    "hr_max": float(hr_max) if hr_max is not None else None,
                    "pace_min_sec_per_km": pace_min_sec,
                    "pace_max_sec_per_km": pace_max_sec,
                    "lactate_min": float(lactate_min) if lactate_min is not None else None,
                    "lactate_max": float(lactate_max) if lactate_max is not None else None
                }

                zones_to_save.append(zone_record)

            # Check for validation errors
            if errors:
                zones_save_status.set({
                    "type": "error",
                    "title": "Erreurs de validation",
                    "message": " | ".join(errors[:3])  # Show first 3 errors
                })
                return

            # Save all zones (insert - append only, no update)
            for zone in zones_to_save:
                success = supa_insert("athlete_training_zones", zone)
                if not success:
                    errors.append(f"Erreur pour zone {zone['zone_number']}")

            if errors:
                zones_save_status.set({
                    "type": "error",
                    "title": "Erreur d'enregistrement",
                    "message": " | ".join(errors)
                })
                return

            # Success!
            zones_save_status.set({
                "type": "success",
                "title": "Enregistrement réussi",
                "message": f"Configuration de {num_zones} zones enregistrée avec succès pour le {effective_date}!"
            })

            # Reload zones
            load_training_zones()

        except Exception as e:
            print(f"Error saving training zones: {e}")
            import traceback
            traceback.print_exc()
            zones_save_status.set({
                "type": "error",
                "title": "Erreur système",
                "message": f"Une erreur est survenue: {str(e)}"
            })

    # Met à jour dynamiquement les bornes MIN/MAX des dates selon l'athlète et le toggle VirtualRun
    @reactive.Effect
    @reactive.event(input.athlete, input.incl_vrun)
    def _update_date_limits():
        sel_name = input.athlete() or ""
        athlete_id = name_to_id.get(sel_name, sel_name)
        inc_vrun = bool(input.incl_vrun())
        dmin, dmax = fetch_date_range(athlete_id, include_vrun=inc_vrun)
        if not dmin or not dmax:
            return
        cur_start = input.date_start() or dmin
        cur_end = input.date_end() or dmax
        new_start = max(dmin, min(cur_start, dmax))
        new_end = max(new_start, min(cur_end, dmax))
        with reactive.isolate():
            ui.update_date("date_start", min=dmin, max=dmax, value=new_start)
            ui.update_date("date_end", min=dmin, max=dmax, value=new_end)

    # ----------------- Phase 1.5: Intervals Visualization - REMOVED -----------------
    # Will be implemented later

# Create app with error handling for production debugging
try:
    app = App(app_ui, server)
except Exception as e:
    import traceback
    error_msg = f"App initialization failed: {str(e)}\n\n{traceback.format_exc()}"
    print(f"[ERROR] {error_msg}")

    # Create a simple error page so we can see what went wrong
    error_ui = ui.page_fluid(
        ui.h1("Erreur d'initialisation"),
        ui.pre(error_msg, style="background: #fee; padding: 20px; overflow: auto;")
    )
    def error_server(input, output, session):
        pass
    app = App(error_ui, error_server)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
