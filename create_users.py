"""
Create users in the database for INS Dashboard authentication.

This script populates the users table with athletes and coach accounts.
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from auth_utils import hash_password

# Load environment
load_dotenv('shiny_env.env')

# Initialize Supabase
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not url or not key:
    print("ERROR: Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in shiny_env.env")
    exit(1)

supabase: Client = create_client(url, key)


def create_users():
    """Create all users (athletes and coach) in the database."""

    # SECURITY NOTE: Passwords should be loaded from environment variables,
    # not hardcoded. Set them in your .env file as:
    # MATTHEW_PASSWORD=<secure_password>
    # KEVIN1_PASSWORD=<secure_password>
    # etc.

    # Define users to create
    users = [
        # Athletes
        {
            'name': 'Matthew Beaudet',
            'role': 'athlete',
            'athlete_id': 'i344978',
            'password': os.getenv('MATTHEW_PASSWORD', 'CHANGE_ME')
        },
        {
            'name': 'Kevin Robertson',
            'role': 'athlete',
            'athlete_id': 'i344979',
            'password': os.getenv('KEVIN1_PASSWORD', 'CHANGE_ME')
        },
        {
            'name': 'Kevin A. Robertson',
            'role': 'athlete',
            'athlete_id': 'i344980',
            'password': os.getenv('KEVIN2_PASSWORD', 'CHANGE_ME')
        },
        {
            'name': 'Zakary Mama-Yari',
            'role': 'athlete',
            'athlete_id': 'i347434',
            'password': os.getenv('ZAKARY_PASSWORD', 'CHANGE_ME')
        },
        {
            'name': 'Sophie Courville',
            'role': 'athlete',
            'athlete_id': 'i95073',
            'password': os.getenv('SOPHIE_PASSWORD', 'CHANGE_ME')
        },
        # Coach
        {
            'name': 'Coach',
            'role': 'coach',
            'athlete_id': None,
            'password': os.getenv('COACH_PASSWORD', 'CHANGE_ME')
        }
    ]
    
    created_count = 0
    skipped_count = 0
    
    for user in users:
        try:
            # Hash the password
            password_hash = hash_password(user['password'])
            
            # Prepare data for insertion
            user_data = {
                'name': user['name'],
                'role': user['role'],
                'athlete_id': user['athlete_id'],
                'password_hash': password_hash
            }
            
            # Insert into database
            result = supabase.table('users').insert(user_data).execute()
            
            # Display success message
            athlete_display = user['athlete_id'] if user['athlete_id'] else 'ALL'
            print(f"Created {user['role']}: {user['name']} ({athlete_display})")
            created_count += 1
            
        except Exception as e:
            error_msg = str(e)
            if 'duplicate' in error_msg.lower() or 'unique' in error_msg.lower():
                athlete_display = user['athlete_id'] if user['athlete_id'] else 'ALL'
                print(f"⊘ Skipped {user['role']}: {user['name']} ({athlete_display}) - already exists")
                skipped_count += 1
            else:
                print(f"Error creating {user['name']}: {error_msg}")
    
    print(f"\n{'='*60}")
    print(f"Successfully created {created_count} users!")
    if skipped_count > 0:
        print(f"Skipped {skipped_count} users (already existed)")
    print(f"{'='*60}")


if __name__ == "__main__":
    print("=== INS Dashboard - User Creation ===\n")
    create_users()
