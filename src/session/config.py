"""Configuration for session behavior."""

from dataclasses import dataclass


@dataclass
class SessionConfig:
    """Configuration for session behavior.
    
    Simple configuration for session timeouts and monitoring.
    """
    
    # Monitoring and metrics
    enable_metrics: bool = False
    
    # Timeout settings
    default_execute_timeout: float = 30.0
    ready_timeout: float = 10.0
    shutdown_timeout: float = 5.0