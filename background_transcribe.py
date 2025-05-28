#!/usr/bin/env python3
# background_transcribe.py - Background process for speech-to-text transcription

import os
import sys
import json
import time
import signal
import logging
import argparse
import traceback
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('transcription_worker.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('background_transcribe')

# Add parent directory to path for importing components
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import components
try:
    from components.Space import Space
    from components.SpeechToText import SpeechToText
except ImportError as e:
    logger.error(f"Failed to import required components: {e}")
    sys.exit(1)

class TranscriptionWorker:
    """Background worker for handling transcription tasks."""
    
    def __init__(self, status_dir='./transcript_jobs'):
        """
        Initialize the transcription worker.
        
        Args:
            status_dir (str): Directory to store transcription job status files
        """
        self.status_dir = Path(status_dir)
        self.status_dir.mkdir(parents=True, exist_ok=True)
        self.space = Space()
        self.stt = None
        self.running = True
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        
        logger.info(f"Transcription worker initialized. Status directory: {self.status_dir}")
    
    def handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}. Shutting down gracefully...")
        self.running = False
    
    def load_speech_to_text(self, model_name='base'):
        """
        Load the SpeechToText component with the specified model.
        
        Args:
            model_name (str): The Whisper model to load (tiny, base, small, medium, large)
            
        Returns:
            bool: True if loaded successfully, False otherwise
        """
        if self.stt is None or self.stt.model_name != model_name:
            try:
                logger.info(f"Loading SpeechToText with model: {model_name}")
                self.stt = SpeechToText(model_name=model_name)
                return True
            except Exception as e:
                logger.error(f"Failed to load SpeechToText: {e}")
                return False
        return True
    
    def create_job(self, space_id, language='en-US', model='base', detect_language=False, 
                  translate_to=None, callback_url=None):
        """
        Create a transcription job.
        
        Args:
            space_id (str): The space ID to transcribe
            language (str): Language code for transcription
            model (str): Whisper model to use
            detect_language (bool): Whether to detect language automatically
            translate_to (str): Language code to translate to
            callback_url (str): URL to call when job completes
            
        Returns:
            str: Job ID
        """
        job_id = f"{space_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        job_data = {
            'job_id': job_id,
            'space_id': space_id,
            'language': language,
            'model': model,
            'detect_language': detect_language,
            'translate_to': translate_to,
            'callback_url': callback_url,
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'progress': 0,
            'result': None,
            'error': None
        }
        
        # Save job data to file
        with open(self.status_dir / f"{job_id}.json", 'w') as f:
            json.dump(job_data, f, indent=4)
        
        logger.info(f"Created transcription job {job_id} for space {space_id}")
        return job_id
    
    def update_job_status(self, job_id, status, progress=None, result=None, error=None):
        """
        Update job status.
        
        Args:
            job_id (str): The job ID
            status (str): New status (pending, processing, completed, failed)
            progress (float, optional): Progress percentage (0-100)
            result (dict, optional): Result data if completed
            error (str, optional): Error message if failed
        """
        job_file = self.status_dir / f"{job_id}.json"
        
        if not job_file.exists():
            logger.error(f"Job file not found: {job_file}")
            return False
        
        try:
            with open(job_file, 'r') as f:
                job_data = json.load(f)
            
            job_data['status'] = status
            job_data['updated_at'] = datetime.now().isoformat()
            
            if progress is not None:
                job_data['progress'] = progress
            
            if result is not None:
                job_data['result'] = result
            
            if error is not None:
                job_data['error'] = error
            
            with open(job_file, 'w') as f:
                json.dump(job_data, f, indent=4)
            
            return True
        except Exception as e:
            logger.error(f"Error updating job status: {e}")
            return False
    
    def get_job_status(self, job_id):
        """
        Get job status.
        
        Args:
            job_id (str): The job ID
            
        Returns:
            dict: Job status data or None if not found
        """
        job_file = self.status_dir / f"{job_id}.json"
        
        if not job_file.exists():
            logger.error(f"Job file not found: {job_file}")
            return None
        
        try:
            with open(job_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading job status: {e}")
            return None
    
    def get_pending_jobs(self):
        """
        Get all pending jobs.
        
        Returns:
            list: List of pending job data
        """
        pending_jobs = []
        
        for job_file in self.status_dir.glob('*.json'):
            try:
                with open(job_file, 'r') as f:
                    job_data = json.load(f)
                    if job_data['status'] == 'pending':
                        pending_jobs.append(job_data)
            except Exception as e:
                logger.error(f"Error reading job file {job_file}: {e}")
        
        return pending_jobs
    
    def process_job(self, job_data):
        """
        Process a transcription job.
        
        Args:
            job_data (dict): Job data
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Handle both 'job_id' and 'id' field names for backward compatibility
        job_id = job_data.get('job_id') or job_data.get('id')
        space_id = job_data.get('space_id')
        
        if not space_id:
            logger.error(f"Job {job_id} missing required space_id field")
            self.update_job_status(job_id, 'failed', error="Missing space_id field")
            return False
        
        try:
            # Update job status to processing
            self.update_job_status(job_id, 'processing', progress=5)
            
            # Load the right model
            # Handle both direct 'model' field and nested in 'options'
            model = job_data.get('model') or job_data.get('options', {}).get('model', 'base')
            if not self.load_speech_to_text(model_name=model):
                self.update_job_status(job_id, 'failed', error=f"Failed to load model: {model}")
                return False
            
            # Update progress
            self.update_job_status(job_id, 'processing', progress=10)
            
            # Process audio file
            logger.info(f"Starting transcription for job {job_id} (space {space_id})")
            
            # Find the audio file
            config = self.space.get_config()
            download_dir = config.get('download_dir', './downloads')
            audio_path = None
            
            for ext in ['mp3', 'm4a', 'wav']:
                file_path = os.path.join(download_dir, f"{space_id}.{ext}")
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    audio_path = file_path
                    break
            
            if not audio_path:
                self.update_job_status(job_id, 'failed', error=f"Audio file not found for space {space_id}")
                return False
            
            # Update progress
            self.update_job_status(job_id, 'processing', progress=15)
            
            # Set up transcription options
            # Handle both direct fields and nested in 'options'
            job_options = job_data.get('options', {})
            language = job_data.get('language') or job_options.get('language', 'en-US')
            detect_language = job_data.get('detect_language', job_options.get('detect_language', False))
            translate_to = job_data.get('translate_to', job_options.get('translate_to'))
            include_timecodes = job_data.get('include_timecodes', job_options.get('include_timecodes', False))
            
            options = {
                'language': language,
                'detect_language': detect_language,
                'verbose': True,
                'include_timecodes': include_timecodes
            }
            
            if translate_to:
                options['translate_to'] = translate_to
            
            # Check if transcript already exists in database before processing
            target_language = translate_to if translate_to else language
            if target_language and len(target_language) == 2:
                target_language = f"{target_language}-{target_language.upper()}"
            
            # Check database for existing transcript
            existing_transcript = None
            try:
                cursor = self.space.connection.cursor(dictionary=True)
                
                # First try exact match
                query = "SELECT * FROM space_transcripts WHERE space_id = %s AND language = %s"
                cursor.execute(query, (space_id, target_language))
                existing_transcript = cursor.fetchone()
                
                # If no exact match, try language family match (e.g., en-US matches en-EN)
                if not existing_transcript and '-' in target_language:
                    base_language = target_language.split('-')[0]
                    query = "SELECT * FROM space_transcripts WHERE space_id = %s AND language LIKE %s"
                    cursor.execute(query, (space_id, f"{base_language}-%"))
                    existing_transcript = cursor.fetchone()
                    if existing_transcript:
                        logger.info(f"Found compatible transcript in {existing_transcript['language']} for requested {target_language}")
                
                cursor.close()
                
                # If transcript exists and overwrite is not enabled, use existing one
                overwrite_option = job_options.get('overwrite', True)
                if existing_transcript and not overwrite_option:
                    logger.info(f"Found existing transcript for {space_id} in {target_language}, skipping AI processing")
                    
                    # Build result data from existing transcript
                    result_data = {
                        "transcript_id": existing_transcript['id'],
                        "space_id": space_id,
                        "language": existing_transcript['language'],
                        "text_sample": existing_transcript['transcript'][:500] + "..." if len(existing_transcript['transcript']) > 500 else existing_transcript['transcript'],
                        "from_database": True
                    }
                    
                    # Mark job as completed without AI processing
                    self.update_job_status(job_id, 'completed', progress=100, result=result_data)
                    logger.info(f"Transcription job {job_id} completed using existing database transcript")
                    return True
                    
            except Exception as db_err:
                logger.warning(f"Error checking existing transcript: {db_err}")
                # Continue with AI processing if database check fails
            
            # Perform transcription using AI
            logger.info(f"Processing transcription with AI for {space_id} in {target_language}")
            
            # Start transcription with progress tracking
            import threading
            import time
            
            # Get audio file size and estimate duration
            audio_file_size = os.path.getsize(audio_path) if os.path.exists(audio_path) else 0
            logger.info(f"Audio file size: {audio_file_size / 1024 / 1024:.1f} MB")
            
            # Estimate audio duration from file size (rough estimate for MP3)
            # MP3 at ~128kbps: 1MB ≈ 1 minute of audio
            estimated_audio_minutes = max(1, (audio_file_size / 1024 / 1024))
            logger.info(f"Estimated audio duration: {estimated_audio_minutes:.1f} minutes")
            
            # Estimate processing time based on file size (rough estimate)
            # Typically ~1-2 minutes per MB for base model
            estimated_seconds = max(30, (audio_file_size / 1024 / 1024) * 60)  # Min 30 seconds
            logger.info(f"Estimated processing time: {estimated_seconds:.0f} seconds")
            
            # Update job status with estimated audio duration
            self.update_job_status(job_id, 'processing', progress=15, 
                                 result={'estimated_audio_minutes': estimated_audio_minutes})
            
            # Start progress tracking thread
            transcription_complete = threading.Event()
            
            def update_progress_during_transcription():
                """Update progress periodically during transcription."""
                start_time = time.time()
                while not transcription_complete.is_set():
                    elapsed = time.time() - start_time
                    progress_ratio = min(elapsed / estimated_seconds, 0.9)  # Cap at 90%
                    progress = int(15 + (progress_ratio * 65))  # 15% to 80%
                    
                    # Include audio duration info in progress updates
                    progress_result = {
                        'estimated_audio_minutes': estimated_audio_minutes,
                        'processing_elapsed_seconds': elapsed
                    }
                    self.update_job_status(job_id, 'processing', progress=progress, result=progress_result)
                    logger.info(f"Transcription progress: {progress}% (elapsed: {elapsed:.0f}s, ~{estimated_audio_minutes:.1f} min audio)")
                    
                    # Update every 30 seconds
                    if transcription_complete.wait(30):
                        break
            
            # Start progress thread
            progress_thread = threading.Thread(target=update_progress_during_transcription)
            progress_thread.daemon = True
            progress_thread.start()
            
            try:
                # Perform the actual transcription
                result = self.stt.transcribe(audio_path, **options)
            finally:
                # Stop progress tracking
                transcription_complete.set()
                progress_thread.join(timeout=1)
            
            # Update progress to 80% when transcription is complete
            self.update_job_status(job_id, 'processing', progress=80)
            
            if not result:
                self.update_job_status(job_id, 'failed', error="Transcription returned no result")
                return False
            
            # Save transcript to database
            try:
                # Get language code from result or use the provided one
                language_code = None
                if translate_to and "target_language" in result and "code" in result["target_language"]:
                    lang = result["target_language"]["code"]
                    language_code = f"{lang}-{lang.upper()}" if len(lang) == 2 else lang
                elif "detected_language" in result and "code" in result["detected_language"]:
                    lang = result["detected_language"]["code"]
                    language_code = f"{lang}-{lang.upper()}" if len(lang) == 2 else lang
                else:
                    language_code = language
                
                # Use the most appropriate text
                if translate_to and "translated_text" in result:
                    transcript_text = result["translated_text"]
                else:
                    transcript_text = result["text"]
                
                # Check for maximum text length issues
                if len(transcript_text) > 64000:  # MySQL TEXT type max is 65535 bytes
                    logger.warning(f"Transcript is too long ({len(transcript_text)} chars), truncating to 64000 chars")
                    transcript_text = transcript_text[:64000]
                
                # Save to database
                transcript_id = self.space.save_transcript(space_id, transcript_text, language_code)
                
                if not transcript_id:
                    self.update_job_status(job_id, 'failed', 
                                          error="Failed to save transcript to database",
                                          result={"text_sample": transcript_text[:500] + "..."})
                    return False
                
                # Save original text as separate transcript if translation was done
                original_transcript_id = None
                if translate_to and "original_text" in result and "original_language" in result:
                    orig_lang = result["original_language"]
                    orig_lang_code = f"{orig_lang}-{orig_lang.upper()}" if len(orig_lang) == 2 else orig_lang
                    
                    original_text = result["original_text"]
                    if len(original_text) > 64000:
                        original_text = original_text[:64000]
                    
                    original_transcript_id = self.space.save_transcript(space_id, original_text, orig_lang_code)
                
                # Get actual audio duration from Whisper result
                actual_duration = result.get("segments", [])
                if actual_duration:
                    # Get the end time of the last segment for actual duration
                    actual_duration_seconds = actual_duration[-1].get("end", 0)
                    actual_audio_minutes = actual_duration_seconds / 60
                else:
                    # Fallback to using the overall duration if available
                    actual_duration_seconds = result.get("duration", 0)
                    actual_audio_minutes = actual_duration_seconds / 60 if actual_duration_seconds else estimated_audio_minutes
                
                # Build result data
                result_data = {
                    "transcript_id": transcript_id,
                    "space_id": space_id,
                    "language": language_code,
                    "text_sample": transcript_text[:500] + "..." if len(transcript_text) > 500 else transcript_text,
                    "audio_duration_minutes": round(actual_audio_minutes, 1),
                    "audio_duration_seconds": round(actual_duration_seconds, 1)
                }
                
                if original_transcript_id:
                    result_data["original_transcript_id"] = original_transcript_id
                
                if "detected_language" in result:
                    result_data["detected_language"] = result["detected_language"]
                
                # Mark job as completed
                self.update_job_status(job_id, 'completed', progress=100, result=result_data)
                logger.info(f"Transcription job {job_id} completed successfully")
                
                return True
                
            except Exception as db_err:
                logger.error(f"Error saving transcript to database: {db_err}")
                self.update_job_status(job_id, 'failed', 
                                     error=f"Error saving transcript: {str(db_err)}",
                                     result={"text_sample": result["text"][:500] + "..."})
                return False
            
        except Exception as e:
            logger.error(f"Error processing job {job_id}: {e}")
            self.update_job_status(job_id, 'failed', error=str(e))
            traceback.print_exc()
            return False
    
    def run(self):
        """Run the worker loop."""
        logger.info("Starting transcription worker loop")
        
        while self.running:
            try:
                # Get pending jobs
                pending_jobs = self.get_pending_jobs()
                
                if pending_jobs:
                    logger.info(f"Found {len(pending_jobs)} pending jobs")
                    
                    # Process the first pending job
                    job = pending_jobs[0]
                    # Handle both 'job_id' and 'id' field names for backward compatibility
                    job_id = job.get('job_id') or job.get('id')
                    space_id = job.get('space_id', 'unknown')
                    logger.info(f"Processing job {job_id} for space {space_id}")
                    
                    # Process the job
                    self.process_job(job)
                
                # Wait before checking for more jobs
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                time.sleep(10)  # Wait longer if there was an error
        
        logger.info("Worker loop terminated")

def main():
    parser = argparse.ArgumentParser(description='Background transcription worker for XSpace Downloader')
    parser.add_argument('--status-dir', type=str, default='./transcript_jobs',
                        help='Directory to store job status files')
    
    args = parser.parse_args()
    
    worker = TranscriptionWorker(status_dir=args.status_dir)
    worker.run()

if __name__ == '__main__':
    main()