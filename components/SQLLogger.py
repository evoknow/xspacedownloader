#!/usr/bin/env python3
"""
SQL Query Logger Component for XSpace Downloader
Logs SQL queries with execution time when enabled by admin settings.
"""

import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

class SQLLogger:
    """Handles SQL query logging with performance metrics."""
    
    def __init__(self, log_dir='./logs'):
        """
        Initialize SQL Logger.
        
        Args:
            log_dir (str): Directory to store SQL logs
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Set up dedicated SQL logger
        self.logger = logging.getLogger('sql_queries')
        self.logger.setLevel(logging.INFO)
        
        # Create SQL-specific log file
        sql_log_file = self.log_dir / 'sql_queries.log'
        if not any(isinstance(h, logging.FileHandler) and h.baseFilename == str(sql_log_file) 
                  for h in self.logger.handlers):
            handler = logging.FileHandler(sql_log_file)
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        self._enabled = False
        self._load_settings()
    
    def _load_settings(self):
        """Load SQL logging settings from config."""
        try:
            config_file = Path('./mainconfig.json')
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    self._enabled = config.get('sql_logging_enabled', False)
        except Exception:
            self._enabled = False
    
    def is_enabled(self) -> bool:
        """Check if SQL logging is currently enabled."""
        self._load_settings()  # Reload settings each time
        return self._enabled
    
    def enable_logging(self) -> bool:
        """Enable SQL query logging."""
        try:
            config_file = Path('./mainconfig.json')
            config = {}
            
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config = json.load(f)
            
            config['sql_logging_enabled'] = True
            
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            self._enabled = True
            self.logger.info("SQL query logging enabled")
            return True
        except Exception as e:
            self.logger.error(f"Failed to enable SQL logging: {e}")
            return False
    
    def disable_logging(self) -> bool:
        """Disable SQL query logging."""
        try:
            config_file = Path('./mainconfig.json')
            config = {}
            
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config = json.load(f)
            
            config['sql_logging_enabled'] = False
            
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            self._enabled = False
            self.logger.info("SQL query logging disabled")
            return True
        except Exception as e:
            self.logger.error(f"Failed to disable SQL logging: {e}")
            return False
    
    def log_query(self, query: str, params: Optional[tuple] = None, 
                  execution_time: Optional[float] = None, 
                  component: str = "Unknown", 
                  error: Optional[str] = None):
        """
        Log a SQL query with execution details.
        
        Args:
            query (str): The SQL query
            params (tuple, optional): Query parameters
            execution_time (float, optional): Execution time in seconds
            component (str): Component that executed the query
            error (str, optional): Error message if query failed
        """
        if not self.is_enabled():
            return
        
        # Clean up query for logging
        clean_query = ' '.join(query.split())
        
        # Prepare log entry
        log_data = {
            'component': component,
            'query': clean_query,
            'params': str(params) if params else None,
            'execution_time_ms': round(execution_time * 1000, 2) if execution_time else None,
            'status': 'ERROR' if error else 'SUCCESS',
            'error': error,
            'timestamp': datetime.now().isoformat()
        }
        
        # Format log message
        if execution_time:
            time_str = f"({execution_time * 1000:.2f}ms)"
        else:
            time_str = ""
        
        status_str = "ERROR" if error else "SUCCESS"
        
        log_message = f"[{component}] {status_str} {time_str} - {clean_query}"
        if params:
            log_message += f" | Params: {params}"
        if error:
            log_message += f" | Error: {error}"
        
        # Log the query
        if error:
            self.logger.error(log_message)
        else:
            self.logger.info(log_message)
    
    def get_recent_logs(self, limit: int = 100) -> list:
        """
        Get recent SQL query logs.
        
        Args:
            limit (int): Maximum number of logs to return
            
        Returns:
            list: Recent SQL query logs
        """
        logs = []
        sql_log_file = self.log_dir / 'sql_queries.log'
        
        if not sql_log_file.exists():
            return logs
        
        try:
            with open(sql_log_file, 'r') as f:
                lines = f.readlines()
            
            # Get the last 'limit' lines
            recent_lines = lines[-limit:] if len(lines) > limit else lines
            
            for line in reversed(recent_lines):
                line = line.strip()
                if line:
                    # Parse log line
                    try:
                        parts = line.split(' - ', 2)
                        if len(parts) >= 3:
                            timestamp = parts[0]
                            level = parts[1]
                            message = parts[2]
                            
                            logs.append({
                                'timestamp': timestamp,
                                'level': level,
                                'message': message
                            })
                    except Exception:
                        # If parsing fails, include raw line
                        logs.append({
                            'timestamp': '',
                            'level': 'INFO',
                            'message': line
                        })
        except Exception as e:
            self.logger.error(f"Error reading SQL logs: {e}")
        
        return logs
    
    def clear_logs(self) -> bool:
        """Clear all SQL query logs."""
        try:
            sql_log_file = self.log_dir / 'sql_queries.log'
            if sql_log_file.exists():
                sql_log_file.unlink()
            self.logger.info("SQL query logs cleared")
            return True
        except Exception as e:
            self.logger.error(f"Failed to clear SQL logs: {e}")
            return False

# Global SQL logger instance
sql_logger = SQLLogger()

def execute_with_logging(cursor, query: str, params: Optional[tuple] = None, 
                        component: str = "Database") -> Any:
    """
    Execute a SQL query with logging.
    
    Args:
        cursor: Database cursor
        query (str): SQL query to execute
        params (tuple, optional): Query parameters
        component (str): Component name for logging
        
    Returns:
        Query result or None if failed
    """
    if not sql_logger.is_enabled():
        # If logging disabled, execute normally
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor
    
    # Execute with timing and logging
    start_time = time.time()
    error = None
    
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        execution_time = time.time() - start_time
        sql_logger.log_query(query, params, execution_time, component)
        return cursor
        
    except Exception as e:
        execution_time = time.time() - start_time
        error = str(e)
        sql_logger.log_query(query, params, execution_time, component, error)
        raise  # Re-raise the exception

def log_query_manual(query: str, execution_time: float, 
                    component: str = "Manual", params: Optional[tuple] = None, 
                    error: Optional[str] = None):
    """
    Manually log a SQL query (for cases where execute_with_logging can't be used).
    
    Args:
        query (str): SQL query
        execution_time (float): Execution time in seconds
        component (str): Component name
        params (tuple, optional): Query parameters
        error (str, optional): Error message if query failed
    """
    sql_logger.log_query(query, params, execution_time, component, error)