#!/usr/bin/env python3
# add_test_space.py
# Add test space URL to database for testing bg_downloader.py

import os
import sys

# Set up virtual environment path
VENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'venv')
VENV_ACTIVATE = os.path.join(VENV_PATH, 'bin', 'activate')

# If this script is not run with the virtual environment Python,
# try to re-execute it with the virtual environment Python
if not hasattr(sys, 'real_prefix') and not sys.prefix == VENV_PATH:
    if os.path.exists(os.path.join(VENV_PATH, 'bin', 'python')):
        venv_python = os.path.join(VENV_PATH, 'bin', 'python')
        os.execl(venv_python, venv_python, *sys.argv)
    else:
        print(f"Warning: Virtual environment not found at {VENV_PATH}")
        print("Trying to continue with system Python...")

# Try to import the Space component
try:
    from components.Space import Space
except ImportError as e:
    print(f"Error importing components: {e}")
    print("Make sure you've activated the virtual environment:")
    print(f"source {VENV_ACTIVATE}")
    sys.exit(1)

def main():
    # Create Space component instance
    space = Space()
    
    # Define the test space URL
    space_url = "https://x.com/i/spaces/1dRJZEpyjlNGB"
    
    # Create space in database
    print(f"Adding space URL: {space_url}")
    space_id = space.create_space(
        url=space_url,
        title="Test Space for Downloader",
        notes="Added for testing bg_downloader.py",
        user_id=1  # Use user ID 1 (or 0 for visitor)
    )
    
    if not space_id:
        print("Failed to create space in database")
        return
    
    print(f"Successfully created space with ID: {space_id}")
    
    # Create download job
    print("Creating download job...")
    job_id = space.create_download_job(
        space_id=space_id,
        user_id=1,
        file_type='mp3'
    )
    
    if not job_id:
        print("Failed to create download job")
        return
    
    print(f"Successfully created download job with ID: {job_id}")
    print(f"\nThe bg_downloader.py daemon should now pick up this job with:")
    print(f"  - Space ID: {space_id}")
    print(f"  - Job ID: {job_id}")
    print(f"  - Status: pending")

if __name__ == "__main__":
    main()