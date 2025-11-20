#!/usr/bin/env python3
"""
Migration file lister for Supabase
Lists SQL migration files to be run in Supabase SQL Editor
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path=".env.dashboard.local")

SUPABASE_URL = os.getenv("SUPABASE_URL")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL must be set")

# Extract project ref from URL
project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")

# Find all SQL migration files
migrations_dir = Path(__file__).parent / "migrations"
sql_files = sorted(migrations_dir.glob("*.sql"))

print("=" * 70)
print("INS Dashboard - Questionnaire Migrations")
print("=" * 70)
print(f"\nSupabase Project: {project_ref}")
print(f"Migrations Directory: {migrations_dir}")
print(f"\nSQL Files to Run:")
print()

for idx, sql_file in enumerate(sql_files, 1):
    print(f"  {idx}. {sql_file.name}")

print("\n" + "=" * 70)
print("INSTRUCTIONS:")
print("=" * 70)
print(f"""
1. Go to: https://supabase.com/dashboard/project/{project_ref}/sql/new

2. Copy and paste the content of each SQL file listed above

3. Click "Run" to execute the migration

4. Repeat for all {len(sql_files)} files

5. Verify tables were created in the Table Editor
""")

print("=" * 70)
print(f"\nTIP: Files are in: {migrations_dir.relative_to(Path.cwd())}/")
print()

# Display first migration file content as example
if sql_files:
    first_file = [f for f in sql_files if 'daily_workout' in f.name]
    if first_file:
        print("=" * 70)
        print(f"Preview: {first_file[0].name}")
        print("=" * 70)
        print(first_file[0].read_text()[:500] + "...")
        print("=" * 70)
