# Multi-Engine Web Search & Scraping API

A high-performance, cost-effective web search and scraping API powered by AWS Lambda and Playwright. Get clean, LLM-ready content from multiple search engines with intelligent fallback and parallel processing.

## Overview

This tool provides a serverless API for web search and content scraping, designed as a cost-effective alternative to commercial SERP APIs. It uses real browser automation (Playwright) to search multiple engines and extract clean, readable content.

### Key Features

- **Multi-Engine Search**: Brave, Startpage, Yahoo, and Yandex with automatic fallback
- **Intelligent Scraping**: Parallel browser tabs with adaptive memory management
- **LLM-Ready Content**: Clean text extraction with quality filtering
- **Image Search**: Bing-powered image search with S3 storage
- **Cost Effective**: ~$0.0015 per request vs $0.005+ for SERP APIs
- **Serverless**: AWS Lambda with automatic scaling
- **Production Ready**: Structured logging, error handling, and monitoring

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ HTTPS
       ▼
┌─────────────────┐
│  API Gateway    │
│  (HTTP API)     │
└────────┬────────┘
         │
         ▼
┌──────────────────────────────────────┐
│     AWS Lambda (Container)           │
│  ┌────────────────────────────────┐  │
│  │  Playwright Browser Engine     │  │
│  │  - Chromium with stealth mode  │  │
│  │  - 11 parallel tabs (10GB)     │  │
│  │  - User agent rotation         │  │
│  └────────────────────────────────┘  │
│  ┌────────────────────────────────┐  │
│  │  Search Engine Integrations    │  │
│  │  - Brave (primary)             │  │
│  │  - Startpage (fallback)        │  │
│  │  - Yahoo (fallback)            │  │
│  │  - Yandex (fallback)           │  │
│  │  - Bing Images                 │  │
│  └────────────────────────────────┘  │
│  ┌────────────────────────────────┐  │
│  │  Content Processing            │  │
│  │  - Parallel scraping           │  │
│  │  - Quality filtering           │  │
│  │  - Duplicate removal           │  │
│  │  - LLM readability check       │  │
│  └────────────────────────────────┘  │
└──────────┬───────────────────────────┘
           │
           ▼
    ┌──────────────┐
    │  Amazon S3   │
    │   (Images)   │
    └──────────────┘
           │
           ▼
    ┌──────────────┐
    │  CloudWatch  │
    │    (Logs)    │
    └──────────────┘
```

### How It Works

1. **Request**: Client sends search query to API Gateway
2. **Search**: Lambda searches primary engine (Brave) with buffer for quality
3. **Fallback**: If results insufficient, tries Startpage → Yahoo → Yandex
4. **Scrape**: Opens parallel browser tabs to extract content from URLs
5. **Filter**: Removes duplicates, blocks low-quality sites, validates readability
6. **Return**: Sends clean, structured JSON response with content

### Performance Characteristics

- **Cold Start**: 8-12 seconds (first request after idle)
- **Warm Request**: 15-20 seconds for k=15 results
- **Memory**: 10GB Lambda with 11 parallel tabs
- **Timeout**: 120 seconds maximum
- **Throughput**: ~200 requests/minute with proper concurrency

## API Reference

### Base URL

```
https://9bn49m5pk4.execute-api.us-east-1.amazonaws.com
```

### Content Search API

Search for web content and scrape full text from results.

**Endpoint**: `POST /`

**Request Body**:
```json
{
  "query": "artificial intelligence",
  "k": 10
}
```

**Parameters**:
- `query` (string, required): Search query (1-500 characters)
- `k` (integer, optional): Number of results to return (1-20, default: 5)

**Response** (200 OK):
```json
{
  "query": "artificial intelligence",
  "engine": "brave",
  "results": [
    {
      "url": "https://example.com/ai-guide",
      "title": "Complete Guide to Artificial Intelligence",
      "content": "Artificial intelligence (AI) is the simulation of human intelligence...",
      "word_count": 1250,
      "success": true,
      "error": null,
      "images": []
    }
  ],
  "total_time": 17.5
}
```

**Response Fields**:
- `query`: Original search query
- `engine`: Engine(s) used (e.g., "brave" or "brave+startpage" for fallback)
- `results`: Array of scraped content objects
  - `url`: Page URL
  - `title`: Page title
  - `content`: Extracted text content (clean, LLM-ready)
  - `word_count`: Number of words in content
  - `success`: Whether scraping succeeded
  - `error`: Error message if scraping failed
  - `images`: Array of image URLs found on page
- `total_time`: Total execution time in seconds

**Example Request**:
```bash
curl -X POST "https://9bn49m5pk4.execute-api.us-east-1.amazonaws.com" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "python web scraping",
    "k": 5
  }'
```

### Image Search API

Search for images and get direct image URLs.

**Endpoint**: `POST /`

**Request Body**:
```json
{
  "query": "mountain landscape",
  "k": 10,
  "image": true
}
```

**Parameters**:
- `query` (string, required): Image search query (1-500 characters)
- `k` (integer, optional): Number of images to return (1-20, default: 5)
- `image` (boolean, required): Must be `true` for image search

**Response** (200 OK):
```json
{
  "query": "mountain landscape",
  "engine": "bing",
  "results": [
    {
      "url": "https://example.com/image1.jpg",
      "title": "",
      "content": "",
      "word_count": 0,
      "success": true,
      "error": null,
      "images": ["https://example.com/image1.jpg"]
    }
  ],
  "total_time": 8.2
}
```

**Example Request**:
```bash
curl -X POST "https://9bn49m5pk4.execute-api.us-east-1.amazonaws.com" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "cute puppies",
    "k": 15,
    "image": true
  }'
```

### Error Responses

**400 Bad Request** - Invalid parameters:
```json
{
  "error": "InvalidParameter",
  "message": "k must be between 1 and 20",
  "requestId": "abc-123-def-456"
}
```

**500 Internal Server Error** - Server error:
```json
{
  "error": "InternalError",
  "message": "Internal server error: Browser session failed",
  "requestId": "abc-123-def-456"
}
```

**504 Gateway Timeout** - Request exceeded timeout:
```json
{
  "error": "TimeoutError",
  "message": "Request exceeded maximum execution time",
  "requestId": "abc-123-def-456"
}
```

## Cost Comparison

### This API vs SERP API

| Feature | This API | SerpAPI | Parallel Web API |
|---------|----------|---------|------------------|
| **Cost per 1,000 requests** | ~$3.30 | $5.00+ | $10.00+ |
| **Monthly cost (10K requests)** | ~$33 | $50+ | $100+ |
| **Content scraping included** | ✅ Yes | ❌ No | ✅ Yes |
| **Full page content** | ✅ Yes | ❌ Snippets only | ✅ Yes |
| **Image search** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Multiple engines** | ✅ 4 engines | ✅ 10+ engines | ✅ 5+ engines |
| **Rate limits** | Your AWS limits | 100/sec | 50/sec |
| **Setup complexity** | Medium | Low | Low |
| **Infrastructure control** | ✅ Full | ❌ None | ❌ None |

### Detailed Cost Breakdown

**AWS Lambda Costs** (10GB memory, 20s avg execution):
- Compute: $0.0000166667 per GB-second
- Per request: 10 GB × 20s × $0.0000166667 = **$0.0033**
- 1,000 requests: **$3.30**
- 10,000 requests: **$33.00**

**API Gateway Costs**:
- $1.00 per million requests
- 10,000 requests: **$0.01**

**S3 Storage** (for images):
- $0.023 per GB/month
- 1 GB stored: **$0.023/month**

**CloudWatch Logs**:
- $0.50 per GB ingested
- ~100 MB/month: **$0.05**

**Total Monthly Cost** (10,000 requests):
- Lambda: $33.00
- API Gateway: $0.01
- S3: $0.02
- CloudWatch: $0.05
- **Total: ~$33/month** or **$0.0033 per request**

### Cost Savings

Compared to SerpAPI at $50/month for 10,000 requests:
- **Savings**: $17/month (34% cheaper)
- **Annual savings**: $204

Compared to Parallel Web API at $100/month:
- **Savings**: $67/month (67% cheaper)
- **Annual savings**: $804

### When to Use This API

**Use this API when**:
- You need full page content, not just snippets
- You want to control infrastructure and costs
- You need 5,000+ requests per month
- You want to customize scraping logic
- You need multiple search engines with fallback

**Use commercial API when**:
- You need <1,000 requests per month
- You want zero infrastructure management
- You need specialized search features (shopping, news, etc.)
- You need instant setup with no DevOps

### Note on S3 Image Storage

The S3 uploader module (`s3_uploader.py`) is included in the codebase but **not currently used**. Image search returns direct image URLs from Bing without uploading to S3. This reduces latency and costs. If you need persistent image storage, you can integrate the S3 uploader by modifying the image search logic in `web_search_tool.py`.

## Quick Start

### Prerequisites

- AWS Account with CLI configured
- Docker installed
- Python 3.11+

### 1. Deploy to AWS

```bash
# Clone repository
git clone <your-repo>
cd web-search-tool

# Set AWS variables
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create ECR repository
aws ecr create-repository --repository-name web-search-lambda --region $AWS_REGION

# Build and push Docker image
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

docker build -t web-search-lambda .
docker tag web-search-lambda:latest \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/web-search-lambda:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/web-search-lambda:latest

# Create S3 bucket for images
export S3_BUCKET_NAME=web-search-images-$AWS_ACCOUNT_ID
aws s3 mb s3://$S3_BUCKET_NAME --region $AWS_REGION

# Create IAM role (see DEPLOYMENT.md for full commands)
# Create Lambda function (see DEPLOYMENT.md for full commands)
# Create API Gateway (see DEPLOYMENT.md for full commands)
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for complete deployment instructions.

### 2. Test the API

```bash
# Get your API endpoint
export API_ENDPOINT=$(aws apigatewayv2 get-apis \
  --query "Items[?Name=='web-search-api'].ApiEndpoint" \
  --output text --region $AWS_REGION)

# Test content search
curl -X POST "$API_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"query": "machine learning", "k": 5}'

# Test image search
curl -X POST "$API_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"query": "sunset beach", "k": 10, "include_images": true}'
```

## Configuration

### Environment Variables

Configure Lambda function via environment variables:

```bash
aws lambda update-function-configuration \
  --function-name web-search-function \
  --environment Variables="{
    S3_BUCKET_NAME=your-bucket-name,
    S3_REGION=us-east-1,
    MAX_PARALLEL_TABS=11,
    SCRAPE_TIMEOUT_MS=10000,
    LOG_LEVEL=INFO
  }"
```

**Available Variables**:
- `S3_BUCKET_NAME` (required): S3 bucket for image storage
- `S3_REGION` (optional): AWS region for S3 (default: us-east-1)
- `MAX_PARALLEL_TABS` (optional): Parallel browser tabs (default: 11)
- `SCRAPE_TIMEOUT_MS` (optional): Timeout per page in ms (default: 10000)
- `LOG_LEVEL` (optional): Logging level (default: INFO)

### Memory and Performance Tuning

**Current Configuration**: 10GB memory, 11 parallel tabs

Adjust based on your needs:

```bash
# Increase to 12GB for 13 parallel tabs
aws lambda update-function-configuration \
  --function-name web-search-function \
  --memory-size 12288

# Update parallel tabs
aws lambda update-function-configuration \
  --function-name web-search-function \
  --environment Variables="{...,MAX_PARALLEL_TABS=13}"
```

**Memory Guidelines**:
- 8GB → 12 tabs
- 10GB → 11-15 tabs
- 12GB → 13-18 tabs

## Features

### Intelligent Search Fallback

The system automatically tries multiple search engines if results are insufficient:

1. **Brave** (primary) - Fast, privacy-focused
2. **Startpage** (fallback) - Google results with privacy
3. **Yahoo** (fallback) - Bing-powered results
4. **Yandex** (fallback) - Russian search engine

Response includes which engines were used:
```json
{
  "engine": "brave+startpage",  // Used both engines
  "results": [...]
}
```

### Quality Filtering

Automatic filtering ensures high-quality results:

- **Duplicate removal**: Normalizes URLs to detect duplicates
- **Blocked domains**: Filters social media, forums (Reddit, Twitter, etc.)
- **Content validation**: Minimum 50 words, LLM-readable text
- **Error filtering**: Removes 403/404 pages

### Adaptive Memory Management

The system monitors memory usage and adjusts parallelism:

- **Normal**: 11 parallel tabs
- **High memory**: Reduces to 5 tabs
- **Approaching timeout**: Returns partial results

### Structured Logging

All requests logged to CloudWatch with structured JSON:

```json
{
  "timestamp": "2024-12-01T10:30:00Z",
  "level": "INFO",
  "message": "Search completed",
  "request_id": "abc-123",
  "query": "python tutorials",
  "k": 10,
  "results_count": 10,
  "engine_used": "brave",
  "total_time": 18.5,
  "memory_usage_mb": 2048.5
}
```

## Monitoring

### CloudWatch Metrics

Key metrics to monitor:

- **Invocations**: Total requests
- **Duration**: Execution time
- **Errors**: Failed requests
- **Throttles**: Rate-limited requests
- **Memory**: Peak memory usage

### CloudWatch Logs Insights Queries

**Average execution time**:
```sql
fields @timestamp, total_time
| filter stage = "search_completed"
| stats avg(total_time) as avg_time, max(total_time) as max_time
```

**Error rate**:
```sql
fields @timestamp, error
| filter stage = "execution_failed"
| stats count() by error
```

**Memory usage**:
```sql
fields @timestamp, memory_usage_mb
| filter stage = "search_completed"
| stats avg(memory_usage_mb) as avg_memory, max(memory_usage_mb) as max_memory
```

## Limitations

- **Rate limits**: Search engines may block excessive requests
- **Cold starts**: First request after idle takes 8-12 seconds
- **Timeout**: Maximum 120 seconds per request
- **Results**: Maximum 20 results per request (k ≤ 20)
- **Content**: Some sites block automated scraping
- **Image search**: Available but may have limited results depending on query

## Troubleshooting

### Empty Results

**Cause**: Search engines blocking requests or no valid content found

**Solution**:
- Try different search engine: `"engine": "startpage"`
- Reduce k value: `"k": 5`
- Check CloudWatch logs for specific errors

### Timeout Errors

**Cause**: Request exceeded 120 second limit

**Solution**:
- Reduce k value
- Increase Lambda timeout (max 900s)
- Check if specific sites are slow

### High Costs

**Cause**: Long execution times or high request volume

**Solution**:
- Reduce memory allocation if not needed
- Optimize k value (lower = faster)
- Set reserved concurrency to limit parallel executions
- Enable S3 lifecycle policies to delete old images

## Development

### Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally with test payload
python -c "
import json
from lambda_handler import lambda_handler

event = {
    'body': json.dumps({'query': 'test', 'k': 3})
}

class Context:
    aws_request_id = 'local-test'
    memory_limit_in_mb = 10240

result = lambda_handler(event, Context())
print(json.dumps(json.loads(result['body']), indent=2))
"
```

### Running Tests

```bash
# Run with Docker locally
docker run -p 9000:8080 \
  -e S3_BUCKET_NAME=test-bucket \
  web-search-lambda

# Test endpoint
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -d '{"body": "{\"query\": \"test\", \"k\": 3}"}'
```

## License

MIT License - see LICENSE file for details

## Support

For issues, questions, or contributions:
- Open an issue on GitHub
- Check [DEPLOYMENT.md](DEPLOYMENT.md) for detailed setup
- Review CloudWatch logs for debugging

---

**Built with**: AWS Lambda, Playwright, Python 3.11, Chromium
