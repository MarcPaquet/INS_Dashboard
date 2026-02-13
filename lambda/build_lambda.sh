#!/bin/bash
# Build Lambda deployment package for INS Dashboard
#
# This script creates a ZIP file ready to upload to AWS Lambda.
# Uses Lambda Layers for pandas/numpy to keep package size small.
#
# Usage:
#   cd lambda/
#   ./build_lambda.sh

set -e

echo "=========================================="
echo "Building INS Dashboard Lambda Package"
echo "=========================================="

# Clean up
rm -rf package/
rm -f lambda_deployment.zip

# Create package directory
mkdir -p package/

echo ""
echo "Step 1a: Installing pandas/numpy for Lambda (Linux x86_64)..."
pip install --target package/ \
    --platform manylinux2014_x86_64 \
    --implementation cp \
    --python-version 3.11 \
    --only-binary=:all: \
    pandas \
    numpy \
    --quiet

echo ""
echo "Step 1b: Installing pure Python packages..."
pip install --target package/ \
    requests \
    python-dotenv \
    fitparse \
    boto3 \
    --quiet

echo ""
echo "Step 2: Copying Lambda scripts..."
cp lambda_function.py package/
cp aws_secrets_loader.py package/

echo ""
echo "Step 3: Copying ingestion scripts from parent..."
cp ../intervals_hybrid_to_supabase.py package/
cp ../moving_time.py package/

echo ""
echo "Step 4: Creating ZIP file..."
cd package/
zip -r ../lambda_deployment.zip . -x "*.pyc" -x "__pycache__/*" -x "*.dist-info/*" -x "*.egg-info/*"
cd ..

# Get size
SIZE=$(du -h lambda_deployment.zip | cut -f1)
echo ""
echo "=========================================="
echo "Build complete!"
echo "  File: lambda_deployment.zip"
echo "  Size: $SIZE"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Upload lambda_deployment.zip to AWS Lambda"
echo "  2. Set timeout to 5 minutes, memory to 512 MB"
echo "  3. Test the function"
