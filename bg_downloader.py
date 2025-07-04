#!/usr/bin/env python3
# bg_downloader.py
# Background daemon to monitor and download X spaces

import os
import sys
import json
import time
import signal
import logging
import datetime
import argparse
import subprocess
import shutil  # for shutil.which()
from pathlib import Path
from typing import Dict, List, Optional, Any
import mysql.connector
from mysql.connector import Error
from components.CostLogger import CostLogger  # For compute cost tracking
from components.Email import Email  # For email notifications

# Check if we're already running in a virtual environment
# If the script is executed with venv Python (as systemd does), skip venv detection
if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
    # Already in venv, continue
    pass
else:
    # Try to find and use virtual environment
    VENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'venv')
    if os.path.exists(os.path.join(VENV_PATH, 'bin', 'python')):
        venv_python = os.path.join(VENV_PATH, 'bin', 'python')
        os.execl(venv_python, venv_python, *sys.argv)
    else:
        print(f"Warning: Virtual environment not found at {VENV_PATH}")
        print("Continuing with current Python...")

# Import components
try:
    from components.Space import Space
except ImportError as e:
    print(f"Error importing components: {e}")
    print("Make sure you've activated the virtual environment:")
    print(f"source {VENV_ACTIVATE}")
    sys.exit(1)

# Configure logging
log_directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_directory, exist_ok=True)
log_file = os.path.join(log_directory, 'bg_downloader.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('bg_downloader')

# Debug logging flag
DEBUG_MODE = False

# Global variables
running = True
max_concurrent_downloads = 5
active_processes = {}  # job_id -> process_info
config = {}


def load_config() -> Dict[str, Any]:
    """
    Load configuration from mainconfig.json
    
    Returns:
        Dict[str, Any]: Configuration dictionary
    """
    try:
        with open('mainconfig.json', 'r') as config_file:
            return json.load(config_file)
    except FileNotFoundError:
        logger.warning("mainconfig.json not found, using default configuration")
        return {
            "max_concurrent_downloads": 5,
            "scan_interval": 5,  # seconds
            "download_dir": "./downloads",
            "log_dir": "./logs"
        }
    except json.JSONDecodeError:
        logger.error("Error parsing mainconfig.json, using default configuration")
        return {
            "max_concurrent_downloads": 5,
            "scan_interval": 5,  # seconds
            "download_dir": "./downloads",
            "log_dir": "./logs"
        }


def daemonize() -> None:
    """
    Daemonize the current process by forking and detaching from the parent.
    """
    # First fork
    try:
        pid = os.fork()
        if pid > 0:
            # Exit the parent process
            sys.exit(0)
    except OSError as e:
        logger.error(f"First fork failed: {e}")
        sys.exit(1)
    
    # Decouple from parent environment
    os.setsid()
    os.umask(0)
    
    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            # Exit from the second parent
            sys.exit(0)
    except OSError as e:
        logger.error(f"Second fork failed: {e}")
        sys.exit(1)
    
    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    
    # Use absolute paths for output files
    base_dir = os.path.dirname(os.path.abspath(__file__))
    stdout_file = os.path.join(base_dir, 'logs', 'bg_downloader.out')
    stderr_file = os.path.join(base_dir, 'logs', 'bg_downloader.err')
    pid_file = os.path.join(base_dir, 'bg_downloader.pid')
    
    with open('/dev/null', 'r') as stdin, \
         open(stdout_file, 'a+') as stdout, \
         open(stderr_file, 'a+') as stderr:
        os.dup2(stdin.fileno(), sys.stdin.fileno())
        os.dup2(stdout.fileno(), sys.stdout.fileno())
        os.dup2(stderr.fileno(), sys.stderr.fileno())
    
    # Write PID file
    with open(pid_file, 'w') as f:
        f.write(str(os.getpid()))
    
    logger.info(f"Daemon started with PID {os.getpid()}")


def scan_for_pending_downloads(space: Space) -> List[Dict[str, Any]]:
    """
    Scan the database for pending downloads using a simple direct SQL query.
    
    Args:
        space (Space): Space component instance (used just for the connection)
        
    Returns:
        List[Dict[str, Any]]: List of pending download jobs
    """
    try:
        # Debug log when checking database
        if DEBUG_MODE:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.debug(f"[DEBUG] {current_time} - Checking database for pending downloads...")
        
        # Get a direct database connection (don't use Space component)
        db_connection = None
        try:
            # Create a new direct database connection every time
            if DEBUG_MODE:
                logger.debug("[DEBUG] Creating fresh database connection")
            
            with open('db_config.json', 'r') as config_file:
                config = json.load(config_file)
                if config["type"] == "mysql":
                    db_config = config["mysql"].copy()
                    # Remove unsupported parameters
                    if 'use_ssl' in db_config:
                        del db_config['use_ssl']
                else:
                    raise ValueError(f"Unsupported database type: {config['type']}")
            
            db_connection = mysql.connector.connect(**db_config)
            
            if DEBUG_MODE:
                logger.debug("[DEBUG] Successfully created fresh database connection")
        except Exception as conn_err:
            logger.error(f"Error creating direct database connection: {conn_err}")
            return []
        
        # Use direct SQL to find pending jobs - super simple approach
        try:
            cursor = db_connection.cursor(dictionary=True)
            
            # Start with a simpler query - just check for pending jobs
            # Always include a log of current jobs
            cursor.execute("SELECT id, space_id, status FROM space_download_scheduler")
            all_jobs = cursor.fetchall()
            
            if DEBUG_MODE and all_jobs:
                logger.debug(f"[DEBUG] All jobs in database: {len(all_jobs)}")
                for job in all_jobs:
                    logger.debug(f"[DEBUG]   Job #{job['id']}: space_id={job['space_id']}, status='{job['status']}'")
            
            # More specific query to handle various states
            query = """
            UPDATE space_download_scheduler 
            SET status = 'pending', process_id = NULL 
            WHERE status = 'downloading' OR 
                  (status = 'in_progress' AND process_id IS NULL) OR
                  (status NOT IN ('completed', 'failed', 'in_progress', 'downloading', 'pending'))
            """
            
            if DEBUG_MODE:
                logger.debug(f"[DEBUG] Resetting all non-completed jobs to pending: {query}")
            
            cursor.execute(query)
            db_connection.commit()
            reset_count = cursor.rowcount
            
            if reset_count > 0:
                logger.info(f"Reset {reset_count} jobs to pending status")
            
            # De-duplicate pending jobs for the same space before returning results
            # First mark duplicates appropriately
            dedup_query = """
            UPDATE space_download_scheduler a
            JOIN (
                SELECT space_id, MIN(id) as min_id 
                FROM space_download_scheduler 
                WHERE status = 'pending' 
                GROUP BY space_id
                HAVING COUNT(*) > 1
            ) b ON a.space_id = b.space_id AND a.id != b.min_id
            SET a.status = 'in_progress', a.process_id = NULL, a.updated_at = NOW()
            WHERE a.status = 'pending'
            """
            
            if DEBUG_MODE:
                logger.debug(f"[DEBUG] De-duplicating pending jobs: {dedup_query}")
                
            cursor.execute(dedup_query)
            db_connection.commit()
            dedup_count = cursor.rowcount
            
            if dedup_count > 0:
                logger.info(f"De-duplicated {dedup_count} pending jobs for the same spaces")
            
            # Now fetch all pending jobs and in_progress jobs with null process_id
            query = """
            SELECT * FROM space_download_scheduler 
            WHERE status = 'pending' OR (status = 'in_progress' AND process_id IS NULL) 
            ORDER BY id ASC   -- Oldest first to prioritize earlier requests
            """
            
            if DEBUG_MODE:
                logger.debug(f"[DEBUG] Fetching pending jobs: {query}")
            
            cursor.execute(query)
            pending_jobs = cursor.fetchall()
            
            job_count = len(pending_jobs)
            if job_count > 0:
                logger.info(f"Found {job_count} pending download jobs")
                
                if DEBUG_MODE:
                    job_ids = [job['id'] for job in pending_jobs]
                    logger.debug(f"[DEBUG] Pending job IDs: {job_ids}")
            else:
                logger.info("No pending download jobs found")
            
            cursor.close()
            db_connection.close()
            
            return pending_jobs
            
        except Exception as query_err:
            logger.error(f"Error executing pending jobs query: {query_err}")
            if db_connection:
                db_connection.close()
            return []
            
    except Exception as e:
        logger.error(f"Error scanning for pending downloads: {e}")
        if DEBUG_MODE:
            logger.debug(f"[DEBUG] Exception details: {str(e)}")
        return []


def claim_download_job(space: Space, job_id: int) -> bool:
    """
    Claim a download job by updating its status and process_id using direct SQL.
    
    Args:
        space (Space): Space component instance (not used)
        job_id (int): ID of the job to claim
        
    Returns:
        bool: True if claimed successfully, False otherwise
    """
    try:
        # Create a new direct connection
        db_connection = None
        try:
            with open('db_config.json', 'r') as config_file:
                config = json.load(config_file)
                if config["type"] == "mysql":
                    db_config = config["mysql"].copy()
                    # Remove unsupported parameters
                    if 'use_ssl' in db_config:
                        del db_config['use_ssl']
                else:
                    raise ValueError(f"Unsupported database type: {config['type']}")
            
            db_connection = mysql.connector.connect(**db_config)
        except Exception as conn_err:
            logger.error(f"Error creating direct database connection: {conn_err}")
            return False
        
        # Update the job with direct SQL
        cursor = db_connection.cursor()
        
        # First check that the job is still pending
        cursor.execute("SELECT status FROM space_download_scheduler WHERE id = %s", (job_id,))
        result = cursor.fetchone()
        
        if not result:
            logger.warning(f"Job {job_id} not found in database")
            cursor.close()
            db_connection.close()
            return False
            
        current_status = result[0]
        
        if current_status != 'pending':
            logger.warning(f"Cannot claim job {job_id} because it has status '{current_status}', not 'pending'")
            cursor.close()
            db_connection.close()
            return False
        
        # Simple update query - make more robust
        update_query = """
        UPDATE space_download_scheduler
        SET status = 'in_progress', process_id = %s, updated_at = NOW()
        WHERE id = %s AND (status = 'pending' OR (status = 'in_progress' AND process_id IS NULL))
        """
        
        process_id = os.getpid()
        cursor.execute(update_query, (process_id, job_id))
        db_connection.commit()
        
        # Check if the update was successful
        rows_affected = cursor.rowcount
        cursor.close()
        db_connection.close()
        
        if rows_affected > 0:
            logger.info(f"Successfully claimed job {job_id} with process ID {process_id}")
            return True
        else:
            logger.warning(f"Failed to claim job {job_id} - it may already be claimed by another process")
            return False
            
    except Exception as e:
        logger.error(f"Error claiming download job {job_id}: {e}")
        return False


def trim_leading_silence(audio_file_path: str, silence_threshold: float = 0.01, max_trim_seconds: int = 300) -> bool:
    """
    Trim leading silence from an audio file using ffmpeg.
    
    Args:
        audio_file_path (str): Path to the audio file
        silence_threshold (float): Silence detection threshold (0.01 = 1% volume)
        max_trim_seconds (int): Maximum seconds to trim from start (safety limit)
        
    Returns:
        bool: True if file was trimmed, False if no trimming was needed
    """
    try:
        # Check if ffmpeg is available
        if not shutil.which('ffmpeg'):
            print("ffmpeg not found, skipping silence trimming")
            return False
        
        # First, detect silence at the beginning
        print(f"Analyzing audio for leading silence: {audio_file_path}")
        
        # Use ffmpeg silencedetect to find the end of initial silence
        detect_cmd = [
            'ffmpeg', '-i', audio_file_path,
            '-af', f'silencedetect=noise={silence_threshold}:d=1',
            '-f', 'null', '-'
        ]
        
        result = subprocess.run(detect_cmd, capture_output=True, text=True, stderr=subprocess.STDOUT)
        output = result.stdout + result.stderr
        
        # Parse the output to find when the first non-silence starts
        silence_end = None
        for line in output.split('\n'):
            if 'silence_end:' in line and silence_end is None:
                try:
                    # Extract the time when silence ends
                    parts = line.split('silence_end:')
                    if len(parts) > 1:
                        time_str = parts[1].split('|')[0].strip()
                        silence_end = float(time_str)
                        break
                except (ValueError, IndexError):
                    continue
        
        # If no silence detected or silence is too short, don't trim
        if silence_end is None or silence_end < 2.0:  # Less than 2 seconds of leading silence
            print(f"No significant leading silence detected (silence_end: {silence_end})")
            return False
        
        # Apply safety limit - don't trim more than max_trim_seconds
        if silence_end > max_trim_seconds:
            print(f"Leading silence ({silence_end}s) exceeds safety limit ({max_trim_seconds}s), trimming to limit")
            silence_end = max_trim_seconds
        
        print(f"Detected {silence_end:.2f} seconds of leading silence, trimming...")
        
        # Create output filename
        path_obj = Path(audio_file_path)
        temp_output = path_obj.parent / f"{path_obj.stem}_trimmed{path_obj.suffix}"
        
        # Trim the audio file
        trim_cmd = [
            'ffmpeg', '-i', audio_file_path,
            '-ss', str(silence_end),  # Start from silence_end seconds
            '-c', 'copy',  # Copy without re-encoding for speed
            str(temp_output), '-y'  # Overwrite if exists
        ]
        
        result = subprocess.run(trim_cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            # Replace original file with trimmed version
            shutil.move(str(temp_output), audio_file_path)
            print(f"Successfully trimmed {silence_end:.2f} seconds of leading silence")
            return True
        else:
            print(f"ffmpeg trim failed: {result.stderr}")
            # Clean up temp file if it exists
            if temp_output.exists():
                temp_output.unlink()
            return False
            
    except Exception as e:
        print(f"Error in trim_leading_silence: {e}")
        return False


def fork_download_process(job_id: int, space_id: str, file_type: str = 'mp3') -> Optional[int]:
    """
    Fork a new process to handle the download.
    
    Args:
        job_id (int): Download job ID
        space_id (str): Space ID to download
        file_type (str): Output file type (mp3, wav, m4a)
        
    Returns:
        Optional[int]: Child process ID if successful, None otherwise
    """
    # Validate file_type to ensure it's a supported format
    if not isinstance(file_type, str):
        logger.warning(f"Invalid file_type {type(file_type)} for job {job_id}, defaulting to mp3")
        file_type = 'mp3'
    # Normalize to lowercase
    file_type = file_type.lower()
    # Ensure it's one of the supported formats
    if file_type not in ['mp3', 'm4a', 'wav']:
        logger.warning(f"Unsupported file_type '{file_type}' for job {job_id}, defaulting to mp3")
        file_type = 'mp3'
    try:
        # Get absolute paths for logs and downloads
        base_dir = os.path.dirname(os.path.abspath(__file__))
        log_dir = Path(os.path.join(base_dir, config.get("log_dir", "logs")))
        download_dir = Path(os.path.join(base_dir, config.get("download_dir", "downloads")))
        
        # Create directories if they don't exist
        log_dir.mkdir(exist_ok=True)
        download_dir.mkdir(exist_ok=True)
        
        # Log file named just by space_id for cleaner organization
        log_file = log_dir / f"{space_id}.log"
        
        # Log the start of processing this job
        with open(log_file, 'a') as f:
            f.write(f"\n\n{'='*80}\n")
            f.write(f"Starting job processing at: {datetime.datetime.now()}\n")
            f.write(f"Job ID: {job_id}, Space ID: {space_id}, File Type: {file_type}\n")
            f.write(f"{'='*80}\n\n")
            f.write("Checking if file already exists...\n")
        
        # First check if the file already exists in the downloads directory
        expected_file = download_dir / f"{space_id}.{file_type}"
        found_valid_file = False
        file_size = 0
        file_duration = 0
        
        # First check with exact name match
        if expected_file.exists():
            file_size = os.path.getsize(expected_file)
            with open(log_file, 'a') as f:
                f.write(f"Found exact file match: {expected_file} (size: {file_size} bytes)\n")
                
            # Check if file appears to be a complete download by verifying the file integrity
            try:
                # For audio files, we can use ffprobe to check if the file is complete and valid
                import subprocess
                
                # Check if the file is a valid audio file using ffprobe
                ffprobe_cmd = [
                    'ffprobe', 
                    '-v', 'error', 
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    str(expected_file)
                ]
                
                with open(log_file, 'a') as f:
                    f.write(f"Validating file with ffprobe: {' '.join(ffprobe_cmd)}\n")
                
                result = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
                
                # If we can read the duration and it's > 0, the file is likely valid
                if result.returncode == 0 and result.stdout.strip():
                    try:
                        duration = float(result.stdout.strip())
                        if duration > 0:
                            found_valid_file = True
                            file_duration = duration
                            logger.info(f"File for space {space_id} verified as valid with duration: {duration} seconds")
                            with open(log_file, 'a') as f:
                                f.write(f"File validation successful: Duration = {duration} seconds\n")
                        else:
                            logger.warning(f"File for space {space_id} has invalid duration: {duration}")
                            with open(log_file, 'a') as f:
                                f.write(f"File validation failed: Invalid duration = {duration} seconds\n")
                    except ValueError:
                        logger.warning(f"Could not parse duration from ffprobe output: {result.stdout.strip()}")
                        with open(log_file, 'a') as f:
                            f.write(f"File validation failed: Could not parse duration from ffprobe output: {result.stdout.strip()}\n")
                else:
                    logger.warning(f"ffprobe validation failed for file {expected_file}: {result.stderr}")
                    with open(log_file, 'a') as f:
                        f.write(f"File validation failed: ffprobe error: {result.stderr}\n")
            except Exception as validate_err:
                logger.warning(f"Error validating file {expected_file}: {validate_err}")
                with open(log_file, 'a') as f:
                    f.write(f"Error validating file: {validate_err}\n")
                
                # If ffprobe is not available, fall back to checking if the file size is reasonable
                if file_size > 1024 * 1024:  # > 1MB is probably a valid audio file
                    logger.info(f"Could not validate file format but size appears reasonable ({file_size} bytes)")
                    with open(log_file, 'a') as f:
                        f.write(f"File seems valid based on size: {file_size} bytes (> 1MB)\n")
                    found_valid_file = True
        else:
            with open(log_file, 'a') as f:
                f.write(f"No exact file match found at: {expected_file}\n")
                f.write("Checking for any file with space ID in name...\n")
                
            # If exact match not found, look for any file containing the space_id
            try:
                possible_files = []
                for f in os.listdir(download_dir):
                    if space_id in f and os.path.isfile(os.path.join(download_dir, f)):
                        possible_files.append(os.path.join(download_dir, f))
                
                if possible_files:
                    matching_file = possible_files[0]
                    file_size = os.path.getsize(matching_file)
                    
                    with open(log_file, 'a') as f:
                        f.write(f"Found matching file: {matching_file} (size: {file_size} bytes)\n")
                    
                    # Validate the file
                    try:
                        import subprocess
                        
                        # Check with ffprobe
                        ffprobe_cmd = [
                            'ffprobe', 
                            '-v', 'error', 
                            '-show_entries', 'format=duration',
                            '-of', 'default=noprint_wrappers=1:nokey=1',
                            str(matching_file)
                        ]
                        
                        with open(log_file, 'a') as f:
                            f.write(f"Validating file with ffprobe: {' '.join(ffprobe_cmd)}\n")
                        
                        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
                        
                        if result.returncode == 0 and result.stdout.strip():
                            try:
                                duration = float(result.stdout.strip())
                                if duration > 0:
                                    found_valid_file = True
                                    file_duration = duration
                                    logger.info(f"File for space {space_id} verified with duration: {duration} seconds")
                                    with open(log_file, 'a') as f:
                                        f.write(f"File validation successful: Duration = {duration} seconds\n")
                                    
                                    # If valid, rename to standard format
                                    matching_filename = os.path.basename(matching_file)
                                    if matching_filename != f"{space_id}.{file_type}":
                                        try:
                                            with open(log_file, 'a') as f:
                                                f.write(f"Renaming file to standard format: {matching_file} -> {expected_file}\n")
                                                
                                            # If the standard file already exists, remove it first
                                            if os.path.exists(expected_file):
                                                os.remove(expected_file)
                                            os.rename(matching_file, expected_file)
                                            logger.info(f"Renamed {matching_file} to {expected_file}")
                                            matching_file = expected_file
                                        except Exception as rename_err:
                                            logger.error(f"Error renaming file: {rename_err}")
                                            with open(log_file, 'a') as f:
                                                f.write(f"Error renaming file: {rename_err}\n")
                                else:
                                    with open(log_file, 'a') as f:
                                        f.write(f"File validation failed: Invalid duration = {duration} seconds\n")
                            except ValueError:
                                with open(log_file, 'a') as f:
                                    f.write(f"File validation failed: Could not parse duration\n")
                        else:
                            with open(log_file, 'a') as f:
                                f.write(f"File validation failed: ffprobe error\n")
                    except Exception as validate_err:
                        with open(log_file, 'a') as f:
                            f.write(f"Error validating file: {validate_err}\n")
                        
                        # Fall back to size check
                        if file_size > 1024 * 1024:  # > 1MB
                            found_valid_file = True
                            with open(log_file, 'a') as f:
                                f.write(f"File seems valid based on size: {file_size} bytes (> 1MB)\n")
                else:
                    with open(log_file, 'a') as f:
                        f.write("No matching files found\n")
            except Exception as file_err:
                logger.error(f"Error checking for existing files: {file_err}")
                with open(log_file, 'a') as f:
                    f.write(f"Error checking for existing files: {file_err}\n")
        
        # If we found a valid file, mark job as completed without downloading
        if found_valid_file:
            with open(log_file, 'a') as f:
                f.write(f"Valid file found for space {space_id}. Marking job as completed without downloading.\n")
                f.write(f"File size: {file_size} bytes, Duration: {file_duration} seconds\n")
                f.write("Updating database...\n")
            
            # Create connection to database
            try:
                with open('db_config.json', 'r') as config_file:
                    db_config = json.load(config_file)
                    if db_config["type"] == "mysql":
                        mysql_config = db_config["mysql"].copy()
                        if 'use_ssl' in mysql_config:
                            del mysql_config['use_ssl']
                            
                        conn = mysql.connector.connect(**mysql_config)
                        cursor = conn.cursor()
                        
                        # 1. First check if there's already a space record
                        cursor.execute("SELECT COUNT(*) FROM spaces WHERE space_id = %s", (space_id,))
                        space_exists = cursor.fetchone()[0] > 0
                        
                        # 2. Update or insert space record
                        if space_exists:
                            with open(log_file, 'a') as f:
                                f.write(f"Updating existing space record for {space_id}\n")
                            
                            # Update existing space record - don't update download_cnt 
                            update_space_query = """
                            UPDATE spaces
                            SET status = 'completed', format = %s, 
                                updated_at = NOW(), downloaded_at = NOW()
                            WHERE space_id = %s
                            """
                            cursor.execute(update_space_query, (str(file_size), space_id))
                        else:
                            with open(log_file, 'a') as f:
                                f.write(f"Creating new space record for {space_id}\n")
                            
                            # Insert new space record - initialize download_cnt to 0
                            insert_space_query = """
                            INSERT INTO spaces
                            (space_id, space_url, filename, status, download_cnt, format, created_at, updated_at, downloaded_at)
                            VALUES (%s, %s, %s, 'completed', 0, %s, NOW(), NOW(), NOW())
                            ON DUPLICATE KEY UPDATE
                            status = 'completed',
                            filename = VALUES(filename),
                            format = VALUES(format),
                            updated_at = NOW(),
                            downloaded_at = NOW()
                            """
                            space_url = f"https://x.com/i/spaces/{space_id}"
                            filename = f"{space_id}.{file_type}"
                            cursor.execute(insert_space_query, (space_id, space_url, filename, str(file_size)))
                        
                        # Calculate download duration and track compute cost
                        download_end_time = time.time()
                        download_duration = download_end_time - download_start_time
                        
                        with open(log_file, 'a') as f:
                            f.write(f"Download duration: {download_duration:.2f} seconds\n")
                        
                        # Get user_id and cookie_id from the job before closing connection
                        cursor.execute("SELECT user_id, cookie_id FROM space_download_scheduler WHERE id = %s", (job_id,))
                        job_result = cursor.fetchone()
                        user_id = job_result[0] if job_result else None
                        cookie_id = job_result[1] if job_result else None
                        
                        # Close current connection before CostLogger
                        cursor.close()
                        conn.close()
                        
                        # Track compute cost with fresh connection
                        try:
                            if user_id:
                                cost_logger = CostLogger()
                                success, message, cost = cost_logger.track_compute_operation(
                                    space_id=space_id,
                                    action='mp3',
                                    compute_time_seconds=download_duration,
                                    user_id=user_id,
                                    cookie_id=cookie_id
                                )
                                
                                with open(log_file, 'a') as f:
                                    f.write(f"Cost tracking: success={success}, message={message}, cost={cost}\n")
                                
                                if not success:
                                    logger.warning(f"Cost tracking failed for job {job_id}: {message}")
                            else:
                                with open(log_file, 'a') as f:
                                    f.write(f"Skipping cost tracking - no user_id for job {job_id}\n")
                                    
                        except Exception as cost_err:
                            logger.error(f"Error tracking compute cost for job {job_id}: {cost_err}")
                            with open(log_file, 'a') as f:
                                f.write(f"Error tracking compute cost: {cost_err}\n")
                        
                        # Re-open connection for remaining operations
                        try:
                            conn = mysql.connector.connect(**mysql_config)
                            cursor = conn.cursor()
                        except Exception as reconnect_err:
                            logger.error(f"Error reconnecting to database: {reconnect_err}")
                            with open(log_file, 'a') as f:
                                f.write(f"Error reconnecting to database: {reconnect_err}\n")
                            return None
                        
                        # Send email notification to user
                        if user_id:
                            try:
                                # Get user email
                                cursor.execute("SELECT email FROM users WHERE id = %s", (user_id,))
                                user_result = cursor.fetchone()
                                
                                if user_result and user_result[0]:
                                    user_email = user_result[0]
                                    
                                    # Get space title if available
                                    cursor.execute("SELECT title FROM spaces WHERE space_id = %s", (space_id,))
                                    space_result = cursor.fetchone()
                                    space_title = space_result[0] if space_result and space_result[0] else f"Space {space_id}"
                                    
                                    # Send email notification
                                    email = Email()
                                    subject = f"Your space download is ready: {space_title}"
                                    body = f"""
                                    <h2>Your space download is complete!</h2>
                                    <p>Hello,</p>
                                    <p>Your requested space has been successfully downloaded and is ready to access.</p>
                                    <ul>
                                        <li><strong>Space:</strong> {space_title}</li>
                                        <li><strong>Space ID:</strong> {space_id}</li>
                                        <li><strong>Format:</strong> {file_type.upper()}</li>
                                        <li><strong>File size:</strong> {file_size / (1024*1024):.1f} MB</li>
                                        <li><strong>Processing time:</strong> {download_duration:.1f} seconds</li>
                                    </ul>
                                    <p>You can now access your space at: <a href="https://xspacedownload.com/spaces/{space_id}">View Space</a></p>
                                    <p>Thank you for using XSpace Downloader!</p>
                                    """
                                    
                                    email.send(
                                        to=user_email,
                                        subject=subject,
                                        body=body,
                                        content_type='text/html'
                                    )
                                    
                                    with open(log_file, 'a') as f:
                                        f.write(f"Email notification sent to {user_email}\n")
                                        
                            except Exception as email_err:
                                logger.error(f"Error sending email notification for job {job_id}: {email_err}")
                                with open(log_file, 'a') as f:
                                    f.write(f"Error sending email notification: {email_err}\n")
                        
                        # 3. Update job status to completed
                        with open(log_file, 'a') as f:
                            f.write(f"Setting job {job_id} status to completed\n")
                            
                        update_job_query = """
                        UPDATE space_download_scheduler 
                        SET status = 'completed', progress_in_size = %s, progress_in_percent = 100,
                            end_time = NOW(), updated_at = NOW()
                        WHERE id = %s
                        """
                        cursor.execute(update_job_query, (file_size, job_id))
                        
                        conn.commit()
                        cursor.close()
                        conn.close()
                        
                        # Trigger cache invalidation since we updated/created a space
                        try:
                            trigger_file = Path('./temp/cache_invalidate.trigger')
                            trigger_file.parent.mkdir(exist_ok=True)
                            trigger_file.touch()
                            with open(log_file, 'a') as f:
                                f.write(f"Triggered cache invalidation after space update\n")
                        except Exception as cache_err:
                            with open(log_file, 'a') as f:
                                f.write(f"Warning: Could not trigger cache invalidation: {cache_err}\n")
                        
                        with open(log_file, 'a') as f:
                            f.write(f"Database updated successfully. Job marked as completed.\n")
                            f.write(f"{'='*80}\n")
                        
                        logger.info(f"Job {job_id} for space {space_id} marked as completed (file already exists)")
                        return None  # No need to start a download process
                        
            except Exception as db_err:
                logger.error(f"Error updating database for existing file: {db_err}")
                with open(log_file, 'a') as f:
                    f.write(f"Error updating database: {db_err}\n")
                    f.write("Will attempt to download the file again to ensure proper completion\n")
        
        # If we get here, we either didn't find a valid file or had database errors
        # Log that we're proceeding with download
        with open(log_file, 'a') as f:
            f.write(f"No valid file found or database errors occurred. Proceeding with download...\n")
            
        # If we found an invalid file, delete it
        if expected_file.exists() and not found_valid_file:
            with open(log_file, 'a') as f:
                f.write(f"Removing invalid file {expected_file} before downloading\n")
            try:
                os.remove(expected_file)
                logger.info(f"Removed invalid file {expected_file}")
            except Exception as del_err:
                logger.error(f"Error removing invalid file: {del_err}")
                with open(log_file, 'a') as f:
                    f.write(f"Error removing invalid file: {del_err}\n")
        
        # Fork a child process
        pid = os.fork()
        
        if pid == 0:
            # This is the child process
            # Redirect stdout and stderr to the log file (append mode to preserve history)
            with open(log_file, 'a') as f:
                # Add a separator for this new download attempt
                f.write("\n\n" + "="*80 + "\n")
                f.write(f"Download attempt started at: {datetime.datetime.now()}\n")
                f.write(f"Job ID: {job_id}, Space ID: {space_id}\n")
                f.write("="*80 + "\n\n")
                f.flush()
                
                # Redirect stdout and stderr to the log file
                os.dup2(f.fileno(), sys.stdout.fileno())
                os.dup2(f.fileno(), sys.stderr.fileno())
                
            print(f"Download process started for space {space_id} (job {job_id})")
            print(f"Process ID: {os.getpid()}")
            print(f"Download directory: {download_dir}")
            
            # Import necessary modules in the child process
            import subprocess
            from components.Space import Space
            import mysql.connector
            
            try:
                # Create a new database connection for this process
                space = Space()
                
                # Get the full space details - handle missing spaces more gracefully
                space_details = space.get_space(space_id)
                
                # If space not found in database, create a minimal record with the space_id
                if not space_details:
                    print(f"Warning: Space {space_id} not found in database, creating minimal space record")
                    # Create a minimal space record with default URL
                    space_url = f"https://x.com/i/spaces/{space_id}"
                    space_details = {
                        'space_id': space_id,
                        'space_url': space_url,
                        'title': f"Space {space_id}",
                        'status': 'pending',
                        'download_cnt': 0
                    }
                    
                    # Try to add this minimal record to the database for future reference
                    try:
                        # Use direct database connection for more reliability
                        with open('db_config.json', 'r') as config_file:
                            db_config = json.load(config_file)
                            if db_config["type"] == "mysql":
                                mysql_config = db_config["mysql"].copy()
                                if 'use_ssl' in mysql_config:
                                    del mysql_config['use_ssl']
                                
                                conn = mysql.connector.connect(**mysql_config)
                                cursor = conn.cursor()
                                
                                # Check if space exists first
                                cursor.execute("SELECT COUNT(*) FROM spaces WHERE space_id = %s", (space_id,))
                                exists = cursor.fetchone()[0] > 0
                                
                                if not exists:
                                    # Try to insert the minimal record
                                    insert_query = """
                                    INSERT INTO spaces 
                                    (space_id, space_url, filename, status, download_cnt, created_at, updated_at)
                                    VALUES (%s, %s, %s, 'pending', 0, NOW(), NOW())
                                    ON DUPLICATE KEY UPDATE
                                    status = VALUES(status),
                                    filename = VALUES(filename),
                                    updated_at = NOW()
                                    """
                                    filename = f"{space_id}.{file_type}"
                                    cursor.execute(insert_query, (space_id, space_url, filename))
                                    conn.commit()
                                    
                                    # Trigger cache invalidation since we created a new space
                                    try:
                                        trigger_file = Path('./temp/cache_invalidate.trigger')
                                        trigger_file.parent.mkdir(exist_ok=True)
                                        trigger_file.touch()
                                        print(f"Triggered cache invalidation after creating space {space_id}")
                                    except Exception as cache_err:
                                        print(f"Warning: Could not trigger cache invalidation: {cache_err}")
                                    
                                    print(f"Added minimal space record to database for {space_id}")
                                
                                cursor.close()
                                conn.close()
                    except Exception as db_err:
                        print(f"Warning: Could not create space record in database: {db_err}")
                else:
                    # Space found in database, use its URL
                    space_url = space_details.get('space_url')
                
                # If we still don't have a URL, construct a default one
                if not space_url:
                    print(f"Warning: No URL found for space {space_id}, using default URL format")
                    space_url = f"https://x.com/i/spaces/{space_id}"
                
                print(f"Space URL: {space_url}")
                
                # Create a standardized filename using space_id
                standard_filename = f"{space_id}.{file_type}"
                
                # Get or create filename from space details as backup filename
                backup_filename = space_details.get('filename')
                if not backup_filename:
                    backup_filename = standard_filename
                elif '.' not in backup_filename:
                    backup_filename = f"{backup_filename}.{file_type}"
                
                # Full path to download file - always use space_id for naming
                output_file = download_dir / standard_filename
                print(f"Output file: {output_file}")
                
                # Update download progress - make sure we're updating the database with the child process ID
                # Set the process_id to current process ID to ensure database tracking works
                process_id = os.getpid()
                print(f"Child process ID: {process_id} for job {job_id}")
                
                # Use direct SQL query for more reliable updates
                try:
                    # Create a direct database connection
                    with open('db_config.json', 'r') as config_file:
                        db_config = json.load(config_file)
                        if db_config["type"] == "mysql":
                            mysql_config = db_config["mysql"].copy()
                            if 'use_ssl' in mysql_config:
                                del mysql_config['use_ssl']
                                
                            conn = mysql.connector.connect(**mysql_config)
                            cursor = conn.cursor()
                            
                            # Update the job status and process_id directly
                            # Set initial progress to ensure UI immediately shows activity
                            update_query = """
                            UPDATE space_download_scheduler 
                            SET status = 'in_progress', process_id = %s, 
                                progress_in_percent = 1, progress_in_size = 1024,
                                updated_at = NOW()
                            WHERE id = %s
                            """
                            cursor.execute(update_query, (process_id, job_id))
                            
                            # Also update the space record to show downloading with initial progress
                            # Keep the format field as the file format, not the file size
                            update_space_query = """
                            UPDATE spaces
                            SET status = 'downloading', download_cnt = 0
                            WHERE space_id = %s
                            """
                            cursor.execute(update_space_query, (space_id,))
                            
                            conn.commit()
                            cursor.close()
                            conn.close()
                            
                            print(f"Updated job {job_id} status to 'in_progress' with process ID {process_id} and initial 1% progress")
                            
                except Exception as update_err:
                    print(f"Error updating job status in database: {update_err}")
                    # Fall back to using the Space component methods
                    space.update_download_progress_by_space(space_id, 0, 1, 'downloading')
                    space.update_download_job(job_id, status='in_progress', process_id=process_id)
                
                print(f"[DEBUG DOWNLOAD] Starting download with yt-dlp for job {job_id}, space {space_id}")
                print(f"[DEBUG DOWNLOAD] Output file will be: {output_file}")
                print(f"[DEBUG DOWNLOAD] Part file will be: {output_file}.part")
                print(f"[DEBUG DOWNLOAD] Space URL: {space_url}")
                
                # Check if yt-dlp is installed, preferring venv version
                # First try to find yt-dlp in the same directory as the Python executable
                print(f"[DEBUG] Python executable: {sys.executable}")
                python_dir = os.path.dirname(sys.executable)
                venv_yt_dlp = os.path.join(python_dir, "yt-dlp")
                print(f"[DEBUG] Looking for venv yt-dlp at: {venv_yt_dlp}")
                print(f"[DEBUG] Venv yt-dlp exists: {os.path.exists(venv_yt_dlp)}")
                
                if os.path.exists(venv_yt_dlp):
                    yt_dlp_path = venv_yt_dlp
                else:
                    yt_dlp_path = shutil.which('yt-dlp')
                if not yt_dlp_path:
                    print("yt-dlp not found in PATH. Attempting to install...")
                    subprocess.call([sys.executable, "-m", "pip", "install", "yt-dlp"])
                    yt_dlp_path = shutil.which('yt-dlp')
                    if yt_dlp_path:
                        print(f"Installed yt-dlp at: {yt_dlp_path}")
                    else:
                        print("Failed to install yt-dlp")
                        raise Exception("yt-dlp not found and could not be installed")
                else:
                    print(f"Found yt-dlp at: {yt_dlp_path}")
                
                # Debug: Check yt-dlp version being used
                try:
                    version_result = subprocess.run([yt_dlp_path, '--version'], 
                                                  capture_output=True, text=True, timeout=10)
                    if version_result.returncode == 0:
                        yt_dlp_version = version_result.stdout.strip()
                        print(f"[DEBUG] Using yt-dlp version: {yt_dlp_version}")
                    else:
                        print(f"[DEBUG] Failed to get yt-dlp version: {version_result.stderr}")
                except Exception as e:
                    print(f"[DEBUG] Error checking yt-dlp version: {e}")
                
                # Create a temporary filename for download
                temp_output = str(output_file) + ".part"
                
                # Ensure the directory exists
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                
                # Create a file watcher function to run in a separate thread
                def file_watcher_thread():
                    """
                    Thread that watches the part file and updates the database directly.
                    This ensures progress is always reported regardless of yt-dlp output.
                    """
                    import time
                    import os
                    import json
                    from mysql.connector import connect
                    
                    print(f"[DEBUG FILE_WATCHER] Starting file watcher thread for job {job_id}, space {space_id}")
                    print(f"[DEBUG FILE_WATCHER] Watching for part file: {str(output_file)}.part")
                    print(f"[DEBUG FILE_WATCHER] Final file will be: {str(output_file)}")
                    
                    last_size = 0
                    update_counter = 0
                    consecutive_no_change = 0
                    
                    while True:
                        try:
                            update_counter += 1
                            
                            # Check for multiple possible part file formats
                            # yt-dlp may create .m4a.part, .mp4.part, .webm.part, etc.
                            output_base = str(output_file).rsplit('.', 1)[0]  # Remove .mp3 extension
                            possible_part_files = [
                                str(output_file) + ".part",           # 1lDxLnrWjwkGm.mp3.part
                                output_base + ".m4a.part",            # 1lDxLnrWjwkGm.m4a.part  
                                output_base + ".mp4.part",            # 1lDxLnrWjwkGm.mp4.part
                                output_base + ".webm.part",           # 1lDxLnrWjwkGm.webm.part
                                output_base + ".aac.part",            # 1lDxLnrWjwkGm.aac.part
                            ]
                            
                            part_file = None
                            final_file = str(output_file)
                            
                            # Find which part file actually exists
                            for possible_file in possible_part_files:
                                if os.path.exists(possible_file):
                                    part_file = possible_file
                                    break
                            
                            print(f"[DEBUG FILE_WATCHER] Loop {update_counter}: Checking files...")
                            print(f"[DEBUG FILE_WATCHER] Checked part files: {possible_part_files}")
                            print(f"[DEBUG FILE_WATCHER] Found part file: {part_file}")
                            print(f"[DEBUG FILE_WATCHER] Final file exists: {os.path.exists(final_file)}")
                            
                            # Check if the download has completed
                            if os.path.exists(final_file):
                                file_size = os.path.getsize(final_file)
                                print(f"[DEBUG FILE_WATCHER] DOWNLOAD COMPLETED! Final file size: {file_size} bytes")
                                
                                # Final update with 100% progress
                                try:
                                    with open('db_config.json', 'r') as config_file:
                                        db_config = json.load(config_file)
                                        if db_config["type"] == "mysql":
                                            mysql_config = db_config["mysql"].copy()
                                            if 'use_ssl' in mysql_config:
                                                del mysql_config['use_ssl']
                                            
                                            # Connect directly to MySQL
                                            conn = connect(**mysql_config)
                                            cursor = conn.cursor()
                                            
                                            # Get job details for cost tracking
                                            cursor.execute("""
                                                SELECT user_id, cookie_id, start_time, file_type
                                                FROM space_download_scheduler 
                                                WHERE id = %s
                                            """, (job_id,))
                                            job_details = cursor.fetchone()
                                            
                                            # Update job with final file size and 100% progress
                                            cursor.execute("""
                                                UPDATE space_download_scheduler 
                                                SET progress_in_size = %s, progress_in_percent = 100, 
                                                    status = 'completed', updated_at = NOW(), end_time = NOW()
                                                WHERE id = %s
                                            """, (int(file_size), job_id))
                                            
                                            # Update space record to completed status 
                                            # Don't update format field with file size
                                            cursor.execute("""
                                                UPDATE spaces 
                                                SET status = 'completed',
                                                    downloaded_at = NOW(), updated_at = NOW()
                                                WHERE space_id = %s
                                            """, (space_id,))
                                            
                                            # Track compute cost for MP3 download before closing connection
                                            if job_details:
                                                try:
                                                    from datetime import datetime
                                                    
                                                    user_id, cookie_id, start_time, file_type = job_details
                                                    end_time = datetime.now()
                                                    
                                                    if start_time:
                                                        # Calculate duration in seconds
                                                        if isinstance(start_time, str):
                                                            start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                                                        duration_seconds = (end_time - start_time).total_seconds()
                                                        
                                                        # Track compute cost directly via database
                                                        action = f"mp3_download" if file_type == 'mp3' else f"{file_type}_download"
                                                        
                                                        # Get compute cost per second from config (fallback to 0.001)
                                                        try:
                                                            cursor.execute("""
                                                                SELECT setting_value FROM app_settings 
                                                                WHERE setting_name = 'compute_cost_per_second'
                                                            """)
                                                            cost_result = cursor.fetchone()
                                                            cost_per_second = float(cost_result[0]) if cost_result else 0.001
                                                        except:
                                                            cost_per_second = 0.001  # Default fallback
                                                            
                                                        total_cost = max(1, round(duration_seconds * cost_per_second))
                                                        
                                                        # Get user balance if logged in user
                                                        if user_id and user_id != 0:
                                                            cursor.execute("SELECT credits FROM users WHERE id = %s", (user_id,))
                                                            balance_result = cursor.fetchone()
                                                            balance_before = float(balance_result[0]) if balance_result else 0.0
                                                            
                                                            # Check if user has sufficient credits
                                                            if balance_before >= total_cost:
                                                                # Deduct credits
                                                                balance_after = balance_before - total_cost
                                                                cursor.execute("""
                                                                    UPDATE users 
                                                                    SET credits = %s 
                                                                    WHERE id = %s
                                                                """, (balance_after, user_id))
                                                                
                                                                # Record compute transaction
                                                                cursor.execute("""
                                                                    INSERT INTO computes 
                                                                    (user_id, cookie_id, space_id, action, compute_time_seconds, 
                                                                     cost_per_second, total_cost, balance_before, balance_after)
                                                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                                                                """, (user_id, cookie_id, space_id, action, duration_seconds,
                                                                      cost_per_second, total_cost, balance_before, balance_after))
                                                                
                                                                print(f"COST TRACKING: {action} cost tracked - ${total_cost:.6f} for {duration_seconds:.2f}s (User {user_id}: ${balance_before:.2f} -> ${balance_after:.2f})")
                                                            else:
                                                                print(f"COST TRACKING: Insufficient credits for user {user_id} - required ${total_cost:.6f}, available ${balance_before:.2f}")
                                                        else:
                                                            print(f"COST TRACKING: {action} by visitor {cookie_id} - ${total_cost:.6f} for {duration_seconds:.2f}s (not charged)")
                                                    
                                                except Exception as cost_err:
                                                    print(f"Error tracking compute cost: {cost_err}")
                                                    # Don't fail the download if cost tracking fails
                                            
                                            conn.commit()
                                            cursor.close()
                                            conn.close()
                                            
                                            print(f"FILE WATCHER: Final update - job completed with size={file_size} bytes")
                                except Exception as db_err:
                                    print(f"Error in file watcher final update: {db_err}")
                                
                                # Exit the thread as the download is complete
                                break
                            
                            # Check the part file for progress updates
                            elif part_file and os.path.exists(part_file):
                                file_size = os.path.getsize(part_file)
                                print(f"[DEBUG FILE_WATCHER] Part file size: {file_size} bytes (was {last_size} bytes)")
                                
                                if file_size == last_size:
                                    consecutive_no_change += 1
                                    print(f"[DEBUG FILE_WATCHER] No size change for {consecutive_no_change} consecutive checks")
                                else:
                                    consecutive_no_change = 0
                                    print(f"[DEBUG FILE_WATCHER] Size increased by {file_size - last_size} bytes!")
                                
                                # Only update DB if size has changed or on every 10th check
                                if file_size != last_size or update_counter % 10 == 0:
                                    print(f"[DEBUG FILE_WATCHER] Triggering DB update (size_changed={file_size != last_size}, every_10th={update_counter % 10 == 0})")
                                    # More accurate progress estimation based on typical file sizes
                                    # Most space recordings are between 30-100MB, so scale accordingly
                                    if file_size > 60*1024*1024:  # > 60MB
                                        estimated_percent = 90 + min(9, int((file_size - 60*1024*1024) / (10*1024*1024)))
                                    elif file_size > 40*1024*1024:  # > 40MB
                                        estimated_percent = 75 + min(15, int((file_size - 40*1024*1024) / (1.33*1024*1024)))
                                    elif file_size > 20*1024*1024:  # > 20MB
                                        estimated_percent = 50 + min(25, int((file_size - 20*1024*1024) / (0.8*1024*1024)))
                                    elif file_size > 10*1024*1024:  # > 10MB
                                        estimated_percent = 25 + min(25, int((file_size - 10*1024*1024) / (0.4*1024*1024)))
                                    elif file_size > 5*1024*1024:   # > 5MB
                                        estimated_percent = 10 + min(15, int((file_size - 5*1024*1024) / (0.33*1024*1024)))
                                    elif file_size > 1*1024*1024:   # > 1MB
                                        estimated_percent = 1 + min(9, int((file_size - 1*1024*1024) / (0.44*1024*1024)))
                                    else:
                                        estimated_percent = 1  # At least show 1% if file exists
                                    
                                    # If size increased, log it
                                    if file_size > last_size:
                                        print(f"FILE WATCHER: Part file size increased to {file_size} bytes (+{file_size - last_size} bytes)")
                                    
                                    # Direct database update using a fresh connection
                                    try:
                                        print(f"[DEBUG FILE_WATCHER] Starting database update for job {job_id}")
                                        print(f"[DEBUG FILE_WATCHER] New size: {file_size}, Estimated percent: {estimated_percent}")
                                        
                                        with open('db_config.json', 'r') as config_file:
                                            db_config = json.load(config_file)
                                            if db_config["type"] == "mysql":
                                                mysql_config = db_config["mysql"].copy()
                                                if 'use_ssl' in mysql_config:
                                                    del mysql_config['use_ssl']
                                                
                                                print(f"[DEBUG FILE_WATCHER] Connecting to MySQL...")
                                                # Connect directly to MySQL
                                                conn = connect(**mysql_config)
                                                cursor = conn.cursor()
                                                print(f"[DEBUG FILE_WATCHER] Connected successfully")
                                                
                                                # First check if job exists
                                                check_query = "SELECT id, progress_in_size, progress_in_percent FROM space_download_scheduler WHERE id = %s"
                                                cursor.execute(check_query, (job_id,))
                                                job_result = cursor.fetchone()
                                                job_exists = job_result is not None
                                                
                                                if job_exists:
                                                    current_size, current_percent = job_result[1], job_result[2]
                                                    print(f"[DEBUG FILE_WATCHER] Job exists. Current DB values: size={current_size}, percent={current_percent}")
                                                else:
                                                    print(f"[DEBUG FILE_WATCHER] ERROR: Job {job_id} does not exist in database!")
                                                
                                                if job_exists:
                                                    # Update job with current file size and progress
                                                    update_query = """
                                                        UPDATE space_download_scheduler 
                                                        SET progress_in_size = %s, progress_in_percent = %s, 
                                                            status = 'in_progress', updated_at = NOW() 
                                                        WHERE id = %s
                                                    """
                                                    print(f"[DEBUG FILE_WATCHER] Executing update query with values: size={int(file_size)}, percent={int(estimated_percent)}, job_id={job_id}")
                                                    
                                                    cursor.execute(update_query, (int(file_size), int(estimated_percent), job_id))
                                                    rows_affected = cursor.rowcount
                                                    print(f"[DEBUG FILE_WATCHER] Update query affected {rows_affected} rows")
                                                    
                                                    # Commit the transaction
                                                    conn.commit()
                                                    print(f"[DEBUG FILE_WATCHER] Transaction committed")
                                                    
                                                    # Verify the update was successful
                                                    cursor.execute("SELECT progress_in_size, progress_in_percent FROM space_download_scheduler WHERE id = %s", (job_id,))
                                                    verify = cursor.fetchone()
                                                    if verify:
                                                        updated_size, updated_percent = verify[0], verify[1]
                                                        print(f"[DEBUG FILE_WATCHER] VERIFIED UPDATE: size={updated_size} bytes, percent={updated_percent}%")
                                                    else:
                                                        print(f"[DEBUG FILE_WATCHER] ERROR: Could not verify update!")
                                                    
                                                    # Check if space exists
                                                    cursor.execute("SELECT id FROM spaces WHERE space_id = %s", (space_id,))
                                                    space_exists = cursor.fetchone() is not None
                                                    print(f"[DEBUG FILE_WATCHER] Space {space_id} exists: {space_exists}")
                                                    
                                                    if space_exists:
                                                        # Update space record with progress and size
                                                        space_update_query = """
                                                            UPDATE spaces 
                                                            SET format = %s, status = 'downloading',
                                                                updated_at = NOW()
                                                            WHERE space_id = %s
                                                        """
                                                        print(f"[DEBUG FILE_WATCHER] Updating space table with format={str(int(file_size))}")
                                                        
                                                        cursor.execute(space_update_query, (str(int(file_size)), space_id))
                                                        space_rows_affected = cursor.rowcount
                                                        print(f"[DEBUG FILE_WATCHER] Space update affected {space_rows_affected} rows")
                                                        
                                                        # Verify the space update was successful
                                                        cursor.execute("SELECT format FROM spaces WHERE space_id = %s", (space_id,))
                                                        verify_space = cursor.fetchone()
                                                        if verify_space:
                                                            updated_format = verify_space[0]
                                                            print(f"FILE WATCHER: Verified space update - format is now {updated_format}")
                                                    else:
                                                        print(f"FILE WATCHER: Space {space_id} not found in database")
                                                else:
                                                    print(f"FILE WATCHER: Job {job_id} not found in database")
                                                
                                                conn.commit()
                                                cursor.close()
                                                conn.close()
                                                
                                                print(f"FILE WATCHER: Updated database with size={file_size}, percent={estimated_percent}%")
                                    except Exception as db_err:
                                        print(f"Error in file watcher thread DB update: {db_err}")
                                    
                                    # Save the current size for the next comparison
                                    last_size = file_size
                            else:
                                print("FILE WATCHER: No part file found yet")
                                
                        except Exception as e:
                            print(f"Error in file watcher thread: {e}")
                            
                        # Sleep for 2 seconds before checking again (more frequent updates)
                        time.sleep(2)
                
                # Start the file watcher thread
                import threading
                print(f"[DEBUG] Starting file watcher thread for job {job_id}")
                watcher_thread = threading.Thread(target=file_watcher_thread)
                watcher_thread.daemon = True  # Thread will exit when main thread exits
                watcher_thread.start()
                print(f"[DEBUG] File watcher thread started successfully")
                
                # Start a dedicated file size tracker that just updates progress_in_size  
                def size_tracker_thread():
                    """
                    Thread that directly updates the progress_in_size field without any other logic.
                    This thread ONLY does one thing - update the file size in the database.
                    """
                    import time
                    import os
                    import json
                    from mysql.connector import connect
                    
                    print(f"Starting dedicated file size tracker thread for job {job_id}")
                    
                    while True:
                        try:
                            # Check for multiple possible part file formats
                            output_base = str(output_file).rsplit('.', 1)[0]  # Remove .mp3 extension
                            possible_part_files = [
                                str(output_file) + ".part",           # 1lDxLnrWjwkGm.mp3.part
                                output_base + ".m4a.part",            # 1lDxLnrWjwkGm.m4a.part  
                                output_base + ".mp4.part",            # 1lDxLnrWjwkGm.mp4.part
                                output_base + ".webm.part",           # 1lDxLnrWjwkGm.webm.part
                                output_base + ".aac.part",            # 1lDxLnrWjwkGm.aac.part
                            ]
                            
                            part_file = None
                            final_file = str(output_file)
                            
                            # Find which part file actually exists
                            for possible_file in possible_part_files:
                                if os.path.exists(possible_file):
                                    part_file = possible_file
                                    break
                            
                            # If final file exists, exit
                            if os.path.exists(final_file):
                                print(f"Size tracker: Final file exists, exiting thread")
                                break
                                
                            # Update the file size if part file exists
                            if part_file and os.path.exists(part_file):
                                file_size = os.path.getsize(part_file)
                                
                                # Direct database update ONLY for file size
                                try:
                                    with open('db_config.json', 'r') as config_file:
                                        db_config = json.load(config_file)
                                        if db_config["type"] == "mysql":
                                            mysql_config = db_config["mysql"].copy()
                                            if 'use_ssl' in mysql_config:
                                                del mysql_config['use_ssl']
                                            
                                            # Connect directly to MySQL
                                            conn = connect(**mysql_config)
                                            cursor = conn.cursor()
                                            
                                            # CRITICAL: Only update the progress_in_size field
                                            cursor.execute("""
                                                UPDATE space_download_scheduler 
                                                SET progress_in_size = %s 
                                                WHERE id = %s
                                            """, (int(file_size), job_id))
                                            
                                            conn.commit()
                                            cursor.close()
                                            conn.close()
                                            
                                            # Only log occasionally to avoid spamming logs
                                            if int(time.time()) % 4 == 0:
                                                print(f"SIZE TRACKER: Updated size to {file_size} bytes for job {job_id}")
                                except Exception as db_err:
                                    print(f"Error in size tracker update: {db_err}")
                        except Exception as e:
                            print(f"Error in size tracker thread: {e}")
                            
                        # Sleep briefly between updates
                        time.sleep(0.5)
                
                # Start the size tracker thread
                size_thread = threading.Thread(target=size_tracker_thread)
                size_thread.daemon = True  # Thread will exit when main thread exits
                size_thread.start()
                
                # Start another thread for heartbeat progress updates
                # This will ensure progress updates happen even if the file watcher misses some
                def heartbeat_progress_thread():
                    """
                    Thread that periodically sends heartbeat progress updates to the database.
                    This ensures progress is always reported regardless of other updates.
                    """
                    import time
                    import os
                    import json
                    from mysql.connector import connect
                    
                    print(f"Starting heartbeat progress thread for job {job_id}, space {space_id}")
                    last_progress = 0
                    last_size = 0
                    
                    # Critical: Make sure job is initialized with progress_in_size = 1024 at minimum
                    # This ensures the frontend sees activity even before part file appears
                    try:
                        with open('db_config.json', 'r') as config_file:
                            db_config = json.load(config_file)
                            if db_config["type"] == "mysql":
                                mysql_config = db_config["mysql"].copy()
                                if 'use_ssl' in mysql_config:
                                    del mysql_config['use_ssl']
                                
                                # Connect directly to MySQL
                                conn = connect(**mysql_config)
                                cursor = conn.cursor()
                                
                                # Update job with initial size
                                cursor.execute("""
                                    UPDATE space_download_scheduler 
                                    SET progress_in_size = 1024, progress_in_percent = 1, 
                                        status = 'in_progress', updated_at = NOW() 
                                    WHERE id = %s AND progress_in_size < 1024
                                """, (job_id,))
                                
                                conn.commit()
                                cursor.close()
                                conn.close()
                    except Exception as init_err:
                        print(f"Error in heartbeat thread initialization: {init_err}")
                    
                    while True:
                        try:
                            # Check if part file exists
                            part_file = str(output_file) + ".part"
                            final_file = str(output_file)
                            
                            # Check if the download has completed
                            if os.path.exists(final_file):
                                file_size = os.path.getsize(final_file)
                                print(f"Heartbeat detected completed file of size {file_size} bytes")
                                
                                # Final update with 100% progress
                                try:
                                    with open('db_config.json', 'r') as config_file:
                                        db_config = json.load(config_file)
                                        if db_config["type"] == "mysql":
                                            mysql_config = db_config["mysql"].copy()
                                            if 'use_ssl' in mysql_config:
                                                del mysql_config['use_ssl']
                                            
                                            # Connect directly to MySQL
                                            conn = connect(**mysql_config)
                                            cursor = conn.cursor()
                                            
                                            # Get job details for cost tracking
                                            cursor.execute("""
                                                SELECT user_id, start_time 
                                                FROM space_download_scheduler 
                                                WHERE id = %s
                                            """, (job_id,))
                                            job_details = cursor.fetchone()
                                            user_id = job_details[0] if job_details else None
                                            start_time = job_details[1] if job_details and job_details[1] else None
                                            
                                            # Update job with final file size and 100% progress
                                            cursor.execute("""
                                                UPDATE space_download_scheduler 
                                                SET progress_in_size = %s, progress_in_percent = 100, 
                                                    status = 'completed', updated_at = NOW(), end_time = NOW()
                                                WHERE id = %s
                                            """, (int(file_size), job_id))
                                            
                                            # Update space record to completed status 
                                            # Don't update format field with file size
                                            cursor.execute("""
                                                UPDATE spaces 
                                                SET status = 'completed',
                                                    downloaded_at = NOW(), updated_at = NOW()
                                                WHERE space_id = %s
                                            """, (space_id,))
                                            
                                            conn.commit()
                                            cursor.close()
                                            conn.close()
                                            
                                            print(f"HEARTBEAT: Final update - job completed with size={file_size} bytes")
                                            
                                            # Track compute cost if user_id and start_time available
                                            if user_id and start_time:
                                                try:
                                                    # Calculate download duration
                                                    from datetime import datetime
                                                    if isinstance(start_time, str):
                                                        start_time_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                                                    else:
                                                        start_time_dt = start_time
                                                    
                                                    end_time_dt = datetime.now()
                                                    download_duration = (end_time_dt - start_time_dt).total_seconds()
                                                    
                                                    # Direct database cost tracking (no Flask session required)
                                                    cost_conn = connect(**mysql_config)
                                                    cost_cursor = cost_conn.cursor(dictionary=True)
                                                    
                                                    # Get current user balance
                                                    cost_cursor.execute("SELECT credits FROM users WHERE id = %s", (user_id,))
                                                    user_result = cost_cursor.fetchone()
                                                    current_balance = float(user_result['credits']) if user_result else 0.0
                                                    
                                                    # Get compute cost per second
                                                    cost_cursor.execute("SELECT setting_value FROM app_settings WHERE setting_name = 'compute_cost_per_second'")
                                                    cost_result = cost_cursor.fetchone()
                                                    cost_per_second = float(cost_result['setting_value']) if cost_result else 0.001
                                                    
                                                    # Calculate total cost
                                                    total_cost = max(1, round(download_duration * cost_per_second))
                                                    
                                                    print(f"HEARTBEAT: Cost calculation - duration={download_duration:.2f}s, cost_per_sec=${cost_per_second:.6f}, total_cost=${total_cost:.6f}")
                                                    
                                                    # Cost tracking is handled by the CostLogger in the forked process
                                                    print(f"HEARTBEAT: Download completed, cost tracking handled by forked process - duration={download_duration:.2f}s, calculated_cost=${total_cost:.6f}")
                                                    
                                                    cost_cursor.close()
                                                    cost_conn.close()
                                                    
                                                except Exception as cost_err:
                                                    print(f"HEARTBEAT: Error tracking compute cost: {cost_err}")
                                            else:
                                                print(f"HEARTBEAT: Skipping cost tracking - user_id={user_id}, start_time={start_time}")
                                except Exception as db_err:
                                    print(f"Error in heartbeat final update: {db_err}")
                                
                                # Exit the thread as the download is complete
                                break
                            
                            # Check the part file for progress updates
                            elif part_file and os.path.exists(part_file):
                                file_size = os.path.getsize(part_file)
                                
                                # Always update DB regardless of changes
                                # More accurate progress estimation based on typical file sizes
                                # Most space recordings are between 30-100MB, so scale accordingly
                                if file_size > 60*1024*1024:  # > 60MB
                                    estimated_percent = 90 + min(9, int((file_size - 60*1024*1024) / (10*1024*1024)))
                                elif file_size > 40*1024*1024:  # > 40MB
                                    estimated_percent = 75 + min(15, int((file_size - 40*1024*1024) / (1.33*1024*1024)))
                                elif file_size > 20*1024*1024:  # > 20MB
                                    estimated_percent = 50 + min(25, int((file_size - 20*1024*1024) / (0.8*1024*1024)))
                                elif file_size > 10*1024*1024:  # > 10MB
                                    estimated_percent = 25 + min(25, int((file_size - 10*1024*1024) / (0.4*1024*1024)))
                                elif file_size > 5*1024*1024:   # > 5MB
                                    estimated_percent = 10 + min(15, int((file_size - 5*1024*1024) / (0.33*1024*1024)))
                                elif file_size > 1*1024*1024:   # > 1MB
                                    estimated_percent = 1 + min(9, int((file_size - 1*1024*1024) / (0.44*1024*1024)))
                                else:
                                    estimated_percent = 1  # At least show 1% if file exists
                                
                                # Always log progress, even if small changes
                                # This helps with debugging and ensures we can see activity
                                print(f"HEARTBEAT: Part file size {file_size} bytes, progress {estimated_percent}%")
                                
                                # ALWAYS update the job's progress_in_size, regardless of other changes
                                # This is critical for accurate progress tracking
                                
                                # Direct database update using a fresh connection
                                try:
                                    with open('db_config.json', 'r') as config_file:
                                        db_config = json.load(config_file)
                                        if db_config["type"] == "mysql":
                                            mysql_config = db_config["mysql"].copy()
                                            if 'use_ssl' in mysql_config:
                                                del mysql_config['use_ssl']
                                            
                                            # Connect directly to MySQL
                                            conn = connect(**mysql_config)
                                            cursor = conn.cursor()
                                            
                                            # First check if job exists
                                            check_query = "SELECT id FROM space_download_scheduler WHERE id = %s"
                                            cursor.execute(check_query, (job_id,))
                                            job_exists = cursor.fetchone() is not None
                                            
                                            if job_exists:
                                                # Update job with current file size and progress
                                                # CRITICAL FIX: Always update progress_in_size, even if no other changes
                                                # This is essential for tracking download progress
                                                cursor.execute("""
                                                    UPDATE space_download_scheduler 
                                                    SET progress_in_size = %s, progress_in_percent = %s, 
                                                        status = 'in_progress', updated_at = NOW() 
                                                    WHERE id = %s
                                                """, (int(file_size), int(estimated_percent), job_id))
                                                
                                                # CRITICAL: Add a backup update that only updates size
                                                # This ensures file size is always tracked correctly
                                                cursor.execute("""
                                                    UPDATE space_download_scheduler 
                                                    SET progress_in_size = %s, updated_at = NOW() 
                                                    WHERE id = %s
                                                """, (int(file_size), job_id))
                                                
                                                # Check if space exists
                                                cursor.execute("SELECT id FROM spaces WHERE space_id = %s", (space_id,))
                                                space_exists = cursor.fetchone() is not None
                                                
                                                if space_exists:
                                                    # Update space record with progress
                                                    # Don't use format field for storing file size
                                                    cursor.execute("""
                                                        UPDATE spaces 
                                                        SET status = 'downloading', download_cnt = %s,
                                                            updated_at = NOW()
                                                        WHERE space_id = %s
                                                    """, (int(estimated_percent), space_id))
                                            
                                            conn.commit()
                                            cursor.close()
                                            conn.close()
                                except Exception as db_err:
                                    print(f"Error in heartbeat thread DB update: {db_err}")
                                
                                # Save the current progress and size for the next comparison
                                last_progress = estimated_percent
                                last_size = file_size
                        except Exception as e:
                            print(f"Error in heartbeat thread: {e}")
                            
                        # Sleep for 1 second before checking again (more frequent updates)
                        time.sleep(1)
                
                # Start the heartbeat thread
                heartbeat_thread = threading.Thread(target=heartbeat_progress_thread)
                heartbeat_thread.daemon = True  # Thread will exit when main thread exits
                heartbeat_thread.start()
                
                # Set up yt-dlp command to download the actual audio file
                # Force MP3 format as the default output format per user requirements
                final_format = 'mp3'  # Always use MP3 regardless of what was requested
                
                yt_dlp_cmd = [
                    yt_dlp_path,
                    "--extract-audio",
                    "--audio-format", final_format,  # Always use MP3 format
                    "--audio-quality", "0",  # Best quality
                    "--output", str(download_dir / f"{space_id}.{final_format}"),  # Ensure .mp3 extension
                    "--no-progress",  # Don't show progress bar (cleaner logs)
                    "--no-warnings",  # Reduce log spam
                    "--no-playlist",  # Don't download playlists
                    "--remux-video", "mp3",  # Force remuxing to mp3 to avoid intermediary files
                    "--postprocessor-args", "-strict -2",  # More permissive ffmpeg options
                ]
                
                # Update output file path and file_type to reflect MP3 format
                output_file = download_dir / f"{space_id}.mp3"
                file_type = 'mp3'
                
                # Add X space extractor if the URL is from X
                if "x.com" in space_url:
                    # Get the absolute path to the extractor
                    extractor_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'space_x_extractor.py')
                    yt_dlp_cmd.extend([
                        "--extractor-args", f"xspace:{extractor_path}",
                    ])
                    print(f"Using X space extractor for: {space_url}")
                    
                # Add URL at the end
                yt_dlp_cmd.append(space_url)
                
                print(f"Download command: {' '.join(yt_dlp_cmd)}")
                
                print(f"Starting download for space {space_id}...")
                
                # Add specific error checking for common space issues
                space_availability_check = None
                try:
                    # First check if the space is publicly available by making a simple request
                    import requests
                    # Set a short timeout to avoid hanging
                    response = requests.head(space_url, timeout=5, allow_redirects=True)
                    
                    if response.status_code != 200:
                        print(f"Warning: Space URL returned status code {response.status_code}")
                        if response.status_code == 404:
                            space_availability_check = "Space not found (404 error)"
                        elif response.status_code >= 400 and response.status_code < 500:
                            space_availability_check = f"Client error accessing space (HTTP {response.status_code})"
                        elif response.status_code >= 500:
                            space_availability_check = f"Server error accessing space (HTTP {response.status_code})"
                    else:
                        print(f"Space URL check succeeded with status code {response.status_code}")
                except Exception as check_err:
                    print(f"Warning: Could not verify space URL availability: {check_err}")
                
                # Log any availability issues but still try to download
                if space_availability_check:
                    print(f"WARNING: {space_availability_check}")
                    print("Will still attempt download but may fail")
                
                # Track download start time for cost calculation
                download_start_time = time.time()
                print(f"[DEBUG DOWNLOAD] Starting download at {datetime.datetime.now()}")
                
                # Run yt-dlp as a subprocess and capture output
                print(f"[DEBUG DOWNLOAD] Executing yt-dlp command...")
                print(f"[DEBUG DOWNLOAD] Command: {' '.join(yt_dlp_cmd)}")
                
                process = subprocess.Popen(
                    yt_dlp_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1
                )
                
                print(f"[DEBUG DOWNLOAD] yt-dlp process started with PID: {process.pid}")
                
                # Process output line by line to track progress
                progress = 0
                last_size_update_time = time.time()
                last_part_check_time = time.time()
                force_update_needed = True  # Start with a forced update to show immediate progress
                
                print(f"[DEBUG DOWNLOAD] Starting to read yt-dlp output...")
                
                # CRITICAL FIX: Directly update job with initial size before starting download
                # This ensures the job's progress_in_size is set immediately
                try:
                    with open('db_config.json', 'r') as config_file:
                        db_config = json.load(config_file)
                        if db_config["type"] == "mysql":
                            mysql_config = db_config["mysql"].copy()
                            if 'use_ssl' in mysql_config:
                                del mysql_config['use_ssl']
                                
                            conn = mysql.connector.connect(**mysql_config)
                            cursor = conn.cursor()
                            
                            # Ensure job starts with a known size value and store start time
                            initial_size_query = """
                            UPDATE space_download_scheduler
                            SET progress_in_size = 1024, updated_at = NOW(), start_time = NOW()
                            WHERE id = %s AND (progress_in_size IS NULL OR progress_in_size < 1024)
                            """
                            cursor.execute(initial_size_query, (job_id,))
                            conn.commit()
                            cursor.close()
                            conn.close()
                            
                            print(f"Set initial progress_in_size to 1024 bytes for job {job_id}")
                except Exception as initial_size_err:
                    print(f"Error setting initial size: {initial_size_err}")
                
                for line in iter(process.stdout.readline, ''):
                    print(f"[DEBUG YT-DLP] {line.strip()}")
                    
                    # Always check part file size at regular intervals
                    current_time = time.time()
                    if current_time - last_part_check_time >= 5:  # Check part file every 5 seconds
                        print(f"[DEBUG DOWNLOAD] Checking part file after 5 seconds...")
                        try:
                            part_file = str(output_file) + ".part"
                            print(f"[DEBUG DOWNLOAD] Checking for part file: {part_file}")
                            
                            if os.path.exists(part_file):
                                file_size = os.path.getsize(part_file)
                                # Record that we have a part file and its size
                                force_update_needed = True  # Force an update when we detect file size change
                                print(f"[DEBUG DOWNLOAD] Part file detected: {part_file}, Size: {file_size} bytes")
                                
                                # CRITICAL FIX: Actively update the database with part file size
                                # to report progress even if yt-dlp isn't reporting percentage
                                estimated_percent = 0
                                if file_size > 0:
                                    # Use improved progress estimation based on file size
                                    if file_size > 60*1024*1024:  # > 60MB
                                        estimated_percent = 90 + min(9, int((file_size - 60*1024*1024) / (10*1024*1024)))
                                    elif file_size > 40*1024*1024:  # > 40MB
                                        estimated_percent = 75 + min(15, int((file_size - 40*1024*1024) / (1.33*1024*1024)))
                                    elif file_size > 20*1024*1024:  # > 20MB
                                        estimated_percent = 50 + min(25, int((file_size - 20*1024*1024) / (0.8*1024*1024)))
                                    elif file_size > 10*1024*1024:  # > 10MB
                                        estimated_percent = 25 + min(25, int((file_size - 10*1024*1024) / (0.4*1024*1024)))
                                    elif file_size > 5*1024*1024:   # > 5MB
                                        estimated_percent = 10 + min(15, int((file_size - 5*1024*1024) / (0.33*1024*1024)))
                                    elif file_size > 1*1024*1024:   # > 1MB
                                        estimated_percent = 1 + min(9, int((file_size - 1*1024*1024) / (0.44*1024*1024)))
                                    else:
                                        estimated_percent = 1

                                # Update both database tables regardless of yt-dlp progress
                                try:
                                    # Create a direct database connection
                                    with open('db_config.json', 'r') as config_file:
                                        db_config = json.load(config_file)
                                        if db_config["type"] == "mysql":
                                            mysql_config = db_config["mysql"].copy()
                                            if 'use_ssl' in mysql_config:
                                                del mysql_config['use_ssl']
                                                
                                            conn = mysql.connector.connect(**mysql_config)
                                            
                                            # 1. Update the job record
                                            cursor = conn.cursor()
                                            job_query = """
                                            UPDATE space_download_scheduler
                                            SET progress_in_size = %s, progress_in_percent = %s, 
                                                status = 'in_progress', updated_at = NOW()
                                            WHERE id = %s
                                            """
                                            cursor.execute(job_query, (file_size, estimated_percent, job_id))
                                            
                                            # 2. Update the space record format field
                                            space_query = """
                                            UPDATE spaces
                                            SET format = %s, status = 'downloading', download_cnt = %s
                                            WHERE space_id = %s
                                            """
                                            cursor.execute(space_query, (str(file_size), estimated_percent, space_id))
                                            
                                            conn.commit()
                                            cursor.close()
                                            conn.close()
                                            
                                            print(f"PART FILE UPDATE: Updated database with size={file_size}, percent={estimated_percent}%")
                                except Exception as db_err:
                                    print(f"Error updating database from part file: {db_err}")
                                
                        except Exception as part_err:
                            print(f"Error checking part file: {part_err}")
                        last_part_check_time = current_time
                    
                    # Try to extract progress from the output
                    percent_found = False
                    percentage_match = None
                    
                    # Look for common yt-dlp progress indicators
                    if '%' in line:
                        try:
                            # Find different possible patterns of percentage reporting
                            
                            # Pattern 1: [download] 25.0% of 123.45MiB at 1.23MiB/s
                            if '[download]' in line and 'of' in line and '%' in line:
                                parts = line.split('%', 1)[0].split()
                                for part in parts:
                                    if part.replace('.', '', 1).isdigit():
                                        percentage_match = float(part)
                                        percent_found = True
                                        print(f"Detected download percentage: {percentage_match}%")
                                        break
                            
                            # Pattern 2: [ffmpeg] progress: 45%
                            elif 'progress' in line.lower() and '%' in line:
                                parts = line.split('%', 1)[0].split(':')
                                if len(parts) > 1:
                                    percentage_str = parts[-1].strip()
                                    if percentage_str.replace('.', '', 1).isdigit():
                                        percentage_match = float(percentage_str)
                                        percent_found = True
                                        print(f"Detected ffmpeg progress: {percentage_match}%")
                            
                            # Pattern 3: Any line with percentage and numbers
                            else:
                                percentage_part = line.split('%')[0]
                                nums = [s for s in percentage_part.split() if s.replace('.', '', 1).isdigit()]
                                if nums:
                                    percentage_match = float(nums[-1])  # Take the last number before %
                                    percent_found = True
                                    print(f"Detected generic progress percentage: {percentage_match}%")
                        except Exception as extract_err:
                            print(f"Error extracting percentage: {extract_err}")
                    
                    # If we found a percentage, update progress
                    if percent_found and percentage_match is not None:
                        current_progress = max(0, min(100, percentage_match))  # Ensure 0-100 range
                        
                        # Only update if progress has changed significantly or at important milestones
                        should_update = (
                            force_update_needed or
                            int(current_progress) > progress + 4 or  # Update on 5% change
                            (progress < 10 and current_progress >= 10) or  # Update at 10%
                            (progress < 25 and current_progress >= 25) or  # Update at 25% 
                            (progress < 50 and current_progress >= 50) or  # Update at 50%
                            (progress < 75 and current_progress >= 75) or  # Update at 75%
                            (progress < 95 and current_progress >= 95) or  # Update at 95%
                            (current_time - last_size_update_time >= 15)   # Force update every 15 seconds
                        )
                        
                        if should_update:
                            progress = int(current_progress)
                            last_size_update_time = current_time
                            force_update_needed = False
                            
                            # Estimate file size based on partial file if possible
                            size_mb = 0
                            download_size_found = False
                            
                            # Method 1: Extract from yt-dlp output line
                            if 'of ' in line and ' at ' in line:
                                try:
                                    # Extract from yt-dlp output
                                    size_str = line.split('of ')[1].split(' at ')[0].strip()
                                    if 'MiB' in size_str:
                                        size_mb = float(size_str.replace('MiB', '').strip()) * 1024 * 1024
                                        download_size_found = True
                                        print(f"Extracted file size from output: {size_mb} bytes (MiB)")
                                    elif 'KiB' in size_str:
                                        size_mb = float(size_str.replace('KiB', '').strip()) * 1024
                                        download_size_found = True
                                        print(f"Extracted file size from output: {size_mb} bytes (KiB)")
                                    elif 'GiB' in size_str:
                                        size_mb = float(size_str.replace('GiB', '').strip()) * 1024 * 1024 * 1024
                                        download_size_found = True
                                        print(f"Extracted file size from output: {size_mb} bytes (GiB)")
                                except Exception as size_err:
                                    print(f"Error extracting size from line: {size_err}")
                            
                            # Method 2: Check part file size (more reliable)
                            if not download_size_found:
                                part_file = str(output_file) + ".part"
                                if os.path.exists(part_file):
                                    file_size = os.path.getsize(part_file)
                                    print(f"Using part file size: {file_size} bytes")
                                    
                                    # If we have progress percentage and file size, estimate total size
                                    if progress > 0:
                                        # Prevent division by zero and unreasonable estimates
                                        if progress >= 1:  # At least 1%
                                            total_size_estimate = file_size * 100 / progress
                                            size_mb = int(total_size_estimate)
                                            download_size_found = True
                                            print(f"Estimated total size: {size_mb} bytes (from {progress}%)")
                                        else:
                                            # Just use current size if progress is too low for reasonable estimate
                                            size_mb = file_size
                                            download_size_found = True
                                            print(f"Using current part file size: {size_mb} bytes")
                                elif os.path.exists(output_file):
                                    size_mb = os.path.getsize(output_file)
                                    download_size_found = True
                                    print(f"Using final file size: {size_mb} bytes")
                            
                            # Use current part file size to show accurate progress
                            part_file = str(output_file) + ".part"
                            if os.path.exists(part_file):
                                part_file_size = os.path.getsize(part_file)
                                # Always prefer actual part file size for progress updates
                                size_mb = part_file_size
                                print(f"Using current part file size for progress: {size_mb} bytes")
                            elif not download_size_found or size_mb < 1024:
                                size_mb = max(1024 * 1024, size_mb)  # At least 1MB
                                print(f"Using minimum file size: {size_mb} bytes")
                            
                            # Make direct SQL update to ensure database reflects progress
                            try:
                                # Create direct database connection
                                with open('db_config.json', 'r') as config_file:
                                    db_config = json.load(config_file)
                                    if db_config["type"] == "mysql":
                                        mysql_config = db_config["mysql"].copy()
                                        if 'use_ssl' in mysql_config:
                                            del mysql_config['use_ssl']
                                            
                                        conn = mysql.connector.connect(**mysql_config)
                                        cursor = conn.cursor()
                                        
                                        # First check if job exists
                                        check_query = "SELECT id, status FROM space_download_scheduler WHERE id = %s"
                                        cursor.execute(check_query, (job_id,))
                                        result = cursor.fetchone()
                                        
                                        if result:
                                            # Update the job status with current progress
                                            job_update_query = """
                                            UPDATE space_download_scheduler 
                                            SET status = 'in_progress', process_id = %s, 
                                                progress_in_percent = %s, progress_in_size = %s,
                                                updated_at = NOW()
                                            WHERE id = %s
                                            """
                                            print(f"IMPORTANT: Updating job {job_id} with size={int(size_mb)} bytes, percent={progress}%")
                                            cursor.execute(job_update_query, (
                                                os.getpid(), progress, int(size_mb), job_id
                                            ))
                                            
                                            # Verify the update was successful
                                            verify_query = "SELECT progress_in_size FROM space_download_scheduler WHERE id = %s"
                                            cursor.execute(verify_query, (job_id,))
                                            verify_result = cursor.fetchone()
                                            if verify_result:
                                                print(f"Verification: progress_in_size is now {verify_result[0]} bytes after update")
                                            
                                            update_count = cursor.rowcount
                                            print(f"Job {job_id} update affected {update_count} rows")
                                        else:
                                            print(f"WARNING: Job {job_id} not found in database")
                                        
                                        # Check if space exists before updating
                                        check_space_query = "SELECT id FROM spaces WHERE space_id = %s"
                                        cursor.execute(check_space_query, (space_id,))
                                        space_result = cursor.fetchone()
                                        
                                        if space_result:
                                            # Also update the space record - CRITICAL: update format field with file size
                                            space_update_query = """
                                            UPDATE spaces
                                            SET status = 'downloading', download_cnt = %s, format = %s
                                            WHERE space_id = %s
                                            """
                                            cursor.execute(space_update_query, (progress, str(int(size_mb)), space_id))
                                            
                                            space_update_count = cursor.rowcount
                                            print(f"Space {space_id} update affected {space_update_count} rows")
                                        else:
                                            print(f"WARNING: Space {space_id} not found in database")
                                        
                                        conn.commit()
                                        cursor.close()
                                        conn.close()
                                        
                                        print(f"Database updated - Progress: {progress}%, Size: {size_mb} bytes")
                            except Exception as db_err:
                                print(f"Error updating progress in database: {db_err}")
                                # Fall back to using Space component methods
                                try:
                                    space.update_download_progress_by_space(
                                        space_id, 
                                        progress_size=int(size_mb),
                                        progress_percent=progress,
                                        status='downloading'
                                    )
                                    space.update_download_job(
                                        job_id,
                                        status='in_progress',
                                        progress_in_size=int(size_mb),
                                        progress_in_percent=progress,
                                        process_id=os.getpid()
                                    )
                                    print(f"Updated progress using Space component methods")
                                except Exception as space_err:
                                    print(f"Error updating progress via Space component: {space_err}")
                
                # Check part file size every 2 seconds regardless of output to ensure progress updates
                last_update_time = time.time()
                part_check_counter = 0
                
                while process.poll() is None:  # While process is still running
                    current_time = time.time()
                    # Check more frequently (every 2 seconds) to ensure better progress tracking
                    if current_time - last_update_time >= 2:
                        part_check_counter += 1
                        try:
                            # Check part file size
                            part_file = str(output_file) + ".part"
                            if os.path.exists(part_file):
                                file_size = os.path.getsize(part_file)
                                print(f"Periodic check: part file size = {file_size} bytes")
                                
                                # Get a size estimate for total file
                                total_size_estimate = file_size
                                
                                # Use improved progress estimation based on part file size
                                # This applies the same algorithm from the database update section
                                estimated_percent = 0
                                if file_size > 1024*1024:  # > 1MB
                                    # Estimate progress based on file size - more generous scaling
                                    # Most space recordings are between 30-100MB, so scale accordingly
                                    if file_size > 60*1024*1024:  # > 60MB
                                        estimated_percent = 90 + min(9, int((file_size - 60*1024*1024) / (10*1024*1024)))
                                    elif file_size > 40*1024*1024:  # > 40MB
                                        estimated_percent = 75 + min(15, int((file_size - 40*1024*1024) / (1.33*1024*1024)))
                                    elif file_size > 20*1024*1024:  # > 20MB
                                        estimated_percent = 50 + min(25, int((file_size - 20*1024*1024) / (0.8*1024*1024)))
                                    elif file_size > 10*1024*1024:  # > 10MB
                                        estimated_percent = 25 + min(25, int((file_size - 10*1024*1024) / (0.4*1024*1024)))
                                    elif file_size > 5*1024*1024:   # > 5MB
                                        estimated_percent = 10 + min(15, int((file_size - 5*1024*1024) / (0.33*1024*1024)))
                                    elif file_size > 1*1024*1024:   # > 1MB
                                        estimated_percent = 1 + min(9, int((file_size - 1*1024*1024) / (0.44*1024*1024)))
                                    else:
                                        estimated_percent = 1
                                    
                                    print(f"Estimating progress as {estimated_percent}% based on file size: {file_size/1024/1024:.2f}MB")
                                    
                                    # Only update if our estimate is higher than current progress
                                    if estimated_percent > progress or progress == 0:
                                        progress = estimated_percent
                                        print(f"Updated progress to {progress}% based on file size estimation")
                                
                                # CRITICAL FIX: Update database directly with part file size
                                # This ensures progress updates happen even if the process has no stdout
                                try:
                                    # Create a direct database connection
                                    with open('db_config.json', 'r') as config_file:
                                        db_config = json.load(config_file)
                                        if db_config["type"] == "mysql":
                                            mysql_config = db_config["mysql"].copy()
                                            if 'use_ssl' in mysql_config:
                                                del mysql_config['use_ssl']
                                                
                                            conn = mysql.connector.connect(**mysql_config)
                                            
                                            # 1. Update the job record
                                            cursor = conn.cursor()
                                            job_query = """
                                            UPDATE space_download_scheduler
                                            SET progress_in_size = %s, progress_in_percent = %s, 
                                                status = 'in_progress', updated_at = NOW()
                                            WHERE id = %s
                                            """
                                            cursor.execute(job_query, (file_size, progress, job_id))
                                            
                                            # 2. Update the space record format field
                                            space_query = """
                                            UPDATE spaces
                                            SET format = %s, status = 'downloading', download_cnt = %s
                                            WHERE space_id = %s
                                            """
                                            cursor.execute(space_query, (str(file_size), progress, space_id))
                                            
                                            conn.commit()
                                            cursor.close()
                                            conn.close()
                                            
                                            print(f"PERIODIC UPDATE: Updated database with size={file_size}, percent={progress}%")
                                except Exception as db_err:
                                    print(f"Error updating database from periodic check: {db_err}")
                                        
                                # Additional database updates will be done below
                                try:
                                    # Create direct database connection
                                    with open('db_config.json', 'r') as config_file:
                                        db_config = json.load(config_file)
                                        if db_config["type"] == "mysql":
                                            mysql_config = db_config["mysql"].copy()
                                            if 'use_ssl' in mysql_config:
                                                del mysql_config['use_ssl']
                                                
                                            conn = mysql.connector.connect(**mysql_config)
                                            cursor = conn.cursor()
                                            
                                            # IMPORTANT: Always update the database with the current file size
                                            # This is critical to ensure progress tracking works correctly
                                            job_size_update_query = """
                                            UPDATE space_download_scheduler
                                            SET progress_in_size = %s, updated_at = NOW()
                                            WHERE id = %s
                                            """
                                            cursor.execute(job_size_update_query, (file_size, job_id))
                                            print(f"DIRECT SIZE UPDATE: Updated job {job_id} with current size={file_size} bytes")
                                            
                                            # For new downloads with no progress yet, set progress to at least 1%
                                            # This helps show some progress on the frontend
                                            current_percent = progress  # Default value if we don't update it
                                            
                                            # Always update progress based on part file size
                                            if file_size > 1024*1024:  # > 1MB
                                                # Estimate progress based on file size - more generous scaling
                                                # Most space recordings are between 30-100MB, so scale accordingly
                                                # Spaces can be up to 3 hours (180 minutes), so estimate ~0.5MB per minute
                                                # Aim for 50% at 20MB, 75% at 40MB, 90% at 60MB
                                                if file_size > 60*1024*1024:  # > 60MB
                                                    estimated_percent = 90 + min(9, int((file_size - 60*1024*1024) / (10*1024*1024)))
                                                elif file_size > 40*1024*1024:  # > 40MB
                                                    estimated_percent = 75 + min(15, int((file_size - 40*1024*1024) / (1.33*1024*1024)))
                                                elif file_size > 20*1024*1024:  # > 20MB
                                                    estimated_percent = 50 + min(25, int((file_size - 20*1024*1024) / (0.8*1024*1024)))
                                                elif file_size > 10*1024*1024:  # > 10MB
                                                    estimated_percent = 25 + min(25, int((file_size - 10*1024*1024) / (0.4*1024*1024)))
                                                elif file_size > 5*1024*1024:   # > 5MB
                                                    estimated_percent = 10 + min(15, int((file_size - 5*1024*1024) / (0.33*1024*1024)))
                                                elif file_size > 1*1024*1024:   # > 1MB
                                                    estimated_percent = 1 + min(9, int((file_size - 1*1024*1024) / (0.44*1024*1024)))
                                                else:
                                                    estimated_percent = 1
                                                
                                                print(f"Estimating progress as {estimated_percent}% based on part file size: {file_size/1024/1024:.2f}MB")
                                                
                                                # Only update if our estimate is higher than current progress
                                                if estimated_percent > progress or progress == 0:
                                                    current_percent = estimated_percent
                                                else:
                                                    # Keep existing progress if it's higher
                                                    current_percent = progress
                                            
                                            # First check if job exists in database
                                            check_query = "SELECT id, status FROM space_download_scheduler WHERE id = %s"
                                            cursor.execute(check_query, (job_id,))
                                            result = cursor.fetchone()
                                            
                                            if result:
                                                # Provide size updates more frequently than percent updates
                                                job_update_query = """
                                                UPDATE space_download_scheduler 
                                                SET status = 'in_progress', process_id = %s, 
                                                    progress_in_size = %s, 
                                                    progress_in_percent = %s,
                                                    updated_at = NOW()
                                                WHERE id = %s
                                                """
                                                
                                                # Use either current part size or estimated total size
                                                # For beginning of downloads, just show current size
                                                # For further along downloads, show estimated total
                                                size_to_update = file_size
                                                
                                                # Always update with actual part file size so the frontend shows progress
                                                print(f"Updating with current part size: {size_to_update}")
                                                
                                                cursor.execute(job_update_query, (
                                                    os.getpid(), size_to_update, current_percent, job_id
                                                ))
                                                
                                                # Update the spaces table status
                                                # Don't use format field for storing file size
                                                space_update_query = """
                                                UPDATE spaces
                                                SET status = 'downloading'
                                                WHERE space_id = %s
                                                """
                                                cursor.execute(space_update_query, (space_id,))
                                                print(f"Updated spaces table status to downloading")
                                                
                                                update_count = cursor.rowcount
                                                print(f"Part check: Job {job_id} update affected {update_count} rows")
                                            else:
                                                print(f"WARNING: Job {job_id} not found in database during part check")
                                            
                                            # Check if space exists before updating
                                            check_space_query = "SELECT id FROM spaces WHERE space_id = %s"
                                            cursor.execute(check_space_query, (space_id,))
                                            space_result = cursor.fetchone()
                                            
                                            if space_result:
                                                # Also update the space record with download_cnt to show progress
                                                space_update_query = """
                                                UPDATE spaces
                                                SET status = 'downloading', download_cnt = %s
                                                WHERE space_id = %s
                                                """
                                                cursor.execute(space_update_query, (current_percent, space_id))
                                                
                                                space_update_count = cursor.rowcount
                                                print(f"Part check: Space {space_id} update affected {space_update_count} rows")
                                            else:
                                                print(f"WARNING: Space {space_id} not found in database during part check")
                                            
                                            conn.commit()
                                            cursor.close()
                                            conn.close()
                                            
                                            print(f"Database updated with size={size_to_update}, percent={current_percent}%")
                                except Exception as db_err:
                                    print(f"Error updating progress from part file: {db_err}")
                                    # Try to use Space component as fallback
                                    try:
                                        space.update_download_job(
                                            job_id,
                                            status='in_progress',
                                            progress_in_size=file_size,
                                            process_id=os.getpid()
                                        )
                                        print("Updated progress using Space component")
                                    except Exception as space_err:
                                        print(f"Error using Space component: {space_err}")
                        except Exception as check_err:
                            print(f"Error checking part file: {check_err}")
                            
                        last_update_time = current_time
                    
                    # Small sleep to prevent CPU spinning
                    time.sleep(0.5)
                
                # Wait for the process to complete
                process.wait()
                process_returncode = process.returncode
                
                # Check if download was successful
                if process_returncode == 0:
                    print("Download completed successfully")
                    
                    # Check if the output file exists
                    # Look for files in the download directory with this space_id
                    matching_files = []
                    try:
                        for filename in os.listdir(str(download_dir)):
                            if space_id in filename:
                                matching_files.append(os.path.join(str(download_dir), filename))
                    except Exception as search_err:
                        print(f"Error searching for output files: {search_err}")
                    
                    if matching_files:
                        output_file = matching_files[0]
                        print(f"Found output file: {output_file}")
                    else:
                        # If we can't find the file, handle the error
                        raise Exception("Download completed but no output file found")
                    
                    # Get file size
                    file_size = os.path.getsize(output_file)
                    print(f"File size: {file_size} bytes")
                    
                    # CRITICAL: Always convert non-MP3 formats to MP3 as required by user
                    if file_type.lower() != 'mp3' or not str(output_file).endswith('.mp3'):
                        # The file exists but is not MP3 format - convert it
                        print(f"Converting {output_file} to MP3 format as required by user")
                        
                        # Define the mp3 output file path
                        mp3_output = str(output_file).rsplit('.', 1)[0] + '.mp3'
                        
                        try:
                            # Use ffmpeg to convert the file to MP3
                            convert_cmd = [
                                'ffmpeg',
                                '-y',  # Overwrite existing files
                                '-i', str(output_file),  # Input file
                                '-acodec', 'libmp3lame',  # Use LAME MP3 encoder
                                '-q:a', '2',  # Use VBR quality 2 (high quality)
                                mp3_output  # Output file
                            ]
                            
                            print(f"Running conversion command: {' '.join(convert_cmd)}")
                            convert_result = subprocess.run(convert_cmd, 
                                                          stdout=subprocess.PIPE, 
                                                          stderr=subprocess.PIPE,
                                                          text=True)
                            
                            if convert_result.returncode == 0 and os.path.exists(mp3_output) and os.path.getsize(mp3_output) > 0:
                                print(f"Successfully converted file to MP3: {mp3_output}")
                                
                                # If conversion successful, delete the original non-MP3 file
                                os.remove(output_file)
                                print(f"Removed original {file_type} file: {output_file}")
                                
                                # Update output_file to point to the MP3 file
                                output_file = mp3_output
                                file_type = 'mp3'
                                
                                # Update the file size for database records
                                file_size = os.path.getsize(output_file)
                                print(f"New MP3 file size: {file_size} bytes")
                            else:
                                print(f"Error converting file to MP3: {convert_result.stderr}")
                                # Continue with validation, don't fail the download
                        except Exception as convert_err:
                            print(f"Error during conversion to MP3: {convert_err}")
                    
                    # Clean up any m4a files that might have been left behind
                    try:
                        # Check for any m4a files with this space_id
                        for filename in os.listdir(str(download_dir)):
                            if space_id in filename and filename.endswith('.m4a') and filename != os.path.basename(output_file):
                                m4a_file = os.path.join(str(download_dir), filename)
                                print(f"Found stray m4a file: {m4a_file}, removing...")
                                os.remove(m4a_file)
                                print(f"Removed stray m4a file: {m4a_file}")
                    except Exception as cleanup_err:
                        print(f"Error cleaning up m4a files: {cleanup_err}")
                        # Non-critical error, continue with validation
                    
                    # Verify that file is valid and complete by checking if it can be read correctly
                    print("Validating downloaded file...")
                    try:
                        # For audio files, we can use ffprobe to check if the file is complete and valid
                        ffprobe_cmd = [
                            'ffprobe', 
                            '-v', 'error', 
                            '-show_entries', 'format=duration',
                            '-of', 'default=noprint_wrappers=1:nokey=1',
                            str(output_file)
                        ]
                        
                        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
                        
                        # If we can read the duration and it's > 0, the file is likely valid
                        if result.returncode == 0 and result.stdout.strip():
                            try:
                                duration = float(result.stdout.strip())
                                if duration > 0:
                                    print(f"File validated successfully: duration = {duration} seconds")
                                else:
                                    print(f"WARNING: File has invalid duration: {duration}")
                                    raise Exception(f"Downloaded file has invalid duration: {duration}")
                            except ValueError:
                                print(f"WARNING: Could not parse duration from ffprobe output: {result.stdout.strip()}")
                                raise Exception(f"Could not parse duration from ffprobe output: {result.stdout.strip()}")
                        else:
                            print(f"WARNING: ffprobe validation failed: {result.stderr}")
                            raise Exception(f"Failed to validate downloaded file: {result.stderr}")
                    except Exception as validate_err:
                        print(f"WARNING: Error validating file: {validate_err}")
                        # If we can't validate with ffprobe, at least check the file size is reasonable
                        if file_size < 100 * 1024:  # Less than 100KB is suspicious for an audio file
                            print(f"WARNING: Output file size ({file_size} bytes) is too small for a valid audio file!")
                            raise Exception(f"Download completed but file size ({file_size} bytes) is too small")
                        print("Could not properly validate file but size appears reasonable, proceeding with caution.")
                    
                    # Update job as completed
                    space.update_download_job(
                        job_id,
                        status='completed',
                        progress_in_size=file_size,
                        progress_in_percent=100
                    )
                    
                    # Also make sure there's a record in the spaces table with status 1 for search
                    try:
                        # Create direct database connection
                        with open('db_config.json', 'r') as config_file:
                            db_config = json.load(config_file)
                            if db_config["type"] == "mysql":
                                mysql_config = db_config["mysql"].copy()
                                if 'use_ssl' in mysql_config:
                                    del mysql_config['use_ssl']
                                    
                                conn = mysql.connector.connect(**mysql_config)
                                cursor = conn.cursor()
                                
                                # Check if space exists
                                cursor.execute("SELECT COUNT(*) FROM spaces WHERE space_id = %s", (space_id,))
                                exists = cursor.fetchone()[0] > 0
                                
                                if exists:
                                    # Update existing space - don't modify download_cnt counter
                                    # Set format field to the file type, not the file size
                                    update_query = """
                                    UPDATE spaces 
                                    SET status = 'completed', format = %s, 
                                        updated_at = NOW(), downloaded_at = NOW()
                                    WHERE space_id = %s
                                    """
                                    cursor.execute(update_query, (file_type, space_id))
                                else:
                                    # Insert new space record with status 'completed' and download_cnt 0
                                    # Store file type in format field, not file size
                                    insert_query = """
                                    INSERT INTO spaces 
                                    (space_id, space_url, filename, status, download_cnt, format, created_at, updated_at, downloaded_at)
                                    VALUES (%s, %s, %s, 'completed', 0, %s, NOW(), NOW(), NOW())
                                    ON DUPLICATE KEY UPDATE
                                    status = 'completed',
                                    filename = VALUES(filename),
                                    format = VALUES(format),
                                    updated_at = NOW(),
                                    downloaded_at = NOW()
                                    """
                                    # Use space details URL if available or construct one
                                    space_url = space_details.get('space_url') if space_details else f"https://x.com/i/spaces/{space_id}"
                                    filename = f"{space_id}.{file_type}"
                                    cursor.execute(insert_query, (space_id, space_url, filename, file_type))
                                
                                conn.commit()
                                
                                # Trigger cache invalidation since we created/updated a space
                                try:
                                    trigger_file = Path('./temp/cache_invalidate.trigger')
                                    trigger_file.parent.mkdir(exist_ok=True)
                                    trigger_file.touch()
                                    print(f"Triggered cache invalidation after space completion")
                                except Exception as cache_err:
                                    print(f"Warning: Could not trigger cache invalidation: {cache_err}")
                                
                                cursor.close()
                                conn.close()
                                print(f"Added/updated space record in spaces table with status 'completed'")
                    except Exception as spaces_err:
                        print(f"Error updating spaces table: {spaces_err}")
                    
                    print(f"Download completed for space {space_id}")
                    
                    # POST-DOWNLOAD PROCESSING: Automatic metadata fetching and audio trimming
                    try:
                        print("Starting post-download processing...")
                        
                        # 1. Automatic metadata fetching
                        print("Fetching metadata automatically...")
                        try:
                            space = Space()
                            metadata_result = space.fetch_and_save_metadata(space_id)
                            if metadata_result and metadata_result.get('success'):
                                print(f"Metadata fetched successfully for space {space_id}")
                            else:
                                print(f"Failed to fetch metadata: {metadata_result.get('error', 'Unknown error') if metadata_result else 'No result'}")
                        except Exception as metadata_err:
                            print(f"Error fetching metadata: {metadata_err}")
                        
                        # 2. Automatic MP3 trimming for leading silence
                        print("Trimming leading silence from audio...")
                        try:
                            trimmed = trim_leading_silence(output_file)
                            if trimmed:
                                print(f"Successfully trimmed leading silence from {output_file}")
                            else:
                                print("No significant leading silence detected or trimming not needed")
                        except Exception as trim_err:
                            print(f"Error trimming audio: {trim_err}")
                        
                        print("Post-download processing completed")
                        
                    except Exception as post_err:
                        print(f"Error in post-download processing: {post_err}")
                    
                    # 3. Send email notification
                    try:
                        print("Sending email notification...")
                        from components.NotificationHelper import NotificationHelper
                        
                        # Get user_id from the job
                        user_id = None
                        space_title = None
                        
                        try:
                            # Get job details from database
                            with open('db_config.json', 'r') as config_file:
                                db_config = json.load(config_file)
                                if db_config["type"] == "mysql":
                                    mysql_config = db_config["mysql"].copy()
                                    if 'use_ssl' in mysql_config:
                                        del mysql_config['use_ssl']
                                    
                                    conn = mysql.connector.connect(**mysql_config)
                                    cursor = conn.cursor(dictionary=True)
                                    
                                    # Get user_id from the job
                                    cursor.execute(
                                        "SELECT user_id FROM space_download_scheduler WHERE id = %s",
                                        (job_id,)
                                    )
                                    job_info = cursor.fetchone()
                                    if job_info:
                                        user_id = job_info['user_id']
                                    
                                    # Get space title
                                    cursor.execute(
                                        "SELECT title FROM spaces WHERE space_id = %s",
                                        (space_id,)
                                    )
                                    space_info = cursor.fetchone()
                                    if space_info:
                                        space_title = space_info['title']
                                    
                                    cursor.close()
                                    conn.close()
                        except Exception as db_err:
                            print(f"Error getting user/space info: {db_err}")
                        
                        if user_id:
                            helper = NotificationHelper()
                            success = helper.send_job_completion_email(
                                user_id=user_id,
                                job_type='download',
                                space_id=space_id,
                                space_title=space_title
                            )
                            if success:
                                print(f"Email notification sent to user {user_id}")
                            else:
                                print("Failed to send email notification")
                        else:
                            print("Could not determine user_id for email notification")
                            
                    except Exception as email_err:
                        print(f"Error sending email notification: {email_err}")
                    
                    return  # Return from child process
                else:
                    print(f"yt-dlp failed with return code {process_returncode}")
                    
                    # Determine the detailed error message to store
                    error_message = f"yt-dlp failed with return code {process_returncode}"
                    
                    # Add more specific error information if we have it
                    if space_availability_check:
                        error_message = f"{space_availability_check}. {error_message}"
                    
                    # Try to extract any error details from the output
                    error_details = []
                    try:
                        # Create a log file path for this space
                        log_dir = Path(os.path.join(base_dir, config.get("log_dir", "logs")))
                        log_file = log_dir / f"{space_id}.log"
                        
                        # Read the log file to find error details
                        if os.path.exists(log_file):
                            with open(log_file, 'r') as f:
                                # Read the last 50 lines to find errors
                                lines = f.readlines()[-50:]
                                for line in lines:
                                    line = line.strip()
                                    if any(err in line.lower() for err in ['error', 'exception', 'failed', 'not found', 'unavailable']):
                                        error_details.append(line)
                    except Exception as log_err:
                        print(f"Error reading log for detailed error message: {log_err}")
                    
                    # Add any additional details to the error message
                    if error_details:
                        error_message += f". Details: {'; '.join(error_details[-3:])}"  # Include last 3 error messages
                    
                    print(f"Final error message: {error_message}")
                    
                    # Update job as failed with the detailed message
                    space.update_download_job(
                        job_id,
                        status='failed',
                        error_message=error_message
                    )
                    return  # Return from child process
                
            except Exception as e:
                print(f"Error in download process for space {space_id}: {e}")
                
                # Create a more detailed error message
                import traceback
                error_message = str(e)
                
                # Add traceback for detailed debugging
                tb = traceback.format_exc()
                print(f"Traceback:\n{tb}")
                
                # Try to extract the most relevant part of the traceback
                tb_lines = tb.split('\n')
                if len(tb_lines) > 5:
                    # Get the last few lines which usually contain the most relevant error info
                    error_details = '; '.join(line.strip() for line in tb_lines[-5:] if line.strip())
                    if error_details and len(error_details) > 10:  # Ensure we have meaningful content
                        error_message += f". Details: {error_details}"
                
                # Include any additional context about the space availability
                if 'space_availability_check' in locals() and space_availability_check:
                    error_message = f"{space_availability_check}. {error_message}"
                
                # Update job as failed with the enhanced error message
                try:
                    space = Space()
                    space.update_download_job(
                        job_id,
                        status='failed',
                        error_message=error_message
                    )
                    print(f"Updated job status to failed with message: {error_message}")
                except Exception as update_error:
                    print(f"Failed to update job status: {update_error}")
                    
                return  # Return from child process
        else:
            # This is the parent process
            # Return the child process ID
            return pid
            
    except Exception as e:
        logger.error(f"Error forking download process: {e}")
        return None


def check_active_processes() -> None:
    """
    Check status of active download processes and handle completed ones.
    """
    global active_processes
    
    completed_jobs = []
    
    for job_id, process_info in active_processes.items():
        pid = process_info.get('pid')
        
        # Check if process is still running
        try:
            # os.waitpid with WNOHANG to check status without blocking
            result_pid, status = os.waitpid(pid, os.WNOHANG)
            
            if result_pid == 0:
                # Process still running
                continue
                
            # Process completed
            logger.info(f"Process {pid} for job {job_id} completed with status {status}")
            
            # Track compute cost for completed download
            if status == 0:  # Only track cost for successful downloads
                try:
                    # Get job details including start/end time and user_id
                    connection = db_pool.get_connection()
                    cursor = connection.cursor(dictionary=True)
                    
                    cursor.execute("""
                        SELECT user_id, space_id, start_time, end_time 
                        FROM space_download_scheduler 
                        WHERE id = %s
                    """, (job_id,))
                    job_details = cursor.fetchone()
                    
                    if job_details and job_details['user_id'] and job_details['start_time'] and job_details['end_time']:
                        user_id = job_details['user_id']
                        space_id = job_details['space_id']
                        
                        # Calculate duration
                        start_time = job_details['start_time']
                        end_time = job_details['end_time']
                        if isinstance(start_time, str):
                            start_time = datetime.datetime.fromisoformat(start_time)
                        if isinstance(end_time, str):
                            end_time = datetime.datetime.fromisoformat(end_time)
                        
                        download_duration = (end_time - start_time).total_seconds()
                        
                        # Get current user balance
                        cursor.execute("SELECT credits FROM users WHERE id = %s", (user_id,))
                        user_result = cursor.fetchone()
                        current_balance = float(user_result['credits']) if user_result else 0.0
                        
                        # Get compute cost per second
                        cursor.execute("SELECT setting_value FROM app_settings WHERE setting_name = 'compute_cost_per_second'")
                        cost_result = cursor.fetchone()
                        cost_per_second = float(cost_result['setting_value']) if cost_result else 0.001
                        
                        # Calculate total cost
                        total_cost = max(1, round(download_duration * cost_per_second))
                        
                        logger.info(f"DAEMON: Cost calculation for job {job_id} - duration={download_duration:.2f}s, cost_per_sec=${cost_per_second:.6f}, total_cost=${total_cost:.6f}")
                        
                        # Cost tracking is handled by the CostLogger in the forked process
                        logger.info(f"DAEMON: Process completed for job {job_id}, cost tracking handled by forked process - duration={download_duration:.2f}s, calculated_cost=${total_cost:.6f}")
                    else:
                        logger.info(f"DAEMON: Skipping cost tracking for job {job_id} - missing required data")
                    
                    cursor.close()
                    connection.close()
                    
                except Exception as cost_err:
                    logger.error(f"DAEMON: Error tracking compute cost for job {job_id}: {cost_err}")
            
            completed_jobs.append(job_id)
            
        except ChildProcessError:
            # Process no longer exists
            logger.info(f"Process {pid} for job {job_id} no longer exists")
            completed_jobs.append(job_id)
        except Exception as e:
            logger.error(f"Error checking process {pid} for job {job_id}: {e}")
    
    # Remove completed jobs from active processes
    for job_id in completed_jobs:
        del active_processes[job_id]


def cleanup() -> None:
    """
    Cleanup resources before exiting.
    """
    logger.info("Cleaning up resources...")
    
    # Remove PID file
    try:
        pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bg_downloader.pid')
        os.unlink(pid_file)
    except OSError:
        pass
    
    # Terminate any active child processes
    for job_id, process_info in active_processes.items():
        pid = process_info.get('pid')
        try:
            # Send SIGTERM to child process
            os.kill(pid, signal.SIGTERM)
            logger.info(f"Sent SIGTERM to process {pid} for job {job_id}")
        except OSError:
            # Process already gone
            pass


def signal_handler(signum, frame) -> None:
    """
    Handle signals to gracefully shutdown.
    
    Args:
        signum: Signal number
        frame: Current stack frame
    """
    global running
    
    logger.info(f"Received signal {signum}, shutting down...")
    running = False
    
    # For SIGINT (Ctrl+C), we need to exit immediately after cleanup
    if signum == signal.SIGINT:
        logger.info("CTRL+C detected, performing cleanup and exiting immediately")
        cleanup()
        sys.exit(0)


def main() -> None:
    """
    Main function to run the background downloader daemon.
    """
    global running, max_concurrent_downloads, config, DEBUG_MODE
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Background daemon for downloading X spaces')
    parser.add_argument('--no-daemon', action='store_true', help='Do not daemonize (run in foreground)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--scan-interval', type=int, help='Override scan interval in seconds')
    args = parser.parse_args()
    
    # Set debug mode
    DEBUG_MODE = args.debug
    if DEBUG_MODE:
        logger.setLevel(logging.DEBUG)
        logger.debug("[DEBUG] Debug mode enabled")
        
        # Configure separate debug log file
        debug_log_file = os.path.join(log_directory, 'bg_downloader_debug.log')
        debug_handler = logging.FileHandler(debug_log_file)
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(debug_handler)
        
        logger.debug(f"[DEBUG] Debug log file: {debug_log_file}")
    
    # Load configuration
    config = load_config()
    max_concurrent_downloads = config.get('max_concurrent_downloads', 5)
    scan_interval = args.scan_interval if args.scan_interval else config.get('scan_interval', 60)
    
    if DEBUG_MODE:
        logger.debug(f"[DEBUG] Configuration loaded: max_concurrent_downloads={max_concurrent_downloads}, scan_interval={scan_interval}")
        logger.debug(f"[DEBUG] Command line args: {args}")
    
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Daemonize if not in foreground mode
    if not args.no_daemon:
        daemonize()
    
    logger.info(f"Starting background downloader (max {max_concurrent_downloads} concurrent downloads)")
    
    # Create Space component
    space = None
    try:
        space = Space()
    except Exception as e:
        logger.error(f"Error initializing Space component: {e}")
        logger.info("Will retry connection in main loop")
    
    # Main loop
    try:
        reconnect_count = 0
        while running:
            try:
                # Ensure we have a valid Space component
                if space is None or not hasattr(space, 'connection') or not space.connection or not space.connection.is_connected():
                    try:
                        logger.info("Creating new database connection...")
                        space = Space()
                        
                        # Test the connection with a simple query
                        cursor = space.connection.cursor()
                        cursor.execute("SELECT 1")
                        cursor.fetchone()
                        cursor.close()
                        
                        # Reset reconnect count on successful connection
                        reconnect_count = 0
                        
                        if DEBUG_MODE:
                            # Check if the space_download_scheduler table exists
                            cursor = space.connection.cursor()
                            cursor.execute("SHOW TABLES LIKE 'space_download_scheduler'")
                            table_exists = cursor.fetchone() is not None
                            cursor.close()
                            
                            logger.debug(f"[DEBUG] space_download_scheduler table exists: {table_exists}")
                            
                            # If table exists, check for pending downloads directly
                            if table_exists:
                                cursor = space.connection.cursor(dictionary=True)
                                cursor.execute("SELECT COUNT(*) as count FROM space_download_scheduler WHERE status = 'pending'")
                                count = cursor.fetchone()['count']
                                logger.debug(f"[DEBUG] Direct count of pending jobs: {count}")
                                cursor.close()
                        
                    except Exception as e:
                        reconnect_count += 1
                        logger.error(f"Failed to create database connection (attempt {reconnect_count}): {e}")
                        logger.info("Will retry in next iteration")
                        
                        # If we've tried too many times, reset everything
                        if reconnect_count > 5:
                            logger.warning("Too many reconnect attempts, reloading database configuration")
                            # Force reload of database configuration
                            try:
                                # Reload config
                                if os.path.exists('db_config.json'):
                                    with open('db_config.json', 'r') as config_file:
                                        db_config = json.load(config_file)
                                        logger.info(f"Reloaded DB config: {db_config['type']}")
                            except Exception as config_e:
                                logger.error(f"Error reloading config: {config_e}")
                                
                        time.sleep(5)  # Wait before retrying
                        continue
                # Check active processes first
                check_active_processes()
                
                # Only scan for new downloads if we're below max concurrent
                if len(active_processes) < max_concurrent_downloads:
                    if DEBUG_MODE:
                        logger.debug(f"[DEBUG] Currently running {len(active_processes)} processes, below maximum of {max_concurrent_downloads}")
                        logger.debug(f"[DEBUG] Active processes: {list(active_processes.keys())}")
                    
                    # Scan for pending downloads
                    pending_jobs = scan_for_pending_downloads(space)
                    
                    # Process pending jobs up to max concurrent limit
                    available_slots = max_concurrent_downloads - len(active_processes)
                    
                    # If we didn't find any jobs but we know there should be one, try a direct database check
                    if not pending_jobs and DEBUG_MODE:
                        logger.debug("[DEBUG] No jobs found through Space.list_download_jobs, attempting direct DB query")
                        try:
                            # Create a direct cursor to query the database
                            cursor = space.connection.cursor(dictionary=True)
                            cursor.execute("SELECT * FROM space_download_scheduler WHERE status = 'pending' ORDER BY id DESC LIMIT %s", (available_slots,))
                            direct_jobs = cursor.fetchall()
                            cursor.close()
                            
                            if direct_jobs:
                                logger.debug(f"[DEBUG] Found {len(direct_jobs)} jobs with direct DB query")
                                pending_jobs = direct_jobs
                        except Exception as direct_e:
                            logger.error(f"Error with direct DB query: {direct_e}")
                    
                    if DEBUG_MODE and pending_jobs:
                        logger.debug(f"[DEBUG] Processing {min(len(pending_jobs), available_slots)} of {len(pending_jobs)} pending jobs with {available_slots} available slots")
                    
                    # Track how many new processes we start in this iteration
                    new_processes_count = 0
                    max_new_processes = min(len(pending_jobs), available_slots)
                    
                    # Track spaces that are being processed to avoid duplicates
                    space_ids_being_processed = set()
                    
                    # First, collect all spaces that are already being processed
                    for active_job_id, process_info in active_processes.items():
                        if 'space_id' in process_info:
                            space_ids_being_processed.add(process_info['space_id'])
                    
                    if DEBUG_MODE:
                        logger.debug(f"[DEBUG] Currently processing spaces: {list(space_ids_being_processed)}")
                    
                    # Process each pending job
                    for job in pending_jobs:
                        # Exit loop if we've started the maximum allowed new processes
                        if new_processes_count >= max_new_processes:
                            if DEBUG_MODE:
                                logger.debug(f"[DEBUG] Started maximum of {new_processes_count} new processes this iteration")
                            break
                            
                        job_id = job.get('id')
                        space_id = job.get('space_id')
                        
                        # Ensure file_type is always one of the supported formats
                        file_type = job.get('file_type', 'mp3')
                        # Normalize file_type to lowercase and ensure it's a valid format
                        if isinstance(file_type, str):
                            file_type = file_type.lower()
                        if file_type not in ['mp3', 'm4a', 'wav']:
                            logger.warning(f"Invalid file_type '{file_type}' for job {job_id}, defaulting to mp3")
                            file_type = 'mp3'
                        
                        # Skip if this job is already in active_processes
                        if job_id in active_processes:
                            if DEBUG_MODE:
                                logger.debug(f"[DEBUG] Job {job_id} is already being processed, skipping")
                            continue
                            
                        # Skip if any job for this space_id is already being processed
                        if space_id in space_ids_being_processed:
                            if DEBUG_MODE:
                                logger.debug(f"[DEBUG] Space {space_id} is already being processed in another job, skipping job {job_id}")
                            
                            # Mark other jobs with same space_id as "in_progress" with NULL process_id to avoid processing them separately
                            try:
                                # Create a direct database connection to update status
                                with open('db_config.json', 'r') as config_file:
                                    db_config = json.load(config_file)
                                    if db_config["type"] == "mysql":
                                        mysql_config = db_config["mysql"].copy()
                                        if 'use_ssl' in mysql_config:
                                            del mysql_config['use_ssl']
                                            
                                        conn = mysql.connector.connect(**mysql_config)
                                        cursor = conn.cursor()
                                        
                                        # Update the job status to in_progress but with NULL process_id
                                        # This prevents other processes from picking it up while not tying it to this process
                                        update_query = """
                                        UPDATE space_download_scheduler
                                        SET status = 'in_progress', process_id = NULL, updated_at = NOW()
                                        WHERE id = %s AND status = 'pending'
                                        """
                                        cursor.execute(update_query, (job_id,))
                                        conn.commit()
                                        cursor.close()
                                        conn.close()
                                        
                                        if DEBUG_MODE:
                                            logger.debug(f"[DEBUG] Marked duplicate job {job_id} for space {space_id} as 'in_progress' with NULL process_id")
                            except Exception as update_err:
                                logger.error(f"Error updating duplicate job status: {update_err}")
                            
                            continue
                            
                        # Add this space_id to the set of spaces being processed
                        space_ids_being_processed.add(space_id)
                        
                        if DEBUG_MODE:
                            logger.debug(f"[DEBUG] Starting to process job {job_id} for space {space_id}, file type: {file_type}")
                        
                        logger.info(f"Processing job {job_id} for space {space_id}")
                        
                        # Claim the download job
                        if claim_download_job(space, job_id):
                            # Fork a new process for the download
                            child_pid = fork_download_process(job_id, space_id, file_type)
                            
                            # If child_pid is None but the job wasn't marked as failed, 
                            # it might mean the file already exists and was marked completed
                            if child_pid:
                                logger.info(f"Started download process {child_pid} for job {job_id}")
                                
                                # Store process info
                                active_processes[job_id] = {
                                    'pid': child_pid,
                                    'space_id': space_id,
                                    'start_time': datetime.datetime.now()
                                }
                                
                                # Increment the counter of new processes started
                                new_processes_count += 1
                            elif child_pid is None:
                                # Check if the file exists in the downloads directory
                                download_dir = Path(os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                                    config.get("download_dir", "downloads")))
                                expected_file = download_dir / f"{space_id}.{file_type}"
                                
                                if expected_file.exists() and os.path.getsize(expected_file) > 0:
                                    logger.info(f"File for job {job_id} (space {space_id}) already exists and was marked as completed")
                                else:
                                    logger.error(f"Failed to start download process for job {job_id}")
                                    
                                    # Update job as failed
                                    space.update_download_job(
                                        job_id,
                                        status='failed',
                                        error_message='Failed to start download process'
                                    )
                        else:
                            logger.error(f"Failed to claim job {job_id}")
                    
                    # If we didn't start any processes but there are pending jobs, log it
                    if new_processes_count == 0 and pending_jobs:
                        logger.warning(f"Found {len(pending_jobs)} pending jobs but didn't start any new processes")
                        
                    # If we did start processes, log it
                    if new_processes_count > 0:
                        logger.info(f"Started {new_processes_count} new download processes this iteration")
                
                # Sleep before next scan, but check if we should exit
                if DEBUG_MODE:
                    logger.debug(f"[DEBUG] Sleeping for {scan_interval} seconds before next scan (checking signals every 10 seconds)")
                
                for i in range(min(scan_interval, 10)):  # Never wait more than 10 seconds without checking signals
                    if not running:
                        break
                    time.sleep(1)
                    
                    # Log sleep countdown only every 10 seconds to avoid log spam
                    if DEBUG_MODE and i > 0 and i % 10 == 0:
                        logger.debug(f"[DEBUG] Sleep progress: {i}/{scan_interval} seconds")
                
            except KeyboardInterrupt:
                logger.info("KeyboardInterrupt inside loop, exiting...")
                running = False
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                logger.info("Continuing operation...")
                time.sleep(5)  # Brief pause after error
                
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt in main try/except, shutting down...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        # Cleanup resources
        cleanup()


if __name__ == "__main__":
    main()