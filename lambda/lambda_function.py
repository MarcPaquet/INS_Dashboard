"""
Lambda handler for INS Dashboard daily ingestion.

Runs ingestion for all athletes for the last 3 days (overlap for safety).
Triggered by:
  - Daily at 6 AM Eastern via EventBridge (scheduled)
  - On-demand via Function URL (HTTP request from dashboard)
"""

import json
import os
import sys
import subprocess
from datetime import datetime, timedelta

# Add current directory to path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aws_secrets_loader import load_all_secrets, save_athletes_json

# Secret token for Function URL authentication
# Set this in Lambda environment variables as REFRESH_TOKEN
REFRESH_TOKEN = os.environ.get('REFRESH_TOKEN', '')


def lambda_handler(event, context):
    """Main Lambda entry point."""

    # Check if this is a Function URL request (HTTP)
    is_http_request = 'requestContext' in event and 'http' in event.get('requestContext', {})

    if is_http_request:
        # Validate authorization for HTTP requests
        headers = event.get('headers', {})
        auth_token = headers.get('authorization', '') or headers.get('Authorization', '')

        if not REFRESH_TOKEN:
            print("ERROR: REFRESH_TOKEN not configured in Lambda environment")
            return {
                'statusCode': 500,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Server not configured for manual refresh'})
            }

        if auth_token != f'Bearer {REFRESH_TOKEN}':
            print(f"ERROR: Invalid authorization token")
            return {
                'statusCode': 401,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Invalid authorization token'})
            }

        print("HTTP request authorized via Function URL")

    # Parse optional athlete filter from request body
    athlete_filter = None
    if is_http_request:
        try:
            body_str = event.get('body', '{}') or '{}'
            body = json.loads(body_str)
            athlete_filter = body.get('athlete_name')
            if athlete_filter:
                print(f"Athlete filter requested: {athlete_filter}")
        except (json.JSONDecodeError, AttributeError):
            pass

    print("=" * 60)
    print("INS Dashboard Daily Ingestion - Lambda")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Trigger: {'Function URL (manual)' if is_http_request else 'EventBridge (scheduled)'}")
    print("=" * 60)

    # Step 1: Load secrets from AWS Secrets Manager
    try:
        athletes = load_all_secrets()
        save_athletes_json(athletes, "/tmp/athletes.json.local")
        # Set env var so ingestion script finds the athletes file
        os.environ["ATHLETES_JSON_PATH"] = "/tmp/athletes.json.local"
    except Exception as e:
        print(f"FATAL: Failed to load secrets: {e}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': f'Failed to load secrets: {str(e)}'})
        }

    # Step 2: Define date range (last 3 days for overlap safety)
    newest = datetime.now().strftime('%Y-%m-%d')
    oldest = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')

    print(f"\nDate range: {oldest} -> {newest}")

    # Filter athletes if a specific athlete was requested
    athletes_to_process = athletes
    if athlete_filter:
        athletes_to_process = [a for a in athletes if a['name'] == athlete_filter]
        if not athletes_to_process:
            # Try case-insensitive match
            athletes_to_process = [a for a in athletes if a['name'].lower() == athlete_filter.lower()]
        if not athletes_to_process:
            print(f"ERROR: Athlete not found: {athlete_filter}")
            return {
                'statusCode': 404,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': f'Athlete not found: {athlete_filter}'})
            }

    print(f"Athletes to process: {len(athletes_to_process)} (of {len(athletes)} total)")
    print()

    # Step 3: Run ingestion for each athlete sequentially
    # (Lambda has limited resources, sequential is safer)
    results = []

    for athlete in athletes_to_process:
        name = athlete['name']
        print(f"Processing: {name}")

        try:
            # Build command - note: using /tmp for athletes.json.local
            cmd = [
                sys.executable,
                os.path.join(os.path.dirname(__file__), 'intervals_hybrid_to_supabase.py'),
                '--athlete', name,
                '--oldest', oldest,
                '--newest', newest
                # Note: No --skip-weather for daily cron (we want weather data)
            ]

            # Run with timeout (5 min per athlete)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                env=os.environ.copy(),
                cwd=os.path.dirname(__file__)
            )

            if result.returncode == 0:
                results.append({'athlete': name, 'status': 'success'})
                print(f"  SUCCESS: {name}")
            else:
                error_msg = result.stderr[:500] if result.stderr else result.stdout[:500]
                results.append({'athlete': name, 'status': 'failed', 'error': error_msg})
                print(f"  FAILED: {name} - {error_msg[:100]}")

        except subprocess.TimeoutExpired:
            results.append({'athlete': name, 'status': 'timeout'})
            print(f"  TIMEOUT: {name}")
        except Exception as e:
            results.append({'athlete': name, 'status': 'error', 'error': str(e)})
            print(f"  ERROR: {name} - {e}")

    # Summary
    success = sum(1 for r in results if r['status'] == 'success')
    failed = len(results) - success

    print()
    print("=" * 60)
    print(f"Completed: {success} success, {failed} failed")
    print(f"Finished: {datetime.now().isoformat()}")
    print("=" * 60)

    response_body = {
        'message': f'Daily ingestion completed: {success}/{len(results)} successful',
        'date_range': {'oldest': oldest, 'newest': newest},
        'results': results
    }

    return {
        'statusCode': 200 if failed == 0 else 207,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Authorization, Content-Type'
        },
        'body': json.dumps(response_body)
    }


# For local testing
if __name__ == "__main__":
    result = lambda_handler({}, None)
    print(json.dumps(result, indent=2))
