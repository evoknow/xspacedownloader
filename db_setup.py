#!/usr/bin/env python3
# db_setup.py - Test and setup database tables

import sys
import os
import subprocess

print("Checking Python environment...")
print(f"Python version: {sys.version}")
print(f"Python path: {sys.executable}")
print(f"In virtual environment: {hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)}")

# Activate virtual environment if not already in one
if not (hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)):
    venv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv")
    
    # Create virtual environment if it doesn't exist
    if not os.path.exists(venv_path):
        print("Creating virtual environment...")
        subprocess.call([sys.executable, "-m", "venv", venv_path])
    
    # Get the path to the virtual environment's Python interpreter
    if sys.platform == 'win32':
        venv_python = os.path.join(venv_path, "Scripts", "python.exe")
    else:
        venv_python = os.path.join(venv_path, "bin", "python")
    
    # Install required packages
    print("Installing required packages...")
    subprocess.call([venv_python, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.call([venv_python, "-m", "pip", "install", "mysql-connector-python"])
    
    # Restart script in virtual environment
    print("Restarting script in virtual environment...")
    os.execv(venv_python, [venv_python] + sys.argv)
    sys.exit(0)

# Now we should be in a virtual environment with mysql-connector-python installed
try:
    import mysql.connector
    from mysql.connector import Error
    
    print("MySQL Connector imported successfully!")
    
    # Load database configuration
    import json
    print("Loading database configuration...")
    
    with open('db_config.json', 'r') as f:
        config = json.load(f)
        db_config = config["mysql"].copy()
        if 'use_ssl' in db_config:
            del db_config['use_ssl']
    
    print(f"Attempting to connect to database at {db_config['host']}...")
    
    # Connect to MySQL
    connection = mysql.connector.connect(**db_config)
    
    if connection.is_connected():
        db_info = connection.get_server_info()
        print(f"Connected to MySQL Server version {db_info}")
        
        cursor = connection.cursor()
        
        # Check for space_download_scheduler table
        cursor.execute("SHOW TABLES LIKE 'space_download_scheduler'")
        result = cursor.fetchone()
        
        if not result:
            print("Table 'space_download_scheduler' does not exist. Creating...")
            
            # Read the SQL from file
            sql_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                       "create_space_download_scheduler.sql")
            
            if os.path.exists(sql_file_path):
                with open(sql_file_path, 'r') as file:
                    sql_script = file.read()
                
                print("Executing SQL script...")
                
                # Execute each statement in the script
                for statement in sql_script.split(';'):
                    if statement.strip():
                        print(f"Executing: {statement[:100]}...")  # Print first 100 chars for brevity
                        cursor.execute(statement)
                
                connection.commit()
                print("Table created successfully!")
            else:
                print(f"SQL file not found: {sql_file_path}")
        else:
            print("Table 'space_download_scheduler' already exists")
        
        # Check for spaces table (for testing)
        cursor.execute("SHOW TABLES LIKE 'spaces'")
        if not cursor.fetchone():
            print("Table 'spaces' does not exist. You need to create this table for testing.")
            
            # Create a basic spaces table for testing
            create_spaces_sql = """
            CREATE TABLE spaces (
                id INT AUTO_INCREMENT PRIMARY KEY,
                space_id VARCHAR(255) NOT NULL,
                space_url VARCHAR(255) NOT NULL,
                filename VARCHAR(255) NULL,
                format VARCHAR(20) NULL,
                notes TEXT NULL,
                user_id INT NULL DEFAULT 0,
                browser_id VARCHAR(32) NULL,
                status VARCHAR(50) NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                downloaded_at TIMESTAMP NULL,
                download_cnt INT NULL DEFAULT 0,
                UNIQUE INDEX idx_space_id (space_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            
            print("Creating spaces table for testing...")
            cursor.execute(create_spaces_sql)
            connection.commit()
            print("Spaces table created!")
        else:
            print("Table 'spaces' already exists")
        
        # List all tables for reference
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        print("Available tables:")
        for table in tables:
            print(f"  - {table[0]}")
        
        cursor.close()
        connection.close()
        print("Connection closed.")
    
except Error as e:
    print(f"Error while connecting to MySQL: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
    import traceback
    traceback.print_exc()

print("Script completed.")