#!/usr/bin/env python3
"""
Test script to verify the progress reporting from the API.
This will simulate a download job and check the response from the API.
"""

import os
import sys
import time
import json
import requests
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description='Test progress reporting from the API')
    parser.add_argument('--port', type=int, default=8080, help='Port where the web app is running')
    parser.add_argument('--job-id', type=int, help='Job ID to check')
    parser.add_argument('--space-id', type=str, help='Space ID to check')
    parser.add_argument('--create-part', action='store_true', help='Create a test .part file to simulate a download')
    parser.add_argument('--part-size', type=int, default=50, help='Size of the part file to create in MB')
    args = parser.parse_args()

    base_url = f'http://localhost:{args.port}'
    
    if args.create_part and args.space_id:
        create_test_part_file(args.space_id, args.part_size)
    
    if args.job_id:
        test_job_progress(base_url, args.job_id)
    
    if args.space_id:
        test_space_progress(base_url, args.space_id)

def create_test_part_file(space_id, size_mb):
    """Create a test .part file to simulate a download in progress."""
    print(f"Creating test part file for space {space_id} with size {size_mb}MB...")
    
    # Get the download directory from the config file
    download_dir = get_download_dir()
    
    # Create the part file
    part_file = os.path.join(download_dir, f"{space_id}.mp3.part")
    
    # Create a file of the specified size
    with open(part_file, 'wb') as f:
        f.seek(size_mb * 1024 * 1024 - 1)
        f.write(b'\0')
    
    print(f"Created test part file: {part_file}")
    print(f"File size: {os.path.getsize(part_file)} bytes")
    
    return part_file

def get_download_dir():
    """Get the download directory from the mainconfig.json file."""
    try:
        with open('mainconfig.json', 'r') as f:
            config = json.load(f)
            return config.get('download_dir', './downloads')
    except Exception as e:
        print(f"Error reading config file: {e}")
        return './downloads'

def test_job_progress(base_url, job_id):
    """Test the progress reporting from the job API endpoint."""
    print(f"Testing job progress for job ID {job_id}...")
    
    url = f"{base_url}/api/status/{job_id}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            print(f"Response from API:")
            print(json.dumps(data, indent=2))
            
            # Check for the updated progress calculation
            if 'progress_in_size' in data and data['progress_in_size'] > 0:
                size_mb = data['progress_in_size'] / (1024 * 1024)
                print(f"File size in MB: {size_mb:.2f}")
                
                # Calculate expected progress based on our new algorithm
                expected_progress = max(1, min(99, int(size_mb)))
                print(f"Expected progress percentage: {expected_progress}%")
                print(f"Actual progress percentage: {data['progress_in_percent']}%")
                
                if data['progress_in_percent'] == expected_progress:
                    print("✅ Progress calculation is correct!")
                else:
                    print("❌ Progress calculation does not match expected value.")
        else:
            print(f"Error: HTTP Status {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Error making request: {e}")

def test_space_progress(base_url, space_id):
    """Test the progress reporting from the space API endpoint."""
    print(f"Testing space progress for space ID {space_id}...")
    
    url = f"{base_url}/api/space_status/{space_id}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            print(f"Response from API:")
            print(json.dumps(data, indent=2))
            
            # Check for part file information
            if data.get('part_file_exists') and data.get('part_file_size', 0) > 0:
                size_mb = data['part_file_size'] / (1024 * 1024)
                print(f"Part file size in MB: {size_mb:.2f}")
                
                # Check if progress_in_percent is correctly calculated
                if 'progress_in_percent' in data:
                    expected_progress = max(1, min(99, int(size_mb)))
                    print(f"Expected progress percentage: {expected_progress}%")
                    print(f"Actual progress percentage: {data['progress_in_percent']}%")
                    
                    if data['progress_in_percent'] == expected_progress:
                        print("✅ Progress calculation is correct!")
                    else:
                        print("❌ Progress calculation does not match expected value.")
        else:
            print(f"Error: HTTP Status {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Error making request: {e}")

if __name__ == "__main__":
    main()