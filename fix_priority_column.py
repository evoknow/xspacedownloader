#!/usr/bin/env python3
"""
Fix missing priority column in space_download_scheduler table.
This script will add the priority column if it's missing.
"""

import os
import sys
import json
import mysql.connector
from mysql.connector import Error

def load_db_config():
    """Load database configuration."""
    try:
        with open('db_config.json', 'r') as f:
            config = json.load(f)
        return config['mysql']
    except Exception as e:
        print(f"Error loading database config: {e}")
        return None

def check_and_add_priority_column():
    """Check if priority column exists and add it if missing."""
    db_config = load_db_config()
    if not db_config:
        print("Failed to load database configuration")
        return False
    
    # Remove unsupported parameters
    if 'use_ssl' in db_config:
        del db_config['use_ssl']
    
    try:
        # Connect to database
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        
        print("Checking if priority column exists in space_download_scheduler table...")
        
        # Check if priority column exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'space_download_scheduler' 
            AND COLUMN_NAME = 'priority'
        """, (db_config['database'],))
        
        column_exists = cursor.fetchone()[0] > 0
        
        if column_exists:
            print("✅ Priority column already exists in space_download_scheduler table")
            return True
        
        print("❌ Priority column is missing. Adding it now...")
        
        # Add priority column
        cursor.execute("""
            ALTER TABLE space_download_scheduler 
            ADD COLUMN priority INT NOT NULL DEFAULT 3 
            COMMENT '1=highest, 2=high, 3=normal, 4=low, 5=lowest'
        """)
        
        print("✅ Priority column added successfully")
        
        # Add index for better performance
        try:
            cursor.execute("""
                CREATE INDEX idx_priority_status 
                ON space_download_scheduler(priority, status)
            """)
            print("✅ Added index on priority and status columns")
        except Error as idx_err:
            if "Duplicate key name" in str(idx_err):
                print("✅ Index on priority and status already exists")
            else:
                print(f"⚠️  Warning: Could not create index: {idx_err}")
        
        # Commit changes
        connection.commit()
        
        # Show current table structure
        print("\nCurrent table structure:")
        cursor.execute("DESCRIBE space_download_scheduler")
        columns = cursor.fetchall()
        for col in columns:
            print(f"  {col[0]} - {col[1]} {'(NULL)' if col[2] == 'YES' else '(NOT NULL)'}")
        
        # Show job statistics by priority
        print("\nCurrent job statistics by priority:")
        cursor.execute("""
            SELECT 
                priority,
                CASE priority
                    WHEN 1 THEN 'Highest'
                    WHEN 2 THEN 'High'
                    WHEN 3 THEN 'Normal'
                    WHEN 4 THEN 'Low'
                    WHEN 5 THEN 'Lowest'
                    ELSE 'Unknown'
                END as priority_label,
                COUNT(*) as total_jobs,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'downloading' THEN 1 ELSE 0 END) as downloading,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM space_download_scheduler
            GROUP BY priority
            ORDER BY priority
        """)
        
        stats = cursor.fetchall()
        if stats:
            print("Priority | Label    | Total | Pending | Downloading | Completed | Failed")
            print("---------|----------|-------|---------|-------------|-----------|-------")
            for stat in stats:
                print(f"{stat[0]:8} | {stat[1]:8} | {stat[2]:5} | {stat[3]:7} | {stat[4]:11} | {stat[5]:9} | {stat[6]:6}")
        else:
            print("No jobs found in the table")
        
        return True
        
    except Error as e:
        print(f"❌ Database error: {e}")
        return False
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals():
            connection.close()

if __name__ == "__main__":
    print("🔧 Priority Column Fix Script")
    print("=" * 40)
    
    success = check_and_add_priority_column()
    
    if success:
        print("\n✅ Priority column fix completed successfully!")
        print("The admin queue management should now work properly.")
    else:
        print("\n❌ Failed to fix priority column")
        print("Please run the SQL script manually or check database permissions.")
        sys.exit(1)