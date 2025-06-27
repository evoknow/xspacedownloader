#!/usr/bin/env python3
"""
LoggingCursor.py - A wrapper for MySQL cursor that logs all SQL queries
"""

import time
from .SQLLogger import sql_logger


class LoggingCursor:
    """Wrapper around MySQL cursor that logs all SQL queries."""
    
    def __init__(self, cursor, component_name="Unknown"):
        """
        Initialize the logging cursor wrapper.
        
        Args:
            cursor: The actual MySQL cursor to wrap
            component_name: Name of the component using this cursor
        """
        self._cursor = cursor
        self._component_name = component_name
    
    def execute(self, query, params=None):
        """Execute a query with logging."""
        if not sql_logger.is_enabled():
            # If logging disabled, execute normally
            return self._cursor.execute(query, params)
        
        # Execute with timing and logging
        start_time = time.time()
        error = None
        
        try:
            result = self._cursor.execute(query, params)
            execution_time = time.time() - start_time
            sql_logger.log_query(query, params, execution_time, self._component_name)
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            error = str(e)
            sql_logger.log_query(query, params, execution_time, self._component_name, error)
            raise  # Re-raise the exception
    
    def executemany(self, query, seq_of_params):
        """Execute many queries with logging."""
        if not sql_logger.is_enabled():
            return self._cursor.executemany(query, seq_of_params)
        
        start_time = time.time()
        error = None
        
        try:
            result = self._cursor.executemany(query, seq_of_params)
            execution_time = time.time() - start_time
            sql_logger.log_query(f"{query} (executemany with {len(seq_of_params)} params)", 
                               str(seq_of_params)[:100] + "..." if len(str(seq_of_params)) > 100 else seq_of_params,
                               execution_time, self._component_name)
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            error = str(e)
            sql_logger.log_query(f"{query} (executemany)", str(seq_of_params)[:100] + "...", 
                               execution_time, self._component_name, error)
            raise
    
    # Delegate all other methods to the wrapped cursor
    def __getattr__(self, name):
        """Delegate all other methods to the wrapped cursor."""
        return getattr(self._cursor, name)
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if hasattr(self._cursor, '__exit__'):
            return self._cursor.__exit__(exc_type, exc_val, exc_tb)
        elif hasattr(self._cursor, 'close'):
            self._cursor.close()


def wrap_cursor(cursor, component_name="Database"):
    """
    Convenience function to wrap a cursor with logging.
    
    Args:
        cursor: MySQL cursor to wrap
        component_name: Name of the component for logging
        
    Returns:
        LoggingCursor: Wrapped cursor with SQL logging
    """
    return LoggingCursor(cursor, component_name)