"""
Calcul du temps en mouvement (algorithme type Strava).

Ce module implémente un algorithme robuste pour calculer le temps actif
en excluant les pauses, basé sur les seuils de vitesse et la détection
des arrêts prolongés.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional, Any

import numpy as np
import pandas as pd


# =============================================================================
# CONSTANTES
# =============================================================================

# Seuils de vitesse par type d'activité (m/s)
SPEED_THRESHOLDS: dict[str, float] = {
    'run': 0.6,          # ~2.2 km/h
    'trailrun': 0.5,     # ~1.8 km/h (terrain difficile)
    'virtualrun': 0.6,   # ~2.2 km/h
    'treadmill': 0.6,    # ~2.2 km/h
    'walking': 0.5,      # ~1.8 km/h
    'cycling': 1.0,      # ~3.6 km/h
    'default': 0.6,      # ~2.2 km/h
}

# Durée minimale d'arrêt à considérer comme pause (secondes)
MIN_STOP_DURATION: float = 10.0


# =============================================================================
# DISTANCE HAVERSINE
# =============================================================================

def haversine_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    """
    Calcule la distance entre deux points GPS via formule de Haversine.

    Args:
        lat1, lon1: Coordonnées du premier point (degrés)
        lat2, lon2: Coordonnées du second point (degrés)

    Returns:
        Distance en mètres
    """
    R = 6371000  # Rayon de la Terre en mètres

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))

    return R * c


# =============================================================================
# CALCUL TEMPS ACTIF (STRAVA-LIKE)
# =============================================================================

def compute_moving_time_strava(
    df: pd.DataFrame,
    activity_type: str = "run"
) -> pd.Series:
    """
    Calcule le temps actif cumulé selon l'algorithme Strava.

    Logique :
    1. Calcule la vitesse entre chaque paire de points GPS consécutifs
    2. Marque un segment comme "en mouvement" si :
       - vitesse >= seuil (selon type d'activité)
       OU
       - durée < MIN_STOP_DURATION (pauses courtes incluses, ex: feux rouges)
    3. Cumule le temps pour les segments "en mouvement"

    Args:
        df: DataFrame avec colonnes 'time' (ou 'ts_offset_ms'), 'lat', 'lng',
            optionnellement 'speed'/'enhanced_speed'/'velocity_smooth'
        activity_type: Type d'activité (run, cycling, etc.)

    Returns:
        Série du temps actif cumulé (secondes) de même longueur que df
    """
    if df is None or df.empty:
        return pd.Series([], dtype=float)

    n = len(df)
    if n < 2:
        return pd.Series([0.0] * n, index=df.index, dtype=float)

    # Seuil de vitesse
    speed_threshold = SPEED_THRESHOLDS.get(
        activity_type.lower(),
        SPEED_THRESHOLDS['default']
    )

    # --- 1. Base temporelle (secondes) ---
    if 'ts_offset_ms' in df.columns:
        t_raw = pd.to_numeric(df['ts_offset_ms'], errors='coerce') / 1000.0
    elif 'time' in df.columns:
        t_raw = pd.to_numeric(df['time'], errors='coerce')
    else:
        # Pas de temps → tout 0
        return pd.Series(np.zeros(n), index=df.index, dtype=float)

    t_raw = t_raw.ffill().fillna(0.0)
    t_raw = t_raw - t_raw.iloc[0]  # Normaliser à 0 au début
    t_raw = t_raw.clip(lower=0.0)

    # Delta temps entre points consécutifs
    dt = t_raw.diff().fillna(0.0).clip(lower=0.0).values

    # --- 2. Calcul de la vitesse ---
    # Priorité : colonnes de vitesse pré-calculées
    v = None
    for col in ('enhanced_speed', 'velocity_smooth', 'speed'):  # Ordre de priorité ajusté
        if col in df.columns:
            v_series = pd.to_numeric(df[col], errors='coerce')
            if v_series.notna().any():  # Vérifier qu'il y a des valeurs non-nulles
                v = v_series.fillna(0.0).values
                break

    # Si pas de vitesse pré-calculée, on la calcule depuis lat/lng
    if v is None:
        has_coords = (
            'lat' in df.columns
            and 'lng' in df.columns
            and df['lat'].notna().any()
            and df['lng'].notna().any()
        )

        if has_coords:
            lats = pd.to_numeric(df['lat'], errors='coerce').ffill().values
            lngs = pd.to_numeric(df['lng'], errors='coerce').ffill().values

            # Distance entre points consécutifs (Haversine)
            distances = np.zeros(n)
            for i in range(1, n):
                if not (np.isnan(lats[i]) or np.isnan(lngs[i]) or np.isnan(lats[i-1]) or np.isnan(lngs[i-1])):
                    distances[i] = haversine_distance(
                        lats[i-1], lngs[i-1],
                        lats[i], lngs[i]
                    )

            # Vitesse = distance / temps
            v = np.where(dt > 0, distances / dt, 0.0)
        else:
            # Pas de coords ni de vitesse → on utilise cadence si dispo
            if 'cadence' in df.columns:
                cad = pd.to_numeric(df['cadence'], errors='coerce').fillna(0.0).values
                # Heuristique : cadence > 1 spm = en mouvement
                v = np.where(cad > 1.0, speed_threshold + 0.1, 0.0)
            else:
                # Aucune donnée → tout est considéré comme arrêt
                v = np.zeros(n)

    # --- 3. Détection des segments en mouvement ---
    # Approche : marquer les points avec vitesse >= seuil comme "en mouvement"
    # Puis combler les trous < MIN_STOP_DURATION (ex: feu rouge)

    moving = v >= speed_threshold

    # Combler les pauses courtes (< MIN_STOP_DURATION)
    # Pour cela, on identifie les séquences d'arrêts et on comble les courtes
    is_stopped = ~moving

    # Identifier les débuts/fins de séquences d'arrêts
    stop_starts = np.where(np.diff(np.concatenate(([False], is_stopped))))[0]
    stop_ends = np.where(np.diff(np.concatenate((is_stopped, [False]))))[0]

    # Pour chaque séquence d'arrêt
    for start_idx, end_idx in zip(stop_starts, stop_ends):
        # Temps d'arrêt pour cette séquence
        stop_duration = t_raw.iloc[end_idx] - t_raw.iloc[start_idx] if end_idx < n else 0

        # Si arrêt court (< MIN_STOP_DURATION), le considérer comme mouvement
        if 0 < stop_duration < MIN_STOP_DURATION:
            moving[start_idx:end_idx+1] = True

    # --- 4. Calcul du temps actif cumulé ---
    dt_active = np.where(moving, dt, 0.0)
    t_active = np.cumsum(dt_active)

    # Garantir que le premier point est à 0
    t_active[0] = 0.0

    return pd.Series(t_active, index=df.index, dtype=float)


# =============================================================================
# CALCUL STATISTIQUES COMPLÈTES
# =============================================================================

def compute_moving_stats(
    df: pd.DataFrame,
    activity_type: str = "run"
) -> dict[str, Any]:
    """
    Calcule les statistiques complètes (temps actif, distance, vitesse moyenne).

    Args:
        df: DataFrame avec time series
        activity_type: Type d'activité

    Returns:
        Dictionnaire avec :
        - moving_time: Temps actif total (s)
        - elapsed_time: Temps écoulé total (s)
        - stopped_time: Temps arrêté total (s)
        - total_distance: Distance totale (m)
        - moving_distance: Distance en mouvement (m)
        - avg_moving_speed: Vitesse moyenne en mouvement (m/s)
    """
    if df is None or df.empty:
        return {
            'moving_time': 0.0,
            'elapsed_time': 0.0,
            'stopped_time': 0.0,
            'total_distance': 0.0,
            'moving_distance': 0.0,
            'avg_moving_speed': 0.0,
        }

    # Temps actif cumulé
    t_active = compute_moving_time_strava(df, activity_type)
    moving_time = float(t_active.iloc[-1]) if len(t_active) > 0 else 0.0

    # Temps écoulé
    if 'ts_offset_ms' in df.columns:
        t_raw = pd.to_numeric(df['ts_offset_ms'], errors='coerce') / 1000.0
    elif 'time' in df.columns:
        t_raw = pd.to_numeric(df['time'], errors='coerce')
    else:
        t_raw = pd.Series([0.0], index=df.index)

    elapsed_time = float(t_raw.iloc[-1] - t_raw.iloc[0]) if len(t_raw) > 1 else 0.0
    stopped_time = max(0.0, elapsed_time - moving_time)

    # Distance
    total_distance = 0.0
    moving_distance = 0.0

    if 'distance' in df.columns:
        dist = pd.to_numeric(df['distance'], errors='coerce')
        if dist.notna().any():
            total_distance = float(dist.iloc[-1] - dist.iloc[0])

    # Si pas de colonne distance, on intègre depuis la vitesse
    if total_distance == 0.0:
        for col in ('speed', 'enhanced_speed', 'velocity_smooth'):
            if col in df.columns:
                v = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
                if 'time' in df.columns:
                    t = pd.to_numeric(df['time'], errors='coerce')
                    dt = t.diff().fillna(0.0).clip(lower=0.0)
                    total_distance = float((v * dt).sum())
                break

    # Distance en mouvement (proportionnelle au temps actif)
    if elapsed_time > 0:
        moving_distance = total_distance * (moving_time / elapsed_time)
    else:
        moving_distance = total_distance

    # Vitesse moyenne en mouvement
    avg_moving_speed = moving_distance / moving_time if moving_time > 0 else 0.0

    return {
        'moving_time': moving_time,
        'elapsed_time': elapsed_time,
        'stopped_time': stopped_time,
        'total_distance': total_distance,
        'moving_distance': moving_distance,
        'avg_moving_speed': avg_moving_speed,
        'moving_time_formatted': str(timedelta(seconds=int(moving_time))),
        'elapsed_time_formatted': str(timedelta(seconds=int(elapsed_time))),
    }


# =============================================================================
# EXEMPLE D'UTILISATION
# =============================================================================

if __name__ == "__main__":
    # Simuler une activité avec arrêt au milieu
    base_time = datetime(2025, 7, 31, 8, 0, 0)

    # Créer DataFrame de test
    data = []
    # Phase 1: en mouvement (0-5 minutes)
    for i in range(300):
        data.append({
            'time': float(i),
            'ts_offset_ms': i * 1000,
            'lat': 45.5 + i * 0.00001,
            'lng': -73.6 + i * 0.00001,
            'speed': 3.0,  # 3 m/s = 10.8 km/h
        })

    # Phase 2: arrêté (5-7 minutes)
    for i in range(300, 420):
        data.append({
            'time': float(i),
            'ts_offset_ms': i * 1000,
            'lat': 45.5 + 300 * 0.00001,
            'lng': -73.6 + 300 * 0.00001,
            'speed': 0.0,  # arrêté
        })

    # Phase 3: en mouvement (7-10 minutes)
    for i in range(420, 600):
        data.append({
            'time': float(i),
            'ts_offset_ms': i * 1000,
            'lat': 45.5 + (300 + (i-420)) * 0.00001,
            'lng': -73.6 + (300 + (i-420)) * 0.00001,
            'speed': 3.5,  # 3.5 m/s = 12.6 km/h
        })

    df = pd.DataFrame(data)

    # Calculer temps actif
    t_active = compute_moving_time_strava(df, activity_type='run')
    stats = compute_moving_stats(df, activity_type='run')

    print("=== Test Algorithme Strava ===")
    print(f"Temps total : {stats['elapsed_time_formatted']}")
    print(f"Temps actif : {stats['moving_time_formatted']}")
    print(f"Temps arrêté : {stats['stopped_time']:.0f}s")
    print(f"Distance totale : {stats['total_distance']:.0f}m")
    print(f"Vitesse moyenne (en mouvement) : {stats['avg_moving_speed']:.2f} m/s ({stats['avg_moving_speed']*3.6:.1f} km/h)")
    print(f"\nDernier point - Temps actif cumulé : {t_active.iloc[-1]:.0f}s")
