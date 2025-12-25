"""
Resource monitoring for AWS Lambda environment.

Tracks memory usage and execution time to enable adaptive behavior
and prevent out-of-memory errors or timeouts.
"""

import os
import psutil
from typing import Optional


class ResourceMonitor:
    """Monitor Lambda function resource usage and adapt behavior accordingly."""
    
    def __init__(self):
        """Initialize the resource monitor."""
        self.process = psutil.Process(os.getpid())
    
    def get_memory_usage_mb(self) -> float:
        """
        Get current memory usage in MB.
        
        Returns:
            float: Current memory usage in megabytes
        """
        memory_info = self.process.memory_info()
        return memory_info.rss / (1024 * 1024)  # Convert bytes to MB
    
    def get_memory_available_mb(self) -> float:
        """
        Get available memory in MB.
        
        Uses the Lambda environment variable AWS_LAMBDA_FUNCTION_MEMORY_SIZE
        to determine allocated memory, then subtracts current usage.
        
        Returns:
            float: Available memory in megabytes
        """
        # Get allocated memory from Lambda environment variable
        allocated_mb = int(os.environ.get('AWS_LAMBDA_FUNCTION_MEMORY_SIZE', '3072'))
        current_usage_mb = self.get_memory_usage_mb()
        return allocated_mb - current_usage_mb
    
    def should_reduce_parallelism(self, threshold: float = 0.8) -> bool:
        """
        Check if memory usage exceeds threshold.
        
        Args:
            threshold: Memory usage threshold as a fraction (default: 0.8 = 80%)
        
        Returns:
            bool: True if memory usage exceeds threshold, False otherwise
        """
        allocated_mb = int(os.environ.get('AWS_LAMBDA_FUNCTION_MEMORY_SIZE', '3072'))
        current_usage_mb = self.get_memory_usage_mb()
        usage_ratio = current_usage_mb / allocated_mb
        return usage_ratio > threshold
    
    def get_time_remaining_seconds(self, context) -> float:
        """
        Get remaining execution time from Lambda context.
        
        Args:
            context: AWS Lambda context object
        
        Returns:
            float: Remaining execution time in seconds
        """
        if context is None:
            # If no context provided (e.g., local testing), return a large value
            return 999999.0
        
        # Lambda context provides get_remaining_time_in_millis()
        remaining_ms = context.get_remaining_time_in_millis()
        return remaining_ms / 1000.0
    
    def should_return_partial_results(
        self, 
        context, 
        buffer: float = 5.0
    ) -> bool:
        """
        Check if approaching timeout and should return partial results.
        
        Args:
            context: AWS Lambda context object
            buffer: Time buffer in seconds before timeout (default: 5.0)
        
        Returns:
            bool: True if time remaining is less than buffer, False otherwise
        """
        remaining_seconds = self.get_time_remaining_seconds(context)
        return remaining_seconds < buffer
