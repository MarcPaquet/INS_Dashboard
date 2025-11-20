# 🚀 ShinyApps.io Deployment Guide - SLS Dashboard

**Project:** INS Dashboard - Saint-Laurent Sélect Running Club
**Platform:** shinyapps.io (Python Shiny)
**App Name:** SLS_Dashboard
**Account:** insquebec-sportsciences
**Created:** November 14, 2025

---

## 📋 Table of Contents

1. [Quick Start](#quick-start)
2. [Prerequisites](#prerequisites)
3. [Initial Setup (One-Time)](#initial-setup-one-time)
4. [Deployment Process](#deployment-process)
5. [Environment Variables Configuration](#environment-variables-configuration)
6. [Post-Deployment Testing](#post-deployment-testing)
7. [Troubleshooting](#troubleshooting)
8. [Updating the App](#updating-the-app)

---

## 🏃 Quick Start

If you've already completed the initial setup, deploying is simple:

```bash
cd /Users/marcantoinepaquet/Documents/INS
./deploy_shinyapps.sh
```

Then configure environment variables in the shinyapps.io dashboard (see [Environment Variables](#environment-variables-configuration)).

---

## ✅ Prerequisites

Before deploying, ensure you have:

- [x] Python 3.9+ installed (3.11+ recommended)
- [x] `rsconnect-python` package installed
- [x] shinyapps.io account credentials (token & secret)
- [x] Supabase credentials (URL & Service Role Key)
- [x] All required files in the project directory:
  - `supabase_shiny.py` (main dashboard)
  - `requirements.txt` (dependencies)
  - `moving_time.py` (utility module)
  - `auth_utils.py` (authentication utilities)

---

## 🔧 Initial Setup (One-Time)

### Step 1: Install rsconnect-python

```bash
pip install rsconnect-python
```

### Step 2: Configure shinyapps.io Account

**From R setup (converted to Python):**

```bash
rsconnect add \
  --account insquebec-sportsciences \
  --name insquebec-sportsciences \
  --token A8B30FDF5CDD0BE8F15D62A5CE40C2B1 \
  --secret 'JD0W9+yuuDNW5eeARUKKD+MDgyl8PcSrkfn7csEt'
```

**Verify configuration:**

```bash
rsconnect list
```

You should see:
```
insquebec-sportsciences (shinyapps.io - insquebec-sportsciences)
```

---

## 📦 Deployment Process

### Option 1: Using the Deployment Script (Recommended)

```bash
cd /Users/marcantoinepaquet/Documents/INS
./deploy_shinyapps.sh
```

The script will:
1. ✅ Check prerequisites
2. ✅ Verify required files
3. ⚠️  Display environment variables reminder
4. 🚀 Deploy to shinyapps.io
5. 📍 Show the app URL

### Option 2: Manual Deployment

```bash
cd /Users/marcantoinepaquet/Documents/INS

rsconnect deploy shiny \
  --account insquebec-sportsciences \
  --name SLS_Dashboard \
  --title "SLS Dashboard - INS Sports Science" \
  --python 3.11 \
  .
```

---

## 🔐 Environment Variables Configuration

**⚠️ CRITICAL: The app will NOT work until you configure these secrets!**

### Step-by-Step Guide

1. **Go to shinyapps.io Dashboard:**
   ```
   https://www.shinyapps.io/admin/#/dashboard
   ```

2. **Click on `SLS_Dashboard` application**

3. **Navigate to:** Settings → Environment Variables (or Variables)

4. **Add the following variables:**

   | Variable Name | Value |
   |---------------|-------|
   | `SUPABASE_URL` | `https://tjpmmczpcapxjfkoyjjy.supabase.co` |
   | `SUPABASE_SERVICE_ROLE_KEY` | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRqcG1tY3pwY2FweGpma295amp5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NDc0Mjg0NiwiZXhwIjoyMDcwMzE4ODQ2fQ.6-v0NhazzW1_m3nKH5D9mQTBCTd1_6VxI7bmx3fSg9w` |
   | `INS_TZ` | `America/Toronto` |

5. **Click "Save"**

6. **Restart the application:**
   - Click the "Restart" button in the dashboard
   - Or redeploy the app

### Where to Find Your Credentials

If you need to retrieve your credentials:

```bash
# Supabase URL
grep SUPABASE_URL /Users/marcantoinepaquet/Documents/INS/.env.dashboard.local

# Supabase Service Role Key
grep SUPABASE_SERVICE_ROLE_KEY /Users/marcantoinepaquet/Documents/INS/.env.dashboard.local
```

---

## 🧪 Post-Deployment Testing

After deploying and configuring environment variables, test the app:

### 1. Access the App

```
https://insquebec-sportsciences.shinyapps.io/SLS_Dashboard/
```

### 2. Test Authentication

Log in with each athlete account:

| Username | Password | Expected Behavior |
|----------|----------|-------------------|
| Matthew | Matthew | See only Matthew's data |
| Kevin1 | Kevin1 | See only Kevin1's data |
| Kevin2 | Kevin2 | See only Kevin2's data |
| Zakary | Zakary | See only Zakary's data |
| Sophie | Sophie | See only Sophie's data |
| Coach | Coach | See all athletes + dropdown selector |

### 3. Verify Data Filtering

- **Athletes:** Should ONLY see their own activities
- **Coach:** Should see all data + ability to filter by athlete

### 4. Test Features

- ✅ Activity detail view (graphs, metrics)
- ✅ Period summary (weekly volume, pie charts)
- ✅ Interval visualization (if enabled)
- ✅ Dual Y-axis charts
- ✅ Manual data entry forms
- ✅ Personal records display

### 5. Check Performance

- Monitor app logs in shinyapps.io dashboard
- Check response times (should be <2 seconds for cached queries)
- Verify no database connection errors

---

## 🐛 Troubleshooting

### Issue: "RuntimeError: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be defined"

**Solution:** Environment variables not configured in shinyapps.io
- Follow [Environment Variables Configuration](#environment-variables-configuration)
- Restart the app after saving variables

### Issue: "ModuleNotFoundError: No module named 'moving_time'"

**Solution:** Supporting files not deployed
- Ensure `moving_time.py` and `auth_utils.py` are in the same directory
- Redeploy with `./deploy_shinyapps.sh`

### Issue: "Application Error" or "500 Internal Server Error"

**Solution:** Check application logs
1. Go to https://www.shinyapps.io/admin/#/application/SLS_Dashboard
2. Click on "Logs" tab
3. Look for error messages
4. Common issues:
   - Missing environment variables
   - Database connection errors
   - Import errors

### Issue: Athletes can see other athletes' data

**Solution:** RLS (Row-Level Security) not configured
- This is expected if Phase 2A Steps 2-7 are not complete
- RLS policies need to be implemented in Supabase
- See: INS_dashboard.md → Phase 2A → Step 2

### Issue: App is slow or times out

**Solutions:**
1. Check Supabase connection from shinyapps.io server
2. Verify database indexes are created
3. Check LRU cache is working
4. Monitor app metrics in shinyapps.io dashboard
5. Consider upgrading to a paid plan for more resources

### Issue: Deployment fails with "invalid Python version"

**Solution:** Use supported Python version
```bash
rsconnect deploy shiny \
  --python 3.11 \
  .
```

Supported versions: 3.9, 3.10, 3.11, 3.12

---

## 🔄 Updating the App

When you make changes to the code:

### Quick Update

```bash
cd /Users/marcantoinepaquet/Documents/INS
./deploy_shinyapps.sh
```

### What Gets Updated

- ✅ Python code changes (`supabase_shiny.py`, `moving_time.py`, `auth_utils.py`)
- ✅ Dependencies (`requirements.txt`)
- ❌ Environment variables (must be updated manually in dashboard)

### Update Process

1. Make your code changes locally
2. Test locally: `python supabase_shiny.py`
3. Commit changes to git (optional but recommended)
4. Deploy: `./deploy_shinyapps.sh`
5. Test in production: Visit app URL
6. Monitor logs for errors

---

## 📊 Monitoring & Maintenance

### Application Dashboard

Access your app dashboard at:
```
https://www.shinyapps.io/admin/#/application/SLS_Dashboard
```

**Available Metrics:**
- 📈 Usage statistics (visits, active hours)
- 📊 Performance metrics (response times)
- 📝 Application logs (errors, warnings)
- 💾 Resource usage (memory, CPU)

### Free Tier Limits (shinyapps.io)

- **Active hours:** 25 hours/month
- **Applications:** 5 apps max
- **RAM:** 1 GB per app
- **Instances:** 1 concurrent instance

⚠️ **Monitor your usage** to avoid hitting limits!

### Recommended Monitoring

1. **Weekly:** Check application logs for errors
2. **Monthly:** Review usage statistics
3. **After updates:** Test all features thoroughly
4. **Before athlete use:** Verify data filtering works correctly

---

## 🔗 Important Links

- **App URL:** https://insquebec-sportsciences.shinyapps.io/SLS_Dashboard/
- **Dashboard:** https://www.shinyapps.io/admin/#/dashboard
- **Documentation:** https://docs.posit.co/shinyapps.io/
- **Support:** https://forum.posit.co/c/shiny/

---

## 📝 Deployment Checklist

Before going live for athletes:

- [ ] Deploy app successfully
- [ ] Configure environment variables
- [ ] Test with all 6 accounts (5 athletes + 1 coach)
- [ ] Verify data filtering (athletes see only their data)
- [ ] Test coach account (sees all + can filter)
- [ ] Check all visualizations work
- [ ] Test manual data entry forms
- [ ] Verify performance (<2s response times)
- [ ] Check application logs (no errors)
- [ ] Monitor resource usage (memory, CPU)
- [ ] Document app URL for athletes
- [ ] Create user guide for athletes (optional)

---

## 🎯 Next Steps (Future Phases)

Once Phase 2A (Authentication) is complete:

1. **Phase 2B:** Survey database integration
2. **Phase 2C:** Wellness API testing
3. **Phase 3:** Analytics engine (after 60-90 days of data)
4. **Phase 5:** Migrate to AWS for production automation

See: [INS_dashboard.md](INS_dashboard.md) for full roadmap.

---

**Last Updated:** November 14, 2025
**Maintained By:** Marc-Antoine Paquet
**Support:** Claude Code
