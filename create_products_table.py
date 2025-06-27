#!/usr/bin/env python3
"""Create products table and insert initial data."""

import json
import mysql.connector
from mysql.connector import Error

def create_products_table():
    """Create the products table and insert initial data."""
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
        with open('create_products_table.sql', 'r') as f:
            sql_commands = f.read()
        
        # Execute the SQL commands
        for command in sql_commands.split(';'):
            command = command.strip()
            if command:
                cursor.execute(command)
        
        connection.commit()
        print("✓ Products table created successfully")
        print("✓ Initial product data inserted")
        
        # Verify the data was inserted
        cursor.execute("SELECT sku, name, price, credits, recurring_credits FROM products ORDER BY price")
        products = cursor.fetchall()
        
        print("\n📦 Products in database:")
        for product in products:
            sku, name, price, credits, recurring = product
            print(f"  • {sku}: {name} - ${price} ({credits} credits{'*' if recurring == 'yes' else ''})")
        
        cursor.close()
        connection.close()
        
    except Error as e:
        print(f"✗ Database error: {e}")
    except Exception as e:
        print(f"✗ Error: {e}")

if __name__ == "__main__":
    create_products_table()