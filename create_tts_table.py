#!/usr/bin/env python3
"""Create TTS jobs table."""

import json
import mysql.connector
from mysql.connector import Error

def create_tts_table():
    """Create the TTS jobs table."""
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
        with open('create_tts_table.sql', 'r') as f:
            sql_commands = f.read()
        
        # Execute the SQL
        for command in sql_commands.split(';'):
            command = command.strip()
            if command:
                cursor.execute(command)
        
        connection.commit()
        print("✓ TTS jobs table created successfully")
        
        cursor.close()
        connection.close()
        
    except Error as e:
        print(f"✗ Database error: {e}")
    except Exception as e:
        print(f"✗ Error: {e}")

if __name__ == "__main__":
    create_tts_table()