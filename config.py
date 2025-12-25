"""
Configuration management for AWS Lambda deployment.

Loads and validates environment variables for the web search Lambda function.
"""

import os
from typing import Optional


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


class Config:
    """
    Centralized configuration from environment variables.
    
    Validates required environment variables and provides typed access
    to configuration values with sensible defaults.
    """
    
    # Required environment variables
    _REQUIRED_VARS = ["S3_BUCKET_NAME"]
    
    # S3 Configuration
    S3_BUCKET_NAME: Optional[str] = None
    S3_REGION: str = "us-east-1"
    
    # Performance Configuration
    MAX_PARALLEL_TABS: int = 20
    SCRAPE_TIMEOUT_MS: int = 8000
    MAX_RESULTS_LIMIT: int = 20
    
    # Lambda Configuration
    MEMORY_MB: int = 3072
    TIMEOUT_SECONDS: int = 60
    
    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    
    @classmethod
    def load(cls) -> None:
        """
        Load configuration from environment variables.
        
        Reads environment variables and populates class attributes.
        Does not validate - call validate() separately.
        """
        # Required S3 configuration
        cls.S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
        cls.S3_REGION = os.environ.get("S3_REGION", "us-east-1")
        
        # Performance configuration with defaults
        cls.MAX_PARALLEL_TABS = int(os.environ.get("MAX_PARALLEL_TABS", "20"))
        cls.SCRAPE_TIMEOUT_MS = int(os.environ.get("SCRAPE_TIMEOUT_MS", "8000"))
        cls.MAX_RESULTS_LIMIT = int(os.environ.get("MAX_RESULTS_LIMIT", "20"))
        
        # Lambda configuration
        cls.MEMORY_MB = int(os.environ.get("MEMORY_MB", "3072"))
        cls.TIMEOUT_SECONDS = int(os.environ.get("TIMEOUT_SECONDS", "60"))
        
        # Logging configuration
        cls.LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    
    @classmethod
    def validate(cls) -> None:
        """
        Validate required environment variables exist.
        
        Raises:
            ConfigurationError: If required environment variables are missing
                with a clear message indicating which variables are missing.
        """
        missing_vars = []
        
        for var in cls._REQUIRED_VARS:
            value = os.environ.get(var)
            if not value:
                missing_vars.append(var)
        
        if missing_vars:
            missing_list = ", ".join(missing_vars)
            raise ConfigurationError(
                f"Missing required environment variable(s): {missing_list}. "
                f"Please set these variables before starting the Lambda function."
            )
        
        # Validate value ranges
        if cls.MAX_PARALLEL_TABS < 1:
            raise ConfigurationError(
                f"MAX_PARALLEL_TABS must be at least 1, got {cls.MAX_PARALLEL_TABS}"
            )
        
        if cls.SCRAPE_TIMEOUT_MS < 1000:
            raise ConfigurationError(
                f"SCRAPE_TIMEOUT_MS must be at least 1000ms, got {cls.SCRAPE_TIMEOUT_MS}"
            )
        
        if cls.MAX_RESULTS_LIMIT < 1:
            raise ConfigurationError(
                f"MAX_RESULTS_LIMIT must be at least 1, got {cls.MAX_RESULTS_LIMIT}"
            )
        
        if cls.MEMORY_MB < 128:
            raise ConfigurationError(
                f"MEMORY_MB must be at least 128, got {cls.MEMORY_MB}"
            )
    
    @classmethod
    def initialize(cls) -> None:
        """
        Load and validate configuration in one step.
        
        This is the main entry point for configuration setup.
        Call this at Lambda initialization time for fail-fast behavior.
        
        Raises:
            ConfigurationError: If configuration is invalid or missing.
        """
        cls.load()
        cls.validate()
    
    @classmethod
    def get_adaptive_max_tabs(cls, current_memory_mb: int) -> int:
        """
        Calculate max tabs based on available memory.
        
        Adapts parallelism based on memory pressure to prevent OOM errors.
        
        Args:
            current_memory_mb: Current memory usage in MB
            
        Returns:
            Recommended maximum number of parallel tabs
        """
        available = cls.MEMORY_MB - current_memory_mb
        
        if available < 500:
            return 5  # Minimal parallelism
        elif available < 1000:
            return 10  # Moderate parallelism
        else:
            return min(cls.MAX_PARALLEL_TABS, 20)  # Full parallelism
    
    @classmethod
    def to_dict(cls) -> dict:
        """
        Export configuration as a dictionary.
        
        Useful for logging and debugging.
        
        Returns:
            Dictionary of configuration values
        """
        return {
            "S3_BUCKET_NAME": cls.S3_BUCKET_NAME,
            "S3_REGION": cls.S3_REGION,
            "MAX_PARALLEL_TABS": cls.MAX_PARALLEL_TABS,
            "SCRAPE_TIMEOUT_MS": cls.SCRAPE_TIMEOUT_MS,
            "MAX_RESULTS_LIMIT": cls.MAX_RESULTS_LIMIT,
            "MEMORY_MB": cls.MEMORY_MB,
            "TIMEOUT_SECONDS": cls.TIMEOUT_SECONDS,
            "LOG_LEVEL": cls.LOG_LEVEL,
        }
