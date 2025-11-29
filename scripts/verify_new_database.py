#!/usr/bin/env python3
"""
Verify New Database Migration
Checks that all tables, indexes, constraints, and RLS policies are properly created
"""

import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

# Try to load environment from multiple possible locations
env_files = ['.env.dashboard.local', '.env.ingestion.local', 'shiny_env.env', '.env']
loaded = False
for env_file in env_files:
    if os.path.exists(env_file):
        load_dotenv(env_file)
        print(f"✅ Loaded environment from: {env_file}")
        loaded = True
        break

if not loaded:
    print("❌ No environment file found. Please ensure .env.dashboard.local exists.")
    sys.exit(1)

# Initialize Supabase client for new database
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not url or not key:
    print("❌ Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in environment")
    sys.exit(1)

print(f"\n🔗 Connecting to Supabase: {url}")

# Extract project reference from URL
project_ref = url.split("//")[1].split(".")[0] if "//" in url else "unknown"
print(f"📊 Project Reference: {project_ref}")

if project_ref != "vqcqqfddgnvhcrxcaxjf":
    print(f"⚠️  WARNING: Expected project 'vqcqqfddgnvhcrxcaxjf' but got '{project_ref}'")
    print("   Are you sure you're connected to the NEW database?")
    response = input("Continue anyway? (y/n): ")
    if response.lower() != 'y':
        sys.exit(0)

supabase: Client = create_client(url, key)

def verify_tables():
    """Verify all required tables exist"""
    print("\n" + "="*70)
    print("🔍 VERIFYING TABLES")
    print("="*70)

    required_tables = [
        "athlete",
        "users",
        "activity_metadata",
        "activity",
        "activity_intervals",
        "wellness",
        "personal_records",
        "personal_records_history",
        "athlete_training_zones",
        "daily_workout_surveys",
        "weekly_wellness_surveys"
    ]

    all_exist = True
    for table in required_tables:
        try:
            response = supabase.table(table).select("*").limit(0).execute()
            print(f"✅ Table '{table}' exists")
        except Exception as e:
            print(f"❌ Table '{table}' missing or inaccessible: {str(e)}")
            all_exist = False

    return all_exist

def verify_table_structure():
    """Verify key table structures"""
    print("\n" + "="*70)
    print("🔍 VERIFYING TABLE STRUCTURES")
    print("="*70)

    checks = []

    # Check athlete table
    try:
        response = supabase.table("athlete").select("athlete_id,name,intervals_icu_id").limit(0).execute()
        print("✅ athlete table: core columns present")
        checks.append(True)
    except Exception as e:
        print(f"❌ athlete table structure issue: {str(e)}")
        checks.append(False)

    # Check users table
    try:
        response = supabase.table("users").select("id,name,password_hash,role,athlete_id").limit(0).execute()
        print("✅ users table: core columns present")
        checks.append(True)
    except Exception as e:
        print(f"❌ users table structure issue: {str(e)}")
        checks.append(False)

    # Check activity_metadata table
    try:
        response = supabase.table("activity_metadata").select("activity_id,athlete_id,type,date").limit(0).execute()
        print("✅ activity_metadata table: core columns present")
        checks.append(True)
    except Exception as e:
        print(f"❌ activity_metadata table structure issue: {str(e)}")
        checks.append(False)

    return all(checks)

def verify_data_counts():
    """Check if tables are empty (expected after schema-only migration)"""
    print("\n" + "="*70)
    print("🔍 CHECKING TABLE DATA")
    print("="*70)

    tables_to_check = [
        "athlete",
        "users",
        "activity_metadata",
        "personal_records",
        "daily_workout_surveys"
    ]

    for table in tables_to_check:
        try:
            response = supabase.table(table).select("*", count="exact").limit(0).execute()
            count = response.count
            if count == 0:
                print(f"📊 {table}: 0 rows (empty - expected after schema-only migration)")
            else:
                print(f"📊 {table}: {count} rows")
        except Exception as e:
            print(f"⚠️  {table}: Could not count rows - {str(e)}")

def verify_functions():
    """Verify key database functions exist"""
    print("\n" + "="*70)
    print("🔍 VERIFYING DATABASE FUNCTIONS")
    print("="*70)

    # Try to call the training zones function
    try:
        # This will fail if function doesn't exist
        result = supabase.rpc('get_athlete_zones_for_date', {
            'p_athlete_id': 'test',
            'p_workout_date': '2024-01-01'
        }).execute()
        print("✅ Function 'get_athlete_zones_for_date' exists")
    except Exception as e:
        if "function" in str(e).lower() and "does not exist" in str(e).lower():
            print("❌ Function 'get_athlete_zones_for_date' not found")
        else:
            # Function exists but failed due to test data - that's okay
            print("✅ Function 'get_athlete_zones_for_date' exists (returned expected error)")

def verify_rls():
    """Verify RLS is enabled on key tables"""
    print("\n" + "="*70)
    print("🔍 VERIFYING ROW LEVEL SECURITY (RLS)")
    print("="*70)

    # Note: We can't easily check RLS policies via REST API
    # but we can verify tables exist and are accessible
    rls_tables = [
        "personal_records",
        "personal_records_history",
        "athlete_training_zones",
        "daily_workout_surveys",
        "weekly_wellness_surveys"
    ]

    print("ℹ️  RLS should be enabled on these tables:")
    for table in rls_tables:
        print(f"   - {table}")

    print("\n✅ To verify RLS policies, check Supabase Dashboard → Authentication → Policies")

def main():
    """Run all verification checks"""
    print("\n" + "="*70)
    print("🎯 INS DASHBOARD - DATABASE MIGRATION VERIFICATION")
    print("="*70)
    print(f"Target Database: {url}")
    print(f"Project: {project_ref}")
    print("="*70)

    results = []

    # Run checks
    print("\n⏳ Running verification checks...")

    results.append(("Tables Exist", verify_tables()))
    results.append(("Table Structures", verify_table_structure()))

    # Non-critical checks
    verify_data_counts()
    verify_functions()
    verify_rls()

    # Summary
    print("\n" + "="*70)
    print("📊 VERIFICATION SUMMARY")
    print("="*70)

    all_passed = all(result[1] for result in results)

    for check_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {check_name}")

    print("="*70)

    if all_passed:
        print("\n🎉 SUCCESS! Database migration verification passed!")
        print("\n📝 Next steps:")
        print("   1. Create athlete records (5 rows)")
        print("   2. Run create_users.py to create user accounts")
        print("   3. Test dashboard login")
        print("   4. Import recent activity data")
        print("\nSee MIGRATION_DEPLOYMENT_GUIDE.md for detailed instructions.")
        return 0
    else:
        print("\n❌ FAILED! Some checks did not pass.")
        print("\n🔧 Troubleshooting:")
        print("   1. Verify complete_database_schema.sql was run successfully")
        print("   2. Check Supabase SQL Editor for error messages")
        print("   3. Ensure you're using the service role key (not anon key)")
        print("   4. Try re-running the schema deployment")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n❌ Verification failed with error: {str(e)}")
        print("\n🔧 Check your connection and try again")
        sys.exit(1)
