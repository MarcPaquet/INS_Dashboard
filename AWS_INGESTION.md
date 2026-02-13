# AWS EC2 Bulk Import Guide - INS Dashboard

**Created:** January 18, 2026
**Purpose:** Step-by-step guide for running bulk data import on AWS EC2
**Status:** First bulk import completed successfully

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Step 1: Connect to EC2](#step-1-connect-to-ec2)
4. [Step 2: Setup Python Environment](#step-2-setup-python-environment)
5. [Step 3: Create Scripts](#step-3-create-scripts)
6. [Step 4: Test AWS Secrets](#step-4-test-aws-secrets)
7. [Step 5: Run Dry-Run Test](#step-5-run-dry-run-test)
8. [Step 6: Run Bulk Import](#step-6-run-bulk-import)
9. [Step 7: Monitor Progress](#step-7-monitor-progress)
10. [Step 8: After Import](#step-8-after-import)
11. [Troubleshooting](#troubleshooting)
12. [Updating Athletes](#updating-athletes)

---

## Overview

This guide covers how to run bulk data import from Intervals.icu to Supabase using AWS EC2.

**What gets imported:**
- Activities (FIT files or Streams API fallback)
- GPS records
- Intervals
- Wellness data (HRV, sleep, soreness)
- Weather data (optional, can skip for bulk import)

**Architecture:**
```
EC2 Instance (t3.small)
    │
    ├── aws_secrets_loader.py    # Loads credentials from Secrets Manager
    ├── run_bulk_import.py       # Orchestrates parallel imports
    ├── intervals_hybrid_to_supabase.py  # Main ingestion script
    └── moving_time.py           # Moving time calculations
    │
    ▼
AWS Secrets Manager
    │
    ├── ins-dashboard/supabase   # Supabase credentials
    ├── ins-dashboard/athletes   # Athlete API keys
    └── ins-dashboard/config     # Configuration
    │
    ▼
Intervals.icu API → Supabase Database
```

---

## Prerequisites

Before starting, ensure:

- [x] EC2 instance `INS-Bulk-Import` is running (t3.small, Ubuntu 24.04)
- [x] IAM role `INS-Dashboard-EC2-Role` attached to instance
- [x] IAM policy `INS-Dashboard-SecretsAccess` with correct region (ca-central-1)
- [x] Secrets created in AWS Secrets Manager (ca-central-1)
- [x] Security group allows outbound HTTPS (port 443)

---

## Step 1: Connect to EC2

1. Go to **AWS Console** → **EC2** → **Instances**
2. Select `INS-Bulk-Import` instance
3. Click **Connect** → **Session Manager** tab → **Connect**

**First command after connecting:**
```bash
bash
```

This switches from `sh` to `bash` (required for `source` command).

---

## Step 2: Setup Python Environment

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and tools
sudo apt install -y python3-venv python3-pip git unzip

# Create project directory
mkdir -p ~/ins-dashboard
cd ~/ins-dashboard

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install boto3 requests python-dotenv fitparse pandas numpy
```

---

## Step 3: Create Scripts

### 3a. Create aws_secrets_loader.py

```bash
nano ~/ins-dashboard/aws_secrets_loader.py
```

Paste this content:

```python
"""
AWS Secrets Loader for INS Dashboard
"""

import boto3
import json
import os
from botocore.exceptions import ClientError

AWS_REGION = "ca-central-1"

def get_secret(secret_name):
    client = boto3.client('secretsmanager', region_name=AWS_REGION)
    try:
        response = client.get_secret_value(SecretId=secret_name)
        return json.loads(response['SecretString'])
    except ClientError as e:
        print(f"Error fetching secret {secret_name}: {e}")
        raise

def load_all_secrets():
    print("Loading secrets from AWS Secrets Manager...")

    supabase = get_secret("ins-dashboard/supabase")
    os.environ["SUPABASE_URL"] = supabase["SUPABASE_URL"]
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = supabase["SUPABASE_SERVICE_ROLE_KEY"]
    print("  Supabase credentials loaded")

    try:
        config = get_secret("ins-dashboard/config")
        for key, value in config.items():
            os.environ[key] = str(value)
        print("  Config loaded")
    except:
        print("  Config not found, using defaults")

    athletes = get_secret("ins-dashboard/athletes")
    print(f"  {len(athletes)} athletes loaded")
    return athletes

def save_athletes_json(athletes, path="athletes.json.local"):
    with open(path, 'w') as f:
        json.dump(athletes, f, indent=2)
    print(f"  Athletes saved to {path}")

if __name__ == "__main__":
    athletes = load_all_secrets()
    save_athletes_json(athletes)
    print("All secrets loaded!")
```

Save: `Ctrl+O`, `Enter`, `Ctrl+X`

### 3b. Download ingestion scripts from GitHub

```bash
cd ~/ins-dashboard
curl -O https://raw.githubusercontent.com/MarcPaquet/INS_Dashboard/main/intervals_hybrid_to_supabase.py
curl -O https://raw.githubusercontent.com/MarcPaquet/INS_Dashboard/main/moving_time.py
```

### 3c. Create run_bulk_import.py

```bash
nano ~/ins-dashboard/run_bulk_import.py
```

Paste this content (adjust dates as needed):

```python
#!/usr/bin/env python3
"""
INS Dashboard Bulk Import
"""

import subprocess
import os
import sys
from datetime import datetime

from aws_secrets_loader import load_all_secrets, save_athletes_json

def run_bulk_import():
    print("=" * 60)
    print("INS Dashboard Bulk Import")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    athletes = load_all_secrets()
    save_athletes_json(athletes)

    # ADJUST THESE DATES AS NEEDED
    OLDEST = "2025-01-01"
    NEWEST = "2026-01-18"

    print(f"\nDate range: {OLDEST} to {NEWEST}")
    print(f"Athletes: {len(athletes)}")
    print("Mode: Parallel, skip weather\n")

    processes = []
    for athlete in athletes:
        name = athlete['name']
        cmd = [
            sys.executable,
            'intervals_hybrid_to_supabase.py',
            '--athlete', name,
            '--oldest', OLDEST,
            '--newest', NEWEST,
            '--wellness-oldest', OLDEST,
            '--wellness-newest', NEWEST,
            '--skip-weather'
        ]
        log_file = open(f"import_{name.replace(' ', '_')}.log", 'w')
        print(f"  Starting: {name}")
        p = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, env=os.environ.copy())
        processes.append((name, p, log_file))

    print("\nWaiting for imports to complete...\n")

    results = []
    for name, p, log_file in processes:
        p.wait()
        log_file.close()
        status = "OK" if p.returncode == 0 else "FAILED"
        results.append((name, p.returncode))
        print(f"  [{status}] {name}")

    print("\n" + "=" * 60)
    success = sum(1 for _, code in results if code == 0)
    failed = len(results) - success
    print(f"Done: {success} success, {failed} failed")
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(run_bulk_import())
```

Save: `Ctrl+O`, `Enter`, `Ctrl+X`

---

## Step 4: Test AWS Secrets

```bash
cd ~/ins-dashboard
source venv/bin/activate
python aws_secrets_loader.py
```

**Expected output:**
```
Loading secrets from AWS Secrets Manager...
  Supabase credentials loaded
  Config loaded
  18 athletes loaded
  Athletes saved to athletes.json.local
All secrets loaded!
```

**If you get "AccessDeniedException":**
- Check IAM policy has correct region: `ca-central-1` (not `us-east-1`)
- See [Troubleshooting](#troubleshooting) section

---

## Step 5: Run Dry-Run Test

Test with one athlete before running full import:

```bash
python intervals_hybrid_to_supabase.py \
  --athlete "Matthew Beaudet" \
  --oldest 2026-01-01 \
  --newest 2026-01-18 \
  --skip-weather \
  --dry-run
```

This shows what would be imported without actually inserting data.

---

## Step 6: Run Bulk Import

**Option A: Run in foreground (if you'll keep the tab open)**
```bash
python -u run_bulk_import.py 2>&1 | tee bulk_import_main.log
```

**Option B: Run in background (recommended - can close browser)**
```bash
nohup python -u run_bulk_import.py > bulk_import_main.log 2>&1 &
```

You'll see a process ID like `[1] 16297`. The import will continue even if you close the browser.

---

## Step 7: Monitor Progress

### Check if still running:
```bash
ps aux | grep intervals_hybrid | grep -v grep | wc -l
```
Shows number of athlete imports still running. When it reaches 0, all done.

### View individual athlete logs:
```bash
tail -50 ~/ins-dashboard/import_Matthew_Beaudet.log
```

### Watch log in real-time:
```bash
tail -f ~/ins-dashboard/import_Matthew_Beaudet.log
```
Press `Ctrl+C` to stop watching.

### Check log file sizes (bigger = more progress):
```bash
ls -lhS ~/ins-dashboard/import_*.log
```

### View main log (shows results when complete):
```bash
cat ~/ins-dashboard/bulk_import_main.log
```

---

## Step 8: After Import

### 8a. Verify Results

```bash
cat ~/ins-dashboard/bulk_import_main.log
```

Should show:
```
============================================================
Done: 18 success, 0 failed
Finished: 2026-01-18 XX:XX:XX
============================================================
```

### 8b. TERMINATE EC2 INSTANCE

**IMPORTANT:** Don't forget this step to avoid charges!

1. Go to **AWS Console** → **EC2** → **Instances**
2. Select `INS-Bulk-Import`
3. Click **Instance state** → **Terminate instance**
4. Confirm termination

---

## Troubleshooting

### "AccessDeniedException" when loading secrets

**Cause:** IAM policy has wrong region.

**Fix:**
1. Go to **IAM** → **Policies** → `INS-Dashboard-SecretsAccess`
2. Click **Edit**
3. Change Resource from:
   ```
   arn:aws:secretsmanager:us-east-1:*:secret:ins-dashboard/*
   ```
   To:
   ```
   arn:aws:secretsmanager:ca-central-1:852798039375:secret:ins-dashboard/*
   ```
4. Save

### "source: not found"

**Cause:** Session Manager uses `sh` by default.

**Fix:** Run `bash` first before other commands.

### "python: not found"

**Cause:** Virtual environment not activated.

**Fix:**
```bash
bash
cd ~/ins-dashboard
source venv/bin/activate
```

### Session Manager won't connect

**Cause:** SSM agent not ready or IAM role missing.

**Fix:**
1. Wait 3-5 minutes after instance launch
2. Verify IAM role has `AmazonSSMManagedInstanceCore` policy

---

## Updating Athletes

To add, remove, or update athletes in AWS Secrets Manager:

1. Go to **AWS Console** → **Secrets Manager** → `ins-dashboard/athletes`
2. Click **Retrieve secret value**
3. Click **Edit**
4. Modify the JSON array:

```json
[
  {"id": "i344978", "name": "Matthew Beaudet", "api_key": "xxx"},
  {"id": "i453408", "name": "Alex Larochelle", "api_key": "xxx"},
  ...
]
```

5. Click **Save**

### Current Athletes (as of Jan 18, 2026)

| Name | Intervals.icu ID |
|------|------------------|
| Matthew Beaudet | i344978 |
| Kevin Robertson | i344979 |
| Kevin A. Robertson | i344980 |
| Sophie Courville | i95073 |
| Zakary Mama-Yari | i347434 |
| Alex Larochelle | i453408 |
| Alexandrine Coursol | i454587 |
| Doan Tran | i453651 |
| Jade Essabar | i453683 |
| Marc-Andre Trudeau Perron | i453625 |
| Marine Garnier | i197667 |
| Myriam Poirier | i453790 |
| Nazim Berrichi | i453396 |
| Robin Lefebvre | i453411 |
| Yassine Aber | i453944 |
| Evans Stephen | i454589 |
| Cedrik Flipo | i486574 |
| Renaud Bordeleau | i482119 |

---

## Quick Reference

### EC2 Connection
```bash
# AWS Console → EC2 → Instances → INS-Bulk-Import → Connect → Session Manager
bash
cd ~/ins-dashboard
source venv/bin/activate
```

### Run Import
```bash
nohup python -u run_bulk_import.py > bulk_import_main.log 2>&1 &
```

### Check Progress
```bash
ps aux | grep intervals_hybrid | grep -v grep | wc -l
cat bulk_import_main.log
```

### View Logs
```bash
tail -50 import_Matthew_Beaudet.log
ls -lhS import_*.log
```

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-18 | Initial bulk import (18 athletes, 2025-01-01 to 2026-01-18) |

---

**END OF GUIDE**
