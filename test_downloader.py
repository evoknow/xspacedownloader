#!/usr/bin/env python3
# test_downloader.py - Create a test space download job and monitor its status

import sys
import os
import time
import argparse
from components.Space import Space

def main():
    """
    Create a test space download job and monitor its status.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test the space downloader')
    parser.add_argument('url', help='The URL of the space to download', 
                       default="https://x.com/i/spaces/1dRJZEpyjlNGB", nargs='?')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    args = parser.parse_args()
    
    url = args.url
    verbose = args.verbose
    
    print(f"Testing download for space URL: {url}")
    
    try:
        # Create Space component
        space = Space()
        
        # Extract space_id from URL
        space_id = space.extract_space_id(url)
        if not space_id:
            print(f"Error: Could not extract space ID from URL {url}")
            sys.exit(1)
        
        print(f"Space ID: {space_id}")
        
        # Check for existing jobs for this space
        existing_job = space.get_download_job(space_id=space_id)
        if existing_job:
            print(f"Found existing job: #{existing_job['id']} with status '{existing_job['status']}'")
            print("Resetting job to pending status...")
            space.update_download_job(
                existing_job['id'], 
                status='pending', 
                error_message=None, 
                progress_in_percent=0,
                progress_in_size=0,
                process_id=None
            )
            job_id = existing_job['id']
        else:
            # Create a new download job
            print("Creating new download job...")
            job_id = space.create_download_job(space_id)
            if not job_id:
                print("Error: Failed to create download job")
                sys.exit(1)
        
        print(f"Job ID: {job_id}")
        
        # Poll for job status
        print("\nPolling for job status (press Ctrl+C to stop)...")
        try:
            while True:
                job = space.get_download_job(job_id=job_id)
                if not job:
                    print("Error: Job not found")
                    break
                
                status = job.get('status', 'unknown')
                progress = job.get('progress_in_percent', 0)
                
                print(f"\rStatus: {status} - Progress: {progress}%", end='')
                
                if verbose:
                    print("")  # New line in verbose mode
                    print(f"Details: {job}")
                
                if status in ['completed', 'failed']:
                    print("\n")
                    print(f"Job {status.upper()}")
                    if status == 'failed' and 'error_message' in job and job['error_message']:
                        print(f"Error: {job['error_message']}")
                    break
                
                time.sleep(3)
        
        except KeyboardInterrupt:
            print("\nStopped polling. The job may still be running in the background.")
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()