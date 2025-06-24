#!/usr/bin/env python3
"""
Background Video Generation Daemon

This daemon processes video generation jobs from the transcript_jobs directory.
It runs continuously and processes jobs with _video.json suffix.
"""

import os
import sys
import time
import json
import logging
import signal
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

# Setup paths
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Import components
from components.VideoGenerator import VideoGenerator

# Setup logging
log_dir = Path(script_dir) / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'video_daemon.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('video_daemon')

class VideoDaemon:
    def __init__(self):
        self.running = True
        self.jobs_dir = Path(script_dir) / 'transcript_jobs'
        self.downloads_dir = Path(script_dir) / 'downloads'
        self.video_generator = VideoGenerator(downloads_dir=str(self.downloads_dir))
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        logger.info("Video daemon initialized")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    def scan_for_jobs(self) -> list:
        """Scan for pending video generation jobs"""
        if not self.jobs_dir.exists():
            return []
        
        pending_jobs = []
        
        # Look for video job files
        for job_file in self.jobs_dir.glob('*_video.json'):
            try:
                with open(job_file, 'r') as f:
                    job_data = json.load(f)
                
                status = job_data.get('status', 'unknown')
                if status in ['pending', 'processing']:
                    pending_jobs.append((job_file, job_data))
                    
            except Exception as e:
                logger.error(f"Error reading job file {job_file}: {e}")
        
        return pending_jobs
    
    def fix_audio_path(self, original_path: str, space_id: str) -> Optional[str]:
        """Fix audio path to point to correct location"""
        # Check if original path exists
        if os.path.exists(original_path):
            return original_path
        
        # Try to find the audio file in downloads directory
        for ext in ['mp3', 'm4a', 'wav']:
            audio_path = self.downloads_dir / f"{space_id}.{ext}"
            if audio_path.exists() and audio_path.stat().st_size > 1024*1024:  # > 1MB
                logger.info(f"Fixed audio path for {space_id}: {original_path} -> {audio_path}")
                return str(audio_path)
        
        return None
    
    def process_job(self, job_file: Path, job_data: Dict) -> bool:
        """Process a single video generation job"""
        job_id = job_data.get('job_id')
        space_id = job_data.get('space_id')
        
        logger.info(f"Processing video job {job_id} for space {space_id}")
        
        try:
            # Fix audio path if needed
            original_audio_path = job_data.get('audio_path')
            fixed_audio_path = self.fix_audio_path(original_audio_path, space_id)
            
            if not fixed_audio_path:
                # Mark job as failed
                job_data['status'] = 'failed'
                job_data['error'] = f'Audio file not found: {original_audio_path}'
                job_data['updated_at'] = datetime.now().isoformat()
                
                with open(job_file, 'w') as f:
                    json.dump(job_data, f, indent=2)
                
                logger.error(f"Audio file not found for job {job_id}: {original_audio_path}")
                return False
            
            # Update audio path in job data if it was fixed
            if fixed_audio_path != original_audio_path:
                job_data['audio_path'] = fixed_audio_path
            
            # Update status to processing
            job_data['status'] = 'processing'
            job_data['updated_at'] = datetime.now().isoformat()
            job_data['progress'] = 5
            
            with open(job_file, 'w') as f:
                json.dump(job_data, f, indent=2)
            
            # Process the video generation
            success = self.video_generator._generate_video_sync(job_id)
            
            if success:
                logger.info(f"Successfully processed video job {job_id}")
                return True
            else:
                logger.error(f"Video generation failed for job {job_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing job {job_id}: {e}")
            logger.error(traceback.format_exc())
            
            # Mark job as failed
            try:
                job_data['status'] = 'failed'
                job_data['error'] = str(e)
                job_data['updated_at'] = datetime.now().isoformat()
                
                with open(job_file, 'w') as f:
                    json.dump(job_data, f, indent=2)
            except Exception as update_error:
                logger.error(f"Failed to update job status: {update_error}")
            
            return False
    
    def run(self):
        """Main daemon loop"""
        logger.info("Starting video generation daemon")
        
        while self.running:
            try:
                # Scan for pending jobs
                pending_jobs = self.scan_for_jobs()
                
                if pending_jobs:
                    logger.info(f"Found {len(pending_jobs)} pending video jobs")
                    
                    for job_file, job_data in pending_jobs:
                        if not self.running:
                            break
                        
                        self.process_job(job_file, job_data)
                        
                        # Small delay between jobs
                        time.sleep(1)
                else:
                    # No jobs, wait longer
                    time.sleep(10)
                    
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                logger.error(traceback.format_exc())
                time.sleep(30)  # Wait before retrying
        
        logger.info("Video daemon stopped")

def main():
    """Main entry point"""
    try:
        daemon = VideoDaemon()
        daemon.run()
    except KeyboardInterrupt:
        logger.info("Daemon interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == '__main__':
    main()