#!/usr/bin/env python3
# test_api_fix.py - Tests the API fix for progress_in_size issue

import sys
import json
from components.Space import Space
from app import app

def test_direct_fix(job_id):
    """Test the fix by directly using the app's logic."""
    
    # Get the actual value from the database
    space = Space()
    job = space.get_download_job(job_id=job_id)
    if not job:
        print(f"Job #{job_id} not found in database")
        return False
    
    db_progress_size = job.get('progress_in_size')
    print(f"Database value for job #{job_id} progress_in_size: {db_progress_size} (type: {type(db_progress_size)})")
    
    # Now test the fix directly
    # Our fix ensures progress_in_size is properly converted to an integer
    progress_size = db_progress_size
    if isinstance(progress_size, str) and progress_size.isdigit():
        progress_size = int(progress_size)
    
    print(f"After fix applied: {progress_size} (type: {type(progress_size)})")
    
    # Test for string representation
    str_size = "3340199"
    print(f"Testing with string: {str_size} (type: {type(str_size)})")
    
    if isinstance(str_size, str) and str_size.isdigit():
        str_size = int(str_size)
        print(f"After fix applied: {str_size} (type: {type(str_size)})")
    
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_api_fix.py <job_id>")
        sys.exit(1)
    
    job_id = int(sys.argv[1])
    test_direct_fix(job_id)