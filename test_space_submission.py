#!/usr/bin/env python3
"""Test script to debug space submission issues."""

import sys
sys.path.append('/Volumes/KabirArchive1/projects/xspacedownload')

from components.Space import Space

def test_space_submission():
    """Test creating a download job for a space."""
    try:
        # Create Space component
        space = Space()
        print("✓ Space component created successfully")
        
        # Test space ID extraction
        test_url = "https://x.com/i/spaces/1jMJgBZnakWGL"
        space_id = space.extract_space_id(test_url)
        print(f"✓ Extracted space ID: {space_id}")
        
        if not space_id:
            print("✗ Failed to extract space ID")
            return
        
        # Try to create download job
        print(f"Attempting to create download job for space {space_id}...")
        job_id = space.create_download_job(space_id)
        
        if job_id:
            print(f"✓ Successfully created download job: {job_id}")
        else:
            print("✗ Failed to create download job")
            
        # Check current jobs
        jobs = space.list_download_jobs(status='pending', limit=10)
        print(f"Current pending jobs: {len(jobs)}")
        for job in jobs:
            print(f"  - Job {job.get('id', 'unknown')}: {job.get('space_id', 'unknown')} ({job.get('status', 'unknown')})")
            
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_space_submission()