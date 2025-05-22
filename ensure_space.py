#!/usr/bin/env python3
# ensure_space.py - Verify space exists in database and add it if needed

import os
import sys
import json
import mysql.connector
from datetime import datetime

def main():
    """
    Check if a space exists in the database and add it if needed.
    """
    if len(sys.argv) < 2:
        print("Usage: python3 ensure_space.py <space_id> [space_url]")
        print("Example: python3 ensure_space.py 1kvJpmvEmpaxE https://x.com/i/spaces/1kvJpmvEmpaxE")
        sys.exit(1)
        
    space_id = sys.argv[1]
    space_url = sys.argv[2] if len(sys.argv) > 2 else f"https://x.com/i/spaces/{space_id}"
    
    print(f"Checking for space: {space_id} ({space_url})")
    
    try:
        # Load database configuration
        with open('db_config.json', 'r') as f:
            config = json.load(f)
            
        if config['type'] == 'mysql':
            db_config = config['mysql'].copy()
            # Remove unsupported parameters
            if 'use_ssl' in db_config:
                del db_config['use_ssl']
        else:
            print(f"Unsupported database type: {config['type']}")
            sys.exit(1)
            
        # Connect to database
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        # Check if space exists
        cursor.execute("SELECT * FROM spaces WHERE space_id = %s", (space_id,))
        space = cursor.fetchone()
        
        if space:
            print(f"Space exists in database: {space}")
            
            # Check download jobs for this space
            cursor.execute("SELECT * FROM space_download_scheduler WHERE space_id = %s", (space_id,))
            jobs = cursor.fetchall()
            
            if jobs:
                print(f"Found {len(jobs)} download jobs for space {space_id}:")
                for job in jobs:
                    print(f"  Job #{job['id']}: status='{job['status']}', created_at={job['created_at']}")
                    
                    # Reset job to pending if it's not completed or failed
                    if job['status'] not in ['completed', 'failed']:
                        print(f"  Resetting job #{job['id']} to pending status...")
                        cursor.execute(
                            """
                            UPDATE space_download_scheduler
                            SET status = 'pending', progress_in_percent = 0, 
                                progress_in_size = 0, process_id = NULL
                            WHERE id = %s
                            """,
                            (job['id'],)
                        )
                        conn.commit()
            else:
                print(f"No download jobs found for space {space_id}")
                
                # Create a download job
                print("Creating download job...")
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute(
                    """
                    INSERT INTO space_download_scheduler
                    (space_id, user_id, status, file_type, start_time, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    """,
                    (space_id, 0, 'pending', 'mp3', current_time)
                )
                conn.commit()
                job_id = cursor.lastrowid
                print(f"Created download job: #{job_id}")
        else:
            print(f"Space {space_id} not found in database. Creating...")
            
            # Create space record
            cursor.execute(
                """
                INSERT INTO spaces 
                (space_id, space_url, filename, format, notes, user_id, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (space_id, space_url, f"{space_id}.mp3", 'mp3', f"Added via ensure_space.py", 0, 'active')
            )
            conn.commit()
            print(f"Created space record for {space_id}")
            
            # Create download job
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                """
                INSERT INTO space_download_scheduler
                (space_id, user_id, status, file_type, start_time, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                """,
                (space_id, 0, 'pending', 'mp3', current_time)
            )
            conn.commit()
            job_id = cursor.lastrowid
            print(f"Created download job: #{job_id}")
            
        # Close connection
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()