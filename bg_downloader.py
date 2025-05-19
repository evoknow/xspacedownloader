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

# Ensure we're using the virtual environment
VENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'venv')
VENV_ACTIVATE = os.path.join(VENV_PATH, 'bin', 'activate')

# If this script is not run with the virtual environment Python,
# try to re-execute it with the virtual environment Python
if not hasattr(sys, 'real_prefix') and not sys.prefix == VENV_PATH:
    if os.path.exists(os.path.join(VENV_PATH, 'bin', 'python')):
        venv_python = os.path.join(VENV_PATH, 'bin', 'python')
        os.execl(venv_python, venv_python, *sys.argv)
    else:
        print(f"Warning: Virtual environment not found at {VENV_PATH}")
        print("Trying to continue with system Python...")

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
            "scan_interval": 60,  # seconds
            "download_dir": "./downloads",
            "log_dir": "./logs"
        }
    except json.JSONDecodeError:
        logger.error("Error parsing mainconfig.json, using default configuration")
        return {
            "max_concurrent_downloads": 5,
            "scan_interval": 60,  # seconds
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


def fork_download_process(job_id: int, space_id: str, file_type: str = 'mp3') -> Optional[int]:
    """
    Fork a new process to handle the download.
    
    Args:
        job_id (int): Download job ID
        space_id (str): Space ID to download
        file_type (str): Output file type (mp3, wav, etc)
        
    Returns:
        Optional[int]: Child process ID if successful, None otherwise
    """
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
                            """
                            space_url = f"https://x.com/i/spaces/{space_id}"
                            filename = f"{space_id}.{file_type}"
                            cursor.execute(insert_space_query, (space_id, space_url, filename, str(file_size)))
                        
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
                                    """
                                    filename = f"{space_id}.{file_type}"
                                    cursor.execute(insert_query, (space_id, space_url, filename))
                                    conn.commit()
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
                            update_query = """
                            UPDATE space_download_scheduler 
                            SET status = 'in_progress', process_id = %s, 
                                updated_at = NOW()
                            WHERE id = %s
                            """
                            cursor.execute(update_query, (process_id, job_id))
                            
                            # Also update the space record to show downloading
                            update_space_query = """
                            UPDATE spaces
                            SET status = 'downloading', download_cnt = 1
                            WHERE space_id = %s
                            """
                            cursor.execute(update_space_query, (space_id,))
                            
                            conn.commit()
                            cursor.close()
                            conn.close()
                            
                            print(f"Updated job {job_id} status to 'in_progress' with process ID {process_id}")
                            
                except Exception as update_err:
                    print(f"Error updating job status in database: {update_err}")
                    # Fall back to using the Space component methods
                    space.update_download_progress_by_space(space_id, 0, 1, 'downloading')
                    space.update_download_job(job_id, status='in_progress', process_id=process_id)
                
                print("Starting download with yt-dlp...")
                
                # Check if yt-dlp is installed
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
                
                # Create a temporary filename for download
                temp_output = str(output_file) + ".part"
                
                # Ensure the directory exists
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                
                # Set up yt-dlp command to download the actual audio file
                yt_dlp_cmd = [
                    yt_dlp_path,
                    "--extract-audio",
                    "--audio-format", file_type,
                    "--audio-quality", "0",  # Best quality
                    "--output", str(output_file),
                    "--no-progress",  # Don't show progress bar (cleaner logs)
                    "--no-warnings",  # Reduce log spam
                    "--no-playlist",  # Don't download playlists
                    space_url
                ]
                
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
                
                # Run yt-dlp as a subprocess and capture output
                process = subprocess.Popen(
                    yt_dlp_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1
                )
                
                # Process output line by line to track progress
                progress = 0
                last_size_update_time = time.time()
                last_part_check_time = time.time()
                force_update_needed = True  # Start with a forced update to show immediate progress
                
                for line in iter(process.stdout.readline, ''):
                    print(line, end='')
                    
                    # Always check part file size at regular intervals
                    current_time = time.time()
                    if current_time - last_part_check_time >= 5:  # Check part file every 5 seconds
                        try:
                            part_file = str(output_file) + ".part"
                            if os.path.exists(part_file):
                                file_size = os.path.getsize(part_file)
                                # Record that we have a part file and its size
                                force_update_needed = True  # Force an update when we detect file size change
                                print(f"Part file detected: {part_file}, Size: {file_size} bytes")
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
                            
                            # Use a minimum reasonable file size to show progress
                            if not download_size_found or size_mb < 1024:
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
                                        
                                        # Update the job status with current progress
                                        job_update_query = """
                                        UPDATE space_download_scheduler 
                                        SET status = 'in_progress', process_id = %s, 
                                            progress_in_percent = %s, progress_in_size = %s,
                                            updated_at = NOW()
                                        WHERE id = %s
                                        """
                                        cursor.execute(job_update_query, (
                                            os.getpid(), progress, int(size_mb), job_id
                                        ))
                                        
                                        # Also update the space record
                                        space_update_query = """
                                        UPDATE spaces
                                        SET status = 'downloading', download_cnt = %s
                                        WHERE space_id = %s
                                        """
                                        cursor.execute(space_update_query, (progress, space_id))
                                        
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
                
                # Check part file size every 5 seconds regardless of output to ensure progress updates
                last_update_time = time.time()
                part_check_counter = 0
                
                while process.poll() is None:  # While process is still running
                    current_time = time.time()
                    # Check every 5 seconds
                    if current_time - last_update_time >= 5:
                        part_check_counter += 1
                        try:
                            # Check part file size
                            part_file = str(output_file) + ".part"
                            if os.path.exists(part_file):
                                file_size = os.path.getsize(part_file)
                                print(f"Periodic check: part file size = {file_size} bytes")
                                
                                # Get a size estimate for total file
                                total_size_estimate = file_size
                                
                                # If we have a progress percent, create a total size estimate
                                if progress > 0 and progress < 100:
                                    # Only estimate if we have a reasonable progress %
                                    if progress >= 1:  # at least 1%
                                        total_size_estimate = int(file_size * 100 / progress)
                                        print(f"Estimated total size: {total_size_estimate} bytes (from {progress}%)")
                                
                                # Even if progress is 0, we should update the database with current part file size
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
                                            
                                            # For new downloads with no progress yet, set progress to at least 1%
                                            # This helps show some progress on the frontend
                                            current_percent = progress
                                            if progress == 0 and file_size > 1024*1024:  # If size > 1MB
                                                current_percent = 1  # Show at least 1% progress
                                            
                                            # If we see actual progress is 0% but we have a significant file part, estimate progress
                                            if progress == 0 and file_size > 10*1024*1024:  # > 10MB
                                                # Estimate progress based on typical file sizes
                                                # Audio files are typically 30-100MB
                                                estimated_percent = max(1, min(10, int(file_size / (1024*1024) / 5)))
                                                current_percent = estimated_percent
                                                print(f"Estimating progress as {estimated_percent}% based on file size")
                                            
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
                                            
                                            # Every third check, update the estimate if progress > 5%
                                            if part_check_counter % 3 == 0 and progress > 5 and total_size_estimate > file_size:
                                                size_to_update = total_size_estimate
                                                print(f"Updating with estimated total size: {size_to_update}")
                                            else:
                                                print(f"Updating with current part size: {size_to_update}")
                                            
                                            cursor.execute(job_update_query, (
                                                os.getpid(), size_to_update, current_percent, job_id
                                            ))
                                            
                                            # Also update the space record status
                                            space_update_query = """
                                            UPDATE spaces
                                            SET status = 'downloading' 
                                            WHERE space_id = %s
                                            """
                                            cursor.execute(space_update_query, (space_id,))
                                            
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
                    
                    # Update space record as completed
                    space.update_download_progress(
                        space_id,
                        progress=100,
                        file_size=file_size
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
                                    update_query = """
                                    UPDATE spaces 
                                    SET status = 'completed', format = %s, 
                                        updated_at = NOW(), downloaded_at = NOW()
                                    WHERE space_id = %s
                                    """
                                    cursor.execute(update_query, (str(file_size), space_id))
                                else:
                                    # Insert new space record with status 'completed' and download_cnt 0
                                    insert_query = """
                                    INSERT INTO spaces 
                                    (space_id, space_url, filename, status, download_cnt, format, created_at, updated_at, downloaded_at)
                                    VALUES (%s, %s, %s, 'completed', 0, %s, NOW(), NOW(), NOW())
                                    """
                                    # Use space details URL if available or construct one
                                    space_url = space_details.get('space_url') if space_details else f"https://x.com/i/spaces/{space_id}"
                                    filename = f"{space_id}.{file_type}"
                                    cursor.execute(insert_query, (space_id, space_url, filename, str(file_size)))
                                
                                conn.commit()
                                cursor.close()
                                conn.close()
                                print(f"Added/updated space record in spaces table with status 'completed'")
                    except Exception as spaces_err:
                        print(f"Error updating spaces table: {spaces_err}")
                    
                    print(f"Download completed for space {space_id}")
                    sys.exit(0)  # Exit successfully
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
                    sys.exit(1)  # Exit with error
                
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
                    
                sys.exit(1)  # Exit with error
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
                        file_type = job.get('file_type', 'mp3')
                        
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