"""
Hybrid activity ingestion from Intervals.icu to Supabase.

Strategy: Prioritize FIT files (complete data + Stryd metrics),
fallback to Streams API if FIT unavailable.

Usage:
    # Import activities for a date range
    python intervals_hybrid_to_supabase.py --oldest 2024-01-01 --newest 2024-12-31

    # Import for specific athlete only
    python intervals_hybrid_to_supabase.py --athlete "Matthew Beaudet" --oldest 2024-01-01 --newest 2024-12-31

    # Dry-run mode (no actual inserts)
    python intervals_hybrid_to_supabase.py --oldest 2024-01-01 --newest 2024-12-31 --dry-run

    # BULK IMPORT: Parallel import with wellness, skip weather (12-15 athletes safe)
    python intervals_hybrid_to_supabase.py --athlete "Matthew Beaudet" --oldest 2021-01-01 --newest 2024-12-31 --wellness-oldest 2021-01-01 --wellness-newest 2024-12-31 --skip-weather &
    python intervals_hybrid_to_supabase.py --athlete "Kevin Robertson" --oldest 2021-01-01 --newest 2024-12-31 --wellness-oldest 2021-01-01 --wellness-newest 2024-12-31 --skip-weather &
    # ... repeat for all athletes (up to 12-15 parallel processes)
    wait  # Wait for all to complete

    # Weather backfill only (check forecast → archive updates)
    python intervals_hybrid_to_supabase.py --backfill-only

Features:
- Duplicate prevention: Skips already-imported activities
- Batch retry: Exponential backoff for failed inserts
- Weather cascade: Archive → Forecast → NULL (never blocks)
- HR fallback: Metadata → Streams → Calculate from records
- Wellness UPSERT: Safe to run multiple times
- Skip weather: --skip-weather flag for bulk import (no API rate limits)
"""

import os
import sys
import json
import argparse
import time
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth
from fitparse import FitFile
import io
from typing import List, Dict, Optional, Tuple
import pandas as pd

# Import algorithme temps actif (Strava-like)
from moving_time import compute_moving_time_strava

load_dotenv(".env", override=True)


def compute_t_active_for_records(records: List[Dict], activity_type: str = "run") -> List[Dict]:
    """
    Calcule t_active_sec pour une liste de records via algorithme Strava.

    Args:
        records: Liste de dicts avec clés: ts_offset_ms, enhanced_speed/velocity_smooth, etc.
        activity_type: Type d'activité (run, cycling, etc.)

    Returns:
        Liste de records enrichie avec t_active_sec (temps cumulé)
    """
    if not records:
        return records

    # Convertir en DataFrame temporaire
    df = pd.DataFrame(records)

    # Calculer t_active_sec via algorithme Strava
    try:
        t_active = compute_moving_time_strava(df, activity_type=activity_type)

        # Ajouter à chaque record
        for i, rec in enumerate(records):
            rec['t_active_sec'] = float(t_active.iloc[i]) if i < len(t_active) else 0.0
    except Exception:
        # Fallback : marquer tout comme actif
        for rec in records:
            rec['t_active_sec'] = 0.0

    return records


# Configuration
BASE_URL = "https://intervals.icu/api/v1"
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
BATCH_SIZE = 500

# Weather API timeouts
OM_TIMEOUT = float(os.environ.get("OM_TIMEOUT", "10"))
AQ_TIMEOUT = float(os.environ.get("AQ_TIMEOUT", "10"))
ELEV_TIMEOUT = float(os.environ.get("ELEV_TIMEOUT", "8"))

# Couleurs
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

# Statistiques globales (Phase 1 Enhanced)
stats = {
    # Existing
    'athletes_processed': 0,
    'activities_found': 0,
    'activities_processed': 0,
    'fit_success': 0,
    'fit_failed': 0,
    'stream_fallback': 0,
    'records_inserted': 0,
    'metadata_inserted': 0,
    'intervals_inserted': 0,

    # NEW: Data completeness tracking
    'outdoor_activities': 0,  # Activities with GPS
    'weather_complete': 0,    # Weather data present
    'weather_from_archive': 0,
    'weather_from_forecast': 0,
    'weather_missing': 0,     # No weather after all retries

    'hr_monitor_used': 0,     # Activities with HR records
    'hr_complete': 0,         # avg_hr present
    'hr_missing': 0,          # No avg_hr despite HR monitor

    # NEW: Retry tracking
    'retries': {
        'weather_archive': 0,
        'weather_forecast': 0,
    },

    # NEW: Bulk import tracking (Phase 2 Pre-Import Audit)
    'activities_skipped': 0,      # Already imported (duplicate prevention)
    'batch_failures': 0,          # Failed record batch inserts
    'wellness_days_imported': 0,  # Days of wellness data imported

    # Enhanced error tracking
    'errors': [],  # List of error messages
    'error_details': []  # List of dicts with full context
}

def log(msg: str, level: str = "INFO"):
    """Logger avec couleurs"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    if level == "ERROR":
        print(f"{Colors.RED}[{timestamp}] {msg}{Colors.END}")
    elif level == "SUCCESS":
        print(f"{Colors.GREEN}[{timestamp}] {msg}{Colors.END}")
    elif level == "WARNING":
        print(f"{Colors.YELLOW}[{timestamp}] {msg}{Colors.END}")
    else:
        print(f"[{timestamp}] {msg}")

# Weather API Functions

def _nearest_from_hourly(payload: dict, target_iso: str, keys: list) -> dict:
    """Select nearest hourly value to target timestamp"""
    out = {k: None for k in keys}
    hourly = (payload or {}).get("hourly", {})
    times = hourly.get("time", [])
    if not times:
        return out
    
    try:
        from datetime import datetime as dt
        ts = [dt.fromisoformat(t.replace('Z', '+00:00')) for t in times]
        tgt = dt.fromisoformat(target_iso.replace('Z', '+00:00'))

        diffs = [abs((t - tgt).total_seconds()) for t in ts]
        idx = diffs.index(min(diffs))
        
        for k in keys:
            arr = hourly.get(k)
            if arr and len(arr) > idx:
                try:
                    out[k] = float(arr[idx]) if arr[idx] is not None else None
                except:
                    out[k] = None
    except:
        pass
    
    return out

def fetch_weather_data(lat: float, lng: float, start_time: str) -> dict:
    """Fetch weather data from Open-Meteo"""
    if not lat or not lng or not start_time:
        return {}
    
    weather_keys = [
        "temperature_2m", "relative_humidity_2m", "dew_point_2m",
        "wind_speed_10m", "wind_gusts_10m", "wind_direction_10m",
        "pressure_msl", "cloudcover", "precipitation",
    ]
    
    params = {
        "latitude": float(lat),
        "longitude": float(lng),
        "hourly": ",".join(weather_keys),
        "past_days": 7,
        "timezone": "auto",
        "timeformat": "iso8601",
        "temperature_unit": "celsius",
        "windspeed_unit": "ms",
    }
    
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params=params,
            timeout=OM_TIMEOUT
        )
        response.raise_for_status()
        return _nearest_from_hourly(response.json(), start_time, weather_keys)
    except:
        return {}

def fetch_air_quality_data(lat: float, lng: float, start_time: str) -> dict:
    """Fetch air quality data from Open-Meteo"""
    if not lat or not lng or not start_time:
        return {}
    
    air_keys = [
        "pm2_5", "pm10", "ozone", "nitrogen_dioxide",
        "sulphur_dioxide", "carbon_monoxide", "us_aqi"
    ]
    
    params = {
        "latitude": float(lat),
        "longitude": float(lng),
        "hourly": ",".join(air_keys),
        "past_days": 7,
        "timezone": "auto",
        "timeformat": "iso8601",
    }
    
    try:
        response = requests.get(
            "https://air-quality-api.open-meteo.com/v1/air-quality",
            params=params,
            timeout=AQ_TIMEOUT
        )
        response.raise_for_status()
        return _nearest_from_hourly(response.json(), start_time, air_keys)
    except:
        return {}

def fetch_weather_archive(lat: float, lng: float, start_time: str) -> dict:
    """Fetch archived weather data from Open-Meteo (for older activities)"""
    if not lat or not lng or not start_time:
        return {}
    
    weather_keys = [
        "temperature_2m", "relative_humidity_2m", "dew_point_2m",
        "wind_speed_10m", "wind_gusts_10m", "wind_direction_10m",
        "pressure_msl", "cloudcover", "precipitation",
    ]
    
    try:
        # Extract date from ISO timestamp
        from datetime import datetime as dt
        activity_date = dt.fromisoformat(start_time.replace('Z', '+00:00')).date()
        
        params = {
            "latitude": float(lat),
            "longitude": float(lng),
            "hourly": ",".join(weather_keys),
            "start_date": activity_date.isoformat(),
            "end_date": activity_date.isoformat(),
            "timezone": "auto",
            "timeformat": "iso8601",
            "temperature_unit": "celsius",
            "windspeed_unit": "ms",
        }
        
        response = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params=params,
            timeout=OM_TIMEOUT
        )
        response.raise_for_status()
        return _nearest_from_hourly(response.json(), start_time, weather_keys)
    except:
        return {}

def fetch_air_quality_archive(lat: float, lng: float, start_time: str) -> dict:
    """Fetch archived air quality data from Open-Meteo (for older activities)"""
    if not lat or not lng or not start_time:
        return {}
    
    air_keys = [
        "pm2_5", "pm10", "ozone", "nitrogen_dioxide",
        "sulphur_dioxide", "carbon_monoxide", "us_aqi"
    ]
    
    try:
        from datetime import datetime as dt
        activity_date = dt.fromisoformat(start_time.replace('Z', '+00:00')).date()
        
        params = {
            "latitude": float(lat),
            "longitude": float(lng),
            "hourly": ",".join(air_keys),
            "start_date": activity_date.isoformat(),
            "end_date": activity_date.isoformat(),
            "timezone": "auto",
            "timeformat": "iso8601",
        }
        
        response = requests.get(
            "https://air-quality-api.open-meteo.com/v1/air-quality",
            params=params,
            timeout=AQ_TIMEOUT
        )
        response.raise_for_status()
        return _nearest_from_hourly(response.json(), start_time, air_keys)
    except:
        return {}

def fetch_elevation(lat: float, lng: float) -> Optional[float]:
    """Fetch elevation from Open-Elevation API"""
    if not lat or not lng:
        return None
    
    try:
        response = requests.get(
            "https://api.open-elevation.com/api/v1/lookup",
            params={"locations": f"{lat},{lng}"},
            timeout=ELEV_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        if results:
            return float(results[0].get("elevation"))
    except:
        pass
    
    return None

# PHASE 1: Weather Retry Cascade (Best Effort)

def fetch_weather_archive_with_retry(lat: float, lng: float, start_time: str) -> Tuple[dict, Optional[str]]:
    """
    Fetch weather archive with detailed error handling.
    
    Returns:
        (weather_data, error_message)
    """
    if not lat or not lng or not start_time:
        return {}, "Missing coordinates or time"
    
    weather_keys = [
        "temperature_2m", "relative_humidity_2m", "dew_point_2m",
        "wind_speed_10m", "wind_gusts_10m", "wind_direction_10m",
        "pressure_msl", "cloudcover", "precipitation",
    ]
    
    try:
        # Extract date from ISO timestamp
        from datetime import datetime as dt
        activity_date = dt.fromisoformat(start_time.replace('Z', '+00:00')).date()
        
        params = {
            "latitude": float(lat),
            "longitude": float(lng),
            "hourly": ",".join(weather_keys),
            "start_date": activity_date.isoformat(),
            "end_date": activity_date.isoformat(),
            "timezone": "auto",
            "timeformat": "iso8601",
            "temperature_unit": "celsius",
            "windspeed_unit": "ms",
        }
        
        response = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params=params,
            timeout=OM_TIMEOUT
        )
        response.raise_for_status()
        data = _nearest_from_hourly(response.json(), start_time, weather_keys)
        
        # Validate we got at least temperature
        if data.get('temperature_2m') is None:
            return {}, "No temperature data in API response"
        
        return data, None
        
    except requests.exceptions.Timeout:
        return {}, "Timeout"
    except requests.exceptions.HTTPError as e:
        return {}, f"HTTP {e.response.status_code}"
    except Exception as e:
        return {}, f"{type(e).__name__}: {str(e)}"


def fetch_weather_forecast_with_retry(lat: float, lng: float, start_time: str) -> Tuple[dict, Optional[str]]:
    """
    Fetch weather forecast as fallback.
    
    NOTE: Forecast API may NOT work for dates in the past.
    This is a best-effort fallback.
    
    Returns:
        (weather_data, error_message)
    """
    if not lat or not lng or not start_time:
        return {}, "Missing coordinates or time"
    
    weather_keys = [
        "temperature_2m", "relative_humidity_2m", "dew_point_2m",
        "wind_speed_10m", "wind_gusts_10m", "wind_direction_10m",
        "pressure_msl", "cloudcover", "precipitation",
    ]
    
    params = {
        "latitude": float(lat),
        "longitude": float(lng),
        "hourly": ",".join(weather_keys),
        "past_days": 7,
        "timezone": "auto",
        "timeformat": "iso8601",
        "temperature_unit": "celsius",
        "windspeed_unit": "ms",
    }
    
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params=params,
            timeout=OM_TIMEOUT
        )
        response.raise_for_status()
        data = _nearest_from_hourly(response.json(), start_time, weather_keys)
        
        if data.get('temperature_2m') is None:
            return {}, "No temperature data in forecast response"
        
        return data, None
        
    except requests.exceptions.Timeout:
        return {}, "Forecast timeout"
    except requests.exceptions.HTTPError as e:
        return {}, f"Forecast HTTP {e.response.status_code}"
    except Exception as e:
        return {}, f"Forecast error: {type(e).__name__}"


def get_weather_best_effort(lat: float, lng: float, start_time: str) -> Tuple[dict, Optional[str], Optional[str]]:
    """
    Try all methods to get weather, but NEVER block import.
    
    Returns:
        (weather_data, source, error_message)
        - weather_data: dict with weather keys, or {} if all failed
        - source: 'archive', 'forecast', or None
        - error_message: None if success, error description if failed
    """
    
    # Strategy 1: Archive (real historical data) - 3 attempts
    for attempt in range(3):
        weather, error = fetch_weather_archive_with_retry(lat, lng, start_time)
        if weather and weather.get('temperature_2m') is not None:
            return weather, 'archive', None
        if attempt < 2:
            time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s
    
    # Strategy 2: Forecast (estimation, may not work for old dates) - 3 attempts
    for attempt in range(3):
        weather, error = fetch_weather_forecast_with_retry(lat, lng, start_time)
        if weather and weather.get('temperature_2m') is not None:
            return weather, 'forecast', 'Archive unavailable, used forecast estimation'
        if attempt < 2:
            time.sleep(2 ** attempt)
    
    # Strategy 3: Complete failure - return empty BUT DON'T BLOCK
    final_error = f"All weather sources failed after 6 attempts. Last error: {error}"
    return {}, None, final_error


# WEATHER BACKFILL SYSTEM

def supa_select(table: str, select: str = "*", params: dict = None) -> pd.DataFrame:
    """
    Query Supabase table and return results as DataFrame.

    Args:
        table: Table name
        select: Columns to select (default: all)
        params: Query parameters (e.g., {"date": "gte.2024-11-01"})

    Returns:
        DataFrame with query results
    """
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}"

    # Add query parameters
    if params:
        for key, value in params.items():
            url += f"&{key}={value}"

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        return pd.DataFrame(data)
    except Exception as e:
        log(f"Query error: {e}", "ERROR")
        return pd.DataFrame()


def backfill_forecast_weather(days_back_min: int = 3, days_back_max: int = 7, dry_run: bool = False):
    """
    Update activities with forecast weather to archive weather.

    Open-Meteo archive data availability:
    - ECMWF IFS: 2 days delay
    - ERA5: 5 days delay

    We check 3-7 days back to ensure archive data is available while
    avoiding endless retries.

    Args:
        days_back_min: Start checking this many days back (default: 3)
        days_back_max: Stop checking after this many days back (default: 7)
        dry_run: If True, only report what would be updated
    """
    from datetime import datetime as dt, timedelta

    # Calculate date range
    today = dt.now().date()
    oldest_date = today - timedelta(days=days_back_max)
    newest_date = today - timedelta(days=days_back_min)

    log(f"\n{Colors.BOLD}{'='*70}")
    log(f"WEATHER BACKFILL: Checking {oldest_date} to {newest_date}")
    log(f"{'='*70}{Colors.END}")

    # Query activities with forecast weather in this range
    params = {
        "date": f"gte.{oldest_date}&date.lte.{newest_date}",
        "weather_source": "eq.forecast"
    }

    activities_to_update = supa_select(
        "activity_metadata",
        select="activity_id,athlete_id,date,start_lat,start_lon,start_time,weather_source",
        params=params
    )

    if activities_to_update.empty:
        log("  No activities with forecast weather found in window")
        return

    log(f"  Found {len(activities_to_update)} activities with forecast weather")

    updated_count = 0
    still_forecast = 0
    no_coords = 0

    for _, activity in activities_to_update.iterrows():
        activity_id = activity['activity_id']
        activity_date = activity['date']

        # Skip if no GPS coordinates
        if pd.isna(activity['start_lat']) or pd.isna(activity['start_lon']):
            log(f"  {activity_id} ({activity_date}): No GPS coordinates")
            no_coords += 1
            continue

        log(f"  Checking {activity_id} ({activity_date})...")

        # Try to fetch archive weather (should be available now)
        weather, weather_source, weather_error = get_weather_best_effort(
            activity['start_lat'],
            activity['start_lon'],
            activity['start_time']
        )

        # Check if we got archive data
        if weather_source == 'archive' and weather:
            log(f"    ✅ Archive weather now available!", "SUCCESS")

            if not dry_run:
                # Build update data with all weather fields
                update_data = {
                    'weather_source': 'archive'
                }

                # Add weather fields if available
                if weather.get('temperature_2m') is not None:
                    update_data['weather_temp_c'] = weather['temperature_2m']
                if weather.get('relative_humidity_2m') is not None:
                    update_data['weather_humidity_pct'] = int(weather['relative_humidity_2m'])
                if weather.get('dew_point_2m') is not None:
                    update_data['weather_dew_point_c'] = weather['dew_point_2m']
                if weather.get('wind_speed_10m') is not None:
                    update_data['weather_wind_speed_ms'] = weather['wind_speed_10m']
                if weather.get('wind_gusts_10m') is not None:
                    update_data['weather_wind_gust_ms'] = weather['wind_gusts_10m']
                if weather.get('wind_direction_10m') is not None:
                    update_data['weather_wind_dir_deg'] = int(weather['wind_direction_10m'])
                if weather.get('pressure_msl') is not None:
                    update_data['weather_pressure_hpa'] = weather['pressure_msl']
                if weather.get('cloudcover') is not None:
                    update_data['weather_cloudcover_pct'] = int(weather['cloudcover'])
                if weather.get('precipitation') is not None:
                    update_data['weather_precip_mm'] = weather['precipitation']

                # Use PATCH to update existing record
                update_url = f"{SUPABASE_URL}/rest/v1/activity_metadata?activity_id=eq.{activity_id}"
                headers = {
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json"
                }

                try:
                    response = requests.patch(update_url, headers=headers, json=update_data, timeout=30)
                    if response.status_code == 200:
                        log(f"    Updated forecast → archive", "SUCCESS")
                        updated_count += 1
                    else:
                        log(f"    Update failed: {response.status_code}", "ERROR")
                except Exception as e:
                    log(f"    Update error: {e}", "ERROR")
            else:
                log(f"    [DRY-RUN] Would update to archive")
                updated_count += 1

        elif weather_source == 'forecast':
            log(f"    ⏳ Still forecast (archive not ready yet)")
            still_forecast += 1
        else:
            log(f"    ⚠️  No weather available: {weather_error}", "WARNING")

    log(f"\n{Colors.BOLD}Backfill Summary:{Colors.END}")
    log(f"  Updated forecast → archive: {updated_count}")
    log(f"  Still using forecast: {still_forecast}")
    log(f"  No coordinates: {no_coords}")
    log("")


# PHASE 1: HR Fallback Enhancement

def get_avg_hr_with_fallback(activity_metadata: dict, streams_data: dict, records: List[dict]) -> Optional[int]:
    """
    Get avg_hr with complete fallback cascade.
    
    Priority:
    1. Intervals.icu activity metadata (most reliable)
    2. Streams API avg_hr field
    3. Calculate from records (heartrate values)
    
    Returns:
        avg_hr as int, or None if no HR data available
    """
    
    # Priority 1: Activity metadata
    if activity_metadata.get('avg_hr'):
        stats['hr_complete'] += 1
        return int(activity_metadata['avg_hr'])
    
    # Priority 2: Streams data
    if streams_data.get('avg_hr'):
        stats['hr_complete'] += 1
        return int(streams_data['avg_hr'])
    
    # Priority 3: Calculate from records
    hr_values = [rec.get('heartrate') for rec in records if rec.get('heartrate') is not None]
    if hr_values:
        calculated_avg = sum(hr_values) / len(hr_values)
        log(f"  ℹ️  avg_hr calculated from {len(hr_values)} records: {int(calculated_avg)} bpm")
        stats['hr_complete'] += 1
        return int(round(calculated_avg))
    
    # No HR data available anywhere
    stats['hr_missing'] += 1
    return None


# PHASE 1: Generic Retry Wrapper

def retry_with_exponential_backoff(
    func: callable,
    *args,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    **kwargs
) -> Tuple[any, Optional[str]]:
    """
    Generic retry wrapper with exponential backoff.
    
    Args:
        func: Function to retry
        max_retries: Number of attempts
        initial_delay: First retry delay (seconds)
        backoff_factor: Multiply delay by this each retry
        *args, **kwargs: Passed to func
    
    Returns:
        (result, error_message)
        - result: Function return value if success, None if all failed
        - error_message: None if success, error description if failed
    """
    last_error = None
    delay = initial_delay
    
    for attempt in range(max_retries):
        try:
            result = func(*args, **kwargs)
            return result, None  # Success
            
        except requests.exceptions.Timeout as e:
            last_error = f"Timeout (attempt {attempt + 1}/{max_retries})"
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= backoff_factor
                
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            if status == 429:  # Rate limit
                last_error = f"Rate limit (attempt {attempt + 1}/{max_retries})"
                if attempt < max_retries - 1:
                    time.sleep(5)  # Fixed 5s for rate limits
            elif 500 <= status < 600:  # Server errors - retry
                last_error = f"HTTP {status} (attempt {attempt + 1}/{max_retries})"
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    delay *= backoff_factor
            else:  # 4xx client errors - don't retry
                last_error = f"HTTP {status}: {e.response.text[:100]}"
                break
                
        except Exception as e:
            last_error = f"{type(e).__name__}: {str(e)}"
            break  # Unknown errors - don't retry
    
    return None, last_error

def download_fit_file_with_retry(athlete: dict, activity_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    """Download FIT file with retry logic"""

    def _download():
        response = requests.get(
            f"{BASE_URL}/activity/{activity_id}/file",
            auth=HTTPBasicAuth('API_KEY', athlete['api_key']),
            timeout=60,
            stream=True
        )
        response.raise_for_status()
        return response.content

    content, error = retry_with_exponential_backoff(_download, max_retries=3)
    return content, error


def get_existing_activity_ids(athlete_id: str) -> set:
    """
    Get set of activity_ids already in database for this athlete.
    Used for duplicate prevention during bulk import.

    Args:
        athlete_id: The athlete's Intervals.icu ID

    Returns:
        Set of activity_id strings already in database
    """
    url = f"{SUPABASE_URL}/rest/v1/activity_metadata"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    params = {
        "select": "activity_id",
        "athlete_id": f"eq.{athlete_id}"
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 200:
            return set(row['activity_id'] for row in response.json())
        else:
            log(f"  Warning: Could not fetch existing activity_ids: {response.status_code}", "WARNING")
            return set()
    except Exception as e:
        log(f"  Warning: Error fetching existing activity_ids: {e}", "WARNING")
        return set()

def load_athletes(athlete_filter: Optional[str] = None) -> List[Dict]:
    """Charger les athlètes"""
    try:
        # Support custom path via env var (for Lambda /tmp/)
        athletes_path = os.environ.get("ATHLETES_JSON_PATH", "athletes.json.local")
        with open(athletes_path, "r") as f:
            athletes = json.load(f)
        
        if athlete_filter:
            athletes = [a for a in athletes if a['name'] == athlete_filter]
        
        log(f"Chargé {len(athletes)} athlète(s)", "SUCCESS")
        return athletes
    except Exception as e:
        log(f"Erreur chargement athlètes: {e}", "ERROR")
        return []

def get_activities(athlete: Dict, oldest: str, newest: str) -> List[Dict]:
    """Récupérer les activités de course"""
    api_key = athlete["api_key"]
    athlete_id = athlete["id"]
    
    try:
        url = f"{BASE_URL}/athlete/{athlete_id}/activities"
        params = {"oldest": oldest, "newest": newest}
        response = requests.get(url, auth=HTTPBasicAuth("API_KEY", api_key), params=params, timeout=30)
        
        if response.status_code == 200:
            activities = response.json()
            # Return ALL activities (running and cross-training)
            return activities
        return []
    except Exception as e:
        log(f"Erreur get_activities: {e}", "ERROR")
        return []

def get_streams(athlete: Dict, activity_id: str) -> Optional[Dict]:
    """Récupérer les streams (fallback) avec retry (Phase 1)"""
    
    def _fetch_streams():
        response = requests.get(
            f"{BASE_URL}/activity/{activity_id}/streams.json",
            auth=HTTPBasicAuth("API_KEY", athlete["api_key"]),
            timeout=20
        )
        response.raise_for_status()
        return response.json()
    
    try:
        streams, error = retry_with_exponential_backoff(_fetch_streams, max_retries=3)
        
        if not streams:
            log(f"  Streams API failed: {error}", "ERROR")
            return None
        
        # Convertir liste en dict si nécessaire
        if isinstance(streams, list):
            streams_dict = {}
            for stream_obj in streams:
                if isinstance(stream_obj, dict):
                    stream_name = stream_obj.get('type', '')
                    stream_data = stream_obj.get('data', [])
                    streams_dict[stream_name] = stream_data
            return streams_dict
        return streams
        
    except Exception as e:
        log(f"  Erreur get_streams: {e}", "ERROR")
        return None

def enrich_intervals_with_active_time(intervals: List[Dict], records: List[Dict]) -> List[Dict]:
    """
    Enrichit les intervals avec les temps actifs (t_active_sec) pour affichage dashboard.
    
    Les intervals d'Intervals.icu utilisent le temps brut (elapsed time).
    Pour le dashboard avec moving time, on calcule start_t_active et end_t_active.
    
    Args:
        intervals: Liste d'intervals avec start_index/end_index
        records: Liste de records avec t_active_sec
    
    Returns:
        Intervals enrichis avec start_t_active et end_t_active
    """
    if not intervals or not records:
        return intervals
    
    for interval in intervals:
        start_idx = interval.get('start_index')
        end_idx = interval.get('end_index')
        
        # Utiliser les indices pour trouver le temps actif
        if start_idx is not None and start_idx < len(records):
            interval['start_t_active'] = records[start_idx].get('t_active_sec', 0.0)
        else:
            interval['start_t_active'] = None
        
        if end_idx is not None and end_idx < len(records):
            interval['end_t_active'] = records[end_idx].get('t_active_sec', 0.0)
        else:
            interval['end_t_active'] = None
    
    return intervals

def get_intervals(athlete: Dict, activity_id: str) -> List[Dict]:
    """Récupérer les intervals d'une activité"""
    api_key = athlete["api_key"]
    
    try:
        url = f"{BASE_URL}/activity/{activity_id}"
        params = {"intervals": "true"}
        response = requests.get(url, auth=HTTPBasicAuth("API_KEY", api_key), params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            intervals = data.get('icu_intervals', [])
            
            # Préparer pour insertion
            formatted_intervals = []
            for interval in intervals:
                # Helper pour convertir en int si non-null
                def to_int(val):
                    if val is None:
                        return None
                    try:
                        # Handle numeric types (int, float)
                        return int(round(float(val)))
                    except (ValueError, TypeError):
                        # If conversion fails (e.g., string), return None
                        return None
                
                formatted_intervals.append({
                    'activity_id': activity_id,
                    'interval_id': to_int(interval.get('id')),
                    'start_index': to_int(interval.get('start_index')),
                    'end_index': to_int(interval.get('end_index')),
                    'start_time': to_int(interval.get('start_time')),
                    'end_time': to_int(interval.get('end_time')),
                    'type': interval.get('type'),
                    'distance': interval.get('distance'),
                    'moving_time': to_int(interval.get('moving_time')),
                    'elapsed_time': to_int(interval.get('elapsed_time')),
                    'average_watts': interval.get('average_watts'),
                    'min_watts': interval.get('min_watts'),  # REAL - keep decimal precision
                    'max_watts': interval.get('max_watts'),  # REAL - keep decimal precision
                    'average_watts_kg': interval.get('average_watts_kg'),
                    'max_watts_kg': interval.get('max_watts_kg'),
                    'intensity': interval.get('intensity'),  # TEXT - keep original value
                    'weighted_average_watts': interval.get('weighted_average_watts'),
                    'training_load': interval.get('training_load'),
                    'joules': interval.get('joules'),  # REAL - keep decimal precision
                    'decoupling': interval.get('decoupling'),
                    'zone': to_int(interval.get('zone')),
                    'zone_min_watts': interval.get('zone_min_watts'),  # REAL - keep decimal precision
                    'zone_max_watts': interval.get('zone_max_watts'),  # REAL - keep decimal precision
                    'average_speed': interval.get('average_speed'),
                    'min_speed': interval.get('min_speed'),
                    'max_speed': interval.get('max_speed'),
                    'average_heartrate': to_int(interval.get('average_heartrate')),
                    'min_heartrate': to_int(interval.get('min_heartrate')),
                    'max_heartrate': to_int(interval.get('max_heartrate')),
                    'average_cadence': to_int(interval.get('average_cadence')),
                    'min_cadence': to_int(interval.get('min_cadence')),
                    'max_cadence': to_int(interval.get('max_cadence')),
                    'average_torque': interval.get('average_torque'),  # REAL - keep decimal precision
                    'min_torque': interval.get('min_torque'),  # REAL - keep decimal precision
                    'max_torque': interval.get('max_torque'),  # REAL - keep decimal precision
                    'total_elevation_gain': interval.get('total_elevation_gain'),
                    'min_altitude': interval.get('min_altitude'),
                    'max_altitude': interval.get('max_altitude'),
                    'average_gradient': interval.get('average_gradient'),
                    'group_id': to_int(interval.get('group_id'))
                })
            
            return formatted_intervals
        return []
    except Exception as e:
        log(f"  Erreur get_intervals: {e}", "WARNING")
        return []

def parse_streams_to_records(streams: Dict, activity_id: str, activity_type: str = 'run') -> List[Dict]:
    """Parser les streams en records Supabase"""
    records = []
    
    # Obtenir la longueur des streams
    time_data = streams.get('time', [])
    if not time_data:
        return []
    
    num_points = len(time_data)
    
    for i in range(num_points):
        point = {
            'activity_id': activity_id,
            'ts_offset_ms': i * 1000  # Approximation: 1 point par seconde
        }
        
        # Time
        if 'time' in streams and i < len(streams['time']):
            val = streams['time'][i]
            if val is not None:
                point['time'] = float(val)
        
        # Position (latlng est un array alterné [lat1, lng1, lat2, lng2, ...])
        if 'latlng' in streams:
            latlng = streams['latlng']
            if i * 2 + 1 < len(latlng):
                lat_val = latlng[i * 2]
                lng_val = latlng[i * 2 + 1]
                if lat_val is not None and lng_val is not None:
                    point['lat'] = float(lat_val)
                    point['lng'] = float(lng_val)
        
        # Altitude
        if 'altitude' in streams and i < len(streams['altitude']):
            val = streams['altitude'][i]
            if val is not None:
                point['enhanced_altitude'] = float(val)
        elif 'fixed_altitude' in streams and i < len(streams['fixed_altitude']):
            val = streams['fixed_altitude'][i]
            if val is not None:
                point['enhanced_altitude'] = float(val)
        
        # Vitesse
        if 'velocity_smooth' in streams and i < len(streams['velocity_smooth']):
            val = streams['velocity_smooth'][i]
            if val is not None:
                vel = float(val)
                point['velocity_smooth'] = vel
                point['enhanced_speed'] = vel
                point['speed'] = vel
        
        # Fréquence cardiaque
        if 'heartrate' in streams and i < len(streams['heartrate']):
            val = streams['heartrate'][i]
            if val is not None:
                point['heartrate'] = int(val)
        
        # Cadence
        if 'cadence' in streams and i < len(streams['cadence']):
            val = streams['cadence'][i]
            if val is not None:
                point['cadence'] = int(val)
        
        # Puissance (rare dans streams)
        if 'watts' in streams and i < len(streams['watts']):
            val = streams['watts'][i]
            if val is not None:
                point['watts'] = float(val)

        records.append(point)

    # *** NOUVEAU : Calculer t_active_sec via algorithme Strava ***
    records = compute_t_active_for_records(records, activity_type=activity_type)

    return records

def download_and_parse_fit(athlete: Dict, activity_id: str, athlete_id: str) -> Tuple[Optional[List[Dict]], Optional[Dict], bool]:
    """
    Télécharger et parser le FIT
    Returns: (records, metadata, success)
    """
    api_key = athlete["api_key"]
    
    try:
        # Télécharger avec retry (Phase 1)
        fit_content, download_error = download_fit_file_with_retry(athlete, activity_id)
        
        if not fit_content:
            log(f"  FIT download failed: {download_error}", "ERROR")
            return None, None, False
        
        log(f"  FIT téléchargé ({len(fit_content):,} bytes)")
        
        # Parser
        fit_file = FitFile(io.BytesIO(fit_content))
        
        records = []
        metadata = {
            'activity_id': activity_id,
            'athlete_id': athlete_id,
            'source': 'intervals_fit',
            'fit_available': True
        }
        
        # Métadonnées de session
        for session in fit_file.get_messages('session'):
            for field in session:
                if field.name == 'start_time':
                    metadata['start_time'] = field.value.isoformat()
                elif field.name == 'total_timer_time':
                    # Use total_timer_time (moving time) instead of total_elapsed_time
                    metadata['duration_sec'] = int(field.value)
                elif field.name == 'total_distance':
                    metadata['distance_m'] = int(field.value)
                elif field.name == 'avg_heart_rate':
                    metadata['avg_hr'] = int(field.value)
                elif field.name == 'sport':
                    metadata['type'] = field.value
        
        # Records
        ts_offset_ms = 0
        start_timestamp = None
        
        for record in fit_file.get_messages('record'):
            point = {
                'activity_id': activity_id,
                'ts_offset_ms': ts_offset_ms
            }
            
            for field in record:
                if field.name == 'timestamp':
                    if start_timestamp is None:
                        start_timestamp = field.value
                    point['time'] = (field.value - start_timestamp).total_seconds()
                
                elif field.name == 'position_lat' and field.value is not None:
                    point['lat'] = field.value * (180.0 / 2**31)
                elif field.name == 'position_long' and field.value is not None:
                    point['lng'] = field.value * (180.0 / 2**31)
                
                elif field.name == 'enhanced_altitude' and field.value is not None:
                    point['enhanced_altitude'] = float(field.value)
                elif field.name == 'altitude' and field.value is not None and 'enhanced_altitude' not in point:
                    point['enhanced_altitude'] = float(field.value)
                
                elif field.name == 'enhanced_speed' and field.value is not None:
                    point['enhanced_speed'] = float(field.value)
                    point['velocity_smooth'] = float(field.value)
                elif field.name == 'speed' and field.value is not None:
                    point['speed'] = float(field.value)
                    if 'enhanced_speed' not in point:
                        point['enhanced_speed'] = float(field.value)
                        point['velocity_smooth'] = float(field.value)
                
                elif field.name == 'heart_rate' and field.value is not None:
                    point['heartrate'] = int(field.value)
                
                elif field.name == 'cadence' and field.value is not None:
                    point['cadence'] = int(field.value)
                
                elif field.name == 'power' and field.value is not None:
                    point['watts'] = float(field.value)
                elif field.name == 'accumulated_power' and field.value is not None and field.value != 65535:
                    if 'watts' not in point:
                        point['watts'] = float(field.value)
                
                # Données Stryd
                elif field.name == 'vertical_oscillation' and field.value is not None:
                    point['vertical_oscillation'] = float(field.value)
                elif field.name == 'stance_time' and field.value is not None:
                    point['ground_contact_time'] = float(field.value)
                elif field.name == 'stance_time_percent' and field.value is not None:
                    point['stance_time_percent'] = float(field.value)
                elif field.name == 'stance_time_balance' and field.value is not None:
                    point['stance_time_balance'] = float(field.value)
                elif field.name == 'vertical_ratio' and field.value is not None:
                    point['vertical_ratio'] = float(field.value)
                elif field.name == 'step_length' and field.value is not None:
                    point['step_length'] = float(field.value)
                elif field.name == 'Leg Spring Stiffness' and field.value is not None:
                    point['leg_spring_stiffness'] = float(field.value)

            records.append(point)
            ts_offset_ms += 1000

        # *** NOUVEAU : Calculer t_active_sec via algorithme Strava ***
        records = compute_t_active_for_records(records, activity_type=metadata.get('type', 'Run').lower())

        # Enrichir métadonnées
        if records:
            if 'start_time' not in metadata and start_timestamp:
                metadata['start_time'] = start_timestamp.isoformat()
            
            for rec in records:
                if 'lat' in rec and 'lng' in rec:
                    metadata['start_lat'] = rec['lat']
                    metadata['start_lon'] = rec['lng']
                    break
            
            for rec in records:
                if 'enhanced_altitude' in rec:
                    metadata['start_elevation_m'] = rec['enhanced_altitude']
                    break
            
            # Phase 1: Enhanced HR fallback with complete cascade
            # Check if we have HR data in records to track HR monitor usage
            hr_in_records = any(rec.get('heartrate') for rec in records)
            if hr_in_records:
                stats['hr_monitor_used'] += 1
                
            # Use enhanced HR fallback
            enhanced_avg_hr = get_avg_hr_with_fallback(metadata, {}, records)
            if enhanced_avg_hr:
                metadata['avg_hr'] = enhanced_avg_hr
        
        log(f"  FIT parsé: {len(records)} records")
        return records, metadata, True
        
    except Exception as e:
        log(f"  Erreur FIT: {str(e)[:100]}", "WARNING")
        return None, None, False

def insert_records_batch_with_retry(records_url: str, headers: dict, batch: List[Dict], max_retries: int = 3) -> Tuple[bool, Optional[str]]:
    """
    Insert a batch of records with retry logic.

    Args:
        records_url: Supabase REST API URL for records table
        headers: Request headers with auth
        batch: List of record dicts to insert
        max_retries: Number of retry attempts

    Returns:
        (success, error_message)
    """
    for attempt in range(max_retries):
        try:
            response = requests.post(records_url, headers=headers, json=batch, timeout=60)
            if response.status_code in [200, 201]:
                return True, None

            error_msg = f"HTTP {response.status_code}: {response.text[:200]}"

            # Don't retry on client errors (4xx) except 429 (rate limit)
            if 400 <= response.status_code < 500 and response.status_code != 429:
                return False, error_msg

            # Rate limit - wait longer
            if response.status_code == 429:
                if attempt < max_retries - 1:
                    log(f"    Rate limited, waiting 5s...", "WARNING")
                    time.sleep(5)
                continue

        except requests.exceptions.Timeout as e:
            error_msg = f"Timeout: {str(e)}"
        except requests.exceptions.RequestException as e:
            error_msg = f"Request error: {str(e)}"

        if attempt < max_retries - 1:
            delay = (2 ** attempt)  # 1s, 2s, 4s
            log(f"    Batch insert failed (attempt {attempt+1}), retrying in {delay}s...", "WARNING")
            time.sleep(delay)

    return False, error_msg


def normalize_records(records: List[Dict]) -> List[Dict]:
    """Normaliser les records pour que tous aient les mêmes clés (fix PGRST102)"""
    if not records:
        return records

    # Collecter toutes les clés uniques
    all_keys = set()
    for record in records:
        all_keys.update(record.keys())

    # Define INTEGER columns that need conversion from float to int
    INTEGER_COLUMNS = {
        'heartrate', 'cadence', 'watts', 'time', 'ts_offset_ms',
        'enhanced_altitude', 't_active_sec'
    }

    # Normaliser chaque record
    normalized = []
    for record in records:
        normalized_record = {}
        for key in all_keys:
            value = record.get(key)
            # Convert floats to integers for INTEGER columns
            if key in INTEGER_COLUMNS and value is not None:
                try:
                    normalized_record[key] = int(round(value))
                except (ValueError, TypeError):
                    normalized_record[key] = value
            else:
                normalized_record[key] = value
        normalized.append(normalized_record)

    return normalized

def insert_to_supabase(records: List[Dict], metadata: Dict, intervals: List[Dict] = None, dry_run: bool = False):
    """Insérer dans Supabase"""
    if dry_run:
        log(f"  [DRY-RUN] Insertion de {len(records)} records + metadata + {len(intervals or [])} intervals + zone time calc")
        return True
    
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation,resolution=merge-duplicates"
        }
        
        # Normaliser les records pour avoir les mêmes clés
        records = normalize_records(records)
        
        # Métadonnées
        meta_url = f"{SUPABASE_URL}/rest/v1/activity_metadata"
        meta_response = requests.post(meta_url, headers=headers, json=[metadata], timeout=30)
        
        if meta_response.status_code not in [200, 201]:
            try:
                error_detail = meta_response.json()
                log(f"  Metadata error {meta_response.status_code}: {error_detail}", "ERROR")
            except:
                log(f"  Metadata error {meta_response.status_code}: {meta_response.text[:200]}", "ERROR")
            return False
        
        stats['metadata_inserted'] += 1
        
        # Records par batches (with retry logic)
        total_inserted = 0
        records_url = f"{SUPABASE_URL}/rest/v1/activity"
        total_batches = (len(records) + BATCH_SIZE - 1) // BATCH_SIZE if records else 0

        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1

            success, error = insert_records_batch_with_retry(records_url, headers, batch)
            if not success:
                log(f"    Batch {batch_num}/{total_batches} FAILED after retries: {error}", "ERROR")
                stats['batch_failures'] += 1
            else:
                total_inserted += len(batch)

        stats['records_inserted'] += total_inserted
        
        # Intervals
        if intervals:
            intervals_url = f"{SUPABASE_URL}/rest/v1/activity_intervals"
            intervals_response = requests.post(intervals_url, headers=headers, json=intervals, timeout=30)
            
            if intervals_response.status_code in [200, 201]:
                stats['intervals_inserted'] += len(intervals)
                log(f"  Inséré {total_inserted} records + metadata + {len(intervals)} intervals", "SUCCESS")
            else:
                try:
                    error_detail = intervals_response.json()
                    log(f"  Intervals error {intervals_response.status_code}: {error_detail}", "WARNING")
                except:
                    log(f"  Intervals error {intervals_response.status_code}: {intervals_response.text[:200]}", "WARNING")
                log(f"  Inséré {total_inserted} records + metadata (sans intervals)", "SUCCESS")
        else:
            log(f"  Inséré {total_inserted} records + metadata", "SUCCESS")

        # Calculate zone time for this activity (incremental calculation)
        # Only for activities with GPS records (running activities)
        if records and len(records) > 0:
            calculate_zone_time_for_activity(metadata['activity_id'])

            # Calculate monotony/strain for the affected week
            if 'date' in metadata and 'athlete_id' in metadata:
                week_start = get_week_start(metadata['date'])
                calculate_monotony_strain_for_week(metadata['athlete_id'], week_start)

        return True
        
    except Exception as e:
        log(f"  Erreur Supabase: {e}", "ERROR")
        return False


def calculate_zone_time_for_activity(activity_id: str, dry_run: bool = False) -> bool:
    """
    Calculate and store zone time for a single activity via SQL function.

    Calls the SQL function calculate_zone_time_for_activity() which:
    1. Gets zones effective on the activity date (temporal matching)
    2. Calculates pace from GPS speed data
    3. Counts seconds in each zone
    4. Upserts result into activity_zone_time table

    Args:
        activity_id: The activity to calculate zone time for
        dry_run: If True, skip the actual calculation

    Returns:
        True if successful, False otherwise
    """
    if dry_run:
        log(f"  [DRY-RUN] Would calculate zone time for {activity_id}")
        return True

    try:
        url = f"{SUPABASE_URL}/rest/v1/rpc/calculate_zone_time_for_activity"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            headers=headers,
            json={"p_activity_id": activity_id},
            timeout=30
        )

        if response.status_code in (200, 204):
            result = response.json()
            if result and len(result) > 0:
                was_inserted = result[0].get('was_inserted', False)
                if was_inserted:
                    total_mins = result[0].get('total_zone_minutes', 0)
                    if total_mins and float(total_mins) > 0:
                        log(f"  Zone time: {float(total_mins):.1f} min", "SUCCESS")
            return True
        else:
            log(f"  Zone time calculation failed: {response.status_code}", "WARNING")
            return False

    except Exception as e:
        log(f"  Zone time calculation error: {e}", "WARNING")
        return False


def calculate_monotony_strain_for_week(athlete_id: str, week_start: date, dry_run: bool = False) -> bool:
    """
    Calculate and store weekly monotony/strain via SQL function.

    Calls the SQL function calculate_monotony_strain_for_week() which:
    1. Queries activity_zone_time for the week
    2. Calculates CV, monotony, strain per zone
    3. Upserts result into weekly_monotony_strain table

    Args:
        athlete_id: The athlete ID
        week_start: Monday of the week to calculate
        dry_run: If True, skip the actual calculation

    Returns:
        True if successful, False otherwise
    """
    if dry_run:
        log(f"  [DRY-RUN] Would calculate monotony/strain for {athlete_id} week {week_start}")
        return True

    try:
        url = f"{SUPABASE_URL}/rest/v1/rpc/calculate_monotony_strain_for_week"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            headers=headers,
            json={
                "p_athlete_id": athlete_id,
                "p_week_start": week_start.isoformat()
            },
            timeout=30
        )

        if response.status_code in (200, 204):
            result = response.json()
            if result and len(result) > 0:
                total_strain = result[0].get('total_strain', 0)
                total_monotony = result[0].get('total_monotony', 0)
                if total_strain and float(total_strain) > 0:
                    log(f"  Monotony/Strain: strain={float(total_strain):.0f}, monotony={float(total_monotony):.2f}", "SUCCESS")
            return True
        else:
            log(f"  Monotony/strain calculation failed: {response.status_code}", "WARNING")
            return False

    except Exception as e:
        log(f"  Monotony/strain calculation error: {e}", "WARNING")
        return False


def get_week_start(activity_date_str: str) -> date:
    """
    Get the Monday (week start) for a given activity date.

    Args:
        activity_date_str: Date string in YYYY-MM-DD format

    Returns:
        The Monday of that week as a date object
    """
    activity_date = datetime.strptime(activity_date_str, "%Y-%m-%d").date()
    # weekday(): Monday=0, Sunday=6
    days_since_monday = activity_date.weekday()
    week_start = activity_date - timedelta(days=days_since_monday)
    return week_start


def process_activity(athlete: Dict, activity: Dict, dry_run: bool = False, skip_weather: bool = False):
    """Traiter une activité avec stratégie hybride"""
    activity_id = activity.get('id')
    activity_type = activity.get('type')
    activity_date = activity.get('start_date_local', '')[:10]
    distance = (activity.get('distance') or 0) / 1000

    log(f"  {activity_type} - {activity_date} - {distance:.2f} km (ID: {activity_id})")

    # Define running activity types
    RUNNING_TYPES = ['run', 'trailrun', 'virtualrun']
    is_running = activity_type and activity_type.lower() in RUNNING_TYPES

    # For non-running activities (cross-training), only import basic metadata
    if not is_running:
        log(f"  → Cross-training activity: importing metadata only (no FIT/weather/intervals)")

        # Extract basic metadata from Intervals.icu activity object
        start_time_str = activity.get('start_date_local')
        distance_m = activity.get('distance')  # Meters
        duration_sec = activity.get('moving_time') or activity.get('elapsed_time')  # Seconds
        avg_hr = activity.get('avg_hr')  # BPM

        metadata = {
            'activity_id': activity_id,
            'athlete_id': athlete['id'],
            'type': activity_type,
            'date': activity_date,
            'start_time': start_time_str,
            'source': 'intervals_basic',
            'fit_available': False
        }

        # Add optional fields only if they exist and are not None
        if distance_m is not None:
            metadata['distance_m'] = int(distance_m)
        if duration_sec is not None:
            metadata['duration_sec'] = int(duration_sec)
        if avg_hr is not None:
            metadata['avg_hr'] = int(avg_hr)

        # Insert metadata only (no records, no intervals)
        success = insert_to_supabase([], metadata, None, dry_run)
        if success:
            stats['activities_processed'] += 1
            log(f"  Cross-training metadata imported successfully", "SUCCESS")
        return success

    # For running activities, continue with full processing
    # Essayer FIT d'abord
    records, metadata, fit_success = download_and_parse_fit(athlete, activity_id, athlete['id'])
    
    if fit_success and records:
        stats['fit_success'] += 1
        # Compléter métadonnées
        metadata.update({
            'type': activity_type,
            'date': activity_date,
            'athlete_id': athlete['id']
        })
        
        # Enrichir avec météo si position disponible (Phase 1: Best Effort)
        # Skip weather if --skip-weather flag is set (bulk import optimization)
        if metadata.get('start_lat') and metadata.get('start_lon') and metadata.get('start_time'):
            stats['outdoor_activities'] += 1

            if skip_weather:
                log(f"  → Skipping weather (--skip-weather flag)")
            else:
                log(f"  → Fetching weather (archive/forecast)...")
                weather, weather_source, weather_error = get_weather_best_effort(
                    metadata['start_lat'], metadata['start_lon'], metadata['start_time']
                )
                air = fetch_air_quality_archive(metadata['start_lat'], metadata['start_lon'], metadata['start_time'])

                # Add weather source tracking
                metadata['weather_source'] = weather_source  # 'archive', 'forecast', or NULL

                if weather:
                    # Weather available - add all fields
                    if weather.get('temperature_2m') is not None:
                        metadata['weather_temp_c'] = weather['temperature_2m']
                    if weather.get('relative_humidity_2m') is not None:
                        metadata['weather_humidity_pct'] = int(weather['relative_humidity_2m'])
                    if weather.get('dew_point_2m') is not None:
                        metadata['weather_dew_point_c'] = weather['dew_point_2m']
                    if weather.get('wind_speed_10m') is not None:
                        metadata['weather_wind_speed_ms'] = weather['wind_speed_10m']
                    if weather.get('wind_gusts_10m') is not None:
                        metadata['weather_wind_gust_ms'] = weather['wind_gusts_10m']
                    if weather.get('wind_direction_10m') is not None:
                        metadata['weather_wind_dir_deg'] = int(weather['wind_direction_10m'])
                    if weather.get('pressure_msl') is not None:
                        metadata['weather_pressure_hpa'] = weather['pressure_msl']
                    if weather.get('cloudcover') is not None:
                        metadata['weather_cloudcover_pct'] = int(weather['cloudcover'])
                    if weather.get('precipitation') is not None:
                        metadata['weather_precip_mm'] = weather['precipitation']

                    # Track weather success
                    stats['weather_complete'] += 1
                    if weather_source == 'archive':
                        stats['weather_from_archive'] += 1
                    elif weather_source == 'forecast':
                        stats['weather_from_forecast'] += 1
                        log(f"   Using forecast weather (archive unavailable)", "WARNING")
                else:
                    # Weather completely unavailable - flag but CONTINUE
                    metadata['weather_error'] = weather_error
                    log(f"  Weather unavailable: {weather_error}", "ERROR")
                    stats['weather_missing'] += 1

                # Ajouter les données de qualité de l'air
                if air.get('pm2_5') is not None:
                    metadata['air_pm2_5'] = air['pm2_5']
                if air.get('pm10') is not None:
                    metadata['air_pm10'] = air['pm10']
                if air.get('ozone') is not None:
                    metadata['air_ozone'] = air['ozone']
                if air.get('nitrogen_dioxide') is not None:
                    metadata['air_no2'] = air['nitrogen_dioxide']
                if air.get('sulphur_dioxide') is not None:
                    metadata['air_so2'] = air['sulphur_dioxide']
                if air.get('carbon_monoxide') is not None:
                    metadata['air_co'] = air['carbon_monoxide']
                if air.get('us_aqi') is not None:
                    metadata['air_us_aqi'] = int(air['us_aqi'])
        
        # Récupérer les intervals
        intervals = get_intervals(athlete, activity_id)
        if intervals:
            log(f"  {len(intervals)} intervals récupérés")
            # Enrichir avec temps actif pour affichage dashboard
            intervals = enrich_intervals_with_active_time(intervals, records)
        
        success = insert_to_supabase(records, metadata, intervals, dry_run)
        if success:
            stats['activities_processed'] += 1
        return success
    
    # Fallback sur streams
    log(f"  → Fallback sur streams", "WARNING")
    stats['stream_fallback'] += 1
    
    streams = get_streams(athlete, activity_id)
    if not streams:
        log(f"  Streams non disponibles", "ERROR")
        stats['fit_failed'] += 1
        return False
    
    log(f"  Streams récupérés")
    
    # Déterminer le type d'activité pour l'algorithme moving time
    activity_type = activity.get('type', 'Run').lower()
    
    records = parse_streams_to_records(streams, activity_id, activity_type)
    if not records:
        log(f"  Aucun record extrait des streams", "ERROR")
        return False
    
    log(f"  Streams parsés: {len(records)} records")
    
    # Get all available fields from Intervals.icu activity data that match our schema
    start_time_str = activity.get('start_date_local')
    distance_m = activity.get('distance')  # Meters
    duration_sec = activity.get('moving_time') or activity.get('elapsed_time')  # Seconds
    avg_hr = activity.get('avg_hr')  # BPM
    
    metadata = {
        'activity_id': activity_id,
        'athlete_id': athlete['id'],
        'type': activity_type,
        'date': activity_date,
        'start_time': start_time_str,
        'source': 'intervals_stream',
        'fit_available': False
    }
    
    # Add fields only if they exist and are not None
    if distance_m is not None:
        metadata['distance_m'] = int(distance_m)
    if duration_sec is not None:
        metadata['duration_sec'] = int(duration_sec)
    if avg_hr is not None:
        metadata['avg_hr'] = int(avg_hr)
    
    # Extraire position de départ des records pour météo
    start_lat, start_lon, start_time = None, None, None
    for rec in records:
        if 'lat' in rec and 'lng' in rec:
            start_lat = rec['lat']
            start_lon = rec['lng']
            break
    if records and 'time' in records[0]:
        # Construire start_time approximatif
        from datetime import datetime, timedelta
        try:
            activity_datetime = datetime.fromisoformat(activity_date)
            start_time = activity_datetime.isoformat()
        except:
            pass
    
    # Enrichir avec météo si position disponible (Phase 1: Best Effort)
    # Skip weather if --skip-weather flag is set (bulk import optimization)
    if start_lat and start_lon and start_time:
        # Always add GPS coordinates
        metadata['start_lat'] = start_lat
        metadata['start_lon'] = start_lon
        stats['outdoor_activities'] += 1

        if skip_weather:
            log(f"  → Skipping weather (--skip-weather flag)")
        else:
            log(f"  → Fetching weather (archive/forecast)...")
            weather, weather_source, weather_error = get_weather_best_effort(
                start_lat, start_lon, start_time
            )
            air = fetch_air_quality_archive(start_lat, start_lon, start_time)

            # Add weather source tracking
            metadata['weather_source'] = weather_source  # 'archive', 'forecast', or NULL

            if weather:
                # Weather available - add all fields
                if weather.get('temperature_2m') is not None:
                    metadata['weather_temp_c'] = weather['temperature_2m']
                if weather.get('relative_humidity_2m') is not None:
                    metadata['weather_humidity_pct'] = int(weather['relative_humidity_2m'])
                if weather.get('dew_point_2m') is not None:
                    metadata['weather_dew_point_c'] = weather['dew_point_2m']
                if weather.get('wind_speed_10m') is not None:
                    metadata['weather_wind_speed_ms'] = weather['wind_speed_10m']
                if weather.get('wind_gusts_10m') is not None:
                    metadata['weather_wind_gust_ms'] = weather['wind_gusts_10m']
                if weather.get('wind_direction_10m') is not None:
                    metadata['weather_wind_dir_deg'] = int(weather['wind_direction_10m'])
                if weather.get('pressure_msl') is not None:
                    metadata['weather_pressure_hpa'] = weather['pressure_msl']
                if weather.get('cloudcover') is not None:
                    metadata['weather_cloudcover_pct'] = int(weather['cloudcover'])
                if weather.get('precipitation') is not None:
                    metadata['weather_precip_mm'] = weather['precipitation']

                # Track weather success
                stats['weather_complete'] += 1
                if weather_source == 'archive':
                    stats['weather_from_archive'] += 1
                elif weather_source == 'forecast':
                    stats['weather_from_forecast'] += 1
                    log(f"   Using forecast weather (archive unavailable)", "WARNING")
            else:
                # Weather completely unavailable - flag but CONTINUE
                metadata['weather_error'] = weather_error
                log(f"  Weather unavailable: {weather_error}", "ERROR")
                stats['weather_missing'] += 1

            # Ajouter les données de qualité de l'air
            if air.get('pm2_5') is not None:
                metadata['air_pm2_5'] = air['pm2_5']
            if air.get('pm10') is not None:
                metadata['air_pm10'] = air['pm10']
            if air.get('ozone') is not None:
                metadata['air_ozone'] = air['ozone']
            if air.get('nitrogen_dioxide') is not None:
                metadata['air_no2'] = air['nitrogen_dioxide']
            if air.get('sulphur_dioxide') is not None:
                metadata['air_so2'] = air['sulphur_dioxide']
            if air.get('carbon_monoxide') is not None:
                metadata['air_co'] = air['carbon_monoxide']
            if air.get('us_aqi') is not None:
                metadata['air_us_aqi'] = int(air['us_aqi'])
    
    # Phase 1: Enhanced HR fallback for streams path
    # Check if we have HR data in records to track HR monitor usage
    hr_in_records = any(rec.get('heartrate') for rec in records)
    if hr_in_records:
        stats['hr_monitor_used'] += 1
        
    # Use enhanced HR fallback with streams data
    enhanced_avg_hr = get_avg_hr_with_fallback(metadata, streams, records)
    if enhanced_avg_hr:
        metadata['avg_hr'] = enhanced_avg_hr
    else:
        log(f"   No HR data available", "WARNING")
    
    # Récupérer les intervals
    intervals = get_intervals(athlete, activity_id)
    if intervals:
        log(f"  {len(intervals)} intervals récupérés")
        # Enrichir avec temps actif pour affichage dashboard
        intervals = enrich_intervals_with_active_time(intervals, records)
    
    success = insert_to_supabase(records, metadata, intervals, dry_run)
    if success:
        stats['activities_processed'] += 1
    
    return success

def process_athlete(athlete: Dict, oldest: str, newest: str, dry_run: bool = False, skip_weather: bool = False):
    """Traiter un athlète"""
    name = athlete['name']
    athlete_id = athlete['id']

    log(f"\n{'='*70}")
    log(f"{name} ({athlete_id})")
    log(f"{'='*70}")

    activities = get_activities(athlete, oldest, newest)

    if not activities:
        log(f"Aucune activité de course trouvée", "WARNING")
        return

    stats['activities_found'] += len(activities)
    log(f"{len(activities)} activités trouvées", "SUCCESS")

    # Fetch existing activity_ids to prevent duplicates
    existing_ids = get_existing_activity_ids(athlete_id)
    if existing_ids:
        log(f"  {len(existing_ids)} activités déjà importées (seront ignorées)")

    for i, activity in enumerate(activities, 1):
        activity_id = activity.get('id')

        # Skip if already imported (duplicate prevention)
        if activity_id in existing_ids:
            log(f"\n[{i}/{len(activities)}] {activity_id} → déjà importé, ignoré")
            stats['activities_skipped'] += 1
            continue

        log(f"\n[{i}/{len(activities)}]")
        process_activity(athlete, activity, dry_run, skip_weather)

    stats['athletes_processed'] += 1

# =============================================================================
# WELLNESS INTEGRATION (merged from intervals_wellness_to_supabase.py)
# =============================================================================

def transform_wellness_record(raw_record: Dict, athlete_id: str) -> Dict:
    """
    Transform wellness record from Intervals.icu to Supabase format.
    Maps camelCase → snake_case according to wellness table schema.
    """
    transformed = {
        'athlete_id': athlete_id,
        'date': raw_record.get('id'),  # 'id' is the date in YYYY-MM-DD format
        'source': 'intervals.icu',
        'created_at': datetime.now().isoformat()
    }

    # Field mapping (camelCase → snake_case)
    field_mapping = {
        'restingHR': 'resting_hr',
        'avgSleepingHR': 'sleeping_hr',
        'hrv': 'hrv_rmssd',
        'hrvSDNN': 'hrv_sdnn',
        'sleepSecs': 'sleep_seconds',
        'sleepScore': 'sleep_score',
        'sleepQuality': 'sleep_quality',
        'spO2': 'spo2',
        'systolic': 'blood_pressure_systolic',
        'diastolic': 'blood_pressure_diastolic',
        'soreness': 'soreness',
        'fatigue': 'fatigue',
        'stress': 'stress',
        'mood': 'mood',
        'motivation': 'motivation',
        'injury': 'injury',
        'weight': 'weight_kg',
        'bodyFat': 'body_fat_pct',
        'muscleMass': 'muscle_mass_kg',
        'hydration': 'hydration',
        'nutrition': 'nutrition',
        'temperature': 'temperature_c',
        'menstruation': 'menstruation',
        'supplements': 'supplements',
        'notes': 'notes'
    }

    for intervals_field, supabase_field in field_mapping.items():
        if intervals_field in raw_record:
            value = raw_record[intervals_field]
            if value is not None:
                if intervals_field == 'sleepSecs':
                    transformed[supabase_field] = int(value)
                elif intervals_field == 'bodyFat':
                    transformed[supabase_field] = float(value * 100) if isinstance(value, (int, float)) else value
                else:
                    transformed[supabase_field] = value

    return transformed


def get_wellness_data(athlete: Dict, target_date: str) -> Optional[List[Dict]]:
    """Fetch wellness data for a specific date from Intervals.icu."""
    athlete_id = athlete['id']
    api_key = athlete['api_key']

    try:
        url = f"{BASE_URL}/athlete/{athlete_id}/wellness"
        params = {"oldest": target_date, "newest": target_date}

        response = requests.get(
            url,
            auth=HTTPBasicAuth("API_KEY", api_key),
            params=params,
            timeout=30
        )

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return []
        else:
            return None
    except Exception as e:
        log(f"  Wellness API error: {e}", "WARNING")
        return None


def insert_wellness_to_supabase(records: List[Dict], dry_run: bool = False) -> bool:
    """Insert wellness data to Supabase using UPSERT (prevents duplicates)."""
    if not records:
        return True

    if dry_run:
        log(f"  [DRY RUN] Would upsert {len(records)} wellness records")
        return True

    try:
        # Use Supabase REST API for upsert
        url = f"{SUPABASE_URL}/rest/v1/wellness"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates"  # UPSERT behavior
        }

        response = requests.post(url, headers=headers, json=records, timeout=30)

        if response.status_code in (200, 201):
            return True
        else:
            log(f"  Wellness upsert error: {response.status_code} - {response.text[:100]}", "ERROR")
            return False
    except Exception as e:
        log(f"  Wellness insert error: {e}", "ERROR")
        return False


def import_wellness_for_date(athletes: List[Dict], target_date: str, dry_run: bool = False):
    """
    Import wellness for ALL athletes for a specific date.
    Called at end of every ingestion run.
    Uses UPSERT - safe to run multiple times per day.
    """
    log(f"\n{Colors.CYAN}{'='*60}{Colors.END}")
    log(f"{Colors.CYAN}{Colors.BOLD}WELLNESS IMPORT: {target_date}{Colors.END}")
    log(f"{Colors.CYAN}{'='*60}{Colors.END}")

    wellness_count = 0
    wellness_success = 0

    for athlete in athletes:
        wellness_data = get_wellness_data(athlete, target_date)

        if wellness_data:
            records = [transform_wellness_record(r, athlete['id']) for r in wellness_data]
            if insert_wellness_to_supabase(records, dry_run):
                wellness_count += len(records)
                wellness_success += 1
                log(f"  ✓ {athlete['name']}: wellness imported", "SUCCESS")
            else:
                log(f"  ✗ {athlete['name']}: wellness insert failed", "ERROR")
        else:
            log(f"  - {athlete['name']}: no wellness data for {target_date}")

    log(f"\n{Colors.BOLD}Wellness Summary:{Colors.END}")
    log(f"  Athletes with wellness: {wellness_success}/{len(athletes)}")
    log(f"  Records processed: {wellness_count}")

    return wellness_count


def import_wellness_date_range(athletes: List[Dict], oldest_date: str, newest_date: str, dry_run: bool = False):
    """
    Import wellness data for a date range (for bulk historical import).

    Args:
        athletes: List of athlete dicts
        oldest_date: Start date (YYYY-MM-DD)
        newest_date: End date (YYYY-MM-DD)
        dry_run: If True, don't actually insert

    Uses UPSERT - safe to run multiple times (idempotent).
    """
    from datetime import timedelta

    log(f"\n{Colors.CYAN}{'='*70}{Colors.END}")
    log(f"{Colors.CYAN}{Colors.BOLD}HISTORICAL WELLNESS IMPORT: {oldest_date} → {newest_date}{Colors.END}")
    log(f"{Colors.CYAN}{'='*70}{Colors.END}")

    start = datetime.strptime(oldest_date, "%Y-%m-%d")
    end = datetime.strptime(newest_date, "%Y-%m-%d")

    total_days = (end - start).days + 1
    total_records = 0
    days_with_data = 0

    current = start
    day_num = 0
    while current <= end:
        day_num += 1
        date_str = current.strftime("%Y-%m-%d")

        # Progress indicator every 30 days
        if day_num % 30 == 1 or day_num == total_days:
            log(f"\n  Processing day {day_num}/{total_days}: {date_str}")

        day_records = 0
        for athlete in athletes:
            wellness_data = get_wellness_data(athlete, date_str)
            if wellness_data:
                records = [transform_wellness_record(r, athlete['id']) for r in wellness_data]
                if insert_wellness_to_supabase(records, dry_run):
                    day_records += len(records)

        if day_records > 0:
            days_with_data += 1
            total_records += day_records

        current += timedelta(days=1)

    stats['wellness_days_imported'] = days_with_data

    log(f"\n{Colors.BOLD}Historical Wellness Summary:{Colors.END}")
    log(f"  Date range: {oldest_date} → {newest_date} ({total_days} days)")
    log(f"  Days with wellness data: {days_with_data}")
    log(f"  Total records imported: {total_records}")


def print_summary():
    """Résumé final (Phase 1 Enhanced)"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}RÉSUMÉ FINAL{Colors.END}")
    print(f"{Colors.BLUE}{'='*70}{Colors.END}\n")

    print(f"Athlètes traités: {stats['athletes_processed']}")
    print(f"Activités trouvées: {stats['activities_found']}")
    print(f"Activités traitées: {stats['activities_processed']}")

    # Show skipped activities if any
    if stats['activities_skipped'] > 0:
        print(f"Activités ignorées (déjà importées): {stats['activities_skipped']}")

    print(f"\nSources:")
    print(f"  FIT réussi: {stats['fit_success']} ({stats['fit_success']/max(stats['activities_found'],1)*100:.1f}%)")
    print(f"  Fallback streams: {stats['stream_fallback']} ({stats['stream_fallback']/max(stats['activities_found'],1)*100:.1f}%)")
    print(f"  Échecs: {stats['fit_failed']}")

    # Phase 1: Weather completeness
    if stats['outdoor_activities'] > 0:
        weather_pct = stats['weather_complete'] / stats['outdoor_activities'] * 100
        print(f"\n️ Météo (activités extérieures):")
        print(f"  Total extérieur: {stats['outdoor_activities']}")
        print(f"  Avec météo: {stats['weather_complete']} ({weather_pct:.1f}%)")
        print(f"    • Archive: {stats['weather_from_archive']}")
        print(f"    • Forecast: {stats['weather_from_forecast']}")
        if stats['weather_missing'] > 0:
            print(f"  {Colors.RED}Sans météo: {stats['weather_missing']}{Colors.END}")
        else:
            print(f"  Sans météo: 0")

    # Phase 1: HR completeness
    if stats['hr_monitor_used'] > 0:
        hr_pct = stats['hr_complete'] / stats['hr_monitor_used'] * 100
        print(f"\nFréquence cardiaque:")
        print(f"  Moniteur utilisé: {stats['hr_monitor_used']}")
        print(f"  HR complète: {stats['hr_complete']} ({hr_pct:.1f}%)")
        if stats['hr_missing'] > 0:
            print(f"  {Colors.YELLOW}HR manquante: {stats['hr_missing']}{Colors.END}")

    print(f"\nDonnées insérées:")
    print(f"  Records: {stats['records_inserted']:,}")
    print(f"  Métadonnées: {stats['metadata_inserted']}")
    print(f"  Intervals: {stats['intervals_inserted']}")

    # Show batch failures if any
    if stats['batch_failures'] > 0:
        print(f"  {Colors.RED}Batch failures: {stats['batch_failures']}{Colors.END}")

    # Show wellness days if imported
    if stats['wellness_days_imported'] > 0:
        print(f"\nWellness:")
        print(f"  Days imported: {stats['wellness_days_imported']}")

    if stats['errors']:
        print(f"\n{Colors.RED}Erreurs ({len(stats['errors'])}):{Colors.END}")
        for error in stats['errors'][:10]:
            print(f"  • {error}")

def main():
    parser = argparse.ArgumentParser(description="Intégration hybride Intervals.icu → Supabase")
    parser.add_argument('--dry-run', action='store_true', help="Mode test")
    parser.add_argument('--oldest', default='2024-08-01', help="Date début")
    parser.add_argument('--newest', default='2024-08-21', help="Date fin")
    parser.add_argument('--athlete', help="Athlète spécifique")
    parser.add_argument('--backfill-weather', action='store_true',
                        help="Update forecast weather to archive (3-7 days back)")
    parser.add_argument('--backfill-only', action='store_true',
                        help="Only run weather backfill, skip activity import")
    parser.add_argument('--backfill-min-days', type=int, default=3,
                        help="Start backfill this many days back (default: 3)")
    parser.add_argument('--backfill-max-days', type=int, default=7,
                        help="Stop backfill after this many days back (default: 7)")
    # Wellness historical import options
    parser.add_argument('--wellness-oldest', type=str,
                        help="Oldest date for historical wellness import (YYYY-MM-DD)")
    parser.add_argument('--wellness-newest', type=str,
                        help="Newest date for historical wellness import (YYYY-MM-DD)")
    # Bulk import optimization
    parser.add_argument('--skip-weather', action='store_true',
                        help="Skip weather/air quality API calls (for bulk historical import)")

    args = parser.parse_args()

    print(f"\n{Colors.BOLD}{'='*70}")
    print("INTÉGRATION HYBRIDE INTERVALS.ICU → SUPABASE")
    print(f"{'='*70}{Colors.END}\n")

    if args.dry_run:
        print(f"{Colors.YELLOW} MODE DRY-RUN{Colors.END}\n")

    # Handle backfill-only mode
    if args.backfill_only:
        print(f"{Colors.BLUE}Mode: Weather backfill only (skipping activity import){Colors.END}")
        print(f"Window: {args.backfill_min_days}-{args.backfill_max_days} days back\n")
        backfill_forecast_weather(
            days_back_min=args.backfill_min_days,
            days_back_max=args.backfill_max_days,
            dry_run=args.dry_run
        )
        return 0

    print(f"Période: {args.oldest} → {args.newest}")
    print(f"Stratégie: FIT (priorité) + Streams (fallback)")
    print(f"Supabase: {SUPABASE_URL}")
    if args.skip_weather:
        print(f"{Colors.YELLOW}⚡ Weather: SKIPPED (bulk import mode){Colors.END}")
    if args.backfill_weather:
        print(f"{Colors.BLUE}Weather backfill: Enabled (3-7 days back){Colors.END}")
    print("")

    athletes = load_athletes(args.athlete)
    if not athletes:
        return 1

    for athlete in athletes:
        process_athlete(athlete, args.oldest, args.newest, args.dry_run, args.skip_weather)

    print_summary()

    # Weather backfill (if requested)
    if args.backfill_weather and not args.dry_run:
        backfill_forecast_weather(
            days_back_min=args.backfill_min_days,
            days_back_max=args.backfill_max_days,
            dry_run=False
        )

    # Import wellness data
    # If historical dates provided, import date range; otherwise import today only
    if args.wellness_oldest and args.wellness_newest:
        import_wellness_date_range(athletes, args.wellness_oldest, args.wellness_newest, args.dry_run)
    else:
        # Import today's wellness for ALL athletes (regardless of activities)
        today = datetime.now().strftime("%Y-%m-%d")
        import_wellness_for_date(athletes, today, args.dry_run)

    # Phase 2: Refresh materialized views after data import
    if not args.dry_run and stats['activities_processed'] > 0:
        # Refresh activity summary view
        try:
            print(f"\n{Colors.BLUE}Refreshing activity summary view...{Colors.END}")
            refresh_url = f"{SUPABASE_URL}/rest/v1/rpc/refresh_activity_summary"
            response = requests.post(
                refresh_url,
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json"
                },
                timeout=60
            )
            if response.status_code in (200, 204):
                print(f"{Colors.GREEN}Activity summary view refreshed{Colors.END}")
            else:
                print(f"{Colors.YELLOW} View refresh returned status {response.status_code}{Colors.END}")
        except Exception as e:
            print(f"{Colors.YELLOW} Could not refresh activity summary view: {e}{Colors.END}")

        # Refresh zone time views (activity_zone_time + weekly_zone_time)
        try:
            print(f"{Colors.BLUE}Refreshing zone time views...{Colors.END}")
            refresh_url = f"{SUPABASE_URL}/rest/v1/rpc/refresh_all_zone_views"
            response = requests.post(
                refresh_url,
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json"
                },
                timeout=300  # Zone views may take longer (processing 2.5M+ rows)
            )
            if response.status_code in (200, 204):
                print(f"{Colors.GREEN}Zone time views refreshed{Colors.END}\n")
            else:
                print(f"{Colors.YELLOW} Zone view refresh returned status {response.status_code}{Colors.END}\n")
        except Exception as e:
            print(f"{Colors.YELLOW} Could not refresh zone views: {e}{Colors.END}\n")

    # Return 0 (success) even when no new activities - that's expected for daily cron
    # Only return 1 if there were actual failures
    return 0 if stats.get('batch_failures', 0) == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
