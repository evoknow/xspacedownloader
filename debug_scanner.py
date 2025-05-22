#!/usr/bin/env python3
# debug_scanner.py - Debug the pending jobs scanner

import sys
import os
import json
import time
import logging
from components.Space import Space

# Configure logging to console for better visibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('debug_scanner')

def scan_for_pending_downloads(space):
    """
    Scan the database for pending downloads with detailed logging.
    
    Args:
        space (Space): Space component instance
    """
    try:
        # Check if connection is still active, if not create a new Space instance
        if not hasattr(space, 'connection') or not space.connection or not space.connection.is_connected():
            logger.info("Database connection lost, reconnecting...")
            space = Space()
            
        # Use the Space component to find pending download jobs
        logger.info("Querying for pending download jobs...")
        
        # Try to check the actual SQL query
        if hasattr(space, 'connection') and space.connection:
            try:
                cursor = space.connection.cursor(dictionary=True)
                # Check the space_download_scheduler table structure
                logger.info("Checking table structure...")
                cursor.execute("DESCRIBE space_download_scheduler")
                columns = cursor.fetchall()
                logger.info(f"Table columns: {', '.join([col['Field'] for col in columns])}")
                
                # Check if there are any records at all
                cursor.execute("SELECT COUNT(*) as count FROM space_download_scheduler")
                total_count = cursor.fetchone()['count']
                logger.info(f"Total jobs in table: {total_count}")
                
                # Check records by status
                cursor.execute("SELECT status, COUNT(*) as count FROM space_download_scheduler GROUP BY status")
                status_counts = cursor.fetchall()
                for status_count in status_counts:
                    logger.info(f"Status '{status_count['status']}': {status_count['count']} job(s)")
                
                # Try directly querying for pending jobs
                cursor.execute("SELECT * FROM space_download_scheduler WHERE status = 'pending'")
                pending_jobs = cursor.fetchall()
                logger.info(f"Direct SQL query found {len(pending_jobs)} pending jobs")
                for job in pending_jobs:
                    logger.info(f"Job #{job['id']} for space {job['space_id']}, created at {job['start_time']}")
                cursor.close()
            except Exception as e:
                logger.error(f"Error examining table: {e}")
            
        # Now try the actual method used by the background downloader
        jobs = space.list_download_jobs(status='pending')
        if jobs:
            logger.info(f"Space.list_download_jobs found {len(jobs)} pending jobs")
            for job in jobs:
                logger.info(f"Job #{job['id']} for space {job['space_id']}")
        else:
            logger.info("Space.list_download_jobs found NO pending jobs")
            
        # Check for active processes
        in_progress_jobs = space.list_download_jobs(status='in_progress')
        if in_progress_jobs:
            logger.info(f"Found {len(in_progress_jobs)} in_progress jobs")
            for job in in_progress_jobs:
                pid = job.get('process_id')
                if pid:
                    # Check if the process is still running
                    try:
                        os.kill(pid, 0)  # Signal 0 doesn't kill the process, just checks if it exists
                        logger.info(f"Process {pid} for job #{job['id']} is still running")
                    except OSError:
                        logger.info(f"Process {pid} for job #{job['id']} is no longer running")
                        logger.info(f"This job might be stuck. Consider resetting it to 'pending'")
                else:
                    logger.info(f"Job #{job['id']} has no process_id")
        else:
            logger.info("No in_progress jobs found")
            
        # Check for failed jobs
        failed_jobs = space.list_download_jobs(status='failed')
        if failed_jobs:
            logger.info(f"Found {len(failed_jobs)} failed jobs")
            for job in failed_jobs:
                logger.info(f"Job #{job['id']} for space {job['space_id']} failed: {job.get('error_message', 'Unknown error')}")
            
        return jobs or []
    except Exception as e:
        logger.error(f"Error scanning for pending downloads: {e}")
        return []

def main():
    """
    Main function to debug the scanner.
    """
    try:
        logger.info("Starting debug scanner...")
        
        # Create Space component
        logger.info("Creating Space component...")
        space = Space()
        
        # Scan for pending downloads
        logger.info("Scanning for pending downloads...")
        jobs = scan_for_pending_downloads(space)
        
        logger.info(f"Found {len(jobs)} pending jobs")
        if jobs:
            logger.info("Would you like to force claim one of these jobs? (y/n)")
            choice = input().lower()
            if choice == 'y':
                job_id = input("Enter job ID to claim: ")
                try:
                    job_id = int(job_id)
                    logger.info(f"Claiming job {job_id}...")
                    success = space.update_download_job(
                        job_id, 
                        status='in_progress',
                        process_id=os.getpid()
                    )
                    if success:
                        logger.info(f"Successfully claimed job {job_id}")
                    else:
                        logger.info(f"Failed to claim job {job_id}")
                except ValueError:
                    logger.error("Invalid job ID")
        
    except Exception as e:
        logger.error(f"Error in debug scanner: {e}")

if __name__ == "__main__":
    main()