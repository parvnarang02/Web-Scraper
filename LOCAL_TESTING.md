# Local Testing Guide

This guide explains how to test the AWS Lambda function locally before deploying to AWS.

## Overview

The `test_local.py` script provides comprehensive local testing capabilities for the Lambda function without requiring Docker or AWS infrastructure. It simulates API Gateway events and validates both content and image search modes.

## Prerequisites

- Python 3.11+
- All dependencies installed: `pip install -r requirements.txt`
- Playwright browsers installed: `playwright install chromium`

## Quick Start

### Run All Tests

```bash
python test_local.py
```

This will run all test suites:
- Content search with valid parameters
- Image search with valid parameters
- Invalid parameter error handling
- CORS preflight OPTIONS request

### Run Specific Tests

```bash
# Test content search only
python test_local.py --test content

# Test image search only
python test_local.py --test image

# Test error handling only
python test_local.py --test invalid

# Test CORS preflight only
python test_local.py --test cors
```

### Custom Configuration

```bash
# Test with 4GB memory limit
python test_local.py --memory 4096

# Test with 30 second timeout
python test_local.py --timeout 30

# Combine options
python test_local.py --test content --memory 4096 --timeout 30
```

## Test Suites

### 1. Content Search Test

Tests the standard content search functionality:
- Query: "python programming"
- K: 3 results
- Engine: brave
- Include Images: False

**Expected Result:**
- Status Code: 200
- Response contains: query, engine, results (array), total_time
- Results array has up to 3 items

### 2. Image Search Test

Tests the image search functionality:
- Query: "cute cats"
- K: 5 results
- Include Images: True

**Expected Result:**
- Status Code: 200
- Response contains: query, engine, results (array), total_time
- Results array has up to 5 items with image URLs

### 3. Invalid Parameters Test

Tests error handling for invalid parameters:
- Query: "test"
- K: 25 (invalid - should be 1-20)
- Engine: brave

**Expected Result:**
- Status Code: 400
- Response contains: error, message, requestId
- Error type: InvalidParameter
- Message indicates k must be between 1 and 20

### 4. CORS Preflight Test

Tests CORS preflight OPTIONS request:
- HTTP Method: OPTIONS

**Expected Result:**
- Status Code: 200
- Headers include:
  - Access-Control-Allow-Origin: *
  - Access-Control-Allow-Methods: POST, OPTIONS
  - Access-Control-Allow-Headers: Content-Type

## Understanding Test Output

### Success Output

```
================================================================================
TEST: Content Search - Valid Request
================================================================================

Request:
  Query: python programming
  K: 3
  Engine: brave
  Include Images: False

✓ PASS: Content search completed

Details:
  status_code: 200
  execution_time_seconds: 12.45
  results_count: 3
  engine_used: brave
  total_time: 12.23
```

### Failure Output

```
✗ FAIL: Content search failed

Details:
  status_code: 500
  errors: ["Missing required field: results"]
  response_body: {"error": "InternalError", "message": "..."}
```

### Summary

```
================================================================================
TEST SUMMARY
================================================================================
✓ PASS: content_search
✓ PASS: image_search
✓ PASS: invalid_parameters
✓ PASS: cors_preflight

Total: 4 tests
Passed: 4
Failed: 0

🎉 All tests passed!
```

## Docker-Based Testing

For testing the actual Docker container that will be deployed to Lambda:

### 1. Build the Docker Image

```bash
docker build -t web-search-lambda .
```

### 2. Run the Container Locally

```bash
docker run -p 9000:8080 \
  -e S3_BUCKET_NAME=test-bucket \
  -e MAX_PARALLEL_TABS=10 \
  -e LOG_LEVEL=INFO \
  web-search-lambda
```

### 3. Test with curl

In another terminal:

```bash
# Content search
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -H "Content-Type: application/json" \
  -d '{
    "httpMethod": "POST",
    "body": "{\"query\": \"python programming\", \"k\": 5, \"engine\": \"brave\"}"
  }'

# Image search
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -H "Content-Type: application/json" \
  -d '{
    "httpMethod": "POST",
    "body": "{\"query\": \"cute cats\", \"k\": 5, \"include_images\": true}"
  }'

# CORS preflight
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -H "Content-Type: application/json" \
  -d '{
    "httpMethod": "OPTIONS"
  }'
```

### 4. Test with Python Script

You can also use the test_local.py script against the Docker container by modifying it to send HTTP requests to `http://localhost:9000/2015-03-31/functions/function/invocations`.

## Troubleshooting

### Import Errors

**Problem:** `ImportError: No module named 'lambda_handler'`

**Solution:** Make sure you're running the script from the project root directory where `lambda_handler.py` is located.

### Playwright Not Installed

**Problem:** `playwright._impl._api_types.Error: Executable doesn't exist`

**Solution:** Install Playwright browsers:
```bash
playwright install chromium
playwright install-deps chromium
```

### Memory Issues

**Problem:** Tests fail with memory errors

**Solution:** Reduce parallelism or increase memory limit:
```bash
python test_local.py --memory 4096
```

Or set environment variable:
```bash
export MAX_PARALLEL_TABS=5
python test_local.py
```

### Timeout Issues

**Problem:** Tests timeout before completing

**Solution:** Increase timeout or reduce k:
```bash
python test_local.py --timeout 120
```

### Docker Container Won't Start

**Problem:** Docker container exits immediately

**Solution:** Check logs:
```bash
docker logs <container-id>
```

Common issues:
- Missing environment variables (S3_BUCKET_NAME)
- Playwright not properly installed in container
- System dependencies missing

## Environment Variables

The following environment variables can be set for testing:

- `S3_BUCKET_NAME`: S3 bucket for image uploads (required for image search)
- `MAX_PARALLEL_TABS`: Maximum parallel browser tabs (default: 20)
- `SCRAPE_TIMEOUT_MS`: Timeout for scraping in milliseconds (default: 8000)
- `LOG_LEVEL`: Logging level (default: INFO)

Example:
```bash
export S3_BUCKET_NAME=my-test-bucket
export MAX_PARALLEL_TABS=10
export LOG_LEVEL=DEBUG
python test_local.py
```

## Integration with CI/CD

You can integrate this testing script into your CI/CD pipeline:

```yaml
# .github/workflows/test.yml
name: Test Lambda Function

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          playwright install chromium
          playwright install-deps chromium
      
      - name: Run local tests
        run: python test_local.py
```

## Next Steps

After successful local testing:

1. Build and push Docker image to ECR
2. Create Lambda function from container image
3. Set up API Gateway
4. Configure environment variables in Lambda
5. Test deployed function with actual API endpoint

See `DEPLOYMENT.md` for deployment instructions.
