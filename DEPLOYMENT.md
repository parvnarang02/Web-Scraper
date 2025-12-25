# AWS Lambda Deployment Guide

This guide provides step-by-step instructions for deploying the Multi-Engine Web Search & Scraping System to AWS Lambda with API Gateway integration.

## Prerequisites

- AWS Account with appropriate permissions
- AWS CLI installed and configured (`aws configure`)
- Docker installed and running
- Python 3.11+ installed locally (for testing)

## Architecture Overview

```
API Client → API Gateway → Lambda Function (Container) → Search Engines
                                ↓
                          S3 (Images) + CloudWatch (Logs)
```

## Deployment Steps

### Step 1: Create ECR Repository

Amazon ECR (Elastic Container Registry) will store your Docker container image.

```bash
# Set your AWS region
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create ECR repository
aws ecr create-repository \
  --repository-name web-search-lambda \
  --region $AWS_REGION

# Expected output:
# {
#     "repository": {
#         "repositoryArn": "arn:aws:ecr:us-east-1:123456789012:repository/web-search-lambda",
#         "repositoryUri": "123456789012.dkr.ecr.us-east-1.amazonaws.com/web-search-lambda"
#     }
# }
```

### Step 2: Build and Push Docker Image

Build the container image and push it to ECR.

```bash
# Authenticate Docker to ECR
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Build the Docker image
docker build -t web-search-lambda .

# Tag the image for ECR
docker tag web-search-lambda:latest \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/web-search-lambda:latest

# Push to ECR
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/web-search-lambda:latest
```

**Note**: The initial build may take 5-10 minutes due to Playwright and Chromium installation.

### Step 3: Create S3 Bucket for Images

Create an S3 bucket to store scraped images (required for image search functionality).

```bash
# Create S3 bucket with unique name
export S3_BUCKET_NAME=web-search-images-$AWS_ACCOUNT_ID

aws s3 mb s3://$S3_BUCKET_NAME --region $AWS_REGION

# Enable versioning (optional but recommended)
aws s3api put-bucket-versioning \
  --bucket $S3_BUCKET_NAME \
  --versioning-configuration Status=Enabled

# Set lifecycle policy to delete old images after 30 days (optional)
cat > lifecycle-policy.json << 'EOF'
{
  "Rules": [
    {
      "Id": "DeleteOldImages",
      "Status": "Enabled",
      "Prefix": "images/",
      "Expiration": {
        "Days": 30
      }
    }
  ]
}
EOF

aws s3api put-bucket-lifecycle-configuration \
  --bucket $S3_BUCKET_NAME \
  --lifecycle-configuration file://lifecycle-policy.json
```

### Step 4: Create IAM Role for Lambda

Create an IAM role with permissions for CloudWatch Logs and S3 access.

```bash
# Create trust policy for Lambda
cat > trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create the IAM role
aws iam create-role \
  --role-name web-search-lambda-role \
  --assume-role-policy-document file://trust-policy.json \
  --description "Execution role for web search Lambda function"

# Attach AWS managed policy for basic Lambda execution (CloudWatch Logs)
aws iam attach-role-policy \
  --role-name web-search-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Create custom policy for S3 access
cat > s3-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:PutObjectAcl",
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::$S3_BUCKET_NAME/*"
    }
  ]
}
EOF

# Attach S3 policy to role
aws iam put-role-policy \
  --role-name web-search-lambda-role \
  --policy-name s3-access-policy \
  --policy-document file://s3-policy.json

# Wait for IAM role to propagate (important!)
echo "Waiting 10 seconds for IAM role to propagate..."
sleep 10
```

### Step 5: Create Lambda Function

Create the Lambda function using the container image from ECR.

```bash
# Create Lambda function
aws lambda create-function \
  --function-name web-search-function \
  --package-type Image \
  --code ImageUri=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/web-search-lambda:latest \
  --role arn:aws:iam::$AWS_ACCOUNT_ID:role/web-search-lambda-role \
  --memory-size 3072 \
  --timeout 60 \
  --environment Variables="{
    S3_BUCKET_NAME=$S3_BUCKET_NAME,
    S3_REGION=$AWS_REGION,
    MAX_PARALLEL_TABS=20,
    SCRAPE_TIMEOUT_MS=8000,
    LOG_LEVEL=INFO
  }" \
  --region $AWS_REGION

# Expected output includes FunctionArn - save this for later
```

**Configuration Notes**:
- **Memory**: 3072 MB (3 GB) - adjust based on workload (2048-4096 MB range)
- **Timeout**: 60 seconds - maximum for web scraping operations
- **Environment Variables**:
  - `S3_BUCKET_NAME`: Your S3 bucket for images
  - `S3_REGION`: AWS region for S3
  - `MAX_PARALLEL_TABS`: Number of concurrent browser tabs (10-20)
  - `SCRAPE_TIMEOUT_MS`: Timeout per page scrape in milliseconds
  - `LOG_LEVEL`: Logging verbosity (DEBUG, INFO, WARNING, ERROR)

### Step 6: Create API Gateway HTTP API

Create an HTTP API in API Gateway to expose the Lambda function.

```bash
# Create HTTP API with Lambda integration
aws apigatewayv2 create-api \
  --name web-search-api \
  --protocol-type HTTP \
  --target arn:aws:lambda:$AWS_REGION:$AWS_ACCOUNT_ID:function:web-search-function \
  --region $AWS_REGION

# Save the API ID from output
export API_ID=$(aws apigatewayv2 get-apis \
  --query "Items[?Name=='web-search-api'].ApiId" \
  --output text \
  --region $AWS_REGION)

# Get the API endpoint
export API_ENDPOINT=$(aws apigatewayv2 get-apis \
  --query "Items[?Name=='web-search-api'].ApiEndpoint" \
  --output text \
  --region $AWS_REGION)

echo "API Endpoint: $API_ENDPOINT"

# Grant API Gateway permission to invoke Lambda
aws lambda add-permission \
  --function-name web-search-function \
  --statement-id apigateway-invoke \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:$AWS_REGION:$AWS_ACCOUNT_ID:$API_ID/*/*" \
  --region $AWS_REGION
```

### Step 7: Configure CORS (Optional)

If you need to call the API from a web browser, configure CORS.

```bash
# Update API to enable CORS
aws apigatewayv2 update-api \
  --api-id $API_ID \
  --cors-configuration AllowOrigins="*",AllowMethods="POST,OPTIONS",AllowHeaders="Content-Type" \
  --region $AWS_REGION
```

## Testing the Deployment

### Test 1: Basic Content Search

```bash
# Test content search
curl -X POST "$API_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "python programming",
    "k": 5,
    "engine": "brave"
  }'
```

**Expected Response**:
```json
{
  "query": "python programming",
  "engine": "brave",
  "results": [
    {
      "url": "https://example.com",
      "title": "Python Programming Guide",
      "content": "...",
      "images": []
    }
  ],
  "total_time": 12.5
}
```

### Test 2: Image Search

```bash
# Test image search
curl -X POST "$API_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "cute puppies",
    "k": 3,
    "include_images": true
  }'
```

### Test 3: Error Handling

```bash
# Test invalid parameters (should return 400)
curl -X POST "$API_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "test",
    "k": 100
  }'
```

**Expected Response**:
```json
{
  "error": "InvalidParameter",
  "message": "k must be between 1 and 20",
  "requestId": "abc-123-def"
}
```

## Monitoring and Logs

### View CloudWatch Logs

```bash
# List log streams
aws logs describe-log-streams \
  --log-group-name /aws/lambda/web-search-function \
  --order-by LastEventTime \
  --descending \
  --max-items 5 \
  --region $AWS_REGION

# Get latest log stream name
export LOG_STREAM=$(aws logs describe-log-streams \
  --log-group-name /aws/lambda/web-search-function \
  --order-by LastEventTime \
  --descending \
  --max-items 1 \
  --query 'logStreams[0].logStreamName' \
  --output text \
  --region $AWS_REGION)

# View logs
aws logs get-log-events \
  --log-group-name /aws/lambda/web-search-function \
  --log-stream-name "$LOG_STREAM" \
  --region $AWS_REGION
```

### CloudWatch Insights Queries

Use CloudWatch Logs Insights for structured log analysis:

```sql
# Query average execution time
fields @timestamp, total_time
| filter @type = "search_completed"
| stats avg(total_time) as avg_time, max(total_time) as max_time, count() as requests

# Query error rates
fields @timestamp, error, message
| filter @type = "error"
| stats count() by error

# Query memory usage
fields @timestamp, memory_used_mb, memory_allocated_mb
| filter @type = "search_completed"
| stats avg(memory_used_mb) as avg_memory, max(memory_used_mb) as max_memory
```

## Updating the Deployment

### Update Lambda Code

When you make code changes, rebuild and push the image, then update Lambda:

```bash
# Rebuild and push image
docker build -t web-search-lambda .
docker tag web-search-lambda:latest \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/web-search-lambda:latest
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/web-search-lambda:latest

# Update Lambda function
aws lambda update-function-code \
  --function-name web-search-function \
  --image-uri $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/web-search-lambda:latest \
  --region $AWS_REGION

# Wait for update to complete
aws lambda wait function-updated \
  --function-name web-search-function \
  --region $AWS_REGION

echo "Lambda function updated successfully!"
```

### Update Environment Variables

```bash
# Update environment variables
aws lambda update-function-configuration \
  --function-name web-search-function \
  --environment Variables="{
    S3_BUCKET_NAME=$S3_BUCKET_NAME,
    S3_REGION=$AWS_REGION,
    MAX_PARALLEL_TABS=15,
    SCRAPE_TIMEOUT_MS=10000,
    LOG_LEVEL=DEBUG
  }" \
  --region $AWS_REGION
```

### Update Memory or Timeout

```bash
# Increase memory to 4096 MB
aws lambda update-function-configuration \
  --function-name web-search-function \
  --memory-size 4096 \
  --region $AWS_REGION

# Update timeout (max 900 seconds for Lambda)
aws lambda update-function-configuration \
  --function-name web-search-function \
  --timeout 90 \
  --region $AWS_REGION
```

## Troubleshooting

### Issue: Cold Start Times > 10 Seconds

**Symptoms**: First request after idle period takes 10+ seconds

**Solutions**:
1. Enable Provisioned Concurrency to keep instances warm:
```bash
aws lambda put-provisioned-concurrency-config \
  --function-name web-search-function \
  --provisioned-concurrent-executions 1 \
  --qualifier '$LATEST' \
  --region $AWS_REGION
```

2. Optimize Docker image size:
   - Remove unnecessary dependencies
   - Use multi-stage builds
   - Compress layers

### Issue: Out of Memory Errors

**Symptoms**: Lambda function fails with "Runtime exited with error: signal: killed"

**Solutions**:
1. Increase memory allocation:
```bash
aws lambda update-function-configuration \
  --function-name web-search-function \
  --memory-size 4096 \
  --region $AWS_REGION
```

2. Reduce parallel tabs in environment variables:
```bash
aws lambda update-function-configuration \
  --function-name web-search-function \
  --environment Variables="{
    S3_BUCKET_NAME=$S3_BUCKET_NAME,
    MAX_PARALLEL_TABS=10,
    SCRAPE_TIMEOUT_MS=8000
  }" \
  --region $AWS_REGION
```

3. Check CloudWatch logs for memory usage patterns

### Issue: Timeout Errors (504)

**Symptoms**: Requests fail after 60 seconds with timeout error

**Solutions**:
1. Reduce the number of results requested (lower `k` value)
2. Increase Lambda timeout (if needed):
```bash
aws lambda update-function-configuration \
  --function-name web-search-function \
  --timeout 90 \
  --region $AWS_REGION
```

3. Check if specific websites are slow - the system should return partial results

### Issue: S3 Upload Failures

**Symptoms**: Image search works but images aren't uploaded to S3

**Solutions**:
1. Verify IAM role has S3 permissions:
```bash
aws iam get-role-policy \
  --role-name web-search-lambda-role \
  --policy-name s3-access-policy
```

2. Check S3 bucket exists and is accessible:
```bash
aws s3 ls s3://$S3_BUCKET_NAME
```

3. Verify environment variable is set correctly:
```bash
aws lambda get-function-configuration \
  --function-name web-search-function \
  --query 'Environment.Variables' \
  --region $AWS_REGION
```

### Issue: Search Engines Blocking Requests

**Symptoms**: Empty results or errors from search engines

**Solutions**:
1. Check user agent rotation is working (review logs)
2. Verify stealth mode is enabled in Playwright configuration
3. Add delays between requests if needed
4. Try different search engines

### Issue: API Gateway 403 Forbidden

**Symptoms**: API returns 403 error when invoked

**Solutions**:
1. Verify Lambda permission for API Gateway:
```bash
aws lambda get-policy \
  --function-name web-search-function \
  --region $AWS_REGION
```

2. Re-add permission if missing:
```bash
aws lambda add-permission \
  --function-name web-search-function \
  --statement-id apigateway-invoke-new \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:$AWS_REGION:$AWS_ACCOUNT_ID:$API_ID/*/*" \
  --region $AWS_REGION
```

### Issue: Docker Build Fails

**Symptoms**: `docker build` command fails during Playwright installation

**Solutions**:
1. Ensure Docker has enough memory allocated (4GB+ recommended)
2. Check internet connectivity for downloading dependencies
3. Try building with `--no-cache` flag:
```bash
docker build --no-cache -t web-search-lambda .
```

### Debugging Tips

1. **Enable Debug Logging**:
```bash
aws lambda update-function-configuration \
  --function-name web-search-function \
  --environment Variables="{S3_BUCKET_NAME=$S3_BUCKET_NAME,LOG_LEVEL=DEBUG}" \
  --region $AWS_REGION
```

2. **Test Locally with Docker**:
```bash
# Run container locally
docker run -p 9000:8080 \
  -e S3_BUCKET_NAME=$S3_BUCKET_NAME \
  -e MAX_PARALLEL_TABS=10 \
  web-search-lambda

# Test with curl
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -d '{"body": "{\"query\": \"test\", \"k\": 3}"}'
```

3. **Check Lambda Metrics**:
```bash
# Get invocation metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=web-search-function \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum \
  --region $AWS_REGION
```

## Cost Optimization

### Estimated Costs

Based on typical usage patterns:

- **Lambda**: $0.0000166667 per GB-second
  - 3GB memory, 30s average execution: ~$0.0015 per request
  - 10,000 requests/month: ~$15/month
  
- **API Gateway**: $1.00 per million requests
  - 10,000 requests/month: ~$0.01/month
  
- **S3**: $0.023 per GB stored
  - 1GB images: ~$0.023/month
  
- **CloudWatch Logs**: $0.50 per GB ingested
  - ~100MB logs/month: ~$0.05/month

**Total**: ~$15-20/month for 10,000 requests

### Cost Reduction Strategies

1. **Use ARM64 Architecture** (20% cost savings):
```bash
# Rebuild with ARM64 base image
# Update Dockerfile first line to:
# FROM public.ecr.aws/lambda/python:3.11-arm64
```

2. **Optimize Memory Allocation**:
   - Start with 2048 MB and monitor actual usage
   - Increase only if needed

3. **Set Reserved Concurrency**:
```bash
# Limit concurrent executions to control costs
aws lambda put-function-concurrency \
  --function-name web-search-function \
  --reserved-concurrent-executions 10 \
  --region $AWS_REGION
```

4. **Enable S3 Lifecycle Policies**:
   - Automatically delete old images after 30 days
   - Move to cheaper storage classes (Glacier) for archives

## Security Best Practices

1. **Enable VPC** (if accessing private resources):
```bash
aws lambda update-function-configuration \
  --function-name web-search-function \
  --vpc-config SubnetIds=subnet-xxx,subnet-yyy,SecurityGroupIds=sg-xxx \
  --region $AWS_REGION
```

2. **Enable AWS X-Ray Tracing**:
```bash
aws lambda update-function-configuration \
  --function-name web-search-function \
  --tracing-config Mode=Active \
  --region $AWS_REGION
```

3. **Add API Key Authentication**:
```bash
# Create usage plan with API key
aws apigatewayv2 create-authorizer \
  --api-id $API_ID \
  --authorizer-type REQUEST \
  --name api-key-auth \
  --region $AWS_REGION
```

4. **Enable CloudWatch Alarms**:
```bash
# Create alarm for error rate
aws cloudwatch put-metric-alarm \
  --alarm-name web-search-errors \
  --alarm-description "Alert on high error rate" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=FunctionName,Value=web-search-function \
  --evaluation-periods 1 \
  --region $AWS_REGION
```

## Cleanup

To remove all deployed resources:

```bash
# Delete Lambda function
aws lambda delete-function \
  --function-name web-search-function \
  --region $AWS_REGION

# Delete API Gateway
aws apigatewayv2 delete-api \
  --api-id $API_ID \
  --region $AWS_REGION

# Delete S3 bucket (must be empty first)
aws s3 rm s3://$S3_BUCKET_NAME --recursive
aws s3 rb s3://$S3_BUCKET_NAME

# Delete IAM role policies
aws iam delete-role-policy \
  --role-name web-search-lambda-role \
  --policy-name s3-access-policy

aws iam detach-role-policy \
  --role-name web-search-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Delete IAM role
aws iam delete-role \
  --role-name web-search-lambda-role

# Delete ECR repository
aws ecr delete-repository \
  --repository-name web-search-lambda \
  --force \
  --region $AWS_REGION

# Delete CloudWatch log group
aws logs delete-log-group \
  --log-group-name /aws/lambda/web-search-function \
  --region $AWS_REGION
```

## Next Steps

1. **Set up CI/CD Pipeline**: Automate deployments with GitHub Actions or AWS CodePipeline
2. **Add Monitoring Dashboards**: Create CloudWatch dashboards for key metrics
3. **Implement Caching**: Add ElastiCache or DynamoDB for result caching
4. **Add Rate Limiting**: Implement per-user rate limits in API Gateway
5. **Enable Auto-scaling**: Configure provisioned concurrency auto-scaling

## Support and Resources

- [AWS Lambda Documentation](https://docs.aws.amazon.com/lambda/)
- [API Gateway Documentation](https://docs.aws.amazon.com/apigateway/)
- [Playwright Documentation](https://playwright.dev/)
- [CloudWatch Logs Insights](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AnalyzingLogData.html)

---

**Deployment Complete!** Your web search Lambda function is now live and accessible via API Gateway.
