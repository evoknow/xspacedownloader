#!/usr/bin/env python3
"""
Script to retry failed transcription jobs with better error handling.
"""

import json
import os
import sys
from pathlib import Path
from components.SpeechToText import SpeechToText
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def retry_transcription(job_file):
    """Retry a failed transcription job."""
    # Load job data
    with open(job_file, 'r') as f:
        job_data = json.load(f)
    
    if job_data['status'] != 'failed':
        logger.info(f"Job {job_data['id']} is not in failed status, skipping")
        return
    
    space_id = job_data['space_id']
    file_path = job_data['file_path']
    
    # Check if file exists
    if not os.path.exists(file_path):
        logger.error(f"Audio file not found: {file_path}")
        return
    
    logger.info(f"Retrying transcription for space {space_id}")
    
    try:
        # Initialize SpeechToText with smaller model to reduce memory usage
        stt = SpeechToText(model_name='tiny')
        
        # Try transcription with shorter chunk duration
        result = stt.transcribe(
            file_path, 
            language='en',
            verbose=True,
            include_timecodes=True
        )
        
        if result and result.get('text'):
            logger.info(f"Transcription successful! Length: {len(result['text'])} characters")
            
            # Update job status
            job_data['status'] = 'completed'
            job_data['result'] = result
            job_data['error'] = None
            
            with open(job_file, 'w') as f:
                json.dump(job_data, f, indent=4)
                
            logger.info(f"Job {job_data['id']} updated to completed status")
        else:
            logger.error("Transcription returned no text")
            
    except Exception as e:
        logger.error(f"Error during transcription: {e}")
        
        # Try with even smaller settings
        try:
            logger.info("Retrying with minimal settings...")
            stt = SpeechToText(model_name='tiny')
            
            # Just get the text without timecodes
            result = stt.transcribe(
                file_path, 
                language='en',
                verbose=False,
                include_timecodes=False
            )
            
            if result and result.get('text'):
                logger.info(f"Minimal transcription successful! Length: {len(result['text'])} characters")
                
                # Update job status
                job_data['status'] = 'completed'
                job_data['result'] = result
                job_data['error'] = None
                
                with open(job_file, 'w') as f:
                    json.dump(job_data, f, indent=4)
                    
                logger.info(f"Job {job_data['id']} updated to completed status")
            else:
                logger.error("Minimal transcription also failed")
                
        except Exception as e2:
            logger.error(f"Minimal transcription error: {e2}")

def main():
    # Find all failed jobs
    jobs_dir = Path('./transcript_jobs')
    failed_jobs = []
    
    for job_file in jobs_dir.glob('*.json'):
        try:
            with open(job_file, 'r') as f:
                job_data = json.load(f)
                if job_data.get('status') == 'failed':
                    failed_jobs.append(job_file)
        except:
            pass
    
    logger.info(f"Found {len(failed_jobs)} failed transcription jobs")
    
    # Retry the first failed job
    if failed_jobs:
        retry_transcription(failed_jobs[0])
    else:
        logger.info("No failed jobs to retry")

if __name__ == "__main__":
    main()