#!/usr/bin/env python3
# components/Logger.py
"""
Centralized Logging Component for XSpace Downloader

This component provides centralized logging functionality for all components.
It checks the DEBUG_LOGGING environment variable to determine whether to
enable file logging for components.

Features:
- Centralized logging configuration
- Environment-based debug logging control
- Component-specific log files in logs/ directory
- Fallback to console logging when debug is disabled
- Thread-safe logging
- Log rotation support

Usage Examples:
    
    # In any component
    from components.Logger import get_logger
    
    class MyComponent:
        def __init__(self):
            self.logger = get_logger('my_component')
            self.logger.info("Component initialized")
        
        def some_method(self):
            self.logger.debug("Debug information")
            self.logger.info("Important information")
            self.logger.warning("Warning message")
            self.logger.error("Error occurred")
"""

import logging
import os
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

# Global logger cache to avoid duplicate loggers
_loggers = {}
_debug_logging_enabled = None

def is_debug_logging_enabled():
    """
    Check if debug logging is enabled via environment variable.
    
    Returns:
        bool: True if DEBUG_LOGGING is set to 'true', False otherwise
    """
    global _debug_logging_enabled
    
    if _debug_logging_enabled is None:
        debug_value = os.environ.get('DEBUG_LOGGING', 'false').lower()
        _debug_logging_enabled = debug_value in ('true', '1', 'yes', 'on')
    
    return _debug_logging_enabled

def get_logger(component_name, level=logging.INFO):
    """
    Get a logger for a specific component.
    
    Args:
        component_name (str): Name of the component (e.g., 'email', 'space', 'user')
        level (int): Logging level (default: logging.INFO)
    
    Returns:
        logging.Logger: Configured logger instance
    """
    global _loggers
    
    # Return cached logger if it exists
    if component_name in _loggers:
        return _loggers[component_name]
    
    # Create new logger
    logger = logging.getLogger(f"{component_name}_component")
    logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    if is_debug_logging_enabled():
        # Debug mode: Log to file
        setup_file_logging(logger, component_name, formatter)
    else:
        # Production mode: Log to console only (captured by systemd/gunicorn)
        setup_console_logging(logger, formatter)
    
    # Prevent propagation to avoid duplicate messages
    logger.propagate = False
    
    # Cache the logger
    _loggers[component_name] = logger
    
    return logger

def setup_file_logging(logger, component_name, formatter):
    """
    Setup file logging for a component.
    
    Args:
        logger (logging.Logger): Logger instance
        component_name (str): Component name for log file
        formatter (logging.Formatter): Log formatter
    """
    # Create logs directory if it doesn't exist
    logs_dir = Path('logs')
    logs_dir.mkdir(exist_ok=True)
    
    # Create file handler with rotation
    log_file = logs_dir / f'{component_name}.log'
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # Also add console handler for immediate feedback
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info(f"Debug logging enabled for {component_name} component")

def setup_console_logging(logger, formatter):
    """
    Setup console-only logging for a component.
    
    Args:
        logger (logging.Logger): Logger instance
        formatter (logging.Formatter): Log formatter
    """
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)

def setup_app_logging(app_name='app', level=logging.INFO):
    """
    Setup logging for the main application.
    
    Args:
        app_name (str): Application name for log files
        level (int): Logging level
    
    Returns:
        logging.Logger: Configured app logger
    """
    app_logger = logging.getLogger(app_name)
    app_logger.setLevel(level)
    
    # Remove existing handlers
    for handler in app_logger.handlers[:]:
        app_logger.removeHandler(handler)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    if is_debug_logging_enabled():
        # Debug mode: Log to file
        logs_dir = Path('logs')
        logs_dir.mkdir(exist_ok=True)
        
        # App log file with rotation
        log_file = logs_dir / f'{app_name}.log'
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=20*1024*1024,  # 20MB for main app
            backupCount=10,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        app_logger.addHandler(file_handler)
        
        # Console handler for immediate feedback
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        app_logger.addHandler(console_handler)
        
        app_logger.info(f"Debug logging enabled for {app_name} application")
    else:
        # Production mode: Console only
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        app_logger.addHandler(console_handler)
    
    app_logger.propagate = False
    return app_logger

def configure_werkzeug_logging():
    """Configure Werkzeug (Flask development server) logging."""
    if is_debug_logging_enabled():
        werkzeug_logger = logging.getLogger('werkzeug')
        
        # Create file handler for werkzeug
        logs_dir = Path('logs')
        logs_dir.mkdir(exist_ok=True)
        
        log_file = logs_dir / 'werkzeug.log'
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        werkzeug_logger.addHandler(file_handler)
        werkzeug_logger.setLevel(logging.INFO)

# Auto-configure on import
if is_debug_logging_enabled():
    configure_werkzeug_logging()