#!/usr/bin/env python3
"""
Intégration Wellness Intervals.icu → Supabase
Récupère les données de bien-être quotidiennes (HRV, sommeil, FC repos, etc.)

Usage:
    # Période spécifique pour tous les athlètes
    python intervals_wellness_to_supabase.py --start-date 2025-05-01 --end-date 2025-05-07
    
    # Un seul athlète
    python intervals_wellness_to_supabase.py --athlete-id i344978 --start-date 2025-05-01 --end-date 2025-05-07
    
    # Mode dry-run (test sans écrire)
    python intervals_wellness_to_supabase.py --start-date 2025-05-01 --end-date 2025-05-07 --dry-run
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from typing import List, Dict, Optional
from supabase import create_client, Client

# Load environment
load_dotenv("ingest.env")

# Configuration
BASE_URL = "https://intervals.icu/api/v1"
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

# Couleurs pour logging
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

# Statistiques globales
stats = {
    'athletes_processed': 0,
    'wellness_records_found': 0,
    'wellness_records_inserted': 0,
    'wellness_records_updated': 0,
    'api_calls_made': 0,
    'errors': []
}

def log(msg: str, level: str = "INFO"):
    """Logger avec couleurs"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    if level == "ERROR":
        print(f"{Colors.RED}[{timestamp}] ✗ {msg}{Colors.END}")
    elif level == "SUCCESS":
        print(f"{Colors.GREEN}[{timestamp}] ✓ {msg}{Colors.END}")
    elif level == "WARNING":
        print(f"{Colors.YELLOW}[{timestamp}] ⚠ {msg}{Colors.END}")
    else:
        print(f"[{timestamp}] {msg}")

def get_athletes() -> List[Dict]:
    """Charger la liste des athlètes depuis athletes.json"""
    try:
        with open('athletes.json', 'r') as f:
            athletes = json.load(f)
        log(f"Athlètes chargés: {len(athletes)}")
        return athletes
    except FileNotFoundError:
        log("Fichier athletes.json introuvable", "ERROR")
        return []
    except Exception as e:
        log(f"Erreur lecture athletes.json: {e}", "ERROR")
        return []

def get_wellness_data(athlete: Dict, start_date: str, end_date: str) -> Optional[List[Dict]]:
    """Récupérer les données wellness d'un athlète pour une période donnée"""
    athlete_id = athlete['id']
    api_key = athlete['api_key']
    
    try:
        url = f"{BASE_URL}/athlete/{athlete_id}/wellness"
        params = {
            "oldest": start_date,
            "newest": end_date
        }
        
        log(f"  → Fetching wellness data: {start_date} to {end_date}")
        
        response = requests.get(
            url,
            auth=HTTPBasicAuth("API_KEY", api_key),
            params=params,
            timeout=30
        )
        
        stats['api_calls_made'] += 1
        
        if response.status_code == 200:
            data = response.json()
            log(f"  ✓ {len(data)} wellness records retrieved")
            return data
        elif response.status_code == 404:
            log(f"  ⚠ No wellness data available for athlete {athlete_id}", "WARNING")
            return []
        else:
            log(f"  ✗ API error {response.status_code}: {response.text[:100]}", "ERROR")
            return None
            
    except requests.exceptions.Timeout:
        log(f"  ✗ Timeout fetching wellness data", "ERROR")
        return None
    except Exception as e:
        log(f"  ✗ Error fetching wellness: {str(e)[:100]}", "ERROR")
        return None

def transform_wellness_record(raw_record: Dict, athlete_id: str) -> Dict:
    """
    Transformer un record wellness d'Intervals.icu vers le format Supabase.
    
    Mapping camelCase → snake_case selon le schéma de la table wellness.
    """
    
    # Champs de base requis
    transformed = {
        'athlete_id': athlete_id,
        'date': raw_record.get('id'),  # 'id' est la date en format YYYY-MM-DD
        'source': 'intervals.icu',
        'created_at': datetime.now().isoformat()
    }
    
    # Mapping des champs wellness (camelCase → snake_case)
    field_mapping = {
        # Fréquence cardiaque
        'restingHR': 'resting_hr',
        'avgSleepingHR': 'sleeping_hr',
        
        # HRV (Heart Rate Variability)
        'hrv': 'hrv_rmssd',  # RMSSD est la métrique HRV standard
        'hrvSDNN': 'hrv_sdnn',
        
        # Sommeil
        'sleepSecs': 'sleep_seconds',
        'sleepScore': 'sleep_score',
        'sleepQuality': 'sleep_quality',
        
        # Oxygène sanguin
        'spO2': 'spo2',
        
        # Tension artérielle
        'systolic': 'blood_pressure_systolic',
        'diastolic': 'blood_pressure_diastolic',
        
        # Métriques subjectives (1-10 scale)
        'soreness': 'soreness',
        'fatigue': 'fatigue',
        'stress': 'stress',
        'mood': 'mood',
        'motivation': 'motivation',
        'injury': 'injury',
        
        # Poids et composition corporelle
        'weight': 'weight_kg',
        'bodyFat': 'body_fat_pct',
        'muscleMass': 'muscle_mass_kg',
        
        # Hydratation et nutrition
        'hydration': 'hydration',
        'nutrition': 'nutrition',
        
        # Autres métriques
        'temperature': 'temperature_c',
        'menstruation': 'menstruation',
        'supplements': 'supplements',
        'notes': 'notes'
    }
    
    # Appliquer le mapping
    for intervals_field, supabase_field in field_mapping.items():
        if intervals_field in raw_record:
            value = raw_record[intervals_field]
            
            # Conversion de types si nécessaire
            if value is not None:
                # Convertir les secondes en heures pour le sommeil
                if intervals_field == 'sleepSecs':
                    transformed[supabase_field] = int(value)
                # Convertir les pourcentages de 0-1 vers 0-100
                elif intervals_field == 'bodyFat':
                    transformed[supabase_field] = float(value * 100) if isinstance(value, (int, float)) else value
                # Garder les autres valeurs telles quelles
                else:
                    transformed[supabase_field] = value
    
    return transformed

def insert_wellness_to_supabase(records: List[Dict], dry_run: bool = False) -> bool:
    """Insérer les données wellness dans Supabase avec upsert"""
    if not records:
        return True
    
    if dry_run:
        log(f"  [DRY RUN] Would insert {len(records)} wellness records")
        return True
    
    try:
        # Initialize Supabase client
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        log(f"  → Inserting {len(records)} wellness records to Supabase")
        
        # Upsert avec clé composite (athlete_id, date)
        response = supabase.table('wellness').upsert(
            records,
            on_conflict='athlete_id,date'
        ).execute()
        
        if response.data:
            inserted_count = len(response.data)
            stats['wellness_records_inserted'] += inserted_count
            log(f"  ✓ {inserted_count} wellness records upserted successfully", "SUCCESS")
            return True
        else:
            log(f"  ✗ No data returned from upsert operation", "ERROR")
            return False
            
    except Exception as e:
        error_msg = f"Supabase upsert error: {str(e)[:200]}"
        log(f"  ✗ {error_msg}", "ERROR")
        stats['errors'].append(error_msg)
        return False

def process_athlete_wellness(athlete: Dict, start_date: str, end_date: str, dry_run: bool = False) -> bool:
    """Traiter les données wellness d'un athlète"""
    athlete_id = athlete['id']
    athlete_name = athlete['name']
    
    log(f"📊 Processing wellness for {athlete_name} (ID: {athlete_id})")
    
    # Récupérer les données wellness
    wellness_data = get_wellness_data(athlete, start_date, end_date)
    
    if wellness_data is None:
        log(f"  ✗ Failed to fetch wellness data", "ERROR")
        return False
    
    if not wellness_data:
        log(f"  ⚠ No wellness data found for period", "WARNING")
        return True
    
    stats['wellness_records_found'] += len(wellness_data)
    
    # Transformer les données
    log(f"  → Transforming {len(wellness_data)} wellness records")
    transformed_records = []
    
    for raw_record in wellness_data:
        try:
            transformed = transform_wellness_record(raw_record, athlete_id)
            transformed_records.append(transformed)
        except Exception as e:
            log(f"  ✗ Error transforming record {raw_record.get('id', 'unknown')}: {e}", "ERROR")
            continue
    
    if not transformed_records:
        log(f"  ✗ No valid records after transformation", "ERROR")
        return False
    
    # Insérer dans Supabase
    success = insert_wellness_to_supabase(transformed_records, dry_run)
    
    if success:
        stats['athletes_processed'] += 1
        log(f"  ✓ Wellness data processed successfully for {athlete_name}", "SUCCESS")
    
    return success

def print_final_stats():
    """Afficher les statistiques finales"""
    print(f"\n{Colors.CYAN}{'='*60}{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}📊 WELLNESS INGESTION SUMMARY{Colors.END}")
    print(f"{Colors.CYAN}{'='*60}{Colors.END}")
    
    print(f"\n📈 {Colors.BOLD}Statistics:{Colors.END}")
    print(f"  Athletes processed: {stats['athletes_processed']}")
    print(f"  API calls made: {stats['api_calls_made']}")
    print(f"  Wellness records found: {stats['wellness_records_found']}")
    print(f"  Records inserted/updated: {stats['wellness_records_inserted']}")
    
    if stats['errors']:
        print(f"\n❌ {Colors.BOLD}Errors ({len(stats['errors'])}):{Colors.END}")
        for error in stats['errors'][:5]:  # Show first 5 errors
            print(f"  • {error}")
        if len(stats['errors']) > 5:
            print(f"  ... and {len(stats['errors']) - 5} more errors")
    
    # Success rate
    if stats['athletes_processed'] > 0:
        success_rate = (stats['wellness_records_inserted'] / stats['wellness_records_found'] * 100) if stats['wellness_records_found'] > 0 else 0
        print(f"\n✅ {Colors.BOLD}Success Rate: {success_rate:.1f}%{Colors.END}")
    
    print(f"\n{Colors.GREEN}✓ Wellness ingestion completed{Colors.END}")

def main():
    parser = argparse.ArgumentParser(description="Intégration wellness Intervals.icu → Supabase")
    parser.add_argument('--start-date', required=True, help="Date début (YYYY-MM-DD)")
    parser.add_argument('--end-date', required=True, help="Date fin (YYYY-MM-DD)")
    parser.add_argument('--athlete-id', help="ID athlète spécifique (optionnel)")
    parser.add_argument('--dry-run', action='store_true', help="Mode test sans écriture")
    
    args = parser.parse_args()
    
    # Validation des dates
    try:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
        
        if start_date > end_date:
            log("Start date must be before end date", "ERROR")
            sys.exit(1)
            
        if end_date > datetime.now():
            log("End date cannot be in the future", "ERROR")
            sys.exit(1)
            
    except ValueError as e:
        log(f"Invalid date format: {e}", "ERROR")
        sys.exit(1)
    
    # Vérification des variables d'environnement
    if not SUPABASE_URL or not SUPABASE_KEY:
        log("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in environment", "ERROR")
        sys.exit(1)
    
    # Header
    print(f"{Colors.CYAN}{Colors.BOLD}🏃 INTERVALS.ICU WELLNESS INGESTION{Colors.END}")
    print(f"{Colors.CYAN}{'='*60}{Colors.END}")
    print(f"Period: {args.start_date} to {args.end_date}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    if args.athlete_id:
        print(f"Athlete: {args.athlete_id}")
    print()
    
    # Charger les athlètes
    athletes = get_athletes()
    if not athletes:
        log("No athletes found", "ERROR")
        sys.exit(1)
    
    # Filtrer par athlète si spécifié
    if args.athlete_id:
        athletes = [a for a in athletes if a['id'] == args.athlete_id]
        if not athletes:
            log(f"Athlete {args.athlete_id} not found", "ERROR")
            sys.exit(1)
    
    log(f"Processing {len(athletes)} athlete(s)")
    
    # Traiter chaque athlète
    for athlete in athletes:
        try:
            process_athlete_wellness(athlete, args.start_date, args.end_date, args.dry_run)
        except Exception as e:
            error_msg = f"Unexpected error processing {athlete['name']}: {str(e)[:100]}"
            log(error_msg, "ERROR")
            stats['errors'].append(error_msg)
            continue
    
    # Statistiques finales
    print_final_stats()

if __name__ == "__main__":
    main()
