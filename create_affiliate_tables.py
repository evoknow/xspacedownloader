#!/usr/bin/env python3
"""Create affiliate system tables"""

import json
import mysql.connector
from pathlib import Path

def create_affiliate_tables():
    """Create affiliate system tables in the database"""
    
    # Load database configuration
    with open('db_config.json', 'r') as f:
        config = json.load(f)
    
    if config['type'] != 'mysql':
        raise ValueError(f"Unsupported database type: {config['type']}")
    
    # Connect to database
    db_config = config['mysql'].copy()
    if 'use_ssl' in db_config:
        del db_config['use_ssl']
    
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()
    
    try:
        # Read SQL file
        sql_file = Path('create_affiliate_tables.sql')
        with open(sql_file, 'r') as f:
            sql_content = f.read()
        
        # Split by semicolons and execute each statement
        statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
        
        for statement in statements:
            if statement:
                print(f"Executing: {statement[:60]}...")
                cursor.execute(statement)
        
        connection.commit()
        print("Successfully created affiliate system tables!")
        
    except mysql.connector.Error as e:
        print(f"Error creating tables: {e}")
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    create_affiliate_tables()