#!/usr/bin/env python3
"""Generate athletes.json template from database."""

"""
Create athletes.json file from existing database data for wellness ingestion.
"""

import os
import json
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment
load_dotenv('shiny_env.env')

# Initialize Supabase
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(url, key)

def create_athletes_json():
    """Create athletes.json from database data."""
    print("🔧 CREATING ATHLETES.JSON FROM DATABASE")
    print("=" * 50)
    
    try:
        # Get athletes from database
        response = supabase.table("athlete") \
            .select("athlete_id, name") \
            .execute()
        
        if not response.data:
            print("❌ No athletes found in database")
            return
        
        # We need API keys for the wellness script
        # Since we don't have them in the database, we'll need to create a template
        athletes_data = []
        
        print("⚠️  NOTE: API keys are required for wellness ingestion.")
        print("Creating template - you'll need to add actual API keys.")
        print()
        
        for athlete in response.data:
            athlete_entry = {
                "id": athlete["athlete_id"],
                "name": athlete["name"],
                "api_key": "YOUR_API_KEY_HERE"  # Placeholder
            }
            athletes_data.append(athlete_entry)
            print(f"  - {athlete['name']} (ID: {athlete['athlete_id']})")
        
        # Save to athletes.json
        with open('/Users/marcantoinepaquet/Documents/INS/athletes.json', 'w') as f:
            json.dump(athletes_data, f, indent=2)
        
        print(f"\n✅ Created athletes.json with {len(athletes_data)} athletes")
        print("📝 Next steps:")
        print("1. Edit athletes.json and add real API keys")
        print("2. Test wellness ingestion with dry-run")
        print("3. Run live wellness ingestion")
        
        # Show sample content
        print(f"\n📄 Sample athletes.json content:")
        print(json.dumps(athletes_data[:2], indent=2))
        
    except Exception as e:
        print(f"❌ Error creating athletes.json: {e}")

if __name__ == "__main__":
    create_athletes_json()
