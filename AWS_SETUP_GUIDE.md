# AWS Setup Guide - INS Dashboard

**Created:** January 16, 2026
**Purpose:** Complete guide for setting up AWS infrastructure for INS Dashboard data ingestion
**Author:** Marc-Antoine Paquet with Claude Code assistance

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Phase 1: Secrets Manager Setup](#phase-1-secrets-manager-setup) ✅ COMPLETED
5. [Phase 2: IAM Configuration](#phase-2-iam-configuration) ✅ COMPLETED
6. [Phase 3: EC2 Bulk Import](#phase-3-ec2-bulk-import) ← CURRENT STEP
7. [Phase 4: Lambda Daily Cron](#phase-4-lambda-daily-cron)
8. [Troubleshooting](#troubleshooting)
9. [Cost Tracking](#cost-tracking)

---

## Overview

### What We're Building

Two automated systems for importing athlete data from Intervals.icu to Supabase:

| System | Purpose | Frequency | AWS Service |
|--------|---------|-----------|-------------|
| **Bulk Import** | Historical data (2024-2026) | One-time | EC2 |
| **Daily Cron** | New activities | Daily at 6 AM ET | Lambda + EventBridge |

### Why AWS?

- Zero maintenance overhead (vs self-managed VMs)
- Precise scheduling with EventBridge
- Built-in monitoring with CloudWatch
- Auto-retry on failures
- Enterprise-grade reliability
- Cost: ~$5-10/month ongoing

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     AWS INFRASTRUCTURE                          │
└─────────────────────────────────────────────────────────────────┘

                    ┌──────────────────┐
                    │  Secrets Manager │
                    │                  │
                    │ • supabase creds │
                    │ • athlete keys   │
                    │ • config         │
                    └────────┬─────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │   EC2 Instance  │           │     Lambda      │
    │  (Bulk Import)  │           │  (Daily Cron)   │
    │                 │           │                 │
    │ • One-time run  │           │ • 6 AM daily    │
    │ • 2-4 hours     │           │ • 5 min max     │
    │ • ~$0.05 total  │           │ • ~$2-5/month   │
    └────────┬────────┘           └────────┬────────┘
             │                             │
             └──────────────┬──────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │     Intervals.icu       │
              │     (Data Source)       │
              └─────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │       Supabase          │
              │   (PostgreSQL Database) │
              └─────────────────────────┘
```

---

## Prerequisites

Before starting, ensure you have:

- [ ] AWS Account with admin access
- [ ] AWS Console access (https://console.aws.amazon.com/)
- [ ] Supabase project credentials (URL + Service Role Key)
- [ ] Intervals.icu API keys for all athletes

### AWS Region

**Using: `ca-central-1` (Canada Central)**

All resources must be created in the same region for secrets access to work.

---

## Phase 1: Secrets Manager Setup

**Status: ✅ COMPLETED (January 16, 2026)**

### What Was Created

Three secrets stored in AWS Secrets Manager:

| Secret Name | Description | Created |
|-------------|-------------|---------|
| `ins-dashboard/supabase` | Supabase URL + Service Role Key | Jan 16, 2026 00:14:30 UTC |
| `ins-dashboard/athletes` | 18 athletes with Intervals.icu API keys | Jan 16, 2026 00:19:47 UTC |
| `ins-dashboard/config` | API URLs, timeouts, timezone | Jan 16, 2026 00:20:48 UTC |

### Secret Contents

#### Secret 1: `ins-dashboard/supabase`

```json
{
  "SUPABASE_URL": "<STORED IN AWS SECRETS MANAGER>",
  "SUPABASE_SERVICE_ROLE_KEY": "<STORED IN AWS SECRETS MANAGER>"
}
```

#### Secret 2: `ins-dashboard/athletes`

```
18 athletes with Intervals.icu API keys — stored in AWS Secrets Manager.
Local copy: athletes.json.local (gitignored)
```

#### Secret 3: `ins-dashboard/config`

```json
{
  "INTERVALS_API_URL": "https://intervals.icu/api/v1",
  "OPENMETEO_API_URL": "https://api.open-meteo.com",
  "OM_TIMEOUT": "10",
  "AQ_TIMEOUT": "10",
  "ELEV_TIMEOUT": "8",
  "BATCH_SIZE": "500",
  "MAX_RETRIES": "3",
  "RETRY_DELAY": "2",
  "INS_TZ": "America/Toronto"
}
```

### How to Verify Secrets

1. Go to AWS Console → Secrets Manager
2. Click on each secret name
3. Click "Retrieve secret value" to view contents

### How to Update Secrets

If you need to add/remove athletes or change credentials:

1. Go to Secrets Manager → Select secret
2. Click "Retrieve secret value"
3. Click "Edit"
4. Modify JSON and click "Save"

---

## Phase 2: IAM Configuration

**Status: ✅ COMPLETED (January 16, 2026)**

### Step 2.1: Create IAM Policy

1. Go to **IAM** → **Policies** → **Create policy**
2. Click **JSON** tab
3. Paste this policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SecretsManagerAccess",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": [
        "arn:aws:secretsmanager:ca-central-1:*:secret:ins-dashboard/*"
      ]
    }
  ]
}
```

4. Click **Next**
5. **Policy name**: `INS-Dashboard-SecretsAccess`
6. **Description**: `Allows read access to INS Dashboard secrets in Secrets Manager`
7. Click **Create policy**

### Step 2.2: Create IAM Role for EC2

1. Go to **IAM** → **Roles** → **Create role**
2. **Trusted entity type**: `AWS service`
3. **Use case**: `EC2`
4. Click **Next**
5. Search and attach these policies:
   - ✅ `INS-Dashboard-SecretsAccess`
   - ✅ `AmazonSSMManagedInstanceCore`
6. Click **Next**
7. **Role name**: `INS-Dashboard-EC2-Role`
8. **Description**: `Role for EC2 instances running INS Dashboard bulk import`
9. Click **Create role**

### Step 2.3: Create IAM Role for Lambda (for later)

1. Go to **IAM** → **Roles** → **Create role**
2. **Trusted entity type**: `AWS service`
3. **Use case**: `Lambda`
4. Click **Next**
5. Search and attach these policies:
   - ✅ `INS-Dashboard-SecretsAccess`
   - ✅ `AWSLambdaBasicExecutionRole`
6. Click **Next**
7. **Role name**: `INS-Dashboard-Lambda-Role`
8. **Description**: `Role for Lambda functions running INS Dashboard daily ingestion`
9. Click **Create role**

### Verification Checklist

- [x] Policy `INS-Dashboard-SecretsAccess` created ✅
- [x] Role `INS-Dashboard-EC2-Role` created with correct policies ✅
- [ ] Role `INS-Dashboard-Lambda-Role` created (will do after bulk import)

---

## Phase 3: EC2 Bulk Import

**Status: ⏳ PENDING**

### Step 3.1: Launch EC2 Instance

1. Go to **EC2** → **Instances** → **Launch instances**

2. **Name and tags**:
   - Name: `INS-Bulk-Import`

3. **Application and OS Images (AMI)**:
   - Select: **Ubuntu Server 24.04 LTS** (HVM, SSD Volume Type)
   - Architecture: 64-bit (x86)

4. **Instance type**:
   - Select: `t3.small` (2 vCPU, 2 GiB RAM)
   - Cost: ~$0.023/hour (~$0.05 for 2-hour run)

5. **Key pair (login)**:
   - Select: **Proceed without a key pair** (we'll use Session Manager)

6. **Network settings**:
   - Click **Edit**
   - VPC: Default VPC
   - Subnet: No preference
   - Auto-assign public IP: **Enable**
   - Security group: Create new
     - ✅ Allow HTTPS traffic from the internet
     - ✅ Allow HTTP traffic from the internet

7. **Configure storage**:
   - Size: **20 GiB**
   - Volume type: gp3
   - Delete on termination: Yes

8. **Advanced details** (expand):
   - IAM instance profile: **INS-Dashboard-EC2-Role**
   - All other settings: Default

9. Click **Launch instance**

### Step 3.2: Connect to EC2

1. Wait 2-3 minutes for instance to initialize
2. Go to **EC2** → **Instances**
3. Select `INS-Bulk-Import` instance
4. Click **Connect** (top right)
5. Select **Session Manager** tab
6. Click **Connect**

A browser-based terminal will open.

### Step 3.3: Initial Server Setup

Run these commands in the Session Manager terminal:

```bash
# Switch to ubuntu user
sudo su - ubuntu

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11 and tools
sudo apt install -y python3.11 python3.11-venv python3-pip git unzip

# Create project directory
mkdir -p ~/ins-dashboard
cd ~/ins-dashboard

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install boto3 requests python-dotenv fitparse pandas numpy
```

### Step 3.4: Upload Ingestion Scripts

**Option A: Clone from GitHub (if repo is public)**

```bash
cd ~/ins-dashboard
git clone https://github.com/MarcPaquet/INS_Dashboard.git .
```

**Option B: Upload manually via S3**

1. Create S3 bucket: `ins-dashboard-scripts`
2. Upload these files:
   - `intervals_hybrid_to_supabase.py`
   - `moving_time.py`
3. Download to EC2:

```bash
aws s3 cp s3://ins-dashboard-scripts/intervals_hybrid_to_supabase.py .
aws s3 cp s3://ins-dashboard-scripts/moving_time.py .
```

**Option C: Copy-paste directly**

Create files using nano/vim and paste contents.

### Step 3.5: Create AWS Secrets Loader Script

Create `aws_secrets_loader.py`:

```bash
cat > ~/ins-dashboard/aws_secrets_loader.py << 'EOF'
"""
AWS Secrets Loader for INS Dashboard

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
    print("  ✓ Supabase credentials loaded")

    # Load config
    try:
        config_secrets = get_secret("ins-dashboard/config")
        for key, value in config_secrets.items():
            os.environ[key] = str(value)
        print("  ✓ Config loaded")
    except Exception:
        print("  ⚠ Config secret not found, using defaults")

    # Load athletes
    athletes = get_secret("ins-dashboard/athletes")
    print(f"  ✓ {len(athletes)} athletes loaded")

    return athletes

def save_athletes_json(athletes: list, path: str = "athletes.json.local"):
    """Save athletes to JSON file for ingestion script.

    NOTE: The ingestion script expects 'athletes.json.local' (not 'athletes.json')
    """
    with open(path, 'w') as f:
        json.dump(athletes, f, indent=2)
    print(f"  ✓ Athletes saved to {path}")

if __name__ == "__main__":
    athletes = load_all_secrets()
    save_athletes_json(athletes)
    print("\nAll secrets loaded successfully!")
    print(f"SUPABASE_URL: {os.environ.get('SUPABASE_URL', 'NOT SET')[:50]}...")
EOF
```

### Step 3.6: Create Bulk Import Runner Script

Create `run_bulk_import.py` (Python script instead of shell for proper env var handling):

```bash
cat > ~/ins-dashboard/run_bulk_import.py << 'EOF'
#!/usr/bin/env python3
"""
INS Dashboard Bulk Import Script

Runs parallel imports for all athletes with proper AWS secrets loading.
Uses subprocess with inherited environment variables.
"""

import json
import subprocess
import os
import sys
from datetime import datetime

# Import the AWS secrets loader
from aws_secrets_loader import load_all_secrets, save_athletes_json

def run_bulk_import():
    print("=" * 60)
    print("INS Dashboard Bulk Import")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    # Step 1: Load secrets and set environment variables
    athletes = load_all_secrets()
    save_athletes_json(athletes)

    # Define date range
    OLDEST = "2024-01-01"
    NEWEST = datetime.now().strftime("%Y-%m-%d")  # Today's date

    # Also include historical wellness
    WELLNESS_OLDEST = OLDEST
    WELLNESS_NEWEST = NEWEST

    print()
    print(f"Date range: {OLDEST} → {NEWEST}")
    print(f"Wellness range: {WELLNESS_OLDEST} → {WELLNESS_NEWEST}")
    print(f"Athletes: {len(athletes)}")
    print(f"Mode: Parallel with --skip-weather (bulk import)")
    print()
    print("Starting parallel imports...")
    print()

    # Step 2: Launch parallel imports
    # Environment variables are already set in os.environ
    processes = []
    for athlete in athletes:
        name = athlete['name']
        cmd = [
            sys.executable,  # Use same Python interpreter
            'intervals_hybrid_to_supabase.py',
            '--athlete', name,
            '--oldest', OLDEST,
            '--newest', NEWEST,
            '--wellness-oldest', WELLNESS_OLDEST,
            '--wellness-newest', WELLNESS_NEWEST,
            '--skip-weather'
        ]

        # Create log file for this athlete
        log_file = open(f"import_{name.replace(' ', '_')}.log", 'w')

        print(f"  Starting: {name}")
        p = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=os.environ.copy()  # Pass current environment with secrets
        )
        processes.append((name, p, log_file))

    # Step 3: Wait for all to complete
    print()
    print("Waiting for imports to complete...")
    print()

    results = []
    for name, p, log_file in processes:
        p.wait()
        log_file.close()
        status = "✓" if p.returncode == 0 else "✗"
        results.append((name, p.returncode))
        print(f"  {status} {name} (exit code: {p.returncode})")

    # Summary
    print()
    print("=" * 60)
    success = sum(1 for _, code in results if code == 0)
    failed = sum(1 for _, code in results if code != 0)
    print(f"Completed: {success} success, {failed} failed")
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Show failed athletes
    if failed > 0:
        print()
        print("Failed athletes (check log files):")
        for name, code in results:
            if code != 0:
                print(f"  - {name}: import_{name.replace(' ', '_')}.log")

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(run_bulk_import())
EOF
```

Make it executable:

```bash
chmod +x ~/ins-dashboard/run_bulk_import.py
```

**Why Python instead of Bash?**
- Environment variables set by `aws_secrets_loader.py` must be in the SAME process
- Subprocess inherits `os.environ` from parent Python process
- Better error handling and logging

### Step 3.7: Test with Dry Run First

**IMPORTANT: Always test before running the full import!**

```bash
cd ~/ins-dashboard
source venv/bin/activate

# Step 1: Test secrets loading (verify AWS connection works)
python aws_secrets_loader.py

# Step 2: Test with ONE athlete, short date range, dry-run mode
python intervals_hybrid_to_supabase.py \
  --athlete "Matthew Beaudet" \
  --oldest 2025-01-01 \
  --newest 2025-01-15 \
  --skip-weather \
  --dry-run

# Expected: Should show activities found without inserting anything
```

**If dry-run succeeds**, you can run the full import.

### Step 3.8: Run the Bulk Import

```bash
cd ~/ins-dashboard
source venv/bin/activate

# Run bulk import (this will take 2-4 hours)
python run_bulk_import.py 2>&1 | tee bulk_import_main.log
```

**Expected Output:**
```
============================================================
INS Dashboard Bulk Import
Started: 2026-01-15 19:30:00
============================================================

Loading secrets from AWS Secrets Manager...
  ✓ Supabase credentials loaded
  ✓ Config loaded
  ✓ 18 athletes loaded
  ✓ Athletes saved to athletes.json.local

Date range: 2024-01-01 → 2026-01-15
Wellness range: 2024-01-01 → 2026-01-15
Athletes: 18
Mode: Parallel with --skip-weather (bulk import)

Starting parallel imports...

  Starting: Matthew Beaudet
  Starting: Kevin Robertson
  ...
```

### Step 3.9: Monitor Progress

In another Session Manager window:

```bash
# Switch to ubuntu user
sudo su - ubuntu
cd ~/ins-dashboard

# Watch main log file
tail -f bulk_import_main.log

# Watch a specific athlete's log
tail -f import_Matthew_Beaudet.log

# Check running processes
ps aux | grep python

# Count running imports
ps aux | grep intervals_hybrid | wc -l
```

### Step 3.10: After Import - Terminate Instance

**IMPORTANT: Don't forget to terminate to avoid charges!**

1. Go to **EC2** → **Instances**
2. Select `INS-Bulk-Import`
3. **Instance state** → **Terminate instance**
4. Confirm termination

---

## Phase 4: Lambda Daily Cron

**Status: ⏳ PENDING (After bulk import)**

### Step 4.1: Create Lambda Function

1. Go to **Lambda** → **Create function**

2. **Function name**: `ins-dashboard-daily-ingestion`

3. **Runtime**: Python 3.11

4. **Architecture**: x86_64

5. **Permissions**:
   - Use existing role: `INS-Dashboard-Lambda-Role`

6. Click **Create function**

### Step 4.2: Configure Lambda Settings

1. Go to **Configuration** tab

2. **General configuration** → Edit:
   - Memory: **512 MB**
   - Timeout: **5 minutes**
   - Click Save

3. **Environment variables** → Edit:
   - Add: `AWS_REGION` = `ca-central-1`
   - Click Save

### Step 4.3: Create Deployment Package

**⚠️ NOTE: The Lambda handler below needs testing. We'll finalize this after the bulk import is complete.**

On your local machine:

```bash
# Create deployment directory
mkdir -p lambda_package
cd lambda_package

# Install dependencies to local directory (Lambda layer)
pip install --target . boto3 requests python-dotenv fitparse pandas numpy

# Copy scripts
cp ../intervals_hybrid_to_supabase.py .
cp ../moving_time.py .
cp ../aws_secrets_loader.py .

# Create Lambda handler
cat > lambda_function.py << 'EOF'
"""
Lambda handler for INS Dashboard daily ingestion.

Runs ingestion for all athletes for the last 3 days (overlap for safety).
"""
import json
import os
import sys
import subprocess
from datetime import datetime, timedelta

# Add current directory to path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aws_secrets_loader import load_all_secrets, save_athletes_json

def lambda_handler(event, context):
    print("=" * 60)
    print("INS Dashboard Daily Ingestion - Lambda")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    # Step 1: Load secrets from AWS Secrets Manager
    athletes = load_all_secrets()
    save_athletes_json(athletes)

    # Step 2: Define date range (last 3 days for overlap safety)
    newest = datetime.now().strftime('%Y-%m-%d')
    oldest = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')

    print(f"Date range: {oldest} → {newest}")
    print(f"Athletes: {len(athletes)}")

    # Step 3: Run ingestion for each athlete sequentially
    # (Lambda has limited resources, so sequential is safer)
    results = []
    for athlete in athletes:
        name = athlete['name']
        print(f"\nProcessing: {name}")

        try:
            cmd = [
                sys.executable,
                'intervals_hybrid_to_supabase.py',
                '--athlete', name,
                '--oldest', oldest,
                '--newest', newest
                # Note: No --skip-weather for daily cron (we want weather data)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,  # 2 min timeout per athlete
                env=os.environ.copy()
            )

            if result.returncode == 0:
                results.append({'athlete': name, 'status': 'success'})
                print(f"  ✓ {name} completed")
            else:
                results.append({'athlete': name, 'status': 'failed', 'error': result.stderr[:500]})
                print(f"  ✗ {name} failed: {result.stderr[:200]}")

        except subprocess.TimeoutExpired:
            results.append({'athlete': name, 'status': 'timeout'})
            print(f"  ✗ {name} timed out")
        except Exception as e:
            results.append({'athlete': name, 'status': 'error', 'error': str(e)})
            print(f"  ✗ {name} error: {e}")

    # Summary
    success = sum(1 for r in results if r['status'] == 'success')
    failed = len(results) - success

    print()
    print("=" * 60)
    print(f"Completed: {success} success, {failed} failed")
    print("=" * 60)

    return {
        'statusCode': 200 if failed == 0 else 207,
        'body': json.dumps({
            'message': f'Daily ingestion completed: {success}/{len(results)} successful',
            'date_range': {'oldest': oldest, 'newest': newest},
            'results': results
        })
    }
EOF

# Create ZIP file
zip -r ../lambda_deployment.zip .
```

**Lambda Considerations:**
- Sequential processing (not parallel) due to Lambda resource limits
- 5-minute timeout should handle all 18 athletes
- No `--skip-weather` flag (we want weather for daily activities)
- Each athlete has 2-minute subprocess timeout

### Step 4.4: Upload to Lambda

1. Go to Lambda function
2. **Code** tab → **Upload from** → **.zip file**
3. Upload `lambda_deployment.zip`

### Step 4.5: Create EventBridge Schedule

1. Go to **EventBridge** → **Schedules** → **Create schedule**

2. **Schedule name**: `ins-dashboard-daily-6am`

3. **Schedule pattern**:
   - Recurring schedule
   - Cron-based: `0 11 * * ? *` (6 AM Eastern = 11 AM UTC)

4. **Target**:
   - AWS Lambda
   - Function: `ins-dashboard-daily-ingestion`

5. **Settings**:
   - Enable schedule: Yes
   - Retry policy: 2 retries

6. Click **Create schedule**

### Step 4.6: Test Lambda

1. Go to Lambda function
2. Click **Test**
3. Create test event with `{}`
4. Click **Test**
5. Check execution results

---

## Troubleshooting

### Secret Access Denied

**Error**: `AccessDeniedException: User is not authorized to perform: secretsmanager:GetSecretValue`

**Solution**:
1. Verify IAM role has `INS-Dashboard-SecretsAccess` policy
2. Check region matches (must be `ca-central-1`)
3. Check secret ARN pattern matches policy

### EC2 Cannot Connect to Internet

**Error**: API calls fail with connection timeout

**Solution**:
1. Verify security group allows outbound HTTPS (port 443)
2. Check instance has public IP
3. Verify route table has internet gateway

### Session Manager Connection Failed

**Error**: Cannot connect via Session Manager

**Solution**:
1. Verify IAM role has `AmazonSSMManagedInstanceCore` policy
2. Wait 5 minutes after launch for SSM agent to initialize
3. Check instance is in "running" state

### Import Script Errors

**Error**: Python module not found

**Solution**:
```bash
source ~/ins-dashboard/venv/bin/activate
pip install <missing-module>
```

---

## Cost Tracking

### Estimated Monthly Costs

| Service | Usage | Monthly Cost |
|---------|-------|--------------|
| Secrets Manager | 3 secrets × $0.40 | ~$1.20 |
| Lambda | 30 invocations × 5 min | ~$2-5 |
| EventBridge | 30 triggers | Free |
| CloudWatch Logs | ~1 GB | ~$1-2 |
| **Total Ongoing** | | **~$5-10/month** |

### One-Time Costs

| Service | Usage | Cost |
|---------|-------|------|
| EC2 t3.small | 2-4 hours | ~$0.05-0.10 |
| Data Transfer | ~1 GB | ~$0.10 |
| **Total One-Time** | | **~$0.20** |

### Cost Monitoring

1. Go to **Billing** → **Budgets**
2. Verify `INS-Dashboard-Alert` budget is active
3. You'll receive email at $8 (80% of $10 budget)

---

## Quick Reference

### AWS Resources Created

| Resource | Name | Region |
|----------|------|--------|
| Secret | `ins-dashboard/supabase` | ca-central-1 |
| Secret | `ins-dashboard/athletes` | ca-central-1 |
| Secret | `ins-dashboard/config` | ca-central-1 |
| IAM Policy | `INS-Dashboard-SecretsAccess` | Global |
| IAM Role | `INS-Dashboard-EC2-Role` | Global |
| IAM Role | `INS-Dashboard-Lambda-Role` | Global |
| EC2 Instance | `INS-Bulk-Import` | ca-central-1 |
| Lambda | `ins-dashboard-daily-ingestion` | ca-central-1 |
| EventBridge | `ins-dashboard-daily-6am` | ca-central-1 |

### Important URLs

- AWS Console: https://console.aws.amazon.com/
- Secrets Manager: https://ca-central-1.console.aws.amazon.com/secretsmanager/
- EC2: https://ca-central-1.console.aws.amazon.com/ec2/
- Lambda: https://ca-central-1.console.aws.amazon.com/lambda/
- CloudWatch: https://ca-central-1.console.aws.amazon.com/cloudwatch/

### CLI Commands

```bash
# List secrets
aws secretsmanager list-secrets --region ca-central-1

# Get secret value
aws secretsmanager get-secret-value --secret-id ins-dashboard/supabase --region ca-central-1

# List EC2 instances
aws ec2 describe-instances --region ca-central-1

# Invoke Lambda manually
aws lambda invoke --function-name ins-dashboard-daily-ingestion --region ca-central-1 output.json
```

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-16 | Initial document created |
| 2026-01-16 | Phase 1 (Secrets Manager) completed |

---

**END OF GUIDE**
