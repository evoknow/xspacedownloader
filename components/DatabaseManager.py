#!/usr/bin/env python3
"""
DatabaseManager.py - Manages MySQL connections with pooling and automatic reconnection
"""

import json
import logging
import threading
import time
from contextlib import contextmanager
import mysql.connector
from mysql.connector import pooling

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Singleton database manager with connection pooling."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DatabaseManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self.pool = None
        self.config = None
        self._load_config()
        self._create_pool()
    
    def _load_config(self):
        """Load database configuration from JSON file."""
        try:
            with open("db_config.json", 'r') as f:
                config = json.load(f)
            
            if config["type"] != "mysql":
                raise ValueError(f"Unsupported database type: {config['type']}")
            
            db_config = config["mysql"].copy()
            
            # Remove unsupported parameters
            if 'use_ssl' in db_config:
                del db_config['use_ssl']
            
            # Clean up config for mysql.connector
            self.config = {
                'host': db_config.get('host'),
                'port': db_config.get('port', 3306),
                'database': db_config.get('database'),
                'user': db_config.get('user'),
                'password': db_config.get('password'),
                'charset': db_config.get('charset', 'utf8mb4'),
                'use_unicode': db_config.get('use_unicode', True),
                'autocommit': False,
                'time_zone': '+00:00',
                'sql_mode': 'TRADITIONAL',
                'connect_timeout': 20,
                'connection_timeout': 20,
                'raise_on_warnings': False
            }
            
            logger.info("Database configuration loaded successfully")
            
        except Exception as e:
            logger.error(f"Error loading database config: {e}")
            raise
    
    def _create_pool(self):
        """Create connection pool."""
        try:
            # Create a connection pool with appropriate settings
            self.pool = pooling.MySQLConnectionPool(
                pool_name="xspace_pool",
                pool_size=5,  # Number of connections in the pool
                pool_reset_session=True,  # Reset session variables when connection is returned to pool
                **self.config
            )
            logger.info("Database connection pool created successfully")
            
        except Exception as e:
            logger.error(f"Error creating connection pool: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """
        Get a connection from the pool as a context manager.
        Automatically handles connection return and error recovery.
        """
        connection = None
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                # Get connection from pool
                connection = self.pool.get_connection()
                
                # Test connection is alive
                connection.ping(reconnect=True, attempts=3, delay=1)
                
                logger.debug(f"Got connection from pool (attempt {attempt + 1})")
                
                yield connection
                
                # If we get here, everything worked
                return
                
            except mysql.connector.errors.PoolError as e:
                logger.warning(f"Pool error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    # Try to recreate the pool
                    try:
                        self._create_pool()
                    except:
                        pass
                else:
                    raise
                    
            except mysql.connector.errors.DatabaseError as e:
                logger.warning(f"Database error on attempt {attempt + 1}: {e}")
                if connection:
                    try:
                        connection.close()
                    except:
                        pass
                    connection = None
                    
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise
                    
            except Exception as e:
                logger.error(f"Unexpected error getting connection: {e}")
                if connection:
                    try:
                        connection.close()
                    except:
                        pass
                raise
                
            finally:
                # Always return connection to pool if we got one
                if connection:
                    try:
                        connection.close()  # This returns it to the pool
                    except:
                        pass
    
    def execute_query(self, query, params=None, fetch_one=False, fetch_all=False):
        """
        Execute a query with automatic connection management.
        
        Args:
            query (str): SQL query to execute
            params (tuple): Query parameters
            fetch_one (bool): Whether to fetch one result
            fetch_all (bool): Whether to fetch all results
            
        Returns:
            Query result or None
        """
        with self.get_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute(query, params or ())
                
                if fetch_one:
                    return cursor.fetchone()
                elif fetch_all:
                    return cursor.fetchall()
                else:
                    # For INSERT/UPDATE/DELETE
                    connection.commit()
                    return cursor.lastrowid if cursor.lastrowid else cursor.rowcount
                    
            except Exception as e:
                connection.rollback()
                raise
            finally:
                cursor.close()
    
    def close_pool(self):
        """Close all connections in the pool."""
        if self.pool:
            try:
                # This will close all connections in the pool
                logger.info("Closing database connection pool")
                # Note: There's no direct close method for the pool in mysql-connector-python
                # Connections will be closed when they're garbage collected
                self.pool = None
            except Exception as e:
                logger.error(f"Error closing pool: {e}")

# Create a singleton instance
db_manager = DatabaseManager()