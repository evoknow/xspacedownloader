#!/usr/bin/env python3
# download_test.py - Simple direct test for downloading a space

import sys
import os
import json
import time
import mysql.connector
from datetime import datetime

def main():
    """Simple test for downloading a space"""
    if len(sys.argv) < 2:
        print("Usage: python download_test.py <space_id>")
        sys.exit(1)
        
    space_id = sys.argv[1]
    file_type = "mp3"
    download_dir = "downloads"
    
    # Create download directory if it doesn't exist
    os.makedirs(download_dir, exist_ok=True)
    
    # Create a test file
    output_file = os.path.join(download_dir, f"{space_id}.{file_type}")
    print(f"Creating test file: {output_file}")
    
    # Check if file already exists
    if os.path.exists(output_file):
        print(f"File already exists: {output_file}")
        file_size = os.path.getsize(output_file)
        print(f"Size: {file_size} bytes")
    else:
        # Create a random file of specific size (500KB) for testing
        with open(output_file, 'wb') as f:
            # Create a file of specific size (500KB) for testing
            chunk_size = 1024  # 1 KB
            for _ in range(500):
                f.write(os.urandom(chunk_size))
        
        file_size = os.path.getsize(output_file)
        print(f"Created test file {output_file} with size: {file_size} bytes")
    
    # Update the database
    print("Updating database...")
    try:
        with open('db_config.json', 'r') as config_file:
            config = json.load(config_file)
            
        if config["type"] == "mysql":
            db_config = config["mysql"].copy()
            # Remove unsupported parameters
            if 'use_ssl' in db_config:
                del db_config['use_ssl']
        else:
            print(f"Unsupported database type: {config['type']}")
            sys.exit(1)
            
        # Connect to the database
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        # Get all download jobs for this space
        cursor.execute("SELECT * FROM space_download_scheduler WHERE space_id = %s", (space_id,))
        jobs = cursor.fetchall()
        
        if jobs:
            print(f"Found {len(jobs)} jobs for space {space_id}")
            for job in jobs:
                job_id = job['id']
                
                # Update job as completed
                print(f"Updating job {job_id} as completed...")
                cursor.execute(
                    """
                    UPDATE space_download_scheduler
                    SET status = 'completed', progress_in_percent = 100,
                        progress_in_size = %s, end_time = NOW(), updated_at = NOW()
                    WHERE id = %s
                    """,
                    (file_size, job_id)
                )
                
                # Also update space record
                cursor.execute(
                    """
                    UPDATE spaces
                    SET status = 'completed', download_cnt = 100, format = %s
                    WHERE space_id = %s
                    """,
                    (file_type, space_id)
                )
                
                conn.commit()
                print(f"Job {job_id} updated successfully")
        else:
            print(f"No jobs found for space {space_id}")
            
        # Close the database connection
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error updating database: {e}")
        
    print("Done!")

if __name__ == "__main__":
    main()