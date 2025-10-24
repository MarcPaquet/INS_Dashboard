#!/usr/bin/env python3
"""
Check the actual database schema to understand the data structure.
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

def check_database_schema():
    """Check the actual database schema and data structure."""
    print("🔍 DATABASE SCHEMA CHECK")
    print("=" * 50)
    
    # Check activity_metadata table
    print("\n1️⃣ activity_metadata table:")
    try:
        metadata_response = supabase.table("activity_metadata") \
            .select("*") \
            .limit(1) \
            .execute()
        
        if metadata_response.data:
            sample = metadata_response.data[0]
            print(f"   ✅ Columns: {list(sample.keys())}")
            print(f"   📊 Sample record: {sample['activity_id']} - {sample.get('date', 'N/A')}")
        else:
            print("   ❌ No data found")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Check activity table (timeseries)
    print("\n2️⃣ activity table (timeseries):")
    try:
        activity_response = supabase.table("activity") \
            .select("*") \
            .limit(1) \
            .execute()
        
        if activity_response.data:
            sample = activity_response.data[0]
            print(f"   ✅ Columns: {list(sample.keys())}")
            print(f"   📊 Sample record: {sample['activity_id']} - time: {sample.get('time', 'N/A')}")
        else:
            print("   ❌ No data found")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Check activity_intervals table
    print("\n3️⃣ activity_intervals table:")
    try:
        intervals_response = supabase.table("activity_intervals") \
            .select("*") \
            .limit(1) \
            .execute()
        
        if intervals_response.data:
            sample = intervals_response.data[0]
            print(f"   ✅ Columns: {list(sample.keys())}")
            print(f"   📊 Sample record: {sample['activity_id']} - start: {sample.get('start_time', 'N/A')}")
        else:
            print("   ❌ No data found")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Check athlete table
    print("\n4️⃣ athlete table:")
    try:
        athlete_response = supabase.table("athlete") \
            .select("*") \
            .limit(1) \
            .execute()
        
        if athlete_response.data:
            sample = athlete_response.data[0]
            print(f"   ✅ Columns: {list(sample.keys())}")
            print(f"   📊 Sample record: {sample['athlete_id']} - {sample.get('name', 'N/A')}")
        else:
            print("   ❌ No data found")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test a specific activity we know works
    print(f"\n🎯 Testing known working activity: i76948562")
    try:
        # Check metadata
        metadata_response = supabase.table("activity_metadata") \
            .select("*") \
            .eq("activity_id", "i76948562") \
            .execute()
        
        if metadata_response.data:
            metadata = metadata_response.data[0]
            print(f"   ✅ Metadata found: {metadata.get('date')} - {metadata.get('type')}")
            print(f"   📊 Duration: {metadata.get('duration_min', 'N/A')} min")
            print(f"   📊 Source: {metadata.get('source', 'N/A')}")
        
        # Check timeseries count
        timeseries_response = supabase.table("activity") \
            .select("time", count="exact") \
            .eq("activity_id", "i76948562") \
            .execute()
        
        print(f"   📊 Timeseries records: {timeseries_response.count}")
        
        # Check intervals count
        intervals_response = supabase.table("activity_intervals") \
            .select("start_time", count="exact") \
            .eq("activity_id", "i76948562") \
            .execute()
        
        print(f"   📊 Intervals: {intervals_response.count}")
        
    except Exception as e:
        print(f"   ❌ Error testing specific activity: {e}")

if __name__ == "__main__":
    check_database_schema()
