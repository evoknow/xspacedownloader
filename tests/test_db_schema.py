#!/usr/bin/env python3
# tests/test_db_schema.py

import unittest
import sys
import os
import time
import mysql.connector
from mysql.connector import Error

from tests.test_config import (
    get_db_connection, log_test_start, log_test_end, log_test_step, logger,
    clear_test_data
)

class TestDBSchema(unittest.TestCase):
    """Test class to verify database schema."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment once before all tests in this class."""
        logger.info("Setting up TestDBSchema test class")
        clear_test_data()
    
    def setUp(self):
        """Set up test environment before each test."""
        try:
            self.connection = get_db_connection()
        except Exception as e:
            logger.error(f"Error in setUp: {str(e)}")
            raise
    
    def tearDown(self):
        """Clean up after each test."""
        try:
            if hasattr(self, 'connection') and self.connection and self.connection.is_connected():
                self.connection.close()
                logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Error in tearDown: {str(e)}")
    
    def test_01_database_connection(self):
        """Test that database connection is working."""
        log_test_start("database_connection")
        
        self.assertTrue(self.connection.is_connected(), "Database connection should be established")
        
        log_test_step("Getting database info")
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("SELECT DATABASE() as db_name, VERSION() as db_version")
        db_info = cursor.fetchone()
        cursor.close()
        
        self.assertIsNotNone(db_info, "Should get database info")
        logger.info(f"Connected to database: {db_info['db_name']}, version: {db_info['db_version']}")
        
        log_test_end("database_connection")
    
    def test_02_required_tables_exist(self):
        """Test that all required tables exist in the database."""
        log_test_start("required_tables_exist")
        
        # Based on the actual database schema
        required_tables = [
            'users', 'spaces', 'tags', 'space_tags',
            'space_metadata', 'space_notes', 'verification_tokens',
            'email_config'
        ]
        
        cursor = self.connection.cursor()
        cursor.execute("SHOW TABLES")
        tables = [table[0] for table in cursor.fetchall()]
        cursor.close()
        
        logger.info(f"Found tables: {', '.join(tables)}")
        
        for table in required_tables:
            log_test_step(f"Checking table: {table}")
            self.assertIn(table, tables, f"Table '{table}' should exist in the database")
        
        log_test_end("required_tables_exist")
    
    def test_03_table_structures(self):
        """Test that table structures match the expected schema."""
        log_test_start("table_structures")
        
        cursor = self.connection.cursor(dictionary=True)
        
        try:
            # Get all tables columns for reference
            log_test_step("Getting table column information")
            table_info = {}
            cursor.execute("SHOW TABLES")
            tables = []
            for table_row in cursor.fetchall():
                # Get the first value from the row, regardless of how it's named
                table_name = list(table_row.values())[0]
                tables.append(table_name)
            
            for table in tables:
                cursor.execute(f"DESCRIBE {table}")
                table_info[table] = {col['Field']: col for col in cursor.fetchall()}
                logger.info(f"Table {table} columns: {', '.join(table_info[table].keys())}")
            
            # Check users table structure
            log_test_step("Checking users table structure")
            if 'users' in table_info:
                columns = table_info['users']
                
                # Using columns in the actual schema
                required_columns = ['id', 'email', 'password', 'created_at']
                
                for col in required_columns:
                    self.assertIn(col, columns, f"Column '{col}' should exist in users table")
            else:
                self.fail("users table not found")
            
            # Check spaces table structure
            log_test_step("Checking spaces table structure")
            if 'spaces' in table_info:
                columns = table_info['spaces']
                
                # Using the actual columns in our database schema
                required_columns = ['space_id', 'space_url', 'filename', 'status', 'created_at', 'user_id', 'browser_id']
                
                for col in required_columns:
                    self.assertIn(col, columns, f"Column '{col}' should exist in spaces table")
            else:
                self.fail("spaces table not found")
            
            # Check space_tags table structure
            log_test_step("Checking space_tags table structure")
            if 'space_tags' in table_info:
                columns = table_info['space_tags']
                
                # Using a subset of columns we know should exist
                required_columns = ['space_id', 'tag_id', 'user_id']
                
                for col in required_columns:
                    self.assertIn(col, columns, f"Column '{col}' should exist in space_tags table")
            else:
                self.fail("space_tags table not found")
                
            # Check email_config table structure
            log_test_step("Checking email_config table structure")
            if 'email_config' in table_info:
                columns = table_info['email_config']
                
                # Using the columns we know should exist
                required_columns = ['id', 'provider', 'api_key', 'from_email', 'from_name', 
                                    'server', 'port', 'username', 'password', 'use_tls']
                
                for col in required_columns:
                    self.assertIn(col, columns, f"Column '{col}' should exist in email_config table")
            else:
                self.fail("email_config table not found")
            
        except Exception as e:
            logger.error(f"Error in test_03_table_structures: {str(e)}")
            raise
        finally:
            cursor.close()
            
        log_test_end("table_structures")
    
    def test_04_foreign_keys(self):
        """Test that foreign key constraints are set up correctly."""
        log_test_start("foreign_keys")
        
        try:
            cursor = self.connection.cursor(dictionary=True)
            db_name = None
            
            # Get current database name
            cursor.execute("SELECT DATABASE() as db_name")
            result = cursor.fetchone()
            if result:
                db_name = result['db_name']
                
            if not db_name:
                self.fail("Could not determine database name")
                
            log_test_step(f"Checking foreign keys in database: {db_name}")
            
            # Check all foreign keys in the database
            cursor.execute(f"""
                SELECT 
                    TABLE_NAME, COLUMN_NAME, CONSTRAINT_NAME,
                    REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                WHERE REFERENCED_TABLE_SCHEMA = '{db_name}'
                ORDER BY TABLE_NAME, COLUMN_NAME
            """)
            
            foreign_keys = cursor.fetchall()
            logger.info(f"Found {len(foreign_keys)} foreign key relationships")
            
            # Log all foreign key relationships
            for fk in foreign_keys:
                logger.info(f"FK: {fk['TABLE_NAME']}.{fk['COLUMN_NAME']} -> "
                           f"{fk['REFERENCED_TABLE_NAME']}.{fk['REFERENCED_COLUMN_NAME']}")
            
            # Check specific relationships between tables
            space_tags_fks = [fk for fk in foreign_keys if fk['TABLE_NAME'] == 'space_tags']
            logger.info(f"Found {len(space_tags_fks)} foreign keys for space_tags table")
            
            # We expect at least some foreign keys in the database
            self.assertGreater(len(foreign_keys), 0, "Database should have foreign key constraints")
            
        except Exception as e:
            logger.error(f"Error in test_04_foreign_keys: {str(e)}")
            raise
        finally:
            if cursor:
                cursor.close()
                
        log_test_end("foreign_keys")

if __name__ == "__main__":
    unittest.main()