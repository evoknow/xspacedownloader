#!/usr/bin/env python3
# tests/test_config.py

import os
import sys
import logging
import json
import uuid
import time
from datetime import datetime

# Add parent directory to path to allow importing components
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set up logging
logging.basicConfig(
    filename='test.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('xspace_tests')

# Test data
TEST_USER = {
    'username': f'testuser_{int(time.time())}',
    'email': f'testuser_{int(time.time())}@example.com',
    'password': 'Test1234!'
}

TEST_SPACE = {
    'url': 'https://x.com/i/spaces/1dRJZEpyjlNGB',
    'title': f'Test Space {int(time.time())}',
    'notes': 'Test notes for automated testing'
}

TEST_TAG = {
    'name': f'testtag_{int(time.time())}'
}

# Test utilities
def get_db_connection():
    """Get a database connection for testing."""
    import mysql.connector
    from mysql.connector import Error
    
    try:
        # Use absolute path to db_config.json
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'db_config.json')
        with open(config_path, 'r') as config_file:
            config = json.load(config_file)
            if config["type"] == "mysql":
                db_config = config["mysql"].copy()
                # Remove unsupported parameters
                if 'use_ssl' in db_config:
                    del db_config['use_ssl']
            else:
                raise ValueError(f"Unsupported database type: {config['type']}")
        
        logger.info(f"Connecting to database at {db_config['host']}:{db_config['port']}")
        connection = mysql.connector.connect(**db_config)
        logger.info("Database connection established successfully")
        return connection
    except Error as e:
        logger.error(f"Error connecting to database: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error connecting to database: {e}")
        raise

def generate_visitor_id():
    """Generate a unique visitor ID for testing."""
    return str(uuid.uuid4())

def log_test_start(test_name):
    """Log the start of a test."""
    logger.info(f"Starting test: {test_name}")

def log_test_end(test_name, success=True):
    """Log the end of a test."""
    if success:
        logger.info(f"Test completed successfully: {test_name}")
    else:
        logger.error(f"Test failed: {test_name}")

def log_test_step(step_description):
    """Log a test step."""
    logger.info(f"  - {step_description}")
    
def clear_test_data():
    """Clear all test data from the database before running tests."""
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Disable foreign key checks temporarily to allow deletion
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        
        # Delete data from tables in reverse order of dependency
        cursor.execute("DELETE FROM verification_tokens WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%')")
        cursor.execute("DELETE FROM space_tags WHERE space_id IN (SELECT space_id FROM spaces WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%'))")
        cursor.execute("DELETE FROM space_notes WHERE space_id IN (SELECT space_id FROM spaces WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%'))")
        cursor.execute("DELETE FROM space_metadata WHERE space_id IN (SELECT space_id FROM spaces WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%'))")
        cursor.execute("DELETE FROM spaces WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%')")
        cursor.execute("DELETE FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%'")
        cursor.execute("DELETE FROM tags WHERE name LIKE '%test%'")
        
        # Enable foreign key checks again
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        
        connection.commit()
        logger.info("Test data cleared from database")
    except Exception as e:
        logger.error(f"Error clearing test data: {e}")
        if connection:
            connection.rollback()
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()