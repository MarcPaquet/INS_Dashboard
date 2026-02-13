"""
AWS Secrets Loader for INS Dashboard Lambda

Fetches credentials from AWS Secrets Manager and sets up environment.
"""

import boto3
import json
import os
from botocore.exceptions import ClientError

AWS_REGION = "ca-central-1"


def get_secret(secret_name: str) -> dict:
    """Fetch a secret from AWS Secrets Manager."""
    client = boto3.client('secretsmanager', region_name=AWS_REGION)

    try:
        response = client.get_secret_value(SecretId=secret_name)
        secret_string = response['SecretString']
        return json.loads(secret_string)
    except ClientError as e:
        print(f"Error fetching secret {secret_name}: {e}")
        raise


def load_all_secrets():
    """Load all INS Dashboard secrets and set environment variables."""
    print("Loading secrets from AWS Secrets Manager...")

    # Load Supabase credentials
    supabase_secrets = get_secret("ins-dashboard/supabase")
    os.environ["SUPABASE_URL"] = supabase_secrets["SUPABASE_URL"]
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = supabase_secrets["SUPABASE_SERVICE_ROLE_KEY"]
    print("  Supabase credentials loaded")

    # Load config (optional)
    try:
        config_secrets = get_secret("ins-dashboard/config")
        for key, value in config_secrets.items():
            os.environ[key] = str(value)
        print("  Config loaded")
    except Exception:
        print("  Config secret not found, using defaults")

    # Load athletes
    athletes = get_secret("ins-dashboard/athletes")
    print(f"  {len(athletes)} athletes loaded")

    return athletes


def save_athletes_json(athletes: list, path: str = "athletes.json.local"):
    """Save athletes to JSON file for ingestion script.

    NOTE: The ingestion script expects 'athletes.json.local' (not 'athletes.json')
    """
    with open(path, 'w') as f:
        json.dump(athletes, f, indent=2)
    print(f"  Athletes saved to {path}")


if __name__ == "__main__":
    athletes = load_all_secrets()
    save_athletes_json(athletes)
    print("\nAll secrets loaded successfully!")
    print(f"SUPABASE_URL: {os.environ.get('SUPABASE_URL', 'NOT SET')[:50]}...")
