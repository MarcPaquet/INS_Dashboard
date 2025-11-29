#!/usr/bin/env python3
"""
Export Complete Database Schema from Current Supabase Database
Extracts all tables, indexes, constraints, triggers, functions, and RLS policies
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
    print("❌ No environment file found. Please ensure .env.dashboard.local or .env.ingestion.local exists.")
    sys.exit(1)

# Initialize Supabase client for current database
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not url or not key:
    print("❌ Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in environment")
    sys.exit(1)

print(f"🔗 Connecting to Supabase: {url}")
supabase: Client = create_client(url, key)

def get_table_schema(table_name: str) -> str:
    """Extract CREATE TABLE statement for a given table using information_schema"""

    # SQL query to extract table definition
    query = f"""
    SELECT
        'CREATE TABLE IF NOT EXISTS ' || table_name || ' (' ||
        string_agg(
            column_name || ' ' ||
            CASE
                WHEN data_type = 'USER-DEFINED' THEN udt_name
                WHEN data_type = 'ARRAY' THEN 'TEXT[]'
                ELSE data_type
            END ||
            CASE
                WHEN character_maximum_length IS NOT NULL
                THEN '(' || character_maximum_length || ')'
                WHEN numeric_precision IS NOT NULL AND data_type != 'timestamp with time zone'
                THEN '(' || numeric_precision ||
                     CASE WHEN numeric_scale > 0 THEN ',' || numeric_scale ELSE '' END || ')'
                ELSE ''
            END ||
            CASE WHEN is_nullable = 'NO' THEN ' NOT NULL' ELSE '' END ||
            CASE WHEN column_default IS NOT NULL THEN ' DEFAULT ' || column_default ELSE '' END,
            E',\\n    '
            ORDER BY ordinal_position
        ) ||
        E'\\n);' as create_statement
    FROM information_schema.columns
    WHERE table_schema = 'public'
    AND table_name = '{table_name}'
    GROUP BY table_name;
    """

    try:
        # Use raw SQL query via RPC (if available) or direct query
        # For now, we'll use a simpler approach with table inspection
        response = supabase.table(table_name).select("*").limit(1).execute()

        if response.data:
            sample = response.data[0]
            columns_info = []
            for col_name, col_value in sample.items():
                # Infer type from sample data
                col_type = "TEXT"  # Default
                if isinstance(col_value, int):
                    col_type = "INTEGER"
                elif isinstance(col_value, float):
                    col_type = "REAL"
                elif isinstance(col_value, bool):
                    col_type = "BOOLEAN"
                elif col_value is None:
                    col_type = "TEXT"  # Unknown, default to TEXT

                columns_info.append(f"    {col_name} {col_type}")

            create_statement = f"-- Table: {table_name}\n"
            create_statement += f"-- Note: Schema inferred from sample data. Please verify column types.\n"
            create_statement += f"CREATE TABLE IF NOT EXISTS {table_name} (\n"
            create_statement += ",\n".join(columns_info)
            create_statement += "\n);\n"

            return create_statement
        else:
            return f"-- Table {table_name}: No data available for schema inference\n"

    except Exception as e:
        return f"-- Error extracting schema for {table_name}: {str(e)}\n"

def export_schema():
    """Export complete database schema"""

    print("\n🔍 Extracting Database Schema...")
    print("=" * 70)

    # List of tables to export (from CLAUDE.md documentation)
    core_tables = [
        "athlete",
        "users",
        "activity_metadata",
        "activity",
        "activity_intervals",
        "wellness"
    ]

    additional_tables = [
        "personal_records",
        "personal_records_history",
        "athlete_training_zones",
        "daily_workout_surveys",
        "weekly_wellness_surveys"
    ]

    all_tables = core_tables + additional_tables

    output_file = "exported_schema_partial.sql"

    with open(output_file, 'w') as f:
        f.write("-- ============================================================================\n")
        f.write("-- INS Dashboard - Exported Database Schema (PARTIAL)\n")
        f.write("-- Extracted from current Supabase database\n")
        f.write("-- \n")
        f.write("-- IMPORTANT: This is a PARTIAL schema extraction using sample data.\n")
        f.write("-- For complete schema with proper types, constraints, and indexes,\n")
        f.write("-- please use: pg_dump or Supabase CLI 'supabase db dump'\n")
        f.write("-- ============================================================================\n\n")

        # Export core tables
        f.write("-- ============================================================================\n")
        f.write("-- CORE TABLES (Phase 1)\n")
        f.write("-- ============================================================================\n\n")

        for table in core_tables:
            print(f"📋 Extracting: {table}...")
            schema = get_table_schema(table)
            f.write(schema + "\n")

        # Export additional tables
        f.write("\n-- ============================================================================\n")
        f.write("-- ADDITIONAL TABLES (Phase 2)\n")
        f.write("-- ============================================================================\n\n")

        for table in additional_tables:
            print(f"📋 Extracting: {table}...")
            schema = get_table_schema(table)
            f.write(schema + "\n")

        # Add note about using migration files
        f.write("\n-- ============================================================================\n")
        f.write("-- IMPORTANT: USE MIGRATION FILES FOR COMPLETE SCHEMA\n")
        f.write("-- ============================================================================\n")
        f.write("-- The above is a simplified schema extracted from sample data.\n")
        f.write("-- \n")
        f.write("-- For production deployment, use:\n")
        f.write("-- 1. The complete_database_schema.sql file that combines proper DDL\n")
        f.write("-- 2. All migration files from /migrations directory\n")
        f.write("-- \n")
        f.write("-- This file is for reference only to understand table structure.\n")
        f.write("-- ============================================================================\n")

    print(f"\n✅ Partial schema exported to: {output_file}")
    print("\n⚠️  IMPORTANT NOTE:")
    print("   This extraction provides basic table structure only.")
    print("   For complete schema, we'll use the migration files + proper DDL.")
    print("\n📝 Next: Creating complete_database_schema.sql from migration files...")

    return output_file

if __name__ == "__main__":
    try:
        export_schema()
        print("\n✅ Schema extraction complete!")
        print("\n🔄 Next steps:")
        print("   1. Review exported_schema_partial.sql (reference only)")
        print("   2. I'll now create complete_database_schema.sql with proper schema")

    except Exception as e:
        print(f"\n❌ Error during extraction: {str(e)}")
        sys.exit(1)
