#!/usr/bin/env python3
"""
Find activities with intervals for Phase 1.5 testing.
Critical first step before implementing intervals visualization.
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

def find_test_activities():
    """Find activities with intervals for testing."""
    print("🔍 Searching for activities with intervals...")
    
    try:
        # First, get all activities with intervals
        intervals_response = supabase.table("activity_intervals") \
            .select("activity_id") \
            .execute()
        
        if not intervals_response.data:
            print("❌ NO ACTIVITIES WITH INTERVALS FOUND!")
            print("\n🚨 CRITICAL: Need to import activities with structured workouts")
            print("   - Check Intervals.icu for athletes with interval sessions")
            print("   - Run test import before continuing with Phase 1.5")
            return []
        
        # Get unique activity IDs with intervals
        activity_ids_with_intervals = list(set(row['activity_id'] for row in intervals_response.data))
        
        # Get activity metadata for these activities
        activities_response = supabase.table("activity_metadata") \
            .select("activity_id, date, athlete_id, type, distance_m") \
            .in_("activity_id", activity_ids_with_intervals) \
            .in_("type", ["Run", "TrailRun"]) \
            .order("date", desc=True) \
            .execute()
        
        if not activities_response.data:
            print("❌ NO RUN ACTIVITIES WITH INTERVALS FOUND!")
            return []
        
        # Get athlete names
        athlete_ids = list(set(row['athlete_id'] for row in activities_response.data))
        athletes_response = supabase.table("athlete") \
            .select("athlete_id, name") \
            .in_("athlete_id", athlete_ids) \
            .execute()
        
        athlete_names = {row['athlete_id']: row['name'] for row in athletes_response.data}
        
        # Count intervals per activity
        interval_counts = {}
        for row in intervals_response.data:
            activity_id = row['activity_id']
            interval_counts[activity_id] = interval_counts.get(activity_id, 0) + 1
        
        # Build result with interval counts
        results = []
        for activity in activities_response.data:
            activity_id = activity['activity_id']
            if activity_id in interval_counts:
                results.append({
                    'activity_id': activity_id,
                    'date': activity['date'],
                    'athlete_name': athlete_names.get(activity['athlete_id'], 'Unknown'),
                    'type': activity['type'],
                    'distance_km': round(activity['distance_m'] / 1000.0, 2) if activity['distance_m'] else 0,
                    'interval_count': interval_counts[activity_id]
                })
        
        # Sort by date desc, then by interval count desc
        results.sort(key=lambda x: (x['date'], x['interval_count']), reverse=True)
        results = results[:15]  # Limit to 15
        
        if not results:
            print("❌ NO ACTIVITIES WITH INTERVALS FOUND!")
            print("\n🚨 CRITICAL: Need to import activities with structured workouts")
            print("   - Check Intervals.icu for athletes with interval sessions")
            print("   - Run test import before continuing with Phase 1.5")
            return []
        
        print(f"✅ Found {len(results)} activities with intervals:")
        print("\n📊 Test Data Available:")
        print("─" * 80)
        print(f"{'Activity ID':<15} {'Date':<12} {'Athlete':<20} {'Type':<10} {'Dist':<8} {'Intervals'}")
        print("─" * 80)
        
        for row in results:
            print(f"{row['activity_id']:<15} {row['date']:<12} {row['athlete_name']:<20} "
                  f"{row['type']:<10} {row['distance_km']:<8} {row['interval_count']}")
        
        # Analyze interval distribution
        total_intervals = sum(row['interval_count'] for row in results)
        max_intervals = max(row['interval_count'] for row in results)
        
        print("─" * 80)
        print(f"📈 Summary: {len(results)} activities, {total_intervals} total intervals")
        print(f"   Max intervals per activity: {max_intervals}")
        
        # Recommend test activities
        print("\n🎯 Recommended Test Activities:")
        simple = [r for r in results if 3 <= r['interval_count'] <= 5]
        complex_activities = [r for r in results if r['interval_count'] >= 8]
        
        if simple:
            print(f"   Simple (3-5 intervals): {simple[0]['activity_id']} ({simple[0]['interval_count']} intervals)")
        if complex_activities:
            print(f"   Complex (8+ intervals): {complex_activities[0]['activity_id']} ({complex_activities[0]['interval_count']} intervals)")
        
        return results
        
    except Exception as e:
        print(f"❌ Error querying intervals: {e}")
        return []

def check_interval_details(activity_id: str):
    """Check detailed interval structure for a specific activity."""
    print(f"\n🔍 Analyzing interval structure for {activity_id}...")
    
    try:
        response = supabase.table("activity_intervals") \
            .select("*") \
            .eq("activity_id", activity_id) \
            .order("start_time") \
            .execute()
        
        if not response.data:
            print(f"❌ No intervals found for {activity_id}")
            return
        
        print(f"✅ Found {len(response.data)} intervals:")
        print("\n📊 Interval Details:")
        print("─" * 100)
        print(f"{'#':<3} {'Start':<8} {'End':<8} {'Duration':<10} {'Distance':<10} {'HR':<6} {'Watts':<6} {'Type'}")
        print("─" * 100)
        
        for i, interval in enumerate(response.data, 1):
            duration = interval.get('moving_time', 0)
            duration_fmt = f"{int(duration//60):02d}:{int(duration%60):02d}"
            distance = interval.get('distance', 0)
            distance_fmt = f"{distance/1000:.2f}km" if distance else "-"
            hr = int(interval.get('average_heartrate', 0)) if interval.get('average_heartrate') else "-"
            watts = int(interval.get('average_watts', 0)) if interval.get('average_watts') else "-"
            interval_type = interval.get('type', 'unknown')
            
            print(f"{i:<3} {interval.get('start_time', 0):<8.0f} {interval.get('end_time', 0):<8.0f} "
                  f"{duration_fmt:<10} {distance_fmt:<10} {hr:<6} {watts:<6} {interval_type}")
        
        print("─" * 100)
        
        # Check for t_active fields
        has_t_active = any(interval.get('start_t_active') is not None for interval in response.data)
        print(f"📍 t_active fields present: {'✅ Yes' if has_t_active else '❌ No (will need calculation)'}")
        
    except Exception as e:
        print(f"❌ Error analyzing intervals: {e}")

if __name__ == "__main__":
    print("🎯 Phase 1.5 - Intervals Data Discovery")
    print("=" * 50)
    
    activities = find_test_activities()
    
    if activities:
        # Analyze the first activity in detail
        first_activity = activities[0]['activity_id']
        check_interval_details(first_activity)
        
        print(f"\n✅ READY FOR PHASE 1.5 IMPLEMENTATION")
        print(f"   Use activity {first_activity} for initial testing")
    else:
        print(f"\n🚨 BLOCKED: No interval data available")
        print(f"   Must import activities with intervals before proceeding")
