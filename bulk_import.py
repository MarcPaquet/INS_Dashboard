#!/usr/bin/env python3
"""
BULK IMPORT MASTER SCRIPT
Orchestrates complete data ingestion: Activities + Wellness + View Refresh

Usage:
    # Import everything for all athletes (last 6 months)
    python bulk_import.py
    
    # Custom date range
    python bulk_import.py --oldest 2024-01-01 --newest 2025-10-30
    
    # Specific athlete
    python bulk_import.py --athlete "Matthew Beaudet"
    
    # Dry run (test without writing)
    python bulk_import.py --dry-run
    
    # Skip wellness import
    python bulk_import.py --skip-wellness
"""

import os
import sys
import argparse
import subprocess
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests

load_dotenv(".env.ingestion.local")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

# Colors for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text: str):
    """Print formatted header"""
    print(f"\n{Colors.BOLD}{'='*80}")
    print(f"  {text}")
    print(f"{'='*80}{Colors.END}\n")

def run_command(cmd: list, description: str) -> bool:
    """Run subprocess command with error handling"""
    print(f"{Colors.BLUE}▶ {description}...{Colors.END}")
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=False,
            text=True
        )
        print(f"{Colors.GREEN}{description} completed{Colors.END}\n")
        return True
    except subprocess.CalledProcessError as e:
        print(f"{Colors.RED}{description} failed with exit code {e.returncode}{Colors.END}\n")
        return False
    except Exception as e:
        print(f"{Colors.RED}{description} failed: {e}{Colors.END}\n")
        return False

def refresh_materialized_view() -> bool:
    """Refresh activity_summary materialized view"""
    print(f"{Colors.BLUE}▶ Refreshing materialized view...{Colors.END}")
    try:
        refresh_url = f"{SUPABASE_URL}/rest/v1/rpc/refresh_activity_summary"
        response = requests.post(
            refresh_url,
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json"
            },
            timeout=120
        )
        if response.status_code in (200, 204):
            print(f"{Colors.GREEN}Materialized view refreshed{Colors.END}\n")
            return True
        else:
            print(f"{Colors.YELLOW} View refresh returned status {response.status_code}{Colors.END}\n")
            return False
    except Exception as e:
        print(f"{Colors.YELLOW} Could not refresh view: {e}{Colors.END}\n")
        return False

def get_data_quality_stats() -> dict:
    """Get data quality statistics from database"""
    try:
        query_url = f"{SUPABASE_URL}/rest/v1/rpc/get_data_quality_metrics"
        response = requests.post(
            query_url,
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json"
            },
            timeout=30
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception:
        return []

def print_data_quality():
    """Print data quality summary"""
    print_header("DATA QUALITY SUMMARY")
    stats = get_data_quality_stats()
    if stats:
        for row in stats:
            metric = row.get('metric', 'Unknown')
            value = row.get('value', 0)
            pct = row.get('percentage')
            if pct:
                print(f"  {metric:.<40} {value:>6} ({pct:>5.1f}%)")
            else:
                print(f"  {metric:.<40} {value:>6}")
    else:
        print("  Could not retrieve statistics")
    print()

def main():
    parser = argparse.ArgumentParser(
        description="Bulk import master script for INS Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import last 6 months for all athletes
  python bulk_import.py
  
  # Import specific date range
  python bulk_import.py --oldest 2024-01-01 --newest 2025-10-30
  
  # Import for specific athlete
  python bulk_import.py --athlete "Matthew Beaudet"
  
  # Test run without writing to database
  python bulk_import.py --dry-run
        """
    )
    
    # Date range arguments
    default_oldest = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
    default_newest = datetime.now().strftime('%Y-%m-%d')
    
    parser.add_argument('--oldest', default=default_oldest, 
                       help=f"Start date (default: {default_oldest})")
    parser.add_argument('--newest', default=default_newest,
                       help=f"End date (default: {default_newest})")
    parser.add_argument('--athlete', help="Specific athlete name (optional)")
    parser.add_argument('--dry-run', action='store_true', 
                       help="Test mode - no database writes")
    parser.add_argument('--skip-wellness', action='store_true',
                       help="Skip wellness data import")
    parser.add_argument('--skip-activities', action='store_true',
                       help="Skip activity data import (wellness only)")
    
    args = parser.parse_args()
    
    # Print banner
    print_header("INS DASHBOARD - BULK DATA IMPORT")
    print(f"  Date range: {args.oldest} → {args.newest}")
    if args.athlete:
        print(f"  Athlete: {args.athlete}")
    else:
        print(f"  Athletes: All")
    if args.dry_run:
        print(f"  {Colors.YELLOW}Mode: DRY RUN (no database writes){Colors.END}")
    else:
        print(f"  Mode: PRODUCTION")
    print()
    
    # Track success
    success = True
    
    # Step 1: Import Activities
    if not args.skip_activities:
        print_header("STEP 1: IMPORTING ACTIVITIES")
        cmd = [
            sys.executable,
            "intervals_hybrid_to_supabase.py",
            "--oldest", args.oldest,
            "--newest", args.newest
        ]
        if args.athlete:
            cmd.extend(["--athlete", args.athlete])
        if args.dry_run:
            cmd.append("--dry-run")
        
        success = run_command(cmd, "Activity import") and success
    else:
        print(f"{Colors.YELLOW}⏭  Skipping activity import{Colors.END}\n")
    
    # Step 2: Import Wellness
    if not args.skip_wellness:
        print_header("STEP 2: IMPORTING WELLNESS DATA")
        cmd = [
            sys.executable,
            "intervals_wellness_to_supabase.py",
            "--start-date", args.oldest,
            "--end-date", args.newest
        ]
        if args.athlete:
            # Note: wellness script uses --athlete-id, need to convert name to ID
            # For now, skip athlete filter for wellness
            print(f"{Colors.YELLOW} Wellness import for specific athlete not yet supported{Colors.END}")
            print(f"{Colors.YELLOW}   Importing wellness for all athletes{Colors.END}\n")
        if args.dry_run:
            cmd.append("--dry-run")
        
        success = run_command(cmd, "Wellness import") and success
    else:
        print(f"{Colors.YELLOW}⏭  Skipping wellness import{Colors.END}\n")
    
    # Step 3: Refresh Materialized View (only if not dry-run)
    if not args.dry_run and not args.skip_activities:
        print_header("STEP 3: REFRESHING MATERIALIZED VIEW")
        success = refresh_materialized_view() and success
    
    # Step 4: Print Data Quality Summary
    if not args.dry_run:
        print_data_quality()
    
    # Final summary
    print_header("BULK IMPORT COMPLETE")
    if success:
        print(f"{Colors.GREEN}All operations completed successfully{Colors.END}")
        if not args.dry_run:
            print(f"\n{Colors.CYAN}Next steps:{Colors.END}")
            print(f"  1. Launch dashboard: python supabase_shiny.py")
            print(f"  2. Verify data in Supabase console")
            print(f"  3. Check data quality metrics above")
        else:
            print(f"\n{Colors.YELLOW}This was a dry run - no data was written{Colors.END}")
            print(f"Remove --dry-run flag to perform actual import")
        print()
        return 0
    else:
        print(f"{Colors.RED}Some operations failed - check logs above{Colors.END}\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
