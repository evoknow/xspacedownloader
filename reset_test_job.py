#!/usr/bin/env python3
# reset_test_job.py - Reset a completed job to pending status for testing

import sys
import argparse
from components.Space import Space

def reset_job(job_id, space_id=None):
    """Reset a job to pending status."""
    try:
        space = Space()
        
        # Get job details if we only have job_id
        if not space_id and job_id:
            job = space.get_download_job(job_id=job_id)
            if job:
                space_id = job.get('space_id')
                print(f"Found space_id: {space_id}")
            else:
                print(f"Job {job_id} not found")
                return False
                
        # If we have space_id but no job_id, find the latest job
        if space_id and not job_id:
            job = space.get_download_job(space_id=space_id)
            if job:
                job_id = job.get('id')
                print(f"Found job_id: {job_id}")
            else:
                print(f"No job found for space {space_id}")
                return False
        
        # Reset the job
        print(f"Resetting job {job_id} to pending status...")
        success = space.update_download_job(
            job_id, 
            status='pending', 
            error_message=None, 
            progress_in_percent=0,
            progress_in_size=0,
            process_id=None
        )
        
        if success:
            print(f"Job {job_id} reset successfully")
            return True
        else:
            print(f"Failed to reset job {job_id}")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    """Parse arguments and reset job."""
    parser = argparse.ArgumentParser(description='Reset a download job to pending status')
    parser.add_argument('--job', type=int, help='Job ID to reset')
    parser.add_argument('--space', help='Space ID to reset (latest job)')
    parser.add_argument('--url', help='Space URL to reset (latest job)')
    args = parser.parse_args()
    
    if not args.job and not args.space and not args.url:
        print("Error: You must provide either --job, --space, or --url")
        return False
    
    space_id = args.space
    job_id = args.job
    
    # If URL is provided, extract space_id
    if args.url:
        try:
            space = Space()
            space_id = space.extract_space_id(args.url)
            if not space_id:
                print(f"Error: Could not extract space ID from URL {args.url}")
                return False
            print(f"Extracted space_id: {space_id}")
        except Exception as e:
            print(f"Error extracting space_id from URL: {e}")
            return False
    
    return reset_job(job_id, space_id)

if __name__ == "__main__":
    main()