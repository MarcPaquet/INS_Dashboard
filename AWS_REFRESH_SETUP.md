# AWS Lambda Function URL Setup for Manual Refresh

This guide explains how to enable the "Sync" button in the dashboard to trigger on-demand data refresh.

## Overview

The Sync button calls your existing Lambda function (`ins-dashboard-daily-ingestion`) via HTTP to trigger an immediate data sync for all athletes.

## Step 1: Generate a Refresh Token

Create a secure random token (this will be your shared secret):

```bash
# Generate a 32-character random token
openssl rand -hex 16
```

Save this token - you'll need it for both AWS and ShinyApps.io.

Example token: `a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6`

## Step 2: Configure Lambda Environment Variable

1. Go to **AWS Console → Lambda → ins-dashboard-daily-ingestion**
2. Click **Configuration → Environment variables**
3. Click **Edit** and add:
   - Key: `REFRESH_TOKEN`
   - Value: `<your-token-from-step-1>`
4. Click **Save**

## Step 3: Create Function URL

1. Go to **AWS Console → Lambda → ins-dashboard-daily-ingestion**
2. Click **Configuration → Function URL**
3. Click **Create function URL**
4. Settings:
   - **Auth type:** `NONE` (we use custom Bearer token auth)
   - **Configure cross-origin resource sharing (CORS):** ✅ Enable
   - **Allow origin:** `*`
   - **Allow methods:** `POST`
   - **Allow headers:** `Authorization, Content-Type`
5. Click **Save**
6. Copy the **Function URL** (e.g., `https://abc123xyz.lambda-url.ca-central-1.on.aws/`)

## Step 4: Update Lambda Code

The Lambda function needs to be updated to handle Function URL requests. Upload the new code:

```bash
cd lambda/
./build_lambda.sh
# Then upload lambda_deployment.zip to AWS Lambda
```

Or manually update via AWS Console → Lambda → Code → Upload from .zip file.

## Step 5: Configure ShinyApps.io

Add these environment variables to your ShinyApps.io app:

1. Go to **shinyapps.io → Your App → Settings → Environment Variables**
2. Add:
   - `LAMBDA_FUNCTION_URL`: `https://abc123xyz.lambda-url.ca-central-1.on.aws/`
   - `LAMBDA_REFRESH_TOKEN`: `<your-token-from-step-1>`
3. Click **Save**

## Step 6: Redeploy Dashboard

```bash
SSL_CERT_FILE=/opt/anaconda3/lib/python3.12/site-packages/certifi/cacert.pem rsconnect deploy shiny . \
  --entrypoint app:app \
  --name insquebec-sportsciences \
  --app-id 16149191 \
  --exclude ".cache" \
  --exclude "*.parquet" \
  # ... (use full deploy command from CLAUDE.md)
```

## Testing

1. Log in to the dashboard
2. You should see a blue "Sync" button next to "Logout"
3. Click it - status will show "Synchronisation en cours..."
4. Wait up to 10 minutes for all athletes to sync
5. Status will show "Daily ingestion completed: 18/18 successful"

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Sync button not visible | Check `LAMBDA_FUNCTION_URL` is set in ShinyApps.io |
| "Erreur d'authentification" | Check `LAMBDA_REFRESH_TOKEN` matches in both AWS and ShinyApps |
| "Server not configured" | Add `REFRESH_TOKEN` to Lambda environment variables |
| Timeout after 15 min | Lambda is still running - check CloudWatch logs |

## Security Notes

- The refresh token acts as a shared secret between dashboard and Lambda
- Function URL with auth type NONE is safe because we validate the Bearer token
- The token should be rotated periodically (update in both AWS and ShinyApps.io)
