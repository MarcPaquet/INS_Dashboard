#!/usr/bin/env python3
"""Validate activity intervals data integrity."""

"""
Check data integrity across multiple activities to see if this is widespread.
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

def check_multiple_activities():
    """Check data integrity across multiple activities."""
    print("🔍 DATA INTEGRITY CHECK - Multiple Activities")
    print("=" * 70)
    
    # Get activities with intervals
    test_activities = ["i78555696", "i78236291", "i77923480", "i78555673", "i77295415"]
    
    results = []
    
    for activity_id in test_activities:
        print(f"\n📊 Checking {activity_id}...")
        
        try:
            # Get activity time range
            activity_response = supabase.table("activity") \
                .select("time") \
                .eq("activity_id", activity_id) \
                .order("time") \
                .execute()
            
            # Get intervals time range
            intervals_response = supabase.table("activity_intervals") \
                .select("start_time, end_time") \
                .eq("activity_id", activity_id) \
                .execute()
            
            if not activity_response.data:
                print(f"   ❌ No timeseries data")
                results.append({"activity_id": activity_id, "status": "NO_TIMESERIES"})
                continue
                
            if not intervals_response.data:
                print(f"   ❌ No intervals data")
                results.append({"activity_id": activity_id, "status": "NO_INTERVALS"})
                continue
            
            # Check ranges
            activity_df = pd.DataFrame(activity_response.data)
            intervals_df = pd.DataFrame(intervals_response.data)
            
            activity_min = activity_df['time'].min()
            activity_max = activity_df['time'].max()
            intervals_min = intervals_df['start_time'].min()
            intervals_max = intervals_df['end_time'].max()
            
            print(f"   📊 Activity range: {activity_min} to {activity_max} ({activity_max - activity_min}s)")
            print(f"   📊 Intervals range: {intervals_min} to {intervals_max} ({intervals_max - intervals_min}s)")
            
            # Check alignment
            if intervals_min >= activity_min and intervals_max <= activity_max:
                print(f"   ✅ ALIGNED")
                results.append({"activity_id": activity_id, "status": "ALIGNED"})
            else:
                print(f"   ❌ MISALIGNED")
                results.append({"activity_id": activity_id, "status": "MISALIGNED"})
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results.append({"activity_id": activity_id, "status": "ERROR"})
    
    # Summary
    print(f"\n📋 SUMMARY:")
    print("-" * 50)
    aligned = sum(1 for r in results if r["status"] == "ALIGNED")
    misaligned = sum(1 for r in results if r["status"] == "MISALIGNED")
    errors = sum(1 for r in results if r["status"] in ["NO_TIMESERIES", "NO_INTERVALS", "ERROR"])
    
    print(f"✅ Aligned: {aligned}")
    print(f"❌ Misaligned: {misaligned}")
    print(f"⚠️  Errors: {errors}")
    
    if misaligned > aligned:
        print(f"\n🚨 CRITICAL: Data integrity issue affects most activities!")
        print(f"   Recommendation: Re-import activities with proper timeseries data")
    elif aligned > 0:
        print(f"\n✅ Some activities are properly aligned")
        print(f"   Recommendation: Use aligned activities for testing")
        
        # Find a good test activity
        for r in results:
            if r["status"] == "ALIGNED":
                print(f"   🎯 Try testing with: {r['activity_id']}")
                break
    
    return results

if __name__ == "__main__":
    check_multiple_activities()
