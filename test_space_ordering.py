#!/usr/bin/env python3
"""
Test script to verify that spaces are ordered by most recent first.
"""

import sys
import json
import mysql.connector
from pathlib import Path

# Add parent directory to path for importing components
sys.path.append(str(Path(__file__).parent))

from components.Space import Space

def test_space_ordering():
    """Test that spaces are ordered by most recent downloads first."""
    try:
        # Load database config
        with open("db_config.json", 'r') as f:
            config = json.load(f)
        
        db_config = config["mysql"].copy()
        if 'use_ssl' in db_config:
            del db_config['use_ssl']
        
        # Connect to database and create Space component
        connection = mysql.connector.connect(**db_config)
        space = Space()  # Space will create its own connection
        space.connection = connection  # Override with our connection
        
        print("Testing space ordering...")
        
        # Test 1: Check completed jobs ordering
        print("\n1. Testing completed jobs ordering:")
        completed_jobs = space.list_download_jobs(status='completed', limit=5)
        
        if completed_jobs:
            print(f"Found {len(completed_jobs)} completed jobs:")
            for i, job in enumerate(completed_jobs, 1):
                end_time = job.get('end_time', 'Unknown')
                space_id = job.get('space_id', 'Unknown')
                print(f"  {i}. Space {space_id} - Completed: {end_time}")
        else:
            print("  No completed jobs found")
        
        # Test 2: Direct query to check spaces table ordering
        print("\n2. Testing spaces table ordering:")
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT space_id, downloaded_at, created_at, status
            FROM spaces 
            WHERE status = 'completed'
            ORDER BY downloaded_at DESC
            LIMIT 5
        """
        cursor.execute(query)
        spaces = cursor.fetchall()
        cursor.close()
        
        if spaces:
            print(f"Found {len(spaces)} completed spaces:")
            for i, space_row in enumerate(spaces, 1):
                downloaded_at = space_row.get('downloaded_at', 'Unknown')
                space_id = space_row.get('space_id', 'Unknown')
                print(f"  {i}. Space {space_id} - Downloaded: {downloaded_at}")
        else:
            print("  No completed spaces found")
        
        # Test 3: Check if ordering is actually by most recent
        if len(spaces) >= 2:
            print("\n3. Verifying order is most recent first:")
            first_date = spaces[0]['downloaded_at']
            second_date = spaces[1]['downloaded_at']
            
            if first_date and second_date:
                if first_date >= second_date:
                    print("  ✅ Correct! First space is more recent than second")
                    print(f"     First: {first_date}")
                    print(f"     Second: {second_date}")
                else:
                    print("  ❌ Incorrect! First space is older than second")
                    print(f"     First: {first_date}")
                    print(f"     Second: {second_date}")
            else:
                print("  ⚠️  Cannot verify - one or both spaces missing download timestamp")
        
        connection.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_space_ordering()