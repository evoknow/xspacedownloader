#!/usr/bin/env python3
# test_api_progress.py - Test script for download progress reporting API

import requests
import json
import sys
import time
import argparse
from datetime import datetime

BASE_URL = 'http://127.0.0.1:5000'  # Default API URL

def get_api_key():
    """Read API key from test_api_key.txt file."""
    try:
        with open('test_api_key.txt', 'r') as f:
            return f.read().strip()
    except:
        print("No API key found in test_api_key.txt")
        print("Create a key first or use an existing one")
        sys.exit(1)

def create_test_download(space_url):
    """Create a test download job for the specified space URL."""
    api_key = get_api_key()
    url = f"{BASE_URL}/api/spaces"
    headers = {
        'X-API-Key': api_key,
        'Content-Type': 'application/json'
    }
    
    # First create or get the space
    space_data = {
        'space_url': space_url,
        'title': 'Test Space for Progress Reporting',
        'notes': 'Testing the progress reporting endpoint'
    }
    
    print(f"Creating space with URL: {space_url}")
    response = requests.post(url, headers=headers, json=space_data)
    
    if response.status_code not in [201, 409]:  # 201 Created or 409 Already exists
        print(f"Failed to create/get space: {response.text}")
        return None, None
    
    # Get the space ID
    space_id = None
    if response.status_code == 201:
        space_id = response.json().get('space_id')
        print(f"Created new space with ID: {space_id}")
    elif response.status_code == 409:
        space_info = response.json().get('space', {})
        space_id = space_info.get('space_id')
        print(f"Using existing space with ID: {space_id}")
    
    if not space_id:
        print("Could not get space ID")
        return None, None
    
    # Now initiate download
    download_url = f"{BASE_URL}/api/spaces/{space_id}/download"
    download_data = {
        'file_type': 'mp3',
        'async': True
    }
    
    print(f"Initiating download for space {space_id}")
    response = requests.post(download_url, headers=headers, json=download_data)
    
    if response.status_code not in [200, 409]:  # 200 OK or 409 Already in progress
        print(f"Failed to initiate download: {response.text}")
        return space_id, None
    
    # Get the job ID
    job_id = None
    if response.status_code == 200:
        job_id = response.json().get('job_id')
        print(f"Created new download job with ID: {job_id}")
    elif response.status_code == 409:
        job_id = response.json().get('status', {}).get('id')
        print(f"Using existing download job with ID: {job_id}")
    
    return space_id, job_id

def get_download_status(job_id, use_web_api=False):
    """Get the status of a download job using either API endpoint."""
    if use_web_api:
        # Use web app's API endpoint (doesn't require auth)
        url = f"{BASE_URL}/api/status/{job_id}"
        response = requests.get(url)
    else:
        # Use API controller endpoint (requires auth)
        api_key = get_api_key()
        url = f"{BASE_URL}/api/downloads/{job_id}"
        headers = {
            'X-API-Key': api_key,
            'Content-Type': 'application/json'
        }
        response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"Error getting status: {response.text}")
        return None
    
    return response.json()

def get_space_status(space_id):
    """Get the status of a space using the web app's API endpoint."""
    url = f"{BASE_URL}/api/space_status/{space_id}"
    response = requests.get(url)
    
    if response.status_code != 200:
        print(f"Error getting space status: {response.text}")
        return None
    
    return response.json()

def test_progress_reporting(job_id, space_id=None, interval=3, use_web_api=False, duration=60):
    """Monitor the download progress using the API."""
    print(f"Monitoring download progress for job {job_id}")
    print("Press Ctrl+C to stop monitoring")
    
    start_time = time.time()
    end_time = start_time + duration
    
    try:
        previous_progress = -1
        previous_size = -1
        
        while time.time() < end_time:
            # Get status from both endpoints for comparison
            api_status = get_download_status(job_id, use_web_api=use_web_api)
            
            if not api_status:
                print("Failed to get status")
                time.sleep(interval)
                continue
            
            # Get space status if space_id is provided
            space_status = None
            if space_id:
                space_status = get_space_status(space_id)
            
            # Extract progress information
            status = api_status.get('status', 'unknown')
            progress = api_status.get('progress_in_percent', 0)
            size = api_status.get('progress_in_size', 0)
            
            # Format the size in KB or MB
            if size < 1024*1024:
                size_str = f"{size/1024:.2f} KB"
            else:
                size_str = f"{size/(1024*1024):.2f} MB"
            
            # Show timestamp for each update
            timestamp = datetime.now().strftime('%H:%M:%S')
            
            # Check if progress or size has changed
            if progress != previous_progress or size != previous_size:
                print(f"[{timestamp}] Status: {status} - Progress: {progress}% - Size: {size_str}")
                previous_progress = progress
                previous_size = size
                
                # Log additional space status info if available
                if space_status:
                    space_progress = space_status.get('progress_in_percent', 0)
                    space_size = space_status.get('progress_in_size', 0)
                    
                    # Format the space size in KB or MB
                    if space_size < 1024*1024:
                        space_size_str = f"{space_size/1024:.2f} KB"
                    else:
                        space_size_str = f"{space_size/(1024*1024):.2f} MB"
                    
                    # Only print if different from job status
                    if space_progress != progress or space_size != size:
                        print(f"  Space Status: {space_status.get('status', 'unknown')} - " + 
                              f"Progress: {space_progress}% - Size: {space_size_str}")
            
            # Check if the download is completed or failed
            if status in ['completed', 'failed']:
                print(f"\nJob {status.upper()}")
                if status == 'failed' and 'error_message' in api_status and api_status['error_message']:
                    print(f"Error: {api_status['error_message']}")
                return True
            
            time.sleep(interval)
            
        print(f"\nMonitoring period of {duration} seconds elapsed.")
        return True
            
    except KeyboardInterrupt:
        print("\nStopped monitoring. The download may still be in progress.")
        return False

def main():
    """Run the test."""
    parser = argparse.ArgumentParser(description='Test the download progress reporting API')
    parser.add_argument('--url', help='The URL of the space to download',
                        default="https://x.com/i/spaces/1dRJZEpyjlNGB")
    parser.add_argument('--job', help='Existing job ID to monitor (skips creating a new job)')
    parser.add_argument('--space', help='Existing space ID to monitor (skips creating a new space)')
    parser.add_argument('--interval', type=int, help='Polling interval in seconds', default=3)
    parser.add_argument('--web-api', action='store_true', help='Use web app API instead of API controller')
    parser.add_argument('--duration', type=int, help='Maximum monitoring duration in seconds', default=60)
    args = parser.parse_args()
    
    job_id = args.job
    space_id = args.space
    
    if not job_id or not space_id:
        if args.job and not args.space:
            print("Job ID provided but space ID missing. Attempting to get space ID from job...")
            job_status = get_download_status(args.job, use_web_api=args.web_api)
            if job_status and 'space_id' in job_status:
                space_id = job_status['space_id']
                job_id = args.job
                print(f"Found space ID: {space_id}")
            else:
                print("Could not determine space ID from job")
    
    if not job_id or not space_id:
        # Create new download
        space_id, job_id = create_test_download(args.url)
        if not job_id:
            print("Failed to create test download job")
            return
    
    # Monitor the progress
    test_progress_reporting(
        job_id, 
        space_id=space_id, 
        interval=args.interval, 
        use_web_api=args.web_api,
        duration=args.duration
    )

if __name__ == "__main__":
    main()