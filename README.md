# 🏃 INS Dashboard - Sports Performance Analytics

**A sports science analytics platform for the Saint-Laurent Sélect Running Club, integrating Intervals.icu data with weather and wellness metrics.**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![Supabase](https://img.shields.io/badge/Database-Supabase-green.svg)](https://supabase.com)
[![Shiny](https://img.shields.io/badge/Dashboard-Shiny-orange.svg)](https://shiny.posit.co/py/)
[![Live](https://img.shields.io/badge/Status-Production-brightgreen.svg)](https://insquebec-sportsciences.shinyapps.io/saintlaurentselect_dashboard/)

---

## 🎯 Overview

```
Intervals.icu (watches) → Supabase (database) → Shiny Dashboard (analytics)
```

The INS Dashboard provides:
- **🔄 Automated Data Ingestion** from Intervals.icu (activities + wellness)
- **🌤️ Weather Integration** with Open-Meteo API (100% coverage)
- **📊 Interactive Dashboard** with CTL/ATL/TSB, interval analysis, and performance metrics
- **🔐 Role-Based Access** (5 athletes + 1 coach)

---

## 📊 Live Dashboard

**Production:** https://insquebec-sportsciences.shinyapps.io/saintlaurentselect_dashboard/

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Supabase account
- Intervals.icu API access

### Installation

```bash
# Clone repository
git clone https://github.com/MarcPaquet/INS_Dashboard.git
cd INS_Dashboard

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Supabase credentials

# Create athletes.json.local with athlete API keys
```

### Run Dashboard Locally
```bash
shiny run supabase_shiny.py
# Access at http://localhost:8000
```

### Import Data
```bash
# Import recent activities (includes wellness automatically)
python intervals_hybrid_to_supabase.py --oldest 2025-11-01 --newest 2025-11-29

# Dry run (test without writing)
python intervals_hybrid_to_supabase.py --oldest 2025-11-01 --newest 2025-11-29 --dry-run

# Specific athlete
python intervals_hybrid_to_supabase.py --athlete "Matthew Beaudet" --oldest 2024-01-01 --newest 2024-12-31
```

---

## 📁 Project Structure

```
INS_Dashboard/
├── supabase_shiny.py              # Main dashboard application
├── intervals_hybrid_to_supabase.py # Data ingestion (activities + wellness)
├── moving_time.py                 # Strava-style moving time algorithm
├── auth_utils.py                  # Password hashing for authentication
├── requirements.txt               # Python dependencies
├── complete_database_schema.sql   # Full database schema
├── CLAUDE.md                      # Project context & backlog
└── migrations/                    # SQL migration files
```

---

## 🏗️ Architecture

### Data Flow
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ INTERVALS.ICU│     │   SUPABASE   │     │ SHINYAPPS.IO │
│   (Source)   │────▶│ (PostgreSQL) │◀────│ (Dashboard)  │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    ▲
       │                    │
       ▼                    │
┌──────────────┐     ┌──────────────┐
│  FIT Files   │     │  OPEN-METEO  │
│  (Binary)    │     │  (Weather)   │
└──────────────┘     └──────────────┘
```

### Key Features
- **FIT File Parsing** with Streams API fallback
- **Weather Enrichment** via Open-Meteo (archive + forecast cascade)
- **Wellness Integration** - HRV, sleep, soreness (daily for all athletes)
- **UPSERT** - Safe to run multiple times per day

---

## 🔧 Configuration

### Environment Variables
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
OM_TIMEOUT=10   # Open-Meteo timeout
AQ_TIMEOUT=10   # Air Quality timeout
```

### Athletes Configuration (`athletes.json.local`)
```json
[
  {
    "id": "i344978",
    "name": "Athlete Name",
    "api_key": "intervals_icu_api_key"
  }
]
```

---

## 📈 Data Statistics

| Metric | Count |
|--------|-------|
| Activities | 970+ |
| GPS Records | 2.5M+ |
| Intervals | 10,400+ |
| Weather Coverage | 100% |

---

## 🔒 Security

- API keys stored locally (`.gitignore`)
- Environment variables for credentials
- Role-based access control (athlete vs coach)
- No hardcoded secrets in repository

---

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

---

**🎯 Built for athletes, by athletes. Train smarter with data-driven insights.**
