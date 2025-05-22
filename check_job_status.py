#!/usr/bin/env python3
# check_job_status.py - Check status of download jobs

from components.Space import Space

def main():
    """Check the status of download jobs and display errors"""
    space = Space()
    
    # Get all jobs
    cursor = space.connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM space_download_scheduler")
    jobs = cursor.fetchall()
    
    print(f"Found {len(jobs)} total download jobs:")
    for job in jobs:
        print(f"\nJob #{job['id']} for space {job['space_id']}:")
        print(f"  Status: {job['status']}")
        print(f"  Progress: {job['progress_in_percent']}%")
        print(f"  Created: {job['created_at']}")
        print(f"  Updated: {job['updated_at']}")
        
        if job['error_message']:
            print(f"  Error: {job['error_message']}")
        
        # Check if space exists
        cursor.execute("SELECT * FROM spaces WHERE space_id = %s", (job['space_id'],))
        space_record = cursor.fetchone()
        
        if space_record:
            print(f"  Space exists with title: {space_record.get('title', 'N/A')}")
        else:
            print(f"  WARNING: Space {job['space_id']} does not exist in spaces table!")
    
    cursor.close()

if __name__ == "__main__":
    main()