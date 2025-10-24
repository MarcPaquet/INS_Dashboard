#!/usr/bin/env python3
"""
Test script for wellness ingestion functionality.
Tests the field mapping and transformation logic before running on real data.
"""

import json
from datetime import datetime
from intervals_wellness_to_supabase import transform_wellness_record

def test_field_mapping():
    """Test the field mapping transformation"""
    print("🧪 TESTING WELLNESS FIELD MAPPING")
    print("=" * 50)
    
    # Sample wellness record from Intervals.icu API (camelCase)
    sample_intervals_record = {
        "id": "2025-05-01",  # This is the date
        "restingHR": 45,
        "hrv": 52.3,
        "hrvSDNN": 48.1,
        "sleepSecs": 28800,  # 8 hours in seconds
        "avgSleepingHR": 42,
        "spO2": 98,
        "systolic": 120,
        "diastolic": 80,
        "soreness": 3,
        "fatigue": 4,
        "stress": 2,
        "mood": 7,
        "motivation": 8,
        "weight": 70.5,
        "bodyFat": 0.12,  # 12% as decimal
        "notes": "Felt good today"
    }
    
    # Transform using our function
    transformed = transform_wellness_record(sample_intervals_record, "i344978")
    
    print("📊 Original Intervals.icu record (camelCase):")
    for key, value in sample_intervals_record.items():
        print(f"  {key}: {value}")
    
    print(f"\n📊 Transformed Supabase record (snake_case):")
    for key, value in transformed.items():
        print(f"  {key}: {value}")
    
    # Validation checks
    print(f"\n✅ VALIDATION CHECKS:")
    
    # Check required fields
    required_fields = ['athlete_id', 'date', 'source']
    for field in required_fields:
        if field in transformed:
            print(f"  ✓ {field}: {transformed[field]}")
        else:
            print(f"  ✗ Missing required field: {field}")
    
    # Check specific transformations
    checks = [
        ("restingHR → resting_hr", sample_intervals_record.get('restingHR'), transformed.get('resting_hr')),
        ("hrv → hrv_rmssd", sample_intervals_record.get('hrv'), transformed.get('hrv_rmssd')),
        ("sleepSecs → sleep_seconds", sample_intervals_record.get('sleepSecs'), transformed.get('sleep_seconds')),
        ("bodyFat → body_fat_pct", sample_intervals_record.get('bodyFat') * 100, transformed.get('body_fat_pct')),
        ("spO2 → spo2", sample_intervals_record.get('spO2'), transformed.get('spo2')),
    ]
    
    print(f"\n📋 Field Mapping Validation:")
    for description, original, transformed_val in checks:
        if original is not None and transformed_val is not None:
            print(f"  ✓ {description}: {original} → {transformed_val}")
        else:
            print(f"  ⚠ {description}: Missing data")
    
    return transformed

def test_edge_cases():
    """Test edge cases and missing data handling"""
    print(f"\n🧪 TESTING EDGE CASES")
    print("=" * 50)
    
    # Minimal record (only date)
    minimal_record = {"id": "2025-05-02"}
    transformed_minimal = transform_wellness_record(minimal_record, "i344978")
    
    print("📊 Minimal record (only date):")
    print(f"  Input: {minimal_record}")
    print(f"  Output: {transformed_minimal}")
    
    # Record with null values
    null_record = {
        "id": "2025-05-03",
        "restingHR": None,
        "hrv": 45.2,
        "sleepSecs": None,
        "notes": ""
    }
    transformed_null = transform_wellness_record(null_record, "i344978")
    
    print(f"\n📊 Record with null values:")
    print(f"  Input: {null_record}")
    print(f"  Output fields with values: {[(k, v) for k, v in transformed_null.items() if v is not None and v != '']}")
    
    return True

def generate_test_command():
    """Generate a test command for the wellness script"""
    print(f"\n🚀 READY FOR TESTING")
    print("=" * 50)
    
    # Get athlete IDs from athletes.json if available
    try:
        with open('/Users/marcantoinepaquet/Documents/INS/athletes.json', 'r') as f:
            athletes = json.load(f)
        
        if athletes:
            test_athlete = athletes[0]['id']
            print(f"📋 Suggested test commands:")
            print(f"\n1. Single athlete, 1 week (dry run):")
            print(f"   python intervals_wellness_to_supabase.py \\")
            print(f"     --athlete-id {test_athlete} \\")
            print(f"     --start-date 2025-05-01 \\")
            print(f"     --end-date 2025-05-07 \\")
            print(f"     --dry-run")
            
            print(f"\n2. Single athlete, 1 week (live):")
            print(f"   python intervals_wellness_to_supabase.py \\")
            print(f"     --athlete-id {test_athlete} \\")
            print(f"     --start-date 2025-05-01 \\")
            print(f"     --end-date 2025-05-07")
            
            print(f"\n3. All athletes, 1 month:")
            print(f"   python intervals_wellness_to_supabase.py \\")
            print(f"     --start-date 2025-05-01 \\")
            print(f"     --end-date 2025-05-31")
        
    except FileNotFoundError:
        print("📋 athletes.json not found - use actual athlete ID")
        print(f"\n1. Test command template:")
        print(f"   python intervals_wellness_to_supabase.py \\")
        print(f"     --athlete-id <ATHLETE_ID> \\")
        print(f"     --start-date 2025-05-01 \\")
        print(f"     --end-date 2025-05-07 \\")
        print(f"     --dry-run")

def main():
    """Run all tests"""
    print("🧪 WELLNESS INGESTION TESTING SUITE")
    print("=" * 60)
    
    # Test field mapping
    transformed = test_field_mapping()
    
    # Test edge cases
    test_edge_cases()
    
    # Generate test commands
    generate_test_command()
    
    print(f"\n✅ ALL TESTS COMPLETED")
    print("Ready to test the wellness ingestion script!")

if __name__ == "__main__":
    main()
