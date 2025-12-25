"""
AWS Lambda handler for web search and scraping tool.
Provides API Gateway integration for content and image search.
"""

import json
import logging
import os
import traceback
import time
from dataclasses import dataclass, field
from typing import Optional, Any, Dict
import asyncio

# Configure structured JSON logging for CloudWatch
class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
        }
        
        # Add extra fields if present
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id
        if hasattr(record, 'query'):
            log_data['query'] = record.query
        if hasattr(record, 'k'):
            log_data['k'] = record.k
        if hasattr(record, 'engine'):
            log_data['engine'] = record.engine
        if hasattr(record, 'include_images'):
            log_data['include_images'] = record.include_images
        if hasattr(record, 'stage'):
            log_data['stage'] = record.stage
        if hasattr(record, 'results_count'):
            log_data['results_count'] = record.results_count
        if hasattr(record, 'engine_used'):
            log_data['engine_used'] = record.engine_used
        if hasattr(record, 'total_time'):
            log_data['total_time'] = record.total_time
        if hasattr(record, 'memory_usage_mb'):
            log_data['memory_usage_mb'] = record.memory_usage_mb
        if hasattr(record, 'memory_available_mb'):
            log_data['memory_available_mb'] = record.memory_available_mb
        if hasattr(record, 'error'):
            log_data['error'] = record.error
        if hasattr(record, 'stack_trace'):
            log_data['stack_trace'] = record.stack_trace
        if hasattr(record, 'http_method'):
            log_data['http_method'] = record.http_method
        if hasattr(record, 'memory_limit_mb'):
            log_data['memory_limit_mb'] = record.memory_limit_mb
        
        return json.dumps(log_data)

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Add JSON formatter to handler
if logger.handlers:
    for handler in logger.handlers:
        handler.setFormatter(JSONFormatter())
else:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

# Import web search tool and resource monitor
from web_search_tool import WebSearchToolPlaywright
from resource_monitor import ResourceMonitor


@dataclass
class ContentSearchRequest:
    """Request model for content search."""
    query: str
    k: int = 5
    engine: str = "brave"
    
    def validate(self) -> None:
        """Validate request parameters."""
        if not self.query or len(self.query.strip()) == 0:
            raise ValueError("Query cannot be empty")
        if len(self.query) > 500:
            raise ValueError("Query must be 1-500 characters")
        if self.k < 1 or self.k > 20:
            raise ValueError("k must be between 1 and 20")
        if self.engine not in ["brave", "startpage", "yahoo", "yandex"]:
            raise ValueError("Unsupported engine. Must be one of: brave, startpage, yahoo, yandex")


@dataclass
class ImageSearchRequest:
    """Request model for image search."""
    query: str
    k: int = 5
    include_images: bool = True
    
    def validate(self) -> None:
        """Validate request parameters."""
        if not self.query or len(self.query.strip()) == 0:
            raise ValueError("Query cannot be empty")
        if len(self.query) > 500:
            raise ValueError("Query must be 1-500 characters")
        if self.k < 1 or self.k > 20:
            raise ValueError("k must be between 1 and 20")


@dataclass
class LambdaResponse:
    """Response model for Lambda function."""
    status_code: int
    body: Dict[str, Any]
    headers: Dict[str, str] = field(default_factory=lambda: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    })
    
    def to_api_gateway_response(self) -> Dict[str, Any]:
        """Convert to API Gateway response format."""
        return {
            "statusCode": self.status_code,
            "body": json.dumps(self.body),
            "headers": self.headers
        }


@dataclass
class ErrorResponse:
    """Error response model."""
    error: str
    message: str
    request_id: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "error": self.error,
            "message": self.message,
            "requestId": self.request_id
        }


def parse_request_body(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse request body from API Gateway event.
    
    Args:
        event: API Gateway event
        
    Returns:
        Parsed request body as dictionary
        
    Raises:
        ValueError: If body is missing or invalid JSON
    """
    body = event.get('body')
    
    if not body:
        raise ValueError("Request body is required")
    
    # Handle base64 encoded body
    if event.get('isBase64Encoded', False):
        import base64
        body = base64.b64decode(body).decode('utf-8')
    
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in request body: {str(e)}")


def create_error_response(
    error_type: str,
    message: str,
    status_code: int,
    request_id: str
) -> Dict[str, Any]:
    """
    Create standardized error response.
    
    Args:
        error_type: Type of error (e.g., "InvalidParameter", "InternalError")
        message: Human-readable error message
        status_code: HTTP status code
        request_id: Request ID for tracking
        
    Returns:
        API Gateway response dictionary
    """
    error_response = ErrorResponse(
        error=error_type,
        message=message,
        request_id=request_id
    )
    
    lambda_response = LambdaResponse(
        status_code=status_code,
        body=error_response.to_dict()
    )
    
    return lambda_response.to_api_gateway_response()


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler function.
    
    Args:
        event: API Gateway event containing:
            - body: JSON with query, k, engine, include_images
            - httpMethod: POST or OPTIONS
            - headers: request headers
        context: Lambda context object
        
    Returns:
        dict: API Gateway response with:
            - statusCode: HTTP status (200, 400, 500, 504)
            - body: JSON string with results or error
            - headers: CORS and content-type headers
    """
    request_id = context.aws_request_id if context else "local"
    start_time = time.time()
    
    # Initialize resource monitor for memory tracking
    resource_monitor = ResourceMonitor()
    
    # Log request with structured data
    logger.info("Lambda invocation started", extra={
        "request_id": request_id,
        "stage": "invocation_started",
        "http_method": event.get('httpMethod', 'UNKNOWN'),
        "memory_limit_mb": getattr(context, 'memory_limit_in_mb', 'unknown'),
        "memory_usage_mb": resource_monitor.get_memory_usage_mb()
    })
    
    # Initialize variables for error logging context
    query = None
    k = None
    engine = None
    include_images = None
    
    try:
        # Handle OPTIONS request for CORS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return LambdaResponse(
                status_code=200,
                body={"message": "OK"}
            ).to_api_gateway_response()
        
        # Parse request body
        try:
            body = parse_request_body(event)
        except ValueError as e:
            logger.warning("Invalid request body", extra={
                "request_id": request_id,
                "stage": "request_parsing_failed",
                "error": str(e)
            })
            return create_error_response(
                error_type="InvalidRequest",
                message=str(e),
                status_code=400,
                request_id=request_id
            )
        
        # Extract parameters
        query = body.get('query')
        k = body.get('k', 5)
        engine = body.get('engine', 'brave')
        include_images = body.get('include_images', False)
        
        # Validate and create request object
        try:
            if include_images:
                request = ImageSearchRequest(
                    query=query,
                    k=k,
                    include_images=include_images
                )
            else:
                request = ContentSearchRequest(
                    query=query,
                    k=k,
                    engine=engine
                )
            request.validate()
        except (ValueError, TypeError) as e:
            logger.warning("Invalid parameters", extra={
                "request_id": request_id,
                "stage": "validation_failed",
                "query": query,
                "k": k,
                "engine": engine,
                "include_images": include_images,
                "error": str(e)
            })
            return create_error_response(
                error_type="InvalidParameter",
                message=str(e),
                status_code=400,
                request_id=request_id
            )
        
        # Log search started with all parameters
        logger.info("Search started", extra={
            "request_id": request_id,
            "stage": "search_started",
            "query": query,
            "k": k,
            "engine": engine if not include_images else "bing",
            "include_images": include_images,
            "memory_usage_mb": resource_monitor.get_memory_usage_mb(),
            "memory_available_mb": resource_monitor.get_memory_available_mb()
        })
        
        # Execute search and scrape with resource monitoring
        tool = WebSearchToolPlaywright(resource_monitor=resource_monitor)
        
        # Log scraping started
        logger.info("Scraping started", extra={
            "request_id": request_id,
            "stage": "scraping_started",
            "query": query,
            "k": k,
            "engine": engine if not include_images else "bing",
            "memory_usage_mb": resource_monitor.get_memory_usage_mb()
        })
        
        # Run async function in event loop
        result = asyncio.run(tool.search_and_scrape(
            query=query,
            k=k,
            engine=engine,
            include_images=include_images,
            lambda_context=context
        ))
        
        # Convert result to dictionary
        result_dict = result.to_dict()
        
        # Calculate total execution time
        total_execution_time = time.time() - start_time
        
        # Log completion with comprehensive metrics
        logger.info("Search completed", extra={
            "request_id": request_id,
            "stage": "search_completed",
            "query": query,
            "k": k,
            "engine": engine if not include_images else "bing",
            "results_count": len(result.results),
            "engine_used": result.engine,
            "total_time": result.total_time,
            "total_execution_time": total_execution_time,
            "memory_usage_mb": resource_monitor.get_memory_usage_mb(),
            "memory_available_mb": resource_monitor.get_memory_available_mb()
        })
        
        # Return success response
        return LambdaResponse(
            status_code=200,
            body=result_dict
        ).to_api_gateway_response()
        
    except Exception as e:
        # Log error with full context and stack trace
        error_msg = str(e)
        stack_trace = traceback.format_exc()
        
        logger.error("Lambda execution failed", extra={
            "request_id": request_id,
            "stage": "execution_failed",
            "error": error_msg,
            "stack_trace": stack_trace,
            "query": query,
            "k": k,
            "engine": engine,
            "include_images": include_images,
            "memory_usage_mb": resource_monitor.get_memory_usage_mb(),
            "total_execution_time": time.time() - start_time
        })
        
        # Return error response
        return create_error_response(
            error_type="InternalError",
            message=f"Internal server error: {error_msg}",
            status_code=500,
            request_id=request_id
        )
