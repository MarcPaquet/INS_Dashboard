#!/usr/bin/env python3
"""
Get a test athlete ID from existing data for wellness testing.
"""

import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment
load_dotenv('shiny_env.env')

# Initialize Supabase
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(url, key)

def get_test_athlete():
    """Get an athlete ID for testing wellness ingestion."""
    print("🔍 FINDING TEST ATHLETE FOR WELLNESS INGESTION")
    print("=" * 60)
    
    try:
        # Get athletes from existing data
        response = supabase.table("athlete") \
            .select("athlete_id, name") \
            .execute()
        
        if response.data:
            print(f"📊 Available athletes:")
            for athlete in response.data:
                print(f"  - {athlete['name']} (ID: {athlete['athlete_id']})")
            
            # Use first athlete for testing
            test_athlete = response.data[0]
            print(f"\n🎯 RECOMMENDED TEST COMMANDS:")
            print(f"Using athlete: {test_athlete['name']} (ID: {test_athlete['athlete_id']})")
            
            print(f"\n1. DRY RUN TEST (recommended first):")
            print(f"python intervals_wellness_to_supabase.py \\")
            print(f"  --athlete-id {test_athlete['athlete_id']} \\")
            print(f"  --start-date 2025-05-01 \\")
            print(f"  --end-date 2025-05-07 \\")
            print(f"  --dry-run")
            
            print(f"\n2. LIVE TEST (after dry run succeeds):")
            print(f"python intervals_wellness_to_supabase.py \\")
            print(f"  --athlete-id {test_athlete['athlete_id']} \\")
            print(f"  --start-date 2025-05-01 \\")
            print(f"  --end-date 2025-05-07")
            
            return test_athlete['athlete_id']
        else:
            print("❌ No athletes found in database")
            return None
            
    except Exception as e:
        print(f"❌ Error getting athletes: {e}")
        return None

if __name__ == "__main__":
    get_test_athlete()
