#!/usr/bin/env python3
# db_status_fix.py - Fix status values in the database

import os
import sys
import json
import mysql.connector
from mysql.connector import Error
import argparse

def connect_to_database():
    """Connect to the database using the configuration in db_config.json."""
    try:
        with open('db_config.json', 'r') as config_file:
            config = json.load(config_file)
            if config["type"] == "mysql":
                db_config = config["mysql"].copy()
                # Remove unsupported parameters
                if 'use_ssl' in db_config:
                    del db_config['use_ssl']
            else:
                raise ValueError(f"Unsupported database type: {config['type']}")
                
        print(f"Connecting to MySQL database at {db_config['host']}:{db_config['port']} as {db_config['user']}")
        connection = mysql.connector.connect(**db_config)
        
        if connection.is_connected():
            print("Successfully connected to the database.")
            return connection
        else:
            print("Failed to connect to the database.")
            return None
    except Error as e:
        print(f"Error connecting to MySQL database: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None

def diagnose_status_field(connection):
    """Check the status column definition and current values."""
    try:
        cursor = connection.cursor(dictionary=True)
        
        # Check column definition
        cursor.execute("SHOW COLUMNS FROM space_download_scheduler LIKE 'status'")
        status_info = cursor.fetchone()
        print(f"Status column definition: {status_info}")
        
        # Check for possible enum values
        enum_type = status_info.get('Type', '')
        if 'enum' in enum_type.lower():
            print(f"Status column is ENUM type with allowed values: {enum_type}")
        
        # Count records by status
        cursor.execute("SELECT status, COUNT(*) as count FROM space_download_scheduler GROUP BY status")
        status_counts = cursor.fetchall()
        print("Current status distribution:")
        for status in status_counts:
            print(f"  {status['status']}: {status['count']} records")
        
        # Check for problematic status values (case mismatch)
        cursor.execute("SELECT id, space_id, status FROM space_download_scheduler WHERE status NOT IN ('pending', 'in_progress', 'completed', 'failed')")
        invalid_statuses = cursor.fetchall()
        if invalid_statuses:
            print("\nFound records with invalid status values:")
            for job in invalid_statuses:
                print(f"  Job #{job['id']} (space {job['space_id']}): '{job['status']}'")
                
        # Check for whitespace in status values
        cursor.execute("SELECT id, space_id, status, LENGTH(status) as len1, LENGTH(TRIM(status)) as len2 FROM space_download_scheduler WHERE LENGTH(status) != LENGTH(TRIM(status))")
        whitespace_statuses = cursor.fetchall()
        if whitespace_statuses:
            print("\nFound records with whitespace in status values:")
            for job in whitespace_statuses:
                print(f"  Job #{job['id']} (space {job['space_id']}): '{job['status']}' (lengths: {job['len1']} vs {job['len2']})")
        
        return status_info
    except Error as e:
        print(f"Error diagnosing status field: {e}")
        return None
    finally:
        cursor.close()

def fix_status_values(connection):
    """Fix status values in the database."""
    try:
        cursor = connection.cursor()
        
        # Fix pending statuses
        cursor.execute("UPDATE space_download_scheduler SET status = 'pending' WHERE LOWER(status) = 'pending' AND status != 'pending'")
        pending_rows = cursor.rowcount
        
        # Fix in_progress statuses
        cursor.execute("UPDATE space_download_scheduler SET status = 'in_progress' WHERE LOWER(status) = 'in_progress' AND status != 'in_progress'")
        in_progress_rows = cursor.rowcount
        
        # Fix completed statuses
        cursor.execute("UPDATE space_download_scheduler SET status = 'completed' WHERE LOWER(status) = 'completed' AND status != 'completed'")
        completed_rows = cursor.rowcount
        
        # Fix failed statuses
        cursor.execute("UPDATE space_download_scheduler SET status = 'failed' WHERE LOWER(status) = 'failed' AND status != 'failed'")
        failed_rows = cursor.rowcount
        
        # Fix status with whitespace
        cursor.execute("UPDATE space_download_scheduler SET status = TRIM(status) WHERE LENGTH(status) != LENGTH(TRIM(status))")
        whitespace_rows = cursor.rowcount
        
        connection.commit()
        
        total_fixed = pending_rows + in_progress_rows + completed_rows + failed_rows + whitespace_rows
        print(f"Fixed {total_fixed} status values:")
        print(f"  Pending: {pending_rows}")
        print(f"  In Progress: {in_progress_rows}")
        print(f"  Completed: {completed_rows}")
        print(f"  Failed: {failed_rows}")
        print(f"  Whitespace: {whitespace_rows}")
        
        return total_fixed
    except Error as e:
        print(f"Error fixing status values: {e}")
        connection.rollback()
        return 0
    finally:
        cursor.close()

def list_jobs(connection, status=None):
    """List all jobs or jobs with a specific status."""
    try:
        cursor = connection.cursor(dictionary=True)
        
        if status:
            cursor.execute("SELECT * FROM space_download_scheduler WHERE status = %s ORDER BY id DESC", (status,))
        else:
            cursor.execute("SELECT * FROM space_download_scheduler ORDER BY id DESC")
            
        jobs = cursor.fetchall()
        
        if jobs:
            print(f"\nFound {len(jobs)} jobs{' with status ' + status if status else ''}:")
            for job in jobs:
                print(f"Job #{job['id']}: space_id={job['space_id']}, status='{job['status']}', created={job['created_at']}")
                
            return jobs
        else:
            print(f"No jobs found{' with status ' + status if status else ''}.")
            return []
    except Error as e:
        print(f"Error listing jobs: {e}")
        return []
    finally:
        cursor.close()

def fix_job_status(connection, job_id, new_status):
    """Fix the status of a specific job."""
    try:
        cursor = connection.cursor()
        
        # Check if job exists
        cursor.execute("SELECT id, status FROM space_download_scheduler WHERE id = %s", (job_id,))
        job = cursor.fetchone()
        
        if not job:
            print(f"Error: Job #{job_id} not found.")
            return False
            
        old_status = job[1]
        
        # Update status
        cursor.execute("UPDATE space_download_scheduler SET status = %s, updated_at = NOW() WHERE id = %s", (new_status, job_id))
        connection.commit()
        
        print(f"Updated job #{job_id} status from '{old_status}' to '{new_status}'.")
        return True
    except Error as e:
        print(f"Error fixing job status: {e}")
        connection.rollback()
        return False
    finally:
        cursor.close()

def recreate_status_enum(connection):
    """Recreate the status enum with the correct values if needed."""
    try:
        cursor = connection.cursor()
        
        # First, check if we need to modify the column
        cursor.execute("SHOW COLUMNS FROM space_download_scheduler LIKE 'status'")
        status_info = cursor.fetchone()
        
        type_info = status_info[1]
        if type_info.lower() == "enum('pending','in_progress','completed','failed')":
            print("Status column type is already correct.")
            return True
        
        # If we need to modify, we'll change it to the correct enum type
        print("Modifying status column to correct enum type...")
        cursor.execute("""
        ALTER TABLE space_download_scheduler 
        MODIFY COLUMN status ENUM('pending','in_progress','completed','failed') NOT NULL DEFAULT 'pending'
        """)
        
        connection.commit()
        print("Status column type updated successfully.")
        
        # Verify the change
        cursor.execute("SHOW COLUMNS FROM space_download_scheduler LIKE 'status'")
        updated_info = cursor.fetchone()
        print(f"Updated status column definition: {updated_info}")
        
        return True
    except Error as e:
        print(f"Error recreating status enum: {e}")
        connection.rollback()
        return False
    finally:
        cursor.close()

def main():
    parser = argparse.ArgumentParser(description="Fix status values in the space_download_scheduler table")
    parser.add_argument("--diagnose", action="store_true", help="Diagnose status field issues")
    parser.add_argument("--fix", action="store_true", help="Fix status values")
    parser.add_argument("--recreate-enum", action="store_true", help="Recreate the status enum with correct values")
    parser.add_argument("--list", action="store_true", help="List all jobs")
    parser.add_argument("--list-pending", action="store_true", help="List pending jobs")
    parser.add_argument("--list-in-progress", action="store_true", help="List in_progress jobs")
    parser.add_argument("--list-failed", action="store_true", help="List failed jobs")
    parser.add_argument("--list-completed", action="store_true", help="List completed jobs")
    parser.add_argument("--fix-job", type=int, help="Fix the status of a specific job")
    parser.add_argument("--new-status", type=str, choices=["pending", "in_progress", "completed", "failed"], help="New status for the job")
    
    args = parser.parse_args()
    
    # Connect to the database
    connection = connect_to_database()
    if not connection:
        print("Could not connect to the database. Exiting.")
        sys.exit(1)
    
    try:
        # Process commands
        if args.diagnose:
            diagnose_status_field(connection)
        elif args.fix:
            fix_status_values(connection)
        elif args.recreate_enum:
            recreate_status_enum(connection)
        elif args.list:
            list_jobs(connection)
        elif args.list_pending:
            list_jobs(connection, "pending")
        elif args.list_in_progress:
            list_jobs(connection, "in_progress")
        elif args.list_failed:
            list_jobs(connection, "failed")
        elif args.list_completed:
            list_jobs(connection, "completed")
        elif args.fix_job and args.new_status:
            fix_job_status(connection, args.fix_job, args.new_status)
        else:
            # If no command specified, diagnose the status field
            diagnose_status_field(connection)
            
    except Exception as e:
        print(f"Error processing command: {e}")
    finally:
        if connection and connection.is_connected():
            connection.close()
            print("Database connection closed.")

if __name__ == "__main__":
    main()