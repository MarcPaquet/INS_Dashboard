#!/usr/bin/env python3
"""
Script to populate missing avg_hr values in activity_metadata table
by calculating them from the timeseries data.
"""

import os
import sys
from dotenv import load_dotenv
import pandas as pd
from supabase import create_client, Client

# Load environment
ENV_PATH = os.environ.get("INS_ENV_FILE") or "/Users/marcantoinepaquet/Documents/INS/shiny_env.env"
load_dotenv(dotenv_path=ENV_PATH, override=False)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Missing Supabase credentials in .env file")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def calculate_and_update_avg_hr():
    """Calculate avg_hr from timeseries and update activity_metadata."""
    
    # 1. Get all activities where avg_hr is NULL
    print("Fetching activities with missing avg_hr...")
    response = supabase.table("activity_metadata").select("activity_id, athlete_id").is_("avg_hr", "null").execute()
    activities_to_fix = response.data
    
    print(f"Found {len(activities_to_fix)} activities with missing avg_hr")
    
    if not activities_to_fix:
        print("No activities to fix!")
        return
    
    # 2. For each activity, calculate avg_hr from timeseries
    updated_count = 0
    skipped_count = 0
    
    for idx, activity in enumerate(activities_to_fix, 1):
        activity_id = activity["activity_id"]
        athlete_id = activity["athlete_id"]
        
        print(f"\n[{idx}/{len(activities_to_fix)}] Processing activity {activity_id}...")
        
        # Get timeseries data
        ts_response = supabase.table("activity").select("heartrate").eq("activity_id", activity_id).execute()
        
        if not ts_response.data:
            print(f"  ⚠️  No timeseries data found")
            skipped_count += 1
            continue
        
        # Extract heartrate values
        heartrates = []
        for record in ts_response.data:
            hr = record.get("heartrate")
            if hr is not None and hr > 0:
                heartrates.append(hr)
        
        if not heartrates:
            print(f"  ⚠️  No valid heartrate data in timeseries")
            skipped_count += 1
            continue
        
        # Calculate average
        avg_hr = sum(heartrates) / len(heartrates)
        print(f"  ✓ Calculated avg_hr: {avg_hr:.1f} bpm (from {len(heartrates)} samples)")
        
        # Update activity_metadata
        update_response = supabase.table("activity_metadata").update({
            "avg_hr": round(avg_hr, 1)
        }).eq("activity_id", activity_id).execute()
        
        if update_response.data:
            print(f"  ✓ Updated metadata")
            updated_count += 1
        else:
            print(f"  ✗ Failed to update")
            skipped_count += 1
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Updated: {updated_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Total:   {len(activities_to_fix)}")
    print(f"{'='*60}")

if __name__ == "__main__":
    print("="*60)
    print("FIX MISSING AVG_HR IN ACTIVITY_METADATA")
    print("="*60)
    
    confirm = input("\nThis will calculate and populate avg_hr from timeseries data.\nContinue? (yes/no): ")
    
    if confirm.lower() in ['yes', 'y']:
        calculate_and_update_avg_hr()
        print("\n✓ Done! Refresh your dashboard to see the updated data.")
    else:
        print("Cancelled.")
