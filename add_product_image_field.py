#!/usr/bin/env python3
"""Add product image field to products table."""

import json
import mysql.connector
from mysql.connector import Error

def add_product_image_field():
    """Add the image_url field to products table."""
    try:
        # Load database configuration
        with open('db_config.json', 'r') as f:
            config = json.load(f)
        
        if config["type"] != "mysql":
            raise ValueError(f"Unsupported database type: {config['type']}")
        
        db_config = config["mysql"].copy()
        if 'use_ssl' in db_config:
            del db_config['use_ssl']
        
        # Connect to database
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        
        # Read and execute SQL file
        with open('add_product_image_field.sql', 'r') as f:
            sql_commands = f.read()
        
        # Execute the SQL commands
        for command in sql_commands.split(';'):
            command = command.strip()
            if command:
                cursor.execute(command)
        
        connection.commit()
        print("✓ Product image field added successfully")
        
        cursor.close()
        connection.close()
        
    except Error as e:
        print(f"✗ Database error: {e}")
    except Exception as e:
        print(f"✗ Error: {e}")

if __name__ == "__main__":
    add_product_image_field()