#!/usr/bin/env python3
# check_pending.py - Manually check for pending downloads

import sys
import os
from components.Space import Space

def main():
    """Check and display pending downloads."""
    print("XSpace Downloader - Pending Jobs Checker")
    print("----------------------------------------")
    
    try:
        # Create Space component
        space = Space()
        
        # Get pending jobs
        pending_jobs = space.list_download_jobs(status='pending')
        
        if not pending_jobs:
            print("No pending jobs found.")
            return
        
        print(f"Found {len(pending_jobs)} pending jobs:")
        for job in pending_jobs:
            space_id = job.get('space_id', 'Unknown')
            job_id = job.get('id', 'Unknown')
            created_at = job.get('start_time', 'Unknown')
            
            print(f"Job #{job_id} for space {space_id} created at {created_at}")
            
            # Get space details
            space_details = space.get_space(space_id)
            if space_details:
                url = space_details.get('space_url', 'Unknown URL')
                print(f"  URL: {url}")
                
                if 'title' in space_details:
                    print(f"  Title: {space_details['title']}")
            
            print(f"  Status: {job.get('status', 'Unknown')}")
            print(f"  File Type: {job.get('file_type', 'Unknown')}")
            print("---")
        
        print("\nWhat would you like to do?")
        print("1. Force job to 'in_progress' status")
        print("2. Reset job to 'pending' status")
        print("3. Delete job")
        print("4. Exit")
        
        choice = input("Enter your choice (1-4): ")
        
        if choice == '1':
            job_id = input("Enter the job ID to force to in_progress: ")
            try:
                job_id = int(job_id)
                success = space.update_download_job(job_id, status='in_progress')
                if success:
                    print(f"Successfully set job #{job_id} to in_progress.")
                else:
                    print(f"Failed to update job #{job_id}.")
            except ValueError:
                print("Invalid job ID.")
        
        elif choice == '2':
            job_id = input("Enter the job ID to reset: ")
            try:
                job_id = int(job_id)
                success = space.update_download_job(job_id, status='pending', 
                                                 error_message=None, 
                                                 progress_in_percent=0,
                                                 progress_in_size=0)
                if success:
                    print(f"Successfully reset job #{job_id}.")
                else:
                    print(f"Failed to reset job #{job_id}.")
            except ValueError:
                print("Invalid job ID.")
        
        elif choice == '3':
            job_id = input("Enter the job ID to delete: ")
            try:
                job_id = int(job_id)
                success = space.delete_download_job(job_id)
                if success:
                    print(f"Successfully deleted job #{job_id}.")
                else:
                    print(f"Failed to delete job #{job_id}.")
            except ValueError:
                print("Invalid job ID.")
        
        elif choice == '4':
            print("Exiting.")
        
        else:
            print("Invalid choice.")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()