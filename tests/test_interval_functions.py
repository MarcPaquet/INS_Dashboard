#!/usr/bin/env python3
"""
Quick test of Phase 1.5 interval data layer functions.
"""

import os
import sys
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment
load_dotenv('shiny_env.env')

# Initialize Supabase
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(url, key)

# Import the functions we just created
sys.path.append('/Users/marcantoinepaquet/Documents/INS')

def get_activity_intervals(activity_id: str) -> pd.DataFrame:
    """Copy of the function from supabase_shiny.py for testing."""
    if not activity_id:
        return pd.DataFrame()
    
    try:
        response = supabase.table("activity_intervals") \
            .select("*") \
            .eq("activity_id", activity_id) \
            .order("start_time") \
            .execute()
        
        df = pd.DataFrame(response.data)
        
        if df.empty:
            return df
        
        # Calculate pace (min/km) - handle division by zero
        df['pace_minkm'] = np.where(
            (df['distance'] > 0) & (df['moving_time'] > 0),
            (df['moving_time'] / 60) / (df['distance'] / 1000),
            np.nan
        )
        
        # Format duration as MM:SS
        df['duration_fmt'] = df['moving_time'].apply(
            lambda x: f"{int(x//60):02d}:{int(x%60):02d}" if pd.notna(x) and x >= 0 else "-"
        )
        
        # Format pace as M:SS/km
        df['pace_fmt'] = df['pace_minkm'].apply(
            lambda x: f"{int(x)}:{int((x % 1) * 60):02d}/km" if pd.notna(x) and x > 0 else "-"
        )
        
        # Format distance
        df['distance_fmt'] = df['distance'].apply(
            lambda x: f"{x/1000:.2f} km" if pd.notna(x) and x > 0 else "-"
        )
        
        return df
        
    except Exception as e:
        print(f"❌ Error fetching intervals for {activity_id}: {e}")
        return pd.DataFrame()

def classify_intervals(df: pd.DataFrame) -> pd.DataFrame:
    """Copy of the function from supabase_shiny.py for testing."""
    if df.empty or len(df) < 2:
        # Single or no intervals - classify as work if present
        if not df.empty:
            df['interval_type'] = 'work'
        return df
    
    df = df.copy()  # Avoid modifying original
    
    # Calculate intensity score (0-1 normalized)
    if 'average_heartrate' in df.columns and df['average_heartrate'].notna().any():
        hr_values = df['average_heartrate'].dropna()
        if len(hr_values) > 1:
            hr_min = hr_values.min()
            hr_max = hr_values.max()
            if hr_max > hr_min:
                df['hr_norm'] = (df['average_heartrate'] - hr_min) / (hr_max - hr_min)
            else:
                df['hr_norm'] = 0.5
        else:
            df['hr_norm'] = 0.5
    else:
        df['hr_norm'] = 0.5
    
    if 'pace_minkm' in df.columns and df['pace_minkm'].notna().any():
        pace_values = df['pace_minkm'].dropna()
        if len(pace_values) > 1:
            pace_min = pace_values.min()
            pace_max = pace_values.max()
            if pace_max > pace_min:
                # Faster pace = higher score (invert)
                df['pace_norm'] = 1 - ((df['pace_minkm'] - pace_min) / (pace_max - pace_min))
            else:
                df['pace_norm'] = 0.5
        else:
            df['pace_norm'] = 0.5
    else:
        df['pace_norm'] = 0.5
    
    # Fill NaN values with 0.5 (neutral)
    df['hr_norm'] = df['hr_norm'].fillna(0.5)
    df['pace_norm'] = df['pace_norm'].fillna(0.5)
    
    df['intensity'] = (df['hr_norm'] + df['pace_norm']) / 2
    median_intensity = df['intensity'].median()
    
    # Classify intervals
    df['interval_type'] = 'unknown'
    for idx in range(len(df)):
        moving_time = df.iloc[idx]['moving_time'] if pd.notna(df.iloc[idx]['moving_time']) else 0
        
        if idx == 0 and moving_time > 300:  # First interval > 5 min
            df.at[df.index[idx], 'interval_type'] = 'warmup'
        elif idx == len(df) - 1 and moving_time > 300:  # Last interval > 5 min
            df.at[df.index[idx], 'interval_type'] = 'cooldown'
        elif df.iloc[idx]['intensity'] > median_intensity:
            df.at[df.index[idx], 'interval_type'] = 'work'
        else:
            df.at[df.index[idx], 'interval_type'] = 'rest'
    
    return df

def detect_workout_pattern(df: pd.DataFrame) -> str:
    """Copy of the function from supabase_shiny.py for testing."""
    if df.empty:
        return ""
    
    work_intervals = df[df['interval_type'] == 'work']
    
    if len(work_intervals) == 0:
        return ""
    
    # Check if all work intervals are similar distance
    distances = work_intervals['distance'].dropna().values
    if len(distances) == 0:
        return ""
    
    distance_std = np.std(distances)
    distance_mean = np.mean(distances)
    
    # Within 50m tolerance → repetitions
    if distance_std < 50 and len(distances) > 1:
        count = len(work_intervals)
        if distance_mean >= 1000:
            dist_str = f"{distance_mean/1000:.2f}km"
        else:
            dist_str = f"{int(distance_mean)}m"
        
        return f"{count} répétitions de {dist_str} avec récupération"
    else:
        # Variable distances - show pattern
        if len(distances) > 1:
            dist_list = []
            for d in distances:
                if d >= 1000:
                    dist_list.append(f"{d/1000:.2f}km")
                else:
                    dist_list.append(f"{int(d)}m")
            return f"Entraînement fractionné: {' - '.join(dist_list)}"
        else:
            # Single work interval
            d = distances[0]
            if d >= 1000:
                dist_str = f"{d/1000:.2f}km"
            else:
                dist_str = f"{int(d)}m"
            return f"Intervalle unique de {dist_str}"

def test_interval_functions():
    """Test the interval data layer functions."""
    print("🧪 Testing Phase 1.5 Interval Functions")
    print("=" * 50)
    
    # Test activity from our discovery
    test_activity = "i78514252"  # 10 intervals
    
    print(f"📊 Testing with activity: {test_activity}")
    
    # Test 1: get_activity_intervals
    print("\n1️⃣ Testing get_activity_intervals...")
    intervals_df = get_activity_intervals(test_activity)
    
    if intervals_df.empty:
        print("❌ No intervals found!")
        return
    
    print(f"✅ Found {len(intervals_df)} intervals")
    print(f"   Columns: {list(intervals_df.columns)}")
    print(f"   Sample pace: {intervals_df['pace_fmt'].iloc[0] if 'pace_fmt' in intervals_df.columns else 'N/A'}")
    print(f"   Sample duration: {intervals_df['duration_fmt'].iloc[0] if 'duration_fmt' in intervals_df.columns else 'N/A'}")
    
    # Test 2: classify_intervals
    print("\n2️⃣ Testing classify_intervals...")
    classified_df = classify_intervals(intervals_df)
    
    if 'interval_type' in classified_df.columns:
        type_counts = classified_df['interval_type'].value_counts()
        print(f"✅ Classification results:")
        for interval_type, count in type_counts.items():
            print(f"   {interval_type}: {count}")
    else:
        print("❌ No interval_type column found!")
    
    # Test 3: detect_workout_pattern
    print("\n3️⃣ Testing detect_workout_pattern...")
    pattern = detect_workout_pattern(classified_df)
    
    if pattern:
        print(f"✅ Detected pattern: {pattern}")
    else:
        print("❌ No pattern detected")
    
    # Test 4: Show sample data
    print("\n📋 Sample Interval Data:")
    print("─" * 80)
    if len(classified_df) > 0:
        cols_to_show = ['duration_fmt', 'distance_fmt', 'pace_fmt', 'interval_type']
        available_cols = [col for col in cols_to_show if col in classified_df.columns]
        
        for i, row in classified_df.head(5).iterrows():
            print(f"Interval {i+1}: ", end="")
            for col in available_cols:
                print(f"{col}={row[col]} ", end="")
            print()
    
    print("\n✅ All tests completed!")

if __name__ == "__main__":
    test_interval_functions()
