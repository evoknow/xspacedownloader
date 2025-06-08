#!/usr/bin/env python3
"""Test script to verify MP3 video generation fix."""

import os
import sys
import logging
from components.VideoGenerator import VideoGenerator

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_video_mp3')

def test_mp3_video_generation():
    """Test video generation with MP3 file."""
    
    # Find an MP3 file in downloads directory
    downloads_dir = os.path.abspath('./downloads')
    mp3_files = [f for f in os.listdir(downloads_dir) if f.endswith('.mp3')]
    
    if not mp3_files:
        logger.error("No MP3 files found in downloads directory")
        return False
    
    # Use the first MP3 file found
    mp3_file = mp3_files[0]
    space_id = mp3_file.replace('.mp3', '')
    audio_path = os.path.join(downloads_dir, mp3_file)
    
    logger.info(f"Testing with MP3 file: {audio_path}")
    logger.info(f"Space ID: {space_id}")
    
    # Create test space data
    space_data = {
        'space_id': space_id,
        'title': 'Test MP3 Video Generation',
        'metadata': {
            'host': 'Test Host',
            'host_handle': '@testhost'
        }
    }
    
    # Initialize VideoGenerator
    video_gen = VideoGenerator()
    
    try:
        # Create video job
        logger.info("Creating video generation job...")
        job_id = video_gen.create_video_job(
            space_id=space_id,
            audio_path=audio_path,
            space_data=space_data,
            user_id='test_user'
        )
        
        logger.info(f"Created job: {job_id}")
        
        # Check job status
        job_status = video_gen.get_job_status(job_id)
        if job_status:
            logger.info(f"Job status: {job_status.get('status')}")
            logger.info(f"Progress: {job_status.get('progress')}%")
            
            if job_status.get('status') == 'completed':
                logger.info(f"Video path: {job_status.get('video_path')}")
                
                # Check if video file exists
                video_path = job_status.get('video_path')
                if video_path and os.path.exists(video_path):
                    video_size = os.path.getsize(video_path)
                    logger.info(f"Video successfully created: {video_path} ({video_size:,} bytes)")
                    return True
                else:
                    logger.error("Video file not found")
            elif job_status.get('status') == 'failed':
                logger.error(f"Job failed: {job_status.get('error')}")
            else:
                logger.warning(f"Job in progress or unknown status: {job_status.get('status')}")
        else:
            logger.error("Could not get job status")
            
    except Exception as e:
        logger.error(f"Error during test: {e}", exc_info=True)
        
    return False

if __name__ == "__main__":
    logger.info("Starting MP3 video generation test...")
    success = test_mp3_video_generation()
    
    if success:
        logger.info("Test completed successfully!")
        sys.exit(0)
    else:
        logger.error("Test failed!")
        sys.exit(1)