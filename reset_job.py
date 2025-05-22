#!/usr/bin/env python3
# reset_job.py - Reset a download job to pending status

import sys
from components.Space import Space

def main():
    """Reset a download job to pending status"""
    if len(sys.argv) < 2:
        print("Usage: python reset_job.py <job_id>")
        sys.exit(1)
        
    job_id = int(sys.argv[1])
    
    # Create Space component
    space = Space()
    
    # Get job details
    job = space.get_download_job(job_id=job_id)
    
    if not job:
        print(f"Job {job_id} not found")
        sys.exit(1)
        
    print(f"Job {job_id} for space {job['space_id']} has status: {job['status']}")
    
    # Reset job to pending
    print(f"Resetting job {job_id} to pending status...")
    space.update_download_job(
        job_id,
        status='pending',
        process_id=None,
        progress_in_percent=0,
        progress_in_size=0,
        error_message=None
    )
    
    print(f"Job {job_id} reset to pending status")
    
    # Get updated job
    job = space.get_download_job(job_id=job_id)
    print(f"Job {job_id} now has status: {job['status']}")

if __name__ == "__main__":
    main()