#!/usr/bin/env python3
"""Background Text-to-Speech daemon for XSpace Downloader."""

import os
import sys
import json
import time
import signal
import subprocess
import multiprocessing
from pathlib import Path
from datetime import datetime
import mysql.connector
from mysql.connector import Error

# Add current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
try:
    from components.Logger import get_logger
    logger = get_logger('background_texttospeech')
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger('background_texttospeech')

# Global variable to control daemon shutdown
shutdown_flag = False

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    global shutdown_flag
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    shutdown_flag = True

def get_db_connection():
    """Get database connection."""
    try:
        with open('db_config.json', 'r') as f:
            config = json.load(f)
        
        if config["type"] != "mysql":
            raise ValueError(f"Unsupported database type: {config['type']}")
        
        db_config = config["mysql"].copy()
        if 'use_ssl' in db_config:
            del db_config['use_ssl']
        
        return mysql.connector.connect(**db_config)
    except Exception as e:
        logger.error(f"Error connecting to database: {e}")
        raise

def get_pending_tts_jobs():
    """Get pending TTS jobs from the database."""
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT id, space_id, user_id, source_text, target_language, 
                   job_data, created_at, priority
            FROM tts_jobs 
            WHERE status = 'pending'
            ORDER BY priority DESC, created_at ASC
            LIMIT 10
        """)
        
        jobs = cursor.fetchall()
        cursor.close()
        connection.close()
        return jobs
        
    except Exception as e:
        logger.error(f"Error getting pending TTS jobs: {e}")
        return []

def update_job_status(job_id, status, progress=None, error_message=None, output_file=None):
    """Update job status in database."""
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        update_fields = ["status = %s", "updated_at = NOW()"]
        params = [status]
        
        if progress is not None:
            update_fields.append("progress = %s")
            params.append(progress)
        
        if error_message:
            update_fields.append("error_message = %s")
            params.append(error_message)
        
        if output_file:
            update_fields.append("output_file = %s")
            params.append(output_file)
        
        if status == 'completed':
            update_fields.append("completed_at = NOW()")
        elif status == 'failed':
            update_fields.append("failed_at = NOW()")
        
        params.append(job_id)
        
        query = f"UPDATE tts_jobs SET {', '.join(update_fields)} WHERE id = %s"
        cursor.execute(query, params)
        connection.commit()
        
        cursor.close()
        connection.close()
        
        logger.info(f"Updated job {job_id} status to {status}")
        
    except Exception as e:
        logger.error(f"Error updating job {job_id} status: {e}")

def record_transaction(user_id, space_id, cost, character_count, language):
    """Record TTS transaction in database."""
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Get current user balance
        cursor.execute("SELECT credits FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            logger.error(f"User {user_id} not found")
            return False
        
        balance_before = float(user['credits'])
        balance_after = balance_before - cost
        
        # Record transaction
        cursor.execute("""
            INSERT INTO transactions 
            (user_id, space_id, action, ai_model, input_tokens, output_tokens, cost, 
             balance_before, balance_after, source_language, target_language)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, space_id, 'text_to_speech', 'TTS', character_count, 0, cost, 
              balance_before, balance_after, 'text', language))
        
        # Update user balance
        cursor.execute("UPDATE users SET credits = %s WHERE id = %s", (balance_after, user_id))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        logger.info(f"Recorded TTS transaction for user {user_id}: {cost} credits")
        return True
        
    except Exception as e:
        logger.error(f"Error recording transaction: {e}")
        return False

def calculate_tts_cost(character_count):
    """Calculate TTS cost based on character count."""
    # Cost: 0.1 credits per 100 characters (similar to other AI services)
    base_cost = max(1, character_count / 100 * 0.1)
    return round(base_cost, 2)

def generate_tts_audio(job):
    """Generate TTS audio file for a job."""
    job_id = job['id']
    space_id = job['space_id']
    user_id = job['user_id']
    source_text = job['source_text']
    target_language = job['target_language']
    
    try:
        logger.info(f"Starting TTS generation for job {job_id}")
        update_job_status(job_id, 'in_progress', 0)
        
        # Create output directory if it doesn't exist
        output_dir = Path('downloads') / 'tts'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = output_dir / f"{space_id}_{target_language}_{timestamp}.mp3"
        
        # Calculate cost
        character_count = len(source_text)
        cost = calculate_tts_cost(character_count)
        
        update_job_status(job_id, 'in_progress', 25)
        
        # For now, we'll use a simple TTS approach (can be enhanced later)
        # This is a placeholder - in production you'd use a real TTS service
        logger.info(f"Generating TTS for {character_count} characters in {target_language}")
        
        # Simulate TTS generation (replace with actual TTS service call)
        import time
        time.sleep(2)  # Simulate processing time
        
        # Create a dummy MP3 file (in production, this would be the actual TTS output)
        with open(output_file, 'w') as f:
            f.write(f"TTS audio for space {space_id} in {target_language}\n")
            f.write(f"Text: {source_text[:100]}...\n")
        
        update_job_status(job_id, 'in_progress', 75)
        
        # Record transaction
        if record_transaction(user_id, space_id, cost, character_count, target_language):
            update_job_status(job_id, 'completed', 100, output_file=str(output_file))
            logger.info(f"TTS job {job_id} completed successfully")
        else:
            update_job_status(job_id, 'failed', error_message="Failed to record transaction")
            logger.error(f"TTS job {job_id} failed: transaction recording failed")
        
    except Exception as e:
        error_msg = f"TTS generation failed: {str(e)}"
        logger.error(f"Job {job_id} failed: {error_msg}")
        update_job_status(job_id, 'failed', error_message=error_msg)

def process_tts_job(job):
    """Process a single TTS job in a separate process."""
    try:
        generate_tts_audio(job)
    except Exception as e:
        logger.error(f"Error processing TTS job {job['id']}: {e}")
        update_job_status(job['id'], 'failed', error_message=str(e))

def main():
    """Main daemon loop."""
    global shutdown_flag
    
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("Background TTS daemon starting...")
    
    # Track active processes
    active_processes = {}
    max_concurrent_jobs = 3  # Limit concurrent TTS jobs
    
    while not shutdown_flag:
        try:
            # Clean up completed processes
            completed_processes = []
            for job_id, process in active_processes.items():
                if not process.is_alive():
                    process.join()
                    completed_processes.append(job_id)
            
            for job_id in completed_processes:
                del active_processes[job_id]
            
            # Get pending jobs if we have capacity
            if len(active_processes) < max_concurrent_jobs:
                pending_jobs = get_pending_tts_jobs()
                
                for job in pending_jobs:
                    if len(active_processes) >= max_concurrent_jobs:
                        break
                    
                    job_id = job['id']
                    if job_id not in active_processes:
                        logger.info(f"Starting TTS job {job_id}")
                        process = multiprocessing.Process(target=process_tts_job, args=(job,))
                        process.start()
                        active_processes[job_id] = process
            
            # Sleep before next iteration
            time.sleep(5)
            
        except Exception as e:
            logger.error(f"Error in main daemon loop: {e}")
            time.sleep(10)
    
    # Clean shutdown
    logger.info("Shutting down TTS daemon...")
    
    # Wait for active processes to complete
    for job_id, process in active_processes.items():
        logger.info(f"Waiting for TTS job {job_id} to complete...")
        process.join(timeout=30)
        if process.is_alive():
            logger.warning(f"Force terminating TTS job {job_id}")
            process.terminate()
            process.join()
    
    logger.info("TTS daemon shutdown complete")

if __name__ == "__main__":
    main()