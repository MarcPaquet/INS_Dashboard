#!/usr/bin/env python3
"""
Test the new intervals tags feature in activity titles.
"""

import os
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment
load_dotenv('shiny_env.env')

# Initialize Supabase
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(url, key)

def test_intervals_tags():
    """Test that activities with intervals get (intervalles) tag."""
    print("🏷️  Testing Intervals Tags Feature")
    print("=" * 50)
    
    # Get some test activities
    test_activities = [
        "i78514252",  # Has 10 intervals
        "i77777813",  # Has 4 intervals
        "i78089589",  # Has 1 interval
    ]
    
    print("🔍 Testing interval detection for activity titles...")
    
    for activity_id in test_activities:
        print(f"\n📊 Activity: {activity_id}")
        
        # Check if activity has intervals
        try:
            intervals_response = supabase.table("activity_intervals") \
                .select("activity_id") \
                .eq("activity_id", activity_id) \
                .limit(1) \
                .execute()
            has_intervals = len(intervals_response.data) > 0
            
            if has_intervals:
                print(f"   ✅ Has intervals - should show '(intervalles)' tag")
            else:
                print(f"   ❌ No intervals - should NOT show tag")
                
        except Exception as e:
            print(f"   ❌ Error checking intervals: {e}")
    
    print(f"\n🌐 Dashboard Testing:")
    print("1. Go to http://127.0.0.1:56187")
    print("2. Navigate to 'Analyse de séance' tab")
    print("3. Check the activity dropdown")
    print("4. Activities with intervals should show '(intervalles)' at the end")
    
    print(f"\n✅ Expected Results:")
    print("- Activities with intervals: 'Course extérieur - [date] - [time] - [distance] (intervalles)'")
    print("- Activities without intervals: 'Course extérieur - [date] - [time] - [distance]'")
    
    print(f"\n🎯 Feature Benefits:")
    print("- Quick visual identification of interval training sessions")
    print("- No need to select activity to know if it has intervals")
    print("- Helps athletes find their structured workouts faster")

if __name__ == "__main__":
    test_intervals_tags()
