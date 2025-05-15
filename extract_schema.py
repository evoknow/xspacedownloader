#!/usr/bin/env python3
# extract_schema.py - Extract MySQL database schema using Python
#
# This script extracts the database schema from the XSpace Downloader MySQL database
# without requiring high-level permissions

import sys
import os
import json
import mysql.connector
from mysql.connector import Error
from datetime import datetime

def get_schema():
    """Extract database schema from MySQL database"""
    print("XSpace Downloader - Database Schema Extraction (Python Method)")
    
    try:
        # Read database configuration
        print("Reading database configuration from db_config.json...")
        with open('db_config.json', 'r') as f:
            db_config = json.load(f)['mysql']
        
        print(f"Database: {db_config['database']} on {db_config['host']}:{db_config['port']}")
        
        # Connect to the database
        print("Connecting to database...")
        connection = mysql.connector.connect(
            host=db_config['host'],
            port=db_config['port'],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )
        
        if connection.is_connected():
            print("Connection successful! Extracting schema...")
            cursor = connection.cursor(dictionary=True)
            
            # Get database information
            cursor.execute('SELECT DATABASE() as database_name')
            db_info = cursor.fetchone()
            database_name = db_info['database_name']
            
            # Get a list of tables
            print("Retrieving table list...")
            cursor.execute('SHOW TABLES')
            table_results = cursor.fetchall()
            
            if not table_results:
                print("No tables found in database!")
                return None
            
            # Extract table name from each result (handling different result formats)
            tables = []
            for table_row in table_results:
                # Get the first value from the row, regardless of how it's named
                table_name = list(table_row.values())[0]
                tables.append(table_name)
            
            print(f"Found {len(tables)} tables: {', '.join(tables)}")
            
            schema = []
            schema.append(f'-- MySQL Schema for {database_name} database')
            schema.append(f'-- Generated with Python on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
            schema.append('-- This file contains the database schema (without data)')
            schema.append('')
            schema.append('-- Create the database if it doesn\'t exist')
            schema.append(f'CREATE DATABASE IF NOT EXISTS `{database_name}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;')
            schema.append(f'USE `{database_name}`;')
            schema.append('')
            
            # For each table, extract structure
            for table_name in tables:
                print(f"Processing table: {table_name}")
                schema.append(f'-- Table structure for table `{table_name}`')
                schema.append(f'DROP TABLE IF EXISTS `{table_name}`;')
                
                try:
                    # Try to get CREATE TABLE statement
                    cursor.execute(f'SHOW CREATE TABLE `{table_name}`')
                    create_table = cursor.fetchone()
                    if create_table and 'Create Table' in create_table:
                        schema.append(create_table['Create Table'] + ';')
                    else:
                        # Fallback to building CREATE TABLE from DESCRIBE
                        schema.append(f'CREATE TABLE `{table_name}` (')
                        
                        # Get column definitions
                        cursor.execute(f'DESCRIBE `{table_name}`')
                        columns = cursor.fetchall()
                        col_defs = []
                        
                        for col in columns:
                            null_str = '' if col['Null'] == 'YES' else 'NOT NULL'
                            default_str = f"DEFAULT '{col['Default']}'" if col['Default'] is not None else ''
                            extra_str = col['Extra'] if col['Extra'] else ''
                            col_defs.append(f"  `{col['Field']}` {col['Type']} {null_str} {default_str} {extra_str}".strip())
                        
                        # Get primary key
                        cursor.execute(f"SHOW KEYS FROM `{table_name}` WHERE Key_name = 'PRIMARY'")
                        primary_keys = cursor.fetchall()
                        if primary_keys:
                            pk_cols = [f"`{pk['Column_name']}`" for pk in primary_keys]
                            col_defs.append(f"  PRIMARY KEY ({', '.join(pk_cols)})")
                        
                        schema.append(',\n'.join(col_defs))
                        schema.append(') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;')
                
                except Error as e:
                    print(f"Error extracting schema for table {table_name}: {e}")
                    # Add a comment about the error in the schema
                    schema.append(f'-- Error extracting schema for table {table_name}: {e}')
                    schema.append(f'-- Basic structure from information_schema:')
                    
                    try:
                        # Try to get basic structure from information_schema
                        cursor.execute(f'''
                            SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA
                            FROM INFORMATION_SCHEMA.COLUMNS 
                            WHERE TABLE_SCHEMA = '{database_name}' AND TABLE_NAME = '{table_name}'
                            ORDER BY ORDINAL_POSITION
                        ''')
                        info_cols = cursor.fetchall()
                        
                        schema.append(f'CREATE TABLE `{table_name}` (')
                        col_defs = []
                        
                        for col in info_cols:
                            null_str = '' if col['IS_NULLABLE'] == 'YES' else 'NOT NULL'
                            default_str = f"DEFAULT '{col['COLUMN_DEFAULT']}'" if col['COLUMN_DEFAULT'] is not None else ''
                            extra_str = col['EXTRA'] if col['EXTRA'] else ''
                            col_defs.append(f"  `{col['COLUMN_NAME']}` {col['COLUMN_TYPE']} {null_str} {default_str} {extra_str}".strip())
                        
                        schema.append(',\n'.join(col_defs))
                        schema.append(') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;')
                    
                    except Error as e2:
                        print(f"Also failed to get basic structure: {e2}")
                        schema.append(f'-- Also failed to get basic structure: {e2}')
                
                schema.append('')
            
            # Add default admin user and API key setup
            schema.append('-- Add default admin user if it doesn\'t exist')
            schema.append('INSERT INTO `users` (`email`, `password`, `status`)')
            schema.append('SELECT \'admin@xspacedownload.com\', \'$2b$10$VGm5DFCi/zXlCH7qeP5m0.WGM/WHxfHEA8lBZ1DC3HqZUi0L.oEUG\', \'active\'')
            schema.append('WHERE NOT EXISTS (SELECT 1 FROM `users` WHERE `email` = \'admin@xspacedownload.com\');')
            schema.append('')
            schema.append('-- Insert a default admin API key')
            schema.append('INSERT INTO `api_keys` (`user_id`, `key`, `name`, `permissions`, `created_at`, `expires_at`, `is_active`)')
            schema.append('SELECT')
            schema.append('    (SELECT `id` FROM `users` WHERE `email` = \'admin@xspacedownload.com\' LIMIT 1),')
            schema.append('    \'DEV_API_KEY_DO_NOT_USE_IN_PRODUCTION\',')
            schema.append('    \'Default Admin API Key\',')
            schema.append('    JSON_ARRAY(')
            schema.append('        \'view_users\', \'manage_users\',')
            schema.append('        \'view_spaces\', \'create_spaces\', \'edit_spaces\', \'delete_spaces\', \'view_all_spaces\', \'edit_all_spaces\', \'delete_all_spaces\',')
            schema.append('        \'download_spaces\', \'download_all_spaces\', \'view_downloads\', \'manage_downloads\', \'view_all_downloads\', \'manage_all_downloads\',')
            schema.append('        \'view_tags\', \'manage_tags\',')
            schema.append('        \'manage_api_keys\',')
            schema.append('        \'view_stats\'')
            schema.append('    ),')
            schema.append('    NOW(),')
            schema.append('    DATE_ADD(NOW(), INTERVAL 1 YEAR),')
            schema.append('    1')
            schema.append('WHERE EXISTS (SELECT 1 FROM `users` WHERE `email` = \'admin@xspacedownload.com\')')
            schema.append('AND NOT EXISTS (SELECT 1 FROM `api_keys` WHERE `name` = \'Default Admin API Key\');')
            
            cursor.close()
            connection.close()
            
            print("Schema extraction completed successfully!")
            
            return '\n'.join(schema)
            
    except Error as e:
        print(f"Error connecting to MySQL database: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None

if __name__ == "__main__":
    schema = get_schema()
    if schema:
        # Write schema to file
        with open('mysql.schema', 'w') as f:
            f.write(schema)
        
        print(f"Schema written to mysql.schema ({os.path.getsize('mysql.schema')} bytes)")
        print("Use this file to recreate the database structure:")
        print("  mysql -u your_username -p < mysql.schema")
    else:
        print("Failed to extract schema. Please check database connection and permissions.")
        sys.exit(1)