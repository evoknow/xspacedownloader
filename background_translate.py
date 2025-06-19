#!/usr/bin/env python3
"""
Background Translation Worker

Processes translation jobs from the translation_jobs directory.
"""

import os
import sys
import json
import time
import logging
import datetime
from pathlib import Path

# Load environment variables
from load_env import load_env
load_env()

# Add the project directory to Python path
project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_dir)

# Import components
from components.Space import Space
from components.Translate import Translate
from components.CostAwareAI import CostAwareAI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('./logs/background_translate.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('background_translate')

class BackgroundTranslate:
    """Background translation job processor."""
    
    def __init__(self):
        """Initialize the background translation worker."""
        self.running = True
        self.jobs_dir = Path('./translation_jobs')
        self.jobs_dir.mkdir(exist_ok=True)
        
        # Initialize components
        try:
            self.space = Space()
            self.translator = Translate()
            logger.info("Background translation worker initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            raise
    
    def process_job(self, job_file: Path):
        """Process a single translation job."""
        try:
            # Load job data
            with open(job_file, 'r') as f:
                job_data = json.load(f)
            
            job_id = job_data.get('id')
            space_id = job_data.get('space_id')
            user_id = job_data.get('user_id')
            source_lang = job_data.get('source_lang', 'auto')
            target_lang = job_data.get('target_lang')
            transcript_text = job_data.get('transcript_text')
            
            logger.info(f"Processing translation job {job_id}: {space_id} -> {target_lang}")
            
            # Update job status to in_progress
            job_data['status'] = 'in_progress'
            job_data['progress'] = 10
            job_data['updated_at'] = datetime.datetime.now().isoformat()
            
            with open(job_file, 'w') as f:
                json.dump(job_data, f)
            
            # Perform translation with cost tracking
            logger.info(f"Starting translation from {source_lang} to {target_lang}")
            success, result = self.translator.translate(
                text=transcript_text,
                source_lang=source_lang,
                target_lang=target_lang,
                space_id=space_id
            )
            
            if not success:
                # Translation failed
                logger.error(f"Translation failed for job {job_id}: {result}")
                job_data['status'] = 'failed'
                job_data['error'] = str(result)
                job_data['progress'] = 0
                job_data['updated_at'] = datetime.datetime.now().isoformat()
                
                with open(job_file, 'w') as f:
                    json.dump(job_data, f)
                return
            
            # Translation successful - update progress
            job_data['progress'] = 80
            job_data['updated_at'] = datetime.datetime.now().isoformat()
            
            with open(job_file, 'w') as f:
                json.dump(job_data, f)
            
            logger.info(f"Translation completed, saving to database for job {job_id}")
            
            # Save translation to database
            cursor = self.space.connection.cursor()
            
            try:
                # Insert the translated transcript
                query = """
                INSERT INTO space_transcripts (space_id, transcript, language, created_at)
                VALUES (%s, %s, %s, %s)
                """
                cursor.execute(query, (
                    space_id,
                    result,
                    target_lang,
                    datetime.datetime.now()
                ))
                
                self.space.connection.commit()
                logger.info(f"Translation saved to database for space {space_id} in {target_lang}")
                
                # Update job status to completed
                job_data['status'] = 'completed'
                job_data['progress'] = 100
                job_data['updated_at'] = datetime.datetime.now().isoformat()
                job_data['result'] = {
                    'space_id': space_id,
                    'language': target_lang,
                    'text_sample': result[:200] + '...' if len(result) > 200 else result
                }
                
                with open(job_file, 'w') as f:
                    json.dump(job_data, f)
                
                logger.info(f"Translation job {job_id} completed successfully")
                
            except Exception as db_error:
                logger.error(f"Database error for job {job_id}: {db_error}")
                self.space.connection.rollback()
                
                job_data['status'] = 'failed'
                job_data['error'] = f"Database error: {str(db_error)}"
                job_data['progress'] = 0
                job_data['updated_at'] = datetime.datetime.now().isoformat()
                
                with open(job_file, 'w') as f:
                    json.dump(job_data, f)
                
            finally:
                cursor.close()
                
        except Exception as e:
            logger.error(f"Error processing translation job {job_file}: {e}")
            
            # Update job status to failed
            try:
                with open(job_file, 'r') as f:
                    job_data = json.load(f)
                
                job_data['status'] = 'failed'
                job_data['error'] = str(e)
                job_data['progress'] = 0
                job_data['updated_at'] = datetime.datetime.now().isoformat()
                
                with open(job_file, 'w') as f:
                    json.dump(job_data, f)
                    
            except Exception as file_error:
                logger.error(f"Failed to update job file after error: {file_error}")
    
    def run(self):
        """Main worker loop."""
        logger.info("Starting background translation worker")
        
        while self.running:
            try:
                # Look for pending translation jobs
                pending_jobs = []
                
                if self.jobs_dir.exists():
                    for job_file in self.jobs_dir.glob('*.json'):
                        try:
                            with open(job_file, 'r') as f:
                                job_data = json.load(f)
                            
                            if job_data.get('status') == 'pending':
                                pending_jobs.append((job_file, job_data.get('created_at', '')))
                                
                        except Exception as e:
                            logger.error(f"Error reading job file {job_file}: {e}")
                
                # Sort jobs by creation time (oldest first)
                pending_jobs.sort(key=lambda x: x[1])
                
                if pending_jobs:
                    # Process the oldest pending job
                    job_file, _ = pending_jobs[0]
                    self.process_job(job_file)
                else:
                    # No pending jobs, sleep for a bit
                    time.sleep(5)
                    
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(10)  # Wait longer on error
    
    def stop(self):
        """Stop the worker."""
        logger.info("Stopping background translation worker")
        self.running = False

def main():
    """Main entry point."""
    try:
        worker = BackgroundTranslate()
        worker.run()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()