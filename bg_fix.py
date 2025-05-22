#!/usr/bin/env python3
# bg_fix.py - Fix and reset failed jobs in the background downloader

import sys
import os
import time
from components.Space import Space

def main():
    """Fix failed jobs in the space_download_scheduler table."""
    print("XSpace Downloader - Job Fixer")
    print("-----------------------------")
    
    # Create Space component
    try:
        space = Space()
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)
    
    # Get failed jobs
    try:
        failed_jobs = space.list_download_jobs(status='failed')
        if not failed_jobs:
            print("No failed jobs found.")
            return
        
        print(f"Found {len(failed_jobs)} failed jobs:")
        for job in failed_jobs:
            print(f"Job #{job['id']} - Space ID: {job['space_id']} - Error: {job.get('error_message', 'Unknown error')}")
        
        # Automatically reset all failed jobs to pending
        for job in failed_jobs:
            success = space.update_download_job(
                job['id'], 
                status='pending', 
                error_message=None, 
                progress_in_percent=0,
                progress_in_size=0,
                process_id=None
            )
            if success:
                print(f"Reset job #{job['id']} for space {job['space_id']} to pending status.")
            else:
                print(f"Failed to reset job #{job['id']}.")
        
        print("\nAll failed jobs have been reset to pending status.")
        print("Please restart the background downloader to process them.")
            
    except Exception as e:
        print(f"Error listing failed jobs: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()