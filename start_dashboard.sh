#!/bin/bash

# Load environment from .env.dashboard.local
export $(cat .env.dashboard.local | grep -v '^#' | xargs)

# Confirm connection
echo "=================================================="
echo "Starting INS Dashboard"
echo "=================================================="
echo "Database: $SUPABASE_URL"
echo "=================================================="
echo ""

# Start dashboard
python supabase_shiny.py
