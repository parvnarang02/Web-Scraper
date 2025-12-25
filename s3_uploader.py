"""
S3 Image Uploader for AWS Lambda deployment.

This module provides functionality to download images from URLs and upload them
to S3 for stable, persistent storage. Used in image search mode.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse
import hashlib

import aiohttp
import boto3
from botocore.exceptions import ClientError, BotoCoreError


logger = logging.getLogger(__name__)


class S3UploadError(Exception):
    """Exception raised when S3 upload fails."""
    pass


async def upload_image_to_s3(
    image_url: str,
    bucket: str,
    key_prefix: str = "images",
    max_retries: int = 3,
    timeout_seconds: int = 10
) -> str:
    """
    Download image from URL and upload to S3.
    
    Args:
        image_url: Source image URL to download
        bucket: S3 bucket name
        key_prefix: S3 key prefix (default: "images")
        max_retries: Maximum number of retry attempts (default: 3)
        timeout_seconds: Timeout for image download (default: 10)
        
    Returns:
        S3 URL of uploaded image (format: s3://bucket/key)
        
    Raises:
        S3UploadError: If upload fails after all retries
        ValueError: If image_url or bucket is invalid
    """
    if not image_url:
        raise ValueError("image_url cannot be empty")
    if not bucket:
        raise ValueError("bucket cannot be empty")
    
    # Generate unique S3 key with timestamp and hash
    s3_key = _generate_s3_key(image_url, key_prefix)
    
    # Download image with retries
    image_data = await _download_image_with_retry(
        image_url, 
        max_retries, 
        timeout_seconds
    )
    
    # Upload to S3 with retries
    await _upload_to_s3_with_retry(
        image_data,
        bucket,
        s3_key,
        max_retries
    )
    
    # Return S3 URL
    s3_url = f"s3://{bucket}/{s3_key}"
    logger.info(f"Successfully uploaded image to {s3_url}")
    
    return s3_url


def _generate_s3_key(image_url: str, key_prefix: str) -> str:
    """
    Generate unique S3 key with timestamp and URL hash.
    
    Args:
        image_url: Source image URL
        key_prefix: Key prefix
        
    Returns:
        S3 key in format: {prefix}/{timestamp}_{hash}.{ext}
    """
    # Extract file extension from URL
    parsed_url = urlparse(image_url)
    path = parsed_url.path
    extension = path.split('.')[-1] if '.' in path else 'jpg'
    
    # Limit extension length and ensure it's alphanumeric
    extension = ''.join(c for c in extension if c.isalnum())[:10]
    if not extension:
        extension = 'jpg'
    
    # Generate hash of URL for uniqueness
    url_hash = hashlib.md5(image_url.encode()).hexdigest()[:12]
    
    # Generate timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Construct S3 key
    s3_key = f"{key_prefix}/{timestamp}_{url_hash}.{extension}"
    
    return s3_key


async def _download_image_with_retry(
    image_url: str,
    max_retries: int,
    timeout_seconds: int
) -> bytes:
    """
    Download image from URL with retry logic.
    
    Args:
        image_url: Source image URL
        max_retries: Maximum retry attempts
        timeout_seconds: Request timeout
        
    Returns:
        Image data as bytes
        
    Raises:
        S3UploadError: If download fails after all retries
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            timeout = aiohttp.ClientTimeout(total=timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        logger.debug(
                            f"Downloaded image from {image_url} "
                            f"({len(image_data)} bytes)"
                        )
                        return image_data
                    else:
                        raise S3UploadError(
                            f"Failed to download image: HTTP {response.status}"
                        )
        
        except asyncio.TimeoutError as e:
            last_error = e
            logger.warning(
                f"Timeout downloading image (attempt {attempt + 1}/{max_retries}): "
                f"{image_url}"
            )
        
        except aiohttp.ClientError as e:
            last_error = e
            logger.warning(
                f"Client error downloading image (attempt {attempt + 1}/{max_retries}): "
                f"{str(e)}"
            )
        
        except Exception as e:
            last_error = e
            logger.warning(
                f"Error downloading image (attempt {attempt + 1}/{max_retries}): "
                f"{str(e)}"
            )
        
        # Exponential backoff before retry
        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)
    
    # All retries failed
    raise S3UploadError(
        f"Failed to download image after {max_retries} attempts: {str(last_error)}"
    )


async def _upload_to_s3_with_retry(
    image_data: bytes,
    bucket: str,
    s3_key: str,
    max_retries: int
) -> None:
    """
    Upload image data to S3 with retry logic.
    
    Args:
        image_data: Image data as bytes
        bucket: S3 bucket name
        s3_key: S3 object key
        max_retries: Maximum retry attempts
        
    Raises:
        S3UploadError: If upload fails after all retries
    """
    s3_client = boto3.client('s3')
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Upload to S3
            s3_client.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=image_data,
                ContentType=_guess_content_type(s3_key)
            )
            
            logger.debug(f"Uploaded image to s3://{bucket}/{s3_key}")
            return
        
        except ClientError as e:
            last_error = e
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            logger.warning(
                f"S3 ClientError (attempt {attempt + 1}/{max_retries}): "
                f"{error_code} - {str(e)}"
            )
        
        except BotoCoreError as e:
            last_error = e
            logger.warning(
                f"S3 BotoCoreError (attempt {attempt + 1}/{max_retries}): "
                f"{str(e)}"
            )
        
        except Exception as e:
            last_error = e
            logger.warning(
                f"Error uploading to S3 (attempt {attempt + 1}/{max_retries}): "
                f"{str(e)}"
            )
        
        # Exponential backoff before retry
        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)
    
    # All retries failed
    raise S3UploadError(
        f"Failed to upload to S3 after {max_retries} attempts: {str(last_error)}"
    )


def _guess_content_type(s3_key: str) -> str:
    """
    Guess content type from S3 key extension.
    
    Args:
        s3_key: S3 object key
        
    Returns:
        Content-Type header value
    """
    extension = s3_key.split('.')[-1].lower()
    
    content_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp',
        'svg': 'image/svg+xml',
        'bmp': 'image/bmp',
        'ico': 'image/x-icon'
    }
    
    return content_types.get(extension, 'application/octet-stream')
