# /Users/marcantoinepaquet/Documents/INS/supabase_shiny.py
# Dashboard Shiny: Analyse de séance (X/Y dynamiques) + Résumé de période (avec toggle VirtualRun)
# Hypothèses:
# - Tables Supabase: activity, activity_metadata, athlete
# - .env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (ou ANON), chargé via INS_ENV_FILE
# - Matplotlib pour les graphiques; Shiny for Python (Express/Core)

from __future__ import annotations
import os
import time
from datetime import date, timedelta
import functools
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.ticker import FuncFormatter
from zoneinfo import ZoneInfo
import requests
from dotenv import load_dotenv
import plotly.graph_objects as go

from shiny import App, ui, render, reactive
from shinywidgets import output_widget, render_plotly

# Import algorithme temps actif (Strava-like)
from moving_time import compute_moving_time_strava

# =============== Performance Monitoring ===============
def timing_decorator(func):
    """Decorator to time function execution (logs if > 100ms)."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        if elapsed > 0.1:  # Log if > 100ms
            print(f"⏱️  {func.__name__}: {elapsed:.3f}s")
        return result
    return wrapper

# Palette de couleurs uniforme (pie + volume hebdo)
COLORS = {
    "Run": "#1f77b4",        # bleu
    "Course": "#1f77b4",     # bleu (Run+TrailRun agrégé)
    "TrailRun": "#f1c40f",   # jaune
    "VirtualRun": "#ff7f0e", # orange
    "Tapis": "#ff7f0e",      # orange (same as VirtualRun)
    "Autre": "#2ca02c"       # vert
}

RUN_TYPES = {"run", "trailrun", "virtualrun", "treadmill"}

# Aliases robustes pour les selects UI (labels & valeurs -> codes canoniques)
XVAR_ALIASES = {
    "moving": "moving", "Temps en mouvement (mm:ss)": "moving",
    "dist": "dist", "Distance (km)": "dist",
}
YVAR_ALIASES = {
    "heartrate": "heartrate", "Fréquence cardiaque (bpm)": "heartrate",
    "cadence": "cadence", "Cadence (spm)": "cadence",
    "pace": "pace", "Allure (min/km)": "pace",
    "watts": "watts", "Puissance (W)": "watts",
    "vertical_oscillation": "vertical_oscillation", "Oscillation Verticale (mm)": "vertical_oscillation",
}

# =============== Chargement .env & session HTTP Supabase ===============
ENV_PATH = os.environ.get("INS_ENV_FILE") or "/Users/marcantoinepaquet/Documents/INS/shiny_env.env"
load_dotenv(dotenv_path=ENV_PATH, override=False)

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY (ou ANON) doivent être définis dans .env")

# Fuseau horaire local pour l’agrégation hebdo
LOCAL_TZ = os.getenv("INS_TZ", "America/Toronto")  # fuseau horaire local pour l’agrégation hebdo

_sess = requests.Session()
_sess.headers.update({"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
_sess.headers.update({"Accept-Encoding": "gzip, deflate"})

# =============== Memory Cache for Metadata (5-minute TTL) ===============
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

# =============== Aides données ===============
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
    cols = ("activity_id,athlete_id,type,date,start_time,distance_m,duration_sec,avg_hr,"
            "weather_temp_c,weather_humidity_pct,weather_wind_speed_ms,weather_cloudcover_pct,air_us_aqi,"
            "distance_km,duration_min,type_lower,pace_skm,type_category")
    # Phase 2: Use materialized view for 3-5x faster queries
    df = supa_select("activity_summary", select=cols, params=params, limit=limit)
    
    if not df.empty:
        if "start_time" in df.columns:
            df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
        df["type"] = df["type"].astype(str).str.strip()
        
        # Phase 2: type_lower and type_category now come from view (pre-computed)
        # Only compute if not present (fallback for compatibility)
        if "type_lower" not in df.columns:
            df["type_lower"] = df["type"].str.lower()
        if "type_category" not in df.columns:
            df["type_category"] = df["type_lower"].map({
                "run": "Course",
                "trailrun": "Course",
                "virtualrun": "Tapis"
            }).fillna("Autre")
    
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
    # Plus ancienne (Phase 2: use activity_summary view)
    df_min = supa_select("activity_summary", select="start_time", params={**params_earliest, "order": "start_time.asc"}, limit=1)
    # Plus récente
    df_max = supa_select("activity_summary", select="start_time", params={**params_latest, "order": "start_time.desc"}, limit=1)
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

@timing_decorator
def _fetch_timeseries_raw(activity_id: str, limit: int = 300000) -> pd.DataFrame:
    """Récupère (et met en cache disque) la série temporelle d'une activité."""
    cols = "activity_id,ts_offset_ms,time,t_active_sec,heartrate,speed,enhanced_speed,velocity_smooth,cadence,watts,vertical_oscillation"
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

    # Fetch from database
    df = supa_select("activity", select=cols, params=params, limit=limit)
    if df.empty:
        return df

    # Dtypes compacts pour accélérer les calculs et réduire la taille disque
    for c in ("ts_offset_ms","time","t_active_sec","heartrate","speed","enhanced_speed","velocity_smooth","cadence","watts","vertical_oscillation"):
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

@functools.lru_cache(maxsize=1024)
def fetch_timeseries_cached(activity_id: str) -> pd.DataFrame:
    """Cache mémoire sur la série d’une activité."""
    return _fetch_timeseries_raw(activity_id)

# =============== Phase 1.5: Intervals Data Layer ===============

@functools.lru_cache(maxsize=512)
def get_activity_intervals(activity_id: str) -> pd.DataFrame:
    """
    Retrieve intervals with calculated metrics.
    
    Returns DataFrame with:
    - interval_id, start_t_active, end_t_active (for time-based X-axis)
    - start_time, end_time (for elapsed time reference)
    - distance (meters), moving_time (seconds)
    - average_heartrate, average_watts
    - calculated fields (pace, formatted strings)
    """
    if not activity_id:
        return pd.DataFrame()
    
    try:
        response = supabase.table("activity_intervals") \
            .select("*") \
            .eq("activity_id", activity_id) \
            .order("start_time") \
            .execute()
        
        df = pd.DataFrame(response.data)
        
        if df.empty:
            return df
        
        # Calculate pace (min/km) - handle division by zero
        df['pace_minkm'] = np.where(
            (df['distance'] > 0) & (df['moving_time'] > 0),
            (df['moving_time'] / 60) / (df['distance'] / 1000),
            np.nan
        )
        
        # Format duration as MM:SS
        df['duration_fmt'] = df['moving_time'].apply(
            lambda x: f"{int(x//60):02d}:{int(x%60):02d}" if pd.notna(x) and x >= 0 else "-"
        )
        
        # Format pace as M:SS/km
        df['pace_fmt'] = df['pace_minkm'].apply(
            lambda x: f"{int(x)}:{int((x % 1) * 60):02d}/km" if pd.notna(x) and x > 0 else "-"
        )
        
        # Format distance
        df['distance_fmt'] = df['distance'].apply(
            lambda x: f"{x/1000:.2f} km" if pd.notna(x) and x > 0 else "-"
        )
        
        return df
        
    except Exception as e:
        print(f"❌ Error fetching intervals for {activity_id}: {e}")
        return pd.DataFrame()

def classify_intervals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Auto-classify intervals as work/rest/warmup/cooldown.
    
    Rules:
    1. First interval > 5 min → warmup
    2. Last interval > 5 min → cooldown  
    3. High intensity (pace < median OR HR > median) → work
    4. Low intensity → rest
    """
    if df.empty or len(df) < 2:
        # Single or no intervals - classify as work if present
        if not df.empty:
            df['interval_type'] = 'work'
        return df
    
    df = df.copy()  # Avoid modifying original
    
    # Calculate intensity score (0-1 normalized)
    if 'average_heartrate' in df.columns and df['average_heartrate'].notna().any():
        hr_values = df['average_heartrate'].dropna()
        if len(hr_values) > 1:
            hr_min = hr_values.min()
            hr_max = hr_values.max()
            if hr_max > hr_min:
                df['hr_norm'] = (df['average_heartrate'] - hr_min) / (hr_max - hr_min)
            else:
                df['hr_norm'] = 0.5
        else:
            df['hr_norm'] = 0.5
    else:
        df['hr_norm'] = 0.5
    
    if 'pace_minkm' in df.columns and df['pace_minkm'].notna().any():
        pace_values = df['pace_minkm'].dropna()
        if len(pace_values) > 1:
            pace_min = pace_values.min()
            pace_max = pace_values.max()
            if pace_max > pace_min:
                # Faster pace = higher score (invert)
                df['pace_norm'] = 1 - ((df['pace_minkm'] - pace_min) / (pace_max - pace_min))
            else:
                df['pace_norm'] = 0.5
        else:
            df['pace_norm'] = 0.5
    else:
        df['pace_norm'] = 0.5
    
    # Fill NaN values with 0.5 (neutral)
    df['hr_norm'] = df['hr_norm'].fillna(0.5)
    df['pace_norm'] = df['pace_norm'].fillna(0.5)
    
    df['intensity'] = (df['hr_norm'] + df['pace_norm']) / 2
    median_intensity = df['intensity'].median()
    
    # Classify intervals
    df['interval_type'] = 'unknown'
    for idx in range(len(df)):
        moving_time = df.iloc[idx]['moving_time'] if pd.notna(df.iloc[idx]['moving_time']) else 0
        
        if idx == 0 and moving_time > 300:  # First interval > 5 min
            df.at[df.index[idx], 'interval_type'] = 'warmup'
        elif idx == len(df) - 1 and moving_time > 300:  # Last interval > 5 min
            df.at[df.index[idx], 'interval_type'] = 'cooldown'
        elif df.iloc[idx]['intensity'] > median_intensity:
            df.at[df.index[idx], 'interval_type'] = 'work'
        else:
            df.at[df.index[idx], 'interval_type'] = 'rest'
    
    return df

def detect_workout_pattern(df: pd.DataFrame) -> str:
    """
    Auto-detect workout patterns.
    
    Examples:
    - "5 répétitions de 1000m avec récupération"
    - "Pyramide: 400-800-1200-800-400m"
    """
    if df.empty:
        return ""
    
    work_intervals = df[df['interval_type'] == 'work']
    
    if len(work_intervals) == 0:
        return ""
    
    # Check if all work intervals are similar distance
    distances = work_intervals['distance'].dropna().values
    if len(distances) == 0:
        return ""
    
    distance_std = np.std(distances)
    distance_mean = np.mean(distances)
    
    # Within 50m tolerance → repetitions
    if distance_std < 50 and len(distances) > 1:
        count = len(work_intervals)
        if distance_mean >= 1000:
            dist_str = f"{distance_mean/1000:.2f}km"
        else:
            dist_str = f"{int(distance_mean)}m"
        
        return f"{count} répétitions de {dist_str} avec récupération"
    else:
        # Variable distances - show pattern
        if len(distances) > 1:
            dist_list = []
            for d in distances:
                if d >= 1000:
                    dist_list.append(f"{d/1000:.2f}km")
                else:
                    dist_list.append(f"{int(d)}m")
            return f"Entraînement fractionné: {' - '.join(dist_list)}"
        else:
            # Single work interval
            d = distances[0]
            if d >= 1000:
                dist_str = f"{d/1000:.2f}km"
            else:
                dist_str = f"{int(d)}m"
            return f"Intervalle unique de {dist_str}"

# =============== Numpy helpers ===============
def _np_max_cols(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    """Row-wise nanmax over existing columns, as float64 numpy array."""
    arrs = []
    for c in cols:
        if c in df.columns:
            arrs.append(pd.to_numeric(df[c], errors="coerce").to_numpy(dtype="float64"))
    if not arrs:
        return np.zeros(len(df), dtype="float64")
    M = np.nanmax(np.column_stack(arrs), axis=1)
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

# =============== Conversions & formatages ===============
def _fmt_mmss(x, _=None):
    try: x = float(x)
    except: return ""
    if x < 0 or not np.isfinite(x): return ""
    m = int(x // 60); s = int(x % 60)
    return f"{m:02d}:{s:02d}"

def _to_pace_sec_per_km(series: pd.Series) -> pd.Series:
    """Convertit vitesse (m/s) → allure (sec/km), NaN si v<=0."""
    v = pd.to_numeric(series, errors="coerce")
    pace = 1000.0 / v
    pace[(v <= 0) | (~np.isfinite(pace))] = np.nan
    return pace.astype("float64")

# =============== Calcul du temps en mouvement (algorithme Strava) ===============
def _active_time_seconds(df: pd.DataFrame, activity_type: str = "run") -> pd.Series:
    """
    Construit un axe 'temps en mouvement' via algorithme Strava.

    IMPORTANT : Ne pas utiliser 't_active_sec' de la BD s'il existe,
    car il peut être incorrect. On recalcule systématiquement.

    Args:
        df: DataFrame avec time series
        activity_type: Type d'activité (run, trailrun, cycling, etc.)

    Returns:
        Série du temps actif cumulé (secondes)
    """
    if df is None or df.empty:
        return pd.Series(dtype=float)

    # Utiliser l'algorithme Strava-like (moving_time.py)
    return compute_moving_time_strava(df, activity_type=activity_type)

# =============== Préparation XY selon choix X/Y ===============
def _prep_xy(df: pd.DataFrame, xvar: str, yvar: str, activity_type: str = "run", smooth_win: int = 21):
    n = len(df)
    if n == 0:
        return np.array([]), np.array([]), "", "", None, None

    # Base time arrays (float64 for numeric stability)
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

    # Speed proxy (m/s): row-wise max over available columns
    spd_cols = [c for c in ("speed","enhanced_speed","velocity_smooth") if c in df.columns]
    v = _np_max_cols(df, spd_cols)

    # Downsample step target (~1200 pts)
    step = max(1, n // 1200)

    # X
    if xvar == "moving":
        # *** OPTIMISÉ : Utiliser t_active_sec de la BD (déjà calculé correctement) ***
        # Fallback sur calcul client si colonne absente (rétrocompatibilité)
        if "t_active_sec" in df.columns and df["t_active_sec"].notna().any():
            x_full = pd.to_numeric(df["t_active_sec"], errors="coerce").to_numpy(dtype="float64")
        else:
            # Fallback: recalculer côté client
            x_full = compute_moving_time_strava(df, activity_type=activity_type).values
        x_label = "Temps en mouvement (mm:ss)"
        x_fmt = FuncFormatter(_fmt_mmss)
    else:
        # distance intégrée (km)
        dist = np.cumsum(np.nan_to_num(v) * dt) / 1000.0
        x_full = dist
        x_label = "Distance (km)"
        x_fmt = None

    # Y
    if yvar == "pace":
        pace = 1000.0 / np.where(np.isfinite(v) & (v > 0), v, np.nan)
        y_full = pace
        y_label = "Allure (min/km)"
        y_fmt = FuncFormatter(_fmt_mmss)
    elif yvar == "cadence":
        # La cadence provenant des appareils est souvent par jambe.
        # On la multiplie par 2 pour obtenir la cadence totale (spm).
        y_full = 2.0 * pd.to_numeric(df.get("cadence"), errors="coerce").to_numpy(dtype="float64")
        y_label = "Cadence (spm)"
        y_fmt = None
    elif yvar == "watts":
        y_full = pd.to_numeric(df.get("watts"), errors="coerce").to_numpy(dtype="float64")
        y_label = "Puissance (W)"
        y_fmt = None
    elif yvar == "vertical_oscillation":
        y_full = pd.to_numeric(df.get("vertical_oscillation"), errors="coerce").to_numpy(dtype="float64")
        y_label = "Oscillation Verticale (mm)"
        y_fmt = None
    else:
        y_full = pd.to_numeric(df.get("heartrate"), errors="coerce").to_numpy(dtype="float64")
        y_label = "Fréquence cardiaque (bpm)"
        y_fmt = None

    # Smoothing then decimation
    y_full = _smooth_nan(y_full, smooth_win)
    x = x_full[::step]
    y = y_full[::step]

    return x, y, x_label, y_label, x_fmt, y_fmt

# =============== UI ===============
today = date.today()
start_default = today - timedelta(days=7)

# Top bar: Athlète, Activité, Période, Toggle VirtualRun
top_bar = ui.div(
    ui.layout_columns(
        # Athlète (colonne ~33%)
        ui.column(4, 
            ui.div(
                ui.tags.label("👤 Athlète", **{"class": "form-label"}),
                ui.input_select("athlete", "", choices=[], width="100%")
            )
        ),

        # Période (colonne ~50%) — grille 2 lignes, "à" à gauche de la 2e ligne
        ui.column(6, ui.div(
            ui.tags.label("📅 Période", **{"class": "form-label"}),
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
                ui.tags.label("⚙️ Options", **{"class": "form-label"}),
                ui.input_checkbox("incl_vrun", "Inclure course sur tapis", value=True)
            )
        ),
    ),
    class_="top-bar-container"
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
        font-size: 1.06rem; 
        padding: 0.65rem 1rem;
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
        font-size: 0.95rem; 
        margin-bottom: 0.5rem;
        font-weight: 600;
        color: #262626;
        letter-spacing: 0.3px;
      }
      
      /* Date inputs */
      input[type="date"].form-control { 
        min-width: 320px;
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
        padding-top: 0.15rem;
        color: #D92323;
      }
      .period-grid .period-end { grid-column: 2; grid-row: 2; }
      
      /* Grid spacing */
      .bslib-grid { row-gap: 20px; column-gap: 20px; }
      
      /* Top bar container */
      .top-bar-container {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.07), 0 1px 3px rgba(0, 0, 0, 0.06);
        margin-bottom: 1.5rem;
      }
      
      /* Enhanced cards */
      .card { 
        width: 100%; 
        max-width: none;
        border: none;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.07), 0 1px 3px rgba(0, 0, 0, 0.06);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        background: white;
      }
      .card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 12px rgba(0, 0, 0, 0.1), 0 2px 4px rgba(0, 0, 0, 0.08);
      }
      
      .card-header {
        background: linear-gradient(135deg, #D91E2E 0%, #D91E2E 100%);
        color: white;
        font-weight: 700;
        font-size: 1.1rem;
        padding: 1rem 1.25rem;
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
        font-size: 0.85rem;
        margin-bottom: 0.3rem;
        font-weight: 600;
      }
      
      .analysis-unified .form-select {
        font-size: 0.95rem;
        padding: 0.5rem 0.75rem;
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
        font-size: 2.2rem;
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
        padding: 0.75rem 1.5rem;
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
        width: 1.2rem;
        height: 1.2rem;
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
      }
      
      /* Radio buttons */
      .form-check-input[type="radio"] {
        border-radius: 50%;
      }
      
      /* Responsive design */
      @media (max-width: 1200px) {
        .summary-grid-full { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .bslib-grid .col-4 { grid-column: span 12 !important; }
      }
      
      @media (max-width: 800px) {
        .summary-grid-full { grid-template-columns: 1fr; }
        h2 { font-size: 1.8rem; }
      }
      
      /* Animations */
      @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
      }
      .card {
        animation: fadeIn 0.4s ease-out;
      }
    """),
    ui.div(
        ui.h2("Dashboard Analytique - Saint-Laurent Sélect"),
        style="padding: 1.5rem 0;"
    ),
    
    # Year calendar visualization
    ui.card(
        ui.card_header(
            ui.layout_columns(
                ui.div("📅 Vue annuelle des activités", style="font-weight: bold; font-size: 0.9rem;"),
                ui.div(
                    ui.input_action_button("prev_year", "◀", style="padding: 0.2rem 0.5rem; font-size: 0.8rem;"),
                    ui.output_text("current_year_display", inline=True, container=ui.span),
                    ui.input_action_button("next_year", "▶", style="padding: 0.2rem 0.5rem; font-size: 0.8rem;"),
                    style="text-align: right; font-size: 0.85rem;"
                ),
                col_widths=[6, 6]
            )
        ),
        ui.div(
            output_widget("year_calendar_heatmap"),
            style="overflow-x: auto;"
        ),
        style="margin-bottom: 1rem;"
    ),
    
    top_bar,
    ui.br(),
    ui.navset_tab(
        ui.nav_panel("Résumé de période",
            # Trend card with integrated controls - full width
            ui.card(
                ui.card_header("📈 Tendance course — moyenne mobile exponentielle"),
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
                        col_widths=[12],
                    ),
                    ui.div(output_widget("run_duration_trend"), style="margin-top: 1rem;"),
                    class_="analysis-unified"
                ),
            ),
            # Three graphs in grid - full width
            ui.div({"class": "summary-grid-full"},
                ui.card(
                    ui.card_header("🥧 Répartition des types (temps total)"),
                    output_widget("pie_types"),
                ),
                ui.card(
                    ui.card_header("💓 Allure vs Fréquence cardiaque — par mois"),
                    output_widget("pace_hr_scatter"),
                ),
                ui.card(
                    ui.card_header("📊 Volume hebdomadaire"),
                    output_widget("weekly_volume"),
                ),
            ),
        ),
        ui.nav_panel("Analyse de séance",
            ui.card(
                ui.card_header("📉 Analyse X/Y dynamique"),
                ui.div(
                    # Top controls row: Activity selector + X/Y axis selectors
                    ui.layout_columns(
                        ui.input_select("activity_sel", "🏃 Activité", choices=[], width="100%"),
                        ui.input_select(
                            "xvar", "📊 Axe X",
                            choices={"Temps en mouvement": "Temps", "Distance (km)": "Distance"},
                            selected="moving", width="100%"
                        ),
                        ui.input_select(
                            "yvar", "📈 Axe Y",
                            choices={
                                "Fréquence cardiaque": "heartrate",
                                "Cadence": "cadence",
                                "Allure": "pace",
                                "Puissance": "watts",
                                "Oscillation Verticale": "vertical_oscillation"
                            },
                            selected="heartrate", width="100%"
                        ),
                        col_widths=[6, 3, 3],
                    ),
                    # Plot
                    ui.div(output_widget("plot_xy"), style="margin-top: 1rem;"),
                    class_="analysis-unified"
                ),
            ),
            
            # Phase 1.5: Intervals visualization card
            ui.card(
                ui.card_header(
                    "📊 Analyse avec intervalles",
                    class_="text-white",
                    style="background: linear-gradient(135deg, #D91E2E 0%, #8B1520 100%);"
                ),
                
                # Axis selectors (same as main graph)
                ui.layout_columns(
                    ui.input_select(
                        "interval_x_axis",
                        "Axe X:",
                        choices={
                            "t_active_sec": "Temps en mouvement",
                            "distance_m": "Distance"
                        },
                        selected="t_active_sec"
                    ),
                    ui.input_select(
                        "interval_y_axis",
                        "Axe Y:",
                        choices={
                            "heartrate": "Fréquence cardiaque",
                            "cadence": "Cadence",
                            "pace": "Allure (min/km)",
                            "watts": "Puissance",
                            "vertical_oscillation": "Oscillation verticale"
                        },
                        selected="heartrate"
                    ),
                    col_widths=[6, 6]
                ),
                
                # Plotly graph
                ui.div(output_widget("interval_enhanced_plot"), style="margin-top: 1rem;"),
                
                # Summary table
                ui.output_ui("intervals_summary"),
                
                class_="mb-3"
            ),
        ),
        id="tabs"
    ),
)

# =============== SERVER ===============
def server(input, output, session):

    # --- Athlètes (id <-> nom)
    athletes_df = fetch_athletes()
    name_to_id = {r["name"]: r["athlete_id"] for _, r in athletes_df.iterrows()}
    id_to_name = {r["athlete_id"]: r["name"] for _, r in athletes_df.iterrows()}
    ui.update_select("athlete", choices=athletes_df["name"].tolist(),
                     selected=(athletes_df["name"].iloc[0] if not athletes_df.empty else None))

    # --- Réactifs
    meta_df_all = reactive.Value(pd.DataFrame())     # meta complètes (avant toggle VirtualRun)
    meta_df = reactive.Value(pd.DataFrame())         # meta filtrées sur période + athlète (+ toggle vrun)
    act_label_to_id = reactive.Value({})             # libellé -> activity_id (pour Run/TrailRun)
    id_to_info = reactive.Value({})                  # activity_id -> infos (type, date_str)
    
    # Calendar heatmap state
    current_calendar_year = reactive.Value(date.today().year)  # Current year for calendar display
    selected_calendar_date = reactive.Value(None)  # Selected date from calendar
    activities_by_date = reactive.Value({})  # date_str -> list of {activity_id, label} (filtered by date range)
    calendar_all_activities = reactive.Value({})  # date_str -> count (ALL data, independent of filters)

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

    # Calendar year navigation
    @reactive.Effect
    @reactive.event(input.prev_year)
    def _goto_prev_year():
        """Navigate to previous year."""
        current = current_calendar_year.get()
        current_calendar_year.set(current - 1)
    
    @reactive.Effect
    @reactive.event(input.next_year)
    def _goto_next_year():
        """Navigate to next year."""
        current = current_calendar_year.get()
        current_calendar_year.set(current + 1)

    @output
    @render.text
    def current_year_display():
        """Display current year."""
        return str(current_calendar_year.get())
    
    # Load ALL activities for calendar (independent of date filters)
    @reactive.Effect
    @reactive.event(input.athlete)
    @timing_decorator
    def _load_calendar_all_data():
        """Load ALL activities for selected athlete to show in calendar (no date filter)."""
        try:
            sel_name = input.athlete() or ""
            athlete_id = name_to_id.get(sel_name, sel_name)
            if not athlete_id:
                calendar_all_activities.set({})
                return
            
            # Fetch ALL activities for this athlete (no date filter)
            # Use activity_summary view for better performance (Phase 2)
            params = {
                "athlete_id": f"eq.{athlete_id}",
                "order": "date.desc",
            }
            cols = "date,duration_sec"
            df_all = supa_select("activity_summary", select=cols, params=params, limit=50000)
            
            if df_all.empty:
                calendar_all_activities.set({})
                return
            
            # Group by date and count activities
            by_date_count = {}
            for _, row in df_all.iterrows():
                date_str = str(row["date"])
                if date_str not in by_date_count:
                    by_date_count[date_str] = 0
                by_date_count[date_str] += 1
            
            calendar_all_activities.set(by_date_count)
        except Exception as e:
            print(f"Error loading calendar data: {e}")
            calendar_all_activities.set({})

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
            if "start_time" in dfr.columns:
                dfr = dfr.sort_values("start_time", ascending=False)  # Plus récent en premier
                dfr["date_str"] = pd.to_datetime(dfr["start_time"]).dt.date.astype(str)
                
                def make_label(row):
                    # Type de course en français
                    type_fr = type_labels.get(str(row["type"]).lower(), str(row["type"]))
                    
                    # Date en format français complet (ex: 2 juillet 2025)
                    date_obj = pd.to_datetime(row["start_time"])
                    mois_fr = ["janvier", "février", "mars", "avril", "mai", "juin", 
                               "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
                    date_str = f"{date_obj.day} {mois_fr[date_obj.month - 1]} {date_obj.year}"
                    
                    # Durée en format mm:ss ou h:mm:ss si > 60 minutes
                    duration_min = row.get("duration_min", 0)
                    
                    # Handle NaN or missing values
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
                    
                    # Distance en km
                    distance_km = row.get("distance_km", 0)
                    if pd.isna(distance_km):
                        dist_str = "0.00"
                    else:
                        dist_str = f"{distance_km:.2f}"
                    
                    # Check if activity has intervals
                    activity_id = str(row["activity_id"])
                    has_intervals = False
                    try:
                        # Quick check for intervals (lightweight query)
                        intervals_response = supabase.table("activity_intervals") \
                            .select("activity_id") \
                            .eq("activity_id", activity_id) \
                            .limit(1) \
                            .execute()
                        has_intervals = len(intervals_response.data) > 0
                    except:
                        pass  # If query fails, just don't add the tag
                    
                    # Build base label
                    base_label = f"{type_fr} - {date_str} - {time_str} - {dist_str} km"
                    
                    # Add intervals tag if applicable
                    if has_intervals:
                        return f"{base_label} (intervalles)"
                    else:
                        return base_label
                
                dfr["label"] = dfr.apply(make_label, axis=1)
                
                # Build activities_by_date for calendar heatmap
                by_date = {}
                for _, r in dfr.iterrows():
                    aid = str(r["activity_id"])
                    labels_map[r["label"]] = aid
                    info_map[aid] = {"type": str(r["type"]), "date_str": r["date_str"]}
                    
                    # Group by date for calendar
                    date_key = r["date_str"]
                    if date_key not in by_date:
                        by_date[date_key] = []
                    by_date[date_key].append({"activity_id": aid, "label": r["label"]})
                
                activities_by_date.set(by_date)
        
        act_label_to_id.set(labels_map)
        id_to_info.set(info_map)
        ui.update_select("activity_sel", choices=list(labels_map.keys()),
                         selected=(next(iter(labels_map)) if labels_map else None))

    # Rechargement des métadonnées quand athlète/période/toggle changent
    @reactive.Effect
    @reactive.event(input.athlete, input.date_start, input.date_end, input.incl_vrun)
    def _reload_meta():
        try:
            sel_name = input.athlete() or ""
            athlete_id = name_to_id.get(sel_name, sel_name)
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
    @render_plotly
    def run_duration_trend():
        """Temps de course moyen (7j vs 28j) pour Run/Trail/Tapis, basé sur la période sélectionnée."""
        df_all = meta_df_all.get().copy()
        
        def empty_fig(msg):
            fig = go.Figure()
            fig.add_annotation(text=msg, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                             font=dict(size=16, color="#666"))
            fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False), 
                            plot_bgcolor="white", height=360)
            return fig
        
        if df_all.empty:
            return empty_fig("Aucune activité")

        try:
            start_date = pd.to_datetime(input.date_start()).date()
            end_date = pd.to_datetime(input.date_end()).date()
        except Exception:
            return empty_fig("Sélectionnez une période valide")

        if start_date > end_date:
            start_date, end_date = end_date, start_date

        metric_mode = input.run_metric() or "time"
        type_series = df_all.get("type_lower")
        if type_series is None:
            type_series = df_all.get("type", pd.Series(dtype=str)).astype(str).str.lower()
        m_run = type_series.isin(RUN_TYPES)
        if not m_run.any():
            return empty_fig("Aucune sortie de course sur cette période")

        metric_col = "duration_min" if metric_mode == "time" else "distance_km"
        if metric_col not in df_all.columns:
            return empty_fig("Mesure indisponible pour ces activités")

        d_all = df_all.loc[m_run].dropna(subset=["date_local"])
        if d_all.empty:
            return empty_fig("Aucune donnée exploitable")

        daily = d_all.groupby("date_local", as_index=True)[metric_col].sum().astype(float)
        daily = daily.sort_index()
        full_index = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
        daily = daily.reindex(full_index, fill_value=0.0)
        daily.index = full_index

        daily_values = daily
        if metric_mode == "dist":
            y_label = "Kilomètres par jour"
            legend_ctl = "CTL 28 j (km)"
            legend_atl = "ATL 7 j (km)"
            legend_tsb = "TSB (km)"
        else:
            y_label = "Minutes par jour"
            legend_ctl = "CTL 28 j (min)"
            legend_atl = "ATL 7 j (min)"
            legend_tsb = "TSB (min)"

        if not np.isfinite(daily_values).any() or np.isclose(daily_values.sum(), 0.0):
            return empty_fig("Valeurs nulles sur cette période")

        ctl = daily_values.ewm(span=28, min_periods=28, adjust=False).mean()
        atl = daily_values.ewm(span=7, min_periods=7, adjust=False).mean()
        tsb = ctl - atl

        mask = ctl.notna()
        if not mask.any():
            return empty_fig("Historique insuffisant pour une moyenne 28 jours.<br>Élargissez la plage.")

        available_idx = ctl.index[mask]
        disp_start = max(start_date, available_idx.min().date())
        disp_end = min(end_date, available_idx.max().date())
        if disp_start > disp_end:
            return empty_fig("Aucune donnée dans la plage sélectionnée")
        display_mask = mask & (ctl.index.date >= disp_start) & (ctl.index.date <= disp_end)
        if not display_mask.any():
            return empty_fig("Aucune donnée dans la plage sélectionnée")

        idx = ctl.index[display_mask]
        ctl_vals = ctl.loc[display_mask]
        atl_vals = atl.loc[display_mask]
        tsb_vals = tsb.loc[display_mask]

        color28 = "#4ba3ff"
        color7 = "#8a58ff"
        color_tsb = "#2ecc71" if metric_mode != "dist" else "#e67e22"

        fig = go.Figure()
        
        # Fill area under CTL
        fig.add_trace(go.Scatter(
            x=idx, y=ctl_vals.values,
            fill='tozeroy',
            fillcolor=f'rgba(75, 163, 255, 0.22)',
            line=dict(color=color28, width=2.6),
            name=legend_ctl,
            mode='lines'
        ))
        
        # ATL line
        fig.add_trace(go.Scatter(
            x=idx, y=atl_vals.values,
            line=dict(color=color7, width=1.8),
            name=legend_atl,
            mode='lines'
        ))
        
        # TSB line (dotted)
        fig.add_trace(go.Scatter(
            x=idx, y=tsb_vals.values,
            line=dict(color=color_tsb, width=1.4, dash='dot'),
            name=legend_tsb,
            mode='lines'
        ))
        
        fig.update_layout(
            title="Moyenne pondérée exponentiellement — CTL / ATL / TSB",
            xaxis=dict(title="Date", showgrid=True, gridcolor='rgba(128, 128, 128, 0.2)'),
            yaxis=dict(title=y_label, showgrid=True, gridcolor='rgba(128, 128, 128, 0.2)'),
            plot_bgcolor='white',
            height=360,
            hovermode='x unified',
            legend=dict(x=0, y=1, bgcolor='rgba(255,255,255,0.8)'),
            margin=dict(l=60, r=30, t=60, b=60)
        )
        
        return fig

    @render_plotly
    def pie_types():
        df = meta_df.get()
        
        def empty_fig(msg):
            fig = go.Figure()
            fig.add_annotation(text=msg, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                             font=dict(size=16, color="#666"))
            fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False), 
                            plot_bgcolor="white", height=480)
            return fig
        
        if df.empty:
            return empty_fig("Aucune activité")

        # Grouper types → "Course" (Run+TrailRun), "Tapis", "Autre" et sommer les durées
        # Use pre-computed type_category field (Phase 1 optimization)
        if "type_category" in df.columns:
            g = df.assign(_grp=df["type_category"])
        else:
            # Fallback if type_category not available
            type_map = {"run": "Course", "trailrun": "Course", "virtualrun": "Tapis"}
            g = df.assign(_grp=df["type"].str.lower().map(type_map).fillna("Autre"))
        s = pd.to_numeric(g["duration_sec"], errors="coerce").fillna(0).groupby(g["_grp"]).sum().sort_values(ascending=False)
        if s.sum() <= 0:
            return empty_fig("Aucune durée disponible")

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
            title="Répartition du temps (période sélectionnée)",
            height=480,
            showlegend=True,
            legend=dict(orientation="v", x=1.0, y=0.5),
            margin=dict(l=20, r=20, t=60, b=20)
        )
        return fig


    @render_plotly
    def pace_hr_scatter():
        """
        Nuage de points : 1 point par activité (pas d'agrégation par bins)
        - X = allure moyenne par activité (sec/km → min/km)
        - Y = FC moyenne par activité (avg_hr)
        - Couleur = mois (YYYY-MM)
        Bornes:
        - X : 3:00 à 6:30 min/km (180s .. 390s)
        - Y : 90 à 200 bpm
        """
        df = meta_df.get().copy()
        
        def empty_fig(msg):
            fig = go.Figure()
            fig.add_annotation(text=msg, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                             font=dict(size=16, color="#666"))
            fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False), 
                            plot_bgcolor="white", height=480)
            return fig
        
        if df.empty:
            return empty_fig("Aucune activité")

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
            return empty_fig("Aucune donnée exploitable (pace/FC)")

        # Allure moyenne par activité (sec/km)
        d["pace_skm"] = d["dur_s"] / d["dist_km"]

        # Mois (YYYY-MM) pour la couleur
        d["month"] = d["start_time_naive"].dt.to_period("M").astype(str)

        # Filtrer plage d'allures demandée : 3:00..6:30 min/km (180..390 s/km)
        d = d[(d["pace_skm"] >= 180) & (d["pace_skm"] <= 390)].copy()

        if d.empty:
            return empty_fig("Aucun point dans la plage d'allure 3:00–6:30")

        # Helper for formatting pace
        def format_pace(sec_per_km):
            mins = int(sec_per_km // 60)
            secs = int(sec_per_km % 60)
            return f"{mins}:{secs:02d}"

        # Scatter : un nuage par mois pour une légende claire
        months = sorted(d["month"].unique())
        colors_tab20 = ['#1f77b4', '#aec7e8', '#ff7f0e', '#ffbb78', '#2ca02c', '#98df8a',
                        '#d62728', '#ff9896', '#9467bd', '#c5b0d5', '#8c564b', '#c49c94',
                        '#e377c2', '#f7b6d2', '#7f7f7f', '#c7c7c7', '#bcbd22', '#dbdb8d',
                        '#17becf', '#9edae5']
        
        fig = go.Figure()
        
        for i, m in enumerate(months):
            gd = d[d["month"] == m]
            color = colors_tab20[i % len(colors_tab20)]
            
            # Scatter points
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
                gdl = gdl[(gdl["bin"] >= 180) & (gdl["bin"] <= 390)]
                if not gdl.empty:
                    b = gdl.groupby("bin", as_index=False)["avg_hr"].mean().sort_values("bin")
                    b["avg_hr"] = b["avg_hr"].rolling(3, center=True, min_periods=1).mean()
                    fig.add_trace(go.Scatter(
                        x=b["bin"].values,
                        y=b["avg_hr"].values,
                        mode='lines',
                        line=dict(color=color, width=2),
                        showlegend=False,
                        hoverinfo='skip'
                    ))

        # Format X axis ticks (3:00 to 6:30 = 180 to 390 seconds/km)
        tick_vals = [180, 195, 210, 225, 240, 255, 270, 285, 300, 315, 330, 345, 360, 375, 390]
        tick_text = [format_pace(v) for v in tick_vals]
        
        fig.update_layout(
            xaxis=dict(
                title="Allure (min/km)",
                range=[180, 390],
                tickmode='array',
                tickvals=tick_vals,
                ticktext=tick_text,
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)'
            ),
            yaxis=dict(
                title="Fréquence cardiaque (bpm)",
                range=[90, 200],
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)'
            ),
            plot_bgcolor='white',
            height=480,
            hovermode='closest',
            legend=dict(title="Mois", orientation="v", x=1.0, y=0.5),
            margin=dict(l=60, r=100, t=40, b=60)
        )
        return fig

    @render_plotly
    def weekly_volume():
        """Aires empilées hebdomadaires en kilomètres, séparées par type (Run, TrailRun, VirtualRun).
        Semaine calée sur LUNDI dans le fuseau LOCAL_TZ et index complet basé sur un calendrier (sans trous).
        """
        df = meta_df.get()
        
        def empty_fig(msg):
            fig = go.Figure()
            fig.add_annotation(text=msg, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                             font=dict(size=16, color="#666"))
            fig.update_layout(xaxis=dict(visible=False), yaxis=dict(visible=False), 
                            plot_bgcolor="white", height=480)
            return fig
        
        if df.empty:
            return empty_fig("Aucune activité")

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
            return empty_fig("Aucune donnée de course")

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

        weeks = pivot.index
        if len(weeks) == 0:
            return empty_fig("Aucune semaine disponible")

        # Create stacked area chart
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=weeks, y=pivot["Run"].values,
            name="Run",
            mode='lines',
            stackgroup='one',
            fillcolor=COLORS.get("Run"),
            line=dict(width=0.5, color=COLORS.get("Run")),
            hovertemplate='<b>Run</b><br>%{y:.1f} km<extra></extra>'
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
            x=weeks, y=pivot["VirtualRun"].values,
            name="Tapis",
            mode='lines',
            stackgroup='one',
            fillcolor=COLORS.get("VirtualRun"),
            line=dict(width=0.5, color=COLORS.get("VirtualRun")),
            hovertemplate='<b>Tapis</b><br>%{y:.1f} km<extra></extra>'
        ))
        
        fig.update_layout(
            title="Volume hebdomadaire par type (km)",
            xaxis=dict(
                title="",
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)'
            ),
            yaxis=dict(
                title="Distance hebdomadaire (km)",
                showgrid=True,
                gridcolor='rgba(128, 128, 128, 0.2)',
                rangemode='tozero'
            ),
            plot_bgcolor='white',
            height=480,
            hovermode='x unified',
            legend=dict(x=0, y=1, bgcolor='rgba(255,255,255,0.8)'),
            margin=dict(l=60, r=30, t=60, b=60)
        )
        return fig
    
    # ----------------- Year Calendar Heatmap for Activity Selection (GitHub-style) -----------------
    @render_plotly
    def year_calendar_heatmap():
        """Render full-year calendar heatmap (GitHub-style) showing ALL activities independent of date filters."""
        import calendar as cal_module
        from datetime import timedelta
        
        current_year = current_calendar_year.get()
        by_date_count = calendar_all_activities.get()  # Use ALL data, not filtered
        
        # Start from Jan 1 of current year
        start_date = date(current_year, 1, 1)
        # Find the Monday before or on Jan 1
        days_to_monday = (start_date.weekday()) % 7
        start_monday = start_date - timedelta(days=days_to_monday)
        
        # End on Dec 31
        end_date = date(current_year, 12, 31)
        # Find the Sunday after or on Dec 31
        days_to_sunday = (6 - end_date.weekday()) % 7
        end_sunday = end_date + timedelta(days=days_to_sunday)
        
        # Build data structure: weeks (rows) x days (columns)
        # Each week is a row with 7 days (Mon-Sun)
        weeks_data = []
        current_date = start_monday
        
        while current_date <= end_sunday:
            week = []
            for _ in range(7):  # Mon to Sun
                date_str = current_date.isoformat()
                
                # Get activity count from ALL data (independent of date filters)
                intensity = by_date_count.get(date_str, 0)
                
                # Only show if within current year
                if current_date.year == current_year:
                    week.append({
                        "date": current_date,
                        "date_str": date_str,
                        "intensity": intensity,
                        "in_year": True
                    })
                else:
                    week.append({
                        "date": current_date,
                        "date_str": date_str,
                        "intensity": 0,
                        "in_year": False
                    })
                
                current_date += timedelta(days=1)
            
            weeks_data.append(week)
        
        # Transpose: we want days of week as rows, weeks as columns (for horizontal display)
        # Row 0 = all Mondays, Row 1 = all Tuesdays, etc.
        day_rows = [[] for _ in range(7)]
        for week in weeks_data:
            for day_idx, day_data in enumerate(week):
                day_rows[day_idx].append(day_data)
        
        # Build heatmap data
        z_values = []
        hover_text = []
        customdata = []
        text_annotations = []  # Day numbers to display on cells
        
        mois_fr = ["Jan", "Fév", "Mar", "Avr", "Mai", "Jun", 
                   "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc"]
        
        for day_row in day_rows:
            z_row = []
            hover_row = []
            custom_row = []
            text_row = []
            for day_data in day_row:
                if not day_data["in_year"]:
                    # Outside current year - empty cell
                    z_row.append(None)
                    hover_row.append("")
                    custom_row.append(None)
                    text_row.append("")
                elif day_data["intensity"] == 0:
                    # No activities - show day number
                    z_row.append(0)
                    hover_row.append(f"{day_data['date'].day} {mois_fr[day_data['date'].month-1]}")
                    custom_row.append(day_data["date_str"])
                    text_row.append(str(day_data["date"].day))
                else:
                    # Has activities - show day number
                    z_row.append(day_data["intensity"])
                    hover_row.append(f"{day_data['date'].day} {mois_fr[day_data['date'].month-1]}<br>{day_data['intensity']} activité(s)")
                    custom_row.append(day_data["date_str"])
                    text_row.append(str(day_data["date"].day))
            
            z_values.append(z_row)
            hover_text.append(hover_row)
            customdata.append(custom_row)
            text_annotations.append(text_row)
        
        # Create heatmap
        # Calculate max intensity (filter out None values)
        max_intensity = 3  # Default
        all_intensities = []
        for row in z_values:
            all_intensities.extend([val for val in row if val is not None])
        if all_intensities:
            max_intensity = max(max_intensity, max(all_intensities))
        
        # Red color gradient using #D91E2E
        # Lighter = fewer activities, Darker = more activities
        fig = go.Figure(data=go.Heatmap(
            z=z_values,
            text=text_annotations,  # Day numbers displayed on cells
            texttemplate='%{text}',  # Show the day number
            textfont=dict(
                size=8,
                color='rgba(80, 80, 80, 0.6)'  # Dark gray text for visibility on red
            ),
            hovertext=hover_text,  # Separate hover text with more info
            hovertemplate='%{hovertext}<extra></extra>',
            colorscale=[
                [0, '#fef2f2'],      # Very light red/pink (no activity)
                [0.25, '#fecaca'],   # Light red (1 activity)
                [0.5, '#f87171'],    # Medium red (2 activities)
                [0.75, '#dc2626'],   # Dark red (3+ activities)
                [1, '#D91E2E']       # Darkest red (many activities) - your color!
            ],
            showscale=False,
            xgap=2,
            ygap=2,
            customdata=customdata,
            zmin=0,
            zmax=max_intensity
        ))
        
        # Month labels at top
        month_positions = []
        month_labels = []
        for month_num in range(1, 13):
            # Find first occurrence of this month
            first_week_idx = None
            for week_idx, week in enumerate(weeks_data):
                if any(d["date"].month == month_num and d["in_year"] for d in week):
                    first_week_idx = week_idx
                    break
            if first_week_idx is not None:
                month_positions.append(first_week_idx)
                month_labels.append(mois_fr[month_num - 1])
        
        # Update layout - compact for top bar visualization
        fig.update_layout(
            xaxis=dict(
                ticktext=month_labels,
                tickvals=month_positions,
                tickangle=0,
                side='top',
                showgrid=False,
                tickfont=dict(size=10)
            ),
            yaxis=dict(
                ticktext=['L', 'M', 'M', 'J', 'V', 'S', 'D'],  # Mon to Sun (top to bottom)
                tickvals=[0, 1, 2, 3, 4, 5, 6],
                showgrid=False,
                fixedrange=True,
                tickfont=dict(size=9),
                autorange='reversed'  # Reverse to show index 0 (Monday) at top
            ),
            height=160,  # Compact height for top bar
            margin=dict(l=25, r=15, t=30, b=15),
            plot_bgcolor='white',
            paper_bgcolor='white',
            dragmode=False,  # No interaction needed
            hovermode='closest'
        )
        
        # Configure hover and text display
        fig.update_traces(
            hoverlabel=dict(bgcolor="white", font_size=11),
        )
        
        return fig

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
        
        df = fetch_timeseries_cached(str(act_id))
        if df.empty:
            return
        
        # Base choices always available
        choices = {
            "Fréquence cardiaque (bpm)": "Fréquence cardiaque",
            "Cadence (spm)": "Cadence",
            "Allure (min/km)": "Allure (min/km)"
        }
        
        # Add power if data exists
        if "watts" in df.columns and df["watts"].notna().any():
            choices["Puissance (W)"] = "Puissance (W)"
        
        # Add vertical oscillation if data exists
        if "vertical_oscillation" in df.columns and df["vertical_oscillation"].notna().any():
            choices["Oscillation Verticale (mm)"] = "Oscillation Verticale"
        
        # Update the select input
        current_selection = input.yvar()
        ui.update_select("yvar", choices=choices, selected=current_selection if current_selection in choices.values() else "heartrate")

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

    @render_plotly
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
            return fig

        # Get info for title
        info = (id_to_info.get() or {}).get(d["act_id"], {})
        ttype = info.get("type"); dstr = info.get("date_str")
        title = d["y_label"]
        if ttype and dstr:
            title += f" — {ttype} — {dstr}"
        
        # Format x-axis values if needed (for time)
        x_values = d["x"]
        x_is_time = d["x_fmt"] is not None
        
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
        
        # Format y-axis values if needed (for pace)
        y_values = d["y"]
        y_is_time = d["y_fmt"] is not None
        
        if y_is_time:
            y_hover = [format_time(val) for val in y_values]
        else:
            y_hover = y_values
        
        # Create the figure
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=x_values,
            y=y_values,
            mode='lines',
            line=dict(color='#1f77b4', width=2),
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
            zeroline=False
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
            
            # Generate tick values
            tick_vals = np.arange(0, x_max + tick_interval, tick_interval)
            tick_vals = tick_vals[tick_vals <= x_max]
            
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
        
        # Update layout
        fig.update_layout(
            title=dict(
                text=title,
                font=dict(size=18, color='#262626')
            ),
            xaxis=xaxis_config,
            yaxis=yaxis_config,
            plot_bgcolor='white',
            height=560,
            hovermode='closest',
            margin=dict(l=60, r=30, t=80, b=60)
        )
        
        return fig

    # Met à jour dynamiquement les bornes MIN/MAX des dates selon l’athlète et le toggle VirtualRun
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

    # ----------------- Phase 1.5: Intervals Visualization -----------------
    
    @render_plotly
    def interval_enhanced_plot():
        """Render activity graph with interval markers."""
        activity_id = input.activity_sel()
        x_axis = input.interval_x_axis()
        y_axis = input.interval_y_axis()
        
        if not activity_id:
            return go.Figure().update_layout(
                title="Sélectionnez une activité pour voir les intervalles",
                height=500
            )
        
        # Get activity timeseries (reuse existing logic)
        try:
            activity_df = fetch_timeseries_cached(activity_id)
        except:
            return go.Figure().update_layout(
                title="Erreur lors du chargement des données d'activité",
                height=500
            )
        
        if activity_df.empty:
            return go.Figure().update_layout(
                title="Aucune donnée trouvée pour cette activité",
                height=500
            )
        
        # Get intervals
        intervals_df = get_activity_intervals(activity_id)
        
        # Create base plot
        fig = go.Figure()
        
        # Prepare X and Y data
        if x_axis == "t_active_sec":
            x_data = activity_df["t_active_sec"] if "t_active_sec" in activity_df.columns else activity_df["time"]
            x_title = "Temps en mouvement (s)"
        else:  # distance_m
            if "distance_m" in activity_df.columns:
                x_data = activity_df["distance_m"] / 1000  # Convert to km
            else:
                # Calculate cumulative distance from speed
                if "enhanced_speed" in activity_df.columns:
                    speed = activity_df["enhanced_speed"].fillna(0)
                    time_diff = activity_df["time"].diff().fillna(0)
                    distance_m = (speed * time_diff).cumsum()
                    x_data = distance_m / 1000
                else:
                    x_data = activity_df["time"]  # Fallback
            x_title = "Distance (km)"
        
        # Prepare Y data
        if y_axis == "pace":
            # Calculate pace from speed
            if "enhanced_speed" in activity_df.columns:
                speed_ms = activity_df["enhanced_speed"].replace(0, np.nan)
                pace_minkm = (1000 / 60) / speed_ms  # Convert m/s to min/km
                y_data = pace_minkm * 60  # Convert to seconds/km for consistent axis
                y_title = "Allure (s/km)"
            else:
                y_data = activity_df.get("heartrate", [])
                y_title = "Fréquence cardiaque (bpm)"
        else:
            y_data = activity_df.get(y_axis, [])
            y_title = {
                "heartrate": "Fréquence cardiaque (bpm)",
                "cadence": "Cadence (spm)",
                "watts": "Puissance (W)",
                "vertical_oscillation": "Oscillation verticale (mm)"
            }.get(y_axis, y_axis)
        
        # Add main activity line
        fig.add_trace(go.Scatter(
            x=x_data,
            y=y_data,
            mode='lines',
            name='Activité',
            line=dict(color='#1f77b4', width=2),
            hovertemplate=f'<b>%{{fullData.name}}</b><br>{x_title}: %{{x}}<br>{y_title}: %{{y}}<extra></extra>'
        ))
        
        # Add interval markers if available
        if not intervals_df.empty:
            intervals_df = classify_intervals(intervals_df)
            
            # Color mapping for intervals
            colors = {
                'work': ('rgba(217, 30, 46, 0.15)', 'rgba(217, 30, 46, 0.4)'),
                'rest': ('rgba(30, 144, 255, 0.15)', 'rgba(30, 144, 255, 0.4)'),
                'warmup': ('rgba(128, 128, 128, 0.15)', 'rgba(128, 128, 128, 0.4)'),
                'cooldown': ('rgba(128, 128, 128, 0.15)', 'rgba(128, 128, 128, 0.4)')
            }
            
            work_count = 0
            for idx, interval in intervals_df.iterrows():
                interval_type = interval.get('interval_type', 'unknown')
                fill_color, border_color = colors.get(interval_type, ('rgba(200,200,200,0.15)', 'rgba(200,200,200,0.4)'))
                
                # Get X positions based on t_active fields
                if x_axis == "t_active_sec":
                    x0 = interval.get('start_t_active', 0)
                    x1 = interval.get('end_t_active', 0)
                else:  # distance - need to calculate from time
                    start_time = interval.get('start_time', 0)
                    end_time = interval.get('end_time', 0)
                    
                    # Find closest time points in activity data
                    if len(activity_df) > 0 and "time" in activity_df.columns:
                        start_idx = (activity_df["time"] - start_time).abs().idxmin()
                        end_idx = (activity_df["time"] - end_time).abs().idxmin()
                        x0 = x_data.iloc[start_idx] if start_idx < len(x_data) else 0
                        x1 = x_data.iloc[end_idx] if end_idx < len(x_data) else 0
                    else:
                        x0, x1 = 0, 0
                
                # Label for interval
                if interval_type == 'work':
                    work_count += 1
                    label = f"Int {work_count}"
                elif interval_type == 'rest':
                    label = "R"
                else:
                    label = interval_type[:1].upper()
                
                # Add shaded region
                if x1 > x0:  # Only add if we have valid positions
                    fig.add_vrect(
                        x0=x0,
                        x1=x1,
                        fillcolor=fill_color,
                        line=dict(color=border_color, width=1, dash='dot'),
                        layer="below",
                        annotation_text=label,
                        annotation_position="top",
                        annotation_font_size=10,
                        annotation_font_color="rgba(0,0,0,0.7)"
                    )
        
        # Update layout
        fig.update_layout(
            title="Activité avec intervalles",
            xaxis_title=x_title,
            yaxis_title=y_title,
            height=500,
            hovermode='x unified',
            showlegend=True
        )
        
        # Special handling for pace axis (invert)
        if y_axis == "pace":
            fig.update_yaxis(autorange="reversed")
        
        return fig
    
    @render.ui
    def intervals_summary():
        """Render intervals summary table."""
        activity_id = input.activity_sel()
        
        if not activity_id:
            return ui.div()
        
        intervals_df = get_activity_intervals(activity_id)
        
        if intervals_df.empty:
            return ui.div(
                ui.p("ℹ️ Aucun intervalle détecté pour cette activité.", 
                     class_="text-muted mt-3")
            )
        
        intervals_df = classify_intervals(intervals_df)
        
        # Build table HTML
        table_html = """
        <div class="table-responsive mt-3">
            <table class="table table-sm table-hover">
                <thead class="table-light">
                    <tr>
                        <th>#</th>
                        <th>Type</th>
                        <th>Durée</th>
                        <th>Distance</th>
                        <th>Allure</th>
                        <th>FC moy</th>
                        <th>Watts</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        work_count = 0
        for idx, row in intervals_df.iterrows():
            itype = row['interval_type']
            
            # Row styling
            if itype == 'work':
                work_count += 1
                row_class = "table-danger"
                num = str(work_count)
            elif itype == 'rest':
                row_class = "table-info"
                num = "R"
            elif itype in ['warmup', 'cooldown']:
                row_class = "table-secondary"
                num = itype[0].upper()
            else:
                row_class = ""
                num = str(idx + 1)
            
            hr = int(row['average_heartrate']) if pd.notna(row.get('average_heartrate')) else "-"
            watts = int(row['average_watts']) if pd.notna(row.get('average_watts')) else "-"
            
            table_html += f"""
            <tr class="{row_class}">
                <td><strong>{num}</strong></td>
                <td>{itype.title()}</td>
                <td>{row['duration_fmt']}</td>
                <td>{row['distance_fmt']}</td>
                <td>{row['pace_fmt']}</td>
                <td>{hr}</td>
                <td>{watts}</td>
            </tr>
            """
        
        table_html += """
                </tbody>
            </table>
        </div>
        """
        
        # Pattern detection
        pattern = detect_workout_pattern(intervals_df)
        if pattern:
            table_html += f"""
            <div class="alert alert-info mt-2">
                💡 <strong>Détecté:</strong> {pattern}
            </div>
            """
        
        return ui.HTML(table_html)

app = App(app_ui, server)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
