#!/usr/bin/env python3
# test_download_progress.py - Test script to verify progress reporting in download jobs

import sys
import time
import os
import argparse
from datetime import datetime
from components.Space import Space
from components.DownloadSpace import DownloadSpace

def test_progress_reporting(space_url, interval=5, duration=60):
    """Test the progress reporting for a space download."""
    try:
        # Create Space component
        space_component = Space()
        
        # Extract space_id from URL
        space_id = space_component.extract_space_id(space_url)
        if not space_id:
            print(f"Error: Could not extract space ID from URL {space_url}")
            return False
        
        print(f"Space ID: {space_id}")
        
        # Check if the file already exists
        download_dir = "downloads"
        file_exists = False
        
        for ext in ['mp3', 'm4a', 'wav']:
            file_path = os.path.join(download_dir, f"{space_id}.{ext}")
            if os.path.exists(file_path) and os.path.getsize(file_path) > 1024*1024:  # > 1MB
                print(f"File already exists: {file_path}")
                file_exists = True
                # Optional: Delete the file to test downloading again
                if os.environ.get('DELETE_EXISTING'):
                    os.remove(file_path)
                    print(f"Deleted existing file: {file_path}")
                    file_exists = False
                break
        
        if file_exists and not os.environ.get('FORCE_DOWNLOAD'):
            print("File already exists. Use FORCE_DOWNLOAD=1 to download again.")
            return True
        
        # Create a downloader
        downloader = DownloadSpace()
        
        # Check for existing jobs for this space
        existing_job = space_component.get_download_job(space_id=space_id)
        if existing_job:
            print(f"Found existing job: #{existing_job['id']} with status '{existing_job['status']}'")
            if existing_job['status'] in ['completed', 'failed'] or os.environ.get('RESET_JOB'):
                print("Resetting job to pending status...")
                space_component.update_download_job(
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
            job_id = space_component.create_download_job(space_id)
            if not job_id:
                print("Error: Failed to create download job")
                return False
                
            # Check immediately if the job has already been processed
            job = space_component.get_download_job(job_id=job_id)
            if job and job.get('status') == 'completed':
                print("Job was immediately marked as completed!")
                print(f"Progress size: {job.get('progress_in_size', 0)} bytes")
                print(f"Check if this is a valid completion or if progress reporting is broken.")
        
        print(f"Job ID: {job_id}")
        
        # Initiate the download in async mode
        print(f"Starting download for {space_url}")
        result = downloader.download(
            space_url=space_url,
            file_type="mp3",
            async_mode=True
        )
        
        if not result:
            print("Error: Failed to start download")
            return False
        
        # Verify result format for async mode
        if isinstance(result, int):
            print(f"Successfully initiated async download with job ID: {result}")
        else:
            print(f"Warning: Unexpected result type: {type(result)}")
        
        # Poll for job status
        print("\nPolling for job status (press Ctrl+C to stop)...")
        start_time = time.time()
        end_time = start_time + duration
        
        try:
            previous_progress = -1
            previous_size = -1
            
            while time.time() < end_time:
                # Get job status
                job = space_component.get_download_job(job_id=job_id)
                if not job:
                    print("Error: Job not found")
                    break
                
                # Extract progress information
                status = job.get('status', 'unknown')
                progress = job.get('progress_in_percent', 0)
                size = job.get('progress_in_size', 0)
                
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
                    
                    # Log details about size change
                    if size != previous_size and previous_size >= 0:
                        size_diff = size - previous_size
                        if size_diff > 0:
                            print(f"  Size increased by {size_diff:,} bytes")
                        else:
                            print(f"  Size decreased by {abs(size_diff):,} bytes (unusual)")
                    
                    previous_progress = progress
                    previous_size = size
                
                # Check if the download is completed or failed
                if status in ['completed', 'failed']:
                    print(f"\nJob {status.upper()}")
                    if status == 'failed' and 'error_message' in job and job['error_message']:
                        print(f"Error: {job['error_message']}")
                    
                    if status == 'completed':
                        # Check if file exists
                        file_exists = False
                        for ext in ['mp3', 'm4a', 'wav']:
                            file_path = os.path.join(download_dir, f"{space_id}.{ext}")
                            if os.path.exists(file_path):
                                file_size = os.path.getsize(file_path)
                                print(f"File downloaded successfully: {file_path}")
                                print(f"File size: {file_size:,} bytes")
                                file_exists = True
                                break
                        
                        if not file_exists:
                            print("Warning: Job marked as completed but file not found!")
                    
                    return True
                
                # Also check if the part file exists and is growing
                part_file = os.path.join(download_dir, f"{space_id}.mp3.part")
                if os.path.exists(part_file):
                    part_size = os.path.getsize(part_file)
                    if part_size > 0:
                        if part_size < 1024*1024:
                            part_size_str = f"{part_size/1024:.2f} KB"
                        else:
                            part_size_str = f"{part_size/(1024*1024):.2f} MB"
                        print(f"Part file exists with size: {part_size_str}")
                        
                        # IMPORTANT: Check if the job's progress_in_size is significantly different from part file size
                        # This would indicate that the progress reporting is not working correctly
                        if size > 0 and abs(part_size - size) > 1024*1024:  # More than 1MB difference
                            print(f"WARNING: Job progress size ({size} bytes) differs significantly from")
                            print(f"         part file size ({part_size} bytes)")
                            print(f"         This may indicate a problem with progress reporting!")
                
                time.sleep(interval)
            
            print(f"\nMonitoring period of {duration} seconds elapsed.")
            return True
                
        except KeyboardInterrupt:
            print("\nStopped monitoring. The download may still be in progress.")
            return False
    
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    """Run the test."""
    parser = argparse.ArgumentParser(description='Test download progress reporting')
    parser.add_argument('--url', help='The URL of the space to download',
                        default="https://x.com/i/spaces/1yoJMopaxkgJQ")
    parser.add_argument('--interval', type=int, help='Polling interval in seconds', default=5)
    parser.add_argument('--duration', type=int, help='Maximum monitoring duration in seconds', default=60)
    args = parser.parse_args()
    
    test_progress_reporting(
        space_url=args.url,
        interval=args.interval,
        duration=args.duration
    )

if __name__ == "__main__":
    main()