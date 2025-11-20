#!/usr/bin/env python3
"""Track import status per athlete."""

"""Vérifie la progression de l'import et identifie où reprendre"""

import os
import requests
import json
from datetime import datetime

# Load env
from dotenv import load_dotenv
load_dotenv(".env.dashboard.local")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY")

# Load athletes
with open("test_athlete.json", "r") as f:
    athletes = json.load(f)

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

print("\n" + "="*80)
print("📊 PROGRESSION DE L'IMPORT")
print("="*80 + "\n")

for athlete in athletes:
    athlete_id = athlete['id']
    name = athlete['name']
    
    # Get FIT activities count in Supabase
    url = f"{SUPABASE_URL}/rest/v1/activity_metadata"
    params = {
        "select": "activity_id,date,start_time",
        "athlete_id": f"eq.{athlete_id}",
        "source": "eq.intervals_fit",
        "order": "start_time.desc"
    }
    
    response = requests.get(url, headers=headers, params=params)
    imported = response.json()
    
    print(f"\n👤 {name} ({athlete_id})")
    print(f"   ✓ {len(imported)} activités FIT importées")
    
    if imported:
        # Get date range
        dates = [a['date'] for a in imported if a.get('date')]
        if dates:
            dates_sorted = sorted(dates)
            print(f"   📅 Plage: {dates_sorted[0]} → {dates_sorted[-1]}")
            
            # Latest activity
            latest = imported[0]
            print(f"   🕒 Dernière: {latest['activity_id']} - {latest['date']}")
    else:
        print(f"   ⚠️  Aucune activité FIT trouvée")

print("\n" + "="*80)
print("💡 RECOMMANDATION")
print("="*80)
print("\nPour reprendre l'import complet:")
print("  /opt/anaconda3/bin/python3 intervals_hybrid_to_supabase.py \\")
print("    --oldest 2025-05-01 \\")
print("    --newest 2025-07-31")
print("\nLe script va automatiquement:")
print("  • Détecter les activités déjà importées (merge-duplicates)")
print("  • Réimporter les manquantes")
print("  • Corriger celles avec mauvaises durées\n")
