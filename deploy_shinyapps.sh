#!/bin/bash
# ============================================================================
# Deployment script for SLS_Dashboard to shinyapps.io
# Project: INS Dashboard - Saint-Laurent Sélect Running Club
# ============================================================================

set -e  # Exit on error

echo "🚀 Starting deployment to shinyapps.io..."

# ============================================================================
# CONFIGURATION
# ============================================================================

APP_NAME="SLS_Dashboard"
ACCOUNT_NAME="insquebec-sportsciences"
PYTHON_VERSION="3.11"  # Or your preferred version (3.9-3.12 supported)

# ============================================================================
# PRE-DEPLOYMENT CHECKS
# ============================================================================

echo "📋 Running pre-deployment checks..."

# Check if rsconnect-python is installed
if ! command -v rsconnect &> /dev/null; then
    echo "❌ rsconnect-python not found. Installing..."
    pip install rsconnect-python
fi

# Check if account is configured
if ! rsconnect list 2>&1 | grep -q "$ACCOUNT_NAME"; then
    echo "❌ Account '$ACCOUNT_NAME' not configured."
    echo "Please run: rsconnect add --account $ACCOUNT_NAME --token YOUR_TOKEN --secret YOUR_SECRET"
    exit 1
fi

# Check required files exist
REQUIRED_FILES=(
    "supabase_shiny.py"
    "requirements.txt"
    "moving_time.py"
    "auth_utils.py"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "❌ Required file missing: $file"
        exit 1
    fi
done

echo "✅ All pre-deployment checks passed!"

# ============================================================================
# ENVIRONMENT VARIABLES WARNING
# ============================================================================

echo ""
echo "⚠️  POST-DEPLOYMENT: Configure Environment Variables"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Go to: https://www.shinyapps.io/admin/#/application/$APP_NAME"
echo "Settings → Environment Variables, then add:"
echo "  - SUPABASE_URL"
echo "  - SUPABASE_SERVICE_ROLE_KEY"
echo "  - INS_TZ = America/Toronto"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
read -p "Press Enter to continue (Ctrl+C to cancel)..."

# ============================================================================
# DEPLOYMENT
# ============================================================================

echo ""
echo "📦 Deploying $APP_NAME to shinyapps.io..."
echo ""

# Deploy the Shiny app
# Note: rsconnect will auto-detect Python version from the environment
rsconnect deploy shiny \
    --account "$ACCOUNT_NAME" \
    --name "$APP_NAME" \
    --title "SLS Dashboard - INS Sports Science" \
    .

# ============================================================================
# POST-DEPLOYMENT
# ============================================================================

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📍 Your app should be available at:"
echo "   https://$ACCOUNT_NAME.shinyapps.io/$APP_NAME/"
echo ""
echo "⚠️  NEXT STEPS (CRITICAL):"
echo "1. Configure environment variables (see instructions above)"
echo "2. Test the application with each athlete account"
echo "3. Verify data filtering works correctly"
echo "4. Check performance and logs"
echo ""
echo "📊 Monitor your app at:"
echo "   https://www.shinyapps.io/admin/#/application/$APP_NAME"
echo ""
