#!/usr/bin/env python3
# components/DownloadSpace.py

"""
DownloadSpace Component for XSpace Downloader

This component handles downloading of X space audio using yt-dlp.
It supports both synchronous and asynchronous downloading, with progress
tracking through the space_download_scheduler table.

Features:
- Download X space audio in various formats (mp3, wav, etc.)
- Asynchronous downloads with progress tracking
- Regular progress updates to the database
- Support for multiple concurrent downloads
- Extraction of space ID from X space URLs

Usage Examples:
    
    # Basic synchronous usage
    from components.DownloadSpace import DownloadSpace
    downloader = DownloadSpace()
    file_path = downloader.download("https://x.com/i/spaces/1dRJZEpyjlNGB")
    
    # Asynchronous download with custom file type
    job_id = downloader.download(
        "https://x.com/i/spaces/1dRJZEpyjlNGB",
        file_type="wav",
        async_mode=True
    )
    
    # Get status of an asynchronous download
    status = downloader.get_download_status(job_id)
"""

import os
import re
import sys
import json
import time
import signal
import shutil
import tempfile
import subprocess
import mysql.connector
import logging
from pathlib import Path
from datetime import datetime
from mysql.connector import Error

# Configure logging
LOG_FILE = "download_space.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('DownloadSpace')

# Import Space component for space_id extraction and database operations
try:
    from components.Space import Space
except ImportError:
    # If this file is executed directly for testing
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from components.Space import Space

class DownloadSpace:
    """
    Class to handle downloading X space audio using yt-dlp.
    Supports synchronous and asynchronous downloads with progress tracking.
    """
    
    # Constants
    DEFAULT_DOWNLOAD_DIR = "downloads"
    SUPPORTED_FORMATS = ["mp3", "wav", "m4a", "ogg", "flac"]
    
    # Get path to yt-dlp in virtual environment if available
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        # We're in a virtual environment
        if sys.platform == 'win32':
            YT_DLP_BINARY = os.path.join(sys.prefix, "Scripts", "yt-dlp.exe")
        else:
            YT_DLP_BINARY = os.path.join(sys.prefix, "bin", "yt-dlp")
    else:
        # Try to use yt-dlp from PATH
        YT_DLP_BINARY = "yt-dlp"
    
    def __init__(self, db_connection=None, download_dir=None):
        """Initialize the DownloadSpace component with optional database connection and download directory."""
        # Initialize Space component for database operations
        self.space_component = Space(db_connection)
        
        # Set download directory
        self.download_dir = download_dir or self.DEFAULT_DOWNLOAD_DIR
        
        # Create download directory if it doesn't exist
        os.makedirs(self.download_dir, exist_ok=True)
    
    def extract_space_id(self, url):
        """
        Extract space_id from X space URL.
        
        Args:
            url (str): The X space URL
            
        Returns:
            str: space_id if found, None otherwise
        """
        return self.space_component.extract_space_id(url)
    
    def _check_yt_dlp_installed(self):
        """
        Check if yt-dlp is installed and available.
        
        Returns:
            bool: True if installed, False otherwise
        """
        print(f"Checking for yt-dlp at: {self.YT_DLP_BINARY}")
        
        # First try the binary approach
        binary_available = False
        if os.path.isfile(self.YT_DLP_BINARY) or shutil.which(self.YT_DLP_BINARY):
            try:
                # Try to run yt-dlp --version
                result = subprocess.run(
                    [self.YT_DLP_BINARY, "--version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                if result.returncode == 0:
                    print(f"yt-dlp binary found: {result.stdout.strip()}")
                    return True
                else:
                    print(f"Error running yt-dlp binary: {result.stderr}")
                    binary_available = False
            except Exception as e:
                print(f"Error running yt-dlp binary: {str(e)}")
                binary_available = False
        else:
            print(f"yt-dlp binary not found at {self.YT_DLP_BINARY} and not in PATH")
            binary_available = False
        
        # If binary approach failed, try module approach
        if not binary_available:
            print("Trying module-based approach for yt-dlp...")
            try:
                # Try to run python -m yt_dlp --version
                result = subprocess.run(
                    [sys.executable, "-m", "yt_dlp", "--version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                if result.returncode == 0:
                    print(f"yt-dlp module found: {result.stdout.strip()}")
                    return True
                else:
                    print(f"Error running yt-dlp module: {result.stderr}")
            except Exception as e:
                print(f"Error running yt-dlp module: {str(e)}")
        
        # If we got here, neither approach worked, try to find yt-dlp in venv
        print("Looking for yt-dlp in virtual environment...")
        venv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "venv")
        possible_yt_dlp_paths = [
            os.path.join(venv_path, "bin", "yt-dlp"),
            os.path.join(venv_path, "Scripts", "yt-dlp.exe")
        ]
        
        for path in possible_yt_dlp_paths:
            if os.path.isfile(path):
                print(f"Found yt-dlp at: {path}")
                self.YT_DLP_BINARY = path
                return True
                
        print("Error: yt-dlp is not installed or not in PATH.")
        print("Please install it with: pip install yt-dlp")
        return False
    
    def _get_output_filename(self, space_id, file_type):
        """
        Generate an output filename for the downloaded space.
        
        Args:
            space_id (str): The space ID
            file_type (str): The output file type
            
        Returns:
            str: The full path to the output file
        """
        # Get space details if available to use title
        space_details = self.space_component.get_space(space_id)
        
        if space_details and 'title' in space_details:
            # Create a safe filename from title with yt-dlp template
            title = space_details['title']
            safe_title = re.sub(r'[^\w\s-]', '', title)
            safe_title = re.sub(r'[\s-]+', '_', safe_title)
            filename_template = f"{safe_title}_{space_id}.%(ext)s"
        else:
            # Use just the space_id if no title available with yt-dlp template
            filename_template = f"{space_id}.%(ext)s"
        
        # Return the full path template for yt-dlp
        return os.path.join(self.download_dir, filename_template)
    
    def _progress_hook(self, d, job_id=None, space_id=None):
        """
        Progress hook function for yt-dlp.
        Updates the download progress in the database.
        
        Args:
            d (dict): Progress information from yt-dlp
            job_id (int, optional): The download job ID for tracking in the database
            space_id (str, optional): The space ID for tracking in the database
        """
        if d['status'] == 'downloading':
            # Extract progress information
            downloaded_bytes = d.get('downloaded_bytes', 0)
            total_bytes = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
            
            # Calculate progress
            progress_in_mb = round(downloaded_bytes / (1024 * 1024), 2)
            progress_percent = int((downloaded_bytes / total_bytes * 100) if total_bytes else 0)
            
            # Limit to 100%
            progress_percent = min(progress_percent, 100)
            
            # Update progress in database if we have job_id or space_id
            if job_id:
                self.space_component.update_download_job(
                    job_id,
                    progress_in_size=progress_in_mb,
                    progress_in_percent=progress_percent
                )
            elif space_id:
                self.space_component.update_download_progress_by_space(
                    space_id,
                    progress_in_mb,
                    progress_percent
                )
                
            # Also update the normal space progress for compatibility
            if space_id:
                self.space_component.update_download_progress(
                    space_id, 
                    progress_percent,
                    file_size=downloaded_bytes
                )
                
            # Print progress
            print(f"\rDownloading: {progress_percent}% ({progress_in_mb:.2f} MB)", end="")
            
        elif d['status'] == 'finished':
            # Extract final file size
            downloaded_bytes = d.get('downloaded_bytes', 0)
            progress_in_mb = round(downloaded_bytes / (1024 * 1024), 2)
            
            # Update status in database
            if job_id:
                self.space_component.update_download_job(
                    job_id,
                    progress_in_size=progress_in_mb,
                    progress_in_percent=100,
                    status='completed'
                )
            elif space_id:
                self.space_component.update_download_progress_by_space(
                    space_id,
                    progress_in_mb,
                    100,
                    status='completed'
                )
                
            # Also update the normal space progress for compatibility
            if space_id:
                self.space_component.update_download_progress(
                    space_id, 
                    100,
                    file_size=downloaded_bytes
                )
                
            print(f"\nDownload completed: {progress_in_mb:.2f} MB")
    
    def _build_yt_dlp_command(self, url, output_path, file_type):
        """
        Build the yt-dlp command.
        
        Args:
            url (str): The X space URL
            output_path (str): The output file path
            file_type (str): The output file type
            
        Returns:
            list: The yt-dlp command as a list
        """
        # Check if we need to use module approach (-m yt_dlp) instead of binary
        use_module_approach = False
        
        if not os.path.isfile(self.YT_DLP_BINARY) and not shutil.which(self.YT_DLP_BINARY):
            # If binary not found, use the module approach
            print("Using module-based approach for yt-dlp")
            use_module_approach = True
        
        # Basic command
        if use_module_approach:
            # Use module approach
            python_bin = sys.executable
            command = [
                python_bin,
                "-m", "yt_dlp",
                "--verbose",
                "--print-traffic",
                "--extract-audio",
                f"--audio-format={file_type}",
                "--audio-quality=0",  # Best quality
                "--continue",  # Resume partial downloads
                "--no-warnings",
                "--no-playlist",  # Only download single item
                "--user-agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "--add-header", "Accept:*/*",
                "--add-header", "Accept-Language:en-US,en;q=0.9",
                "-o", output_path
            ]
        else:
            # Use binary approach
            command = [
                self.YT_DLP_BINARY,
                "--verbose",
                "--print-traffic",
                "--extract-audio",
                f"--audio-format={file_type}",
                "--audio-quality=0",  # Best quality
                "--continue",  # Resume partial downloads
                "--no-warnings",
                "--no-playlist",  # Only download single item
                "--user-agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "--add-header", "Accept:*/*",
                "--add-header", "Accept-Language:en-US,en;q=0.9",
                "-o", output_path
            ]
        
        # Add URL
        command.append(url)
        
        print(f"Command: {' '.join(command)}")
        return command
    
    def _create_user_friendly_error_message(self, stdout_output, stderr_output, return_code):
        """
        Create a user-friendly error message from yt-dlp output.
        
        Args:
            stdout_output (str): Standard output from yt-dlp
            stderr_output (str): Standard error from yt-dlp
            return_code (int): Exit code from yt-dlp
            
        Returns:
            str: User-friendly error message
        """
        combined_output = f"{stdout_output} {stderr_output}".lower()
        
        # Check for Twitter/X infrastructure issues
        if any(indicator in combined_output for indicator in [
            'http error 403', 'http error 500', 'http error 502', 'http error 503',
            'client error accessing space', 'internal server error', 'over capacity',
            'timeout', 'unable to download json metadata'
        ]):
            return ("X (Twitter) servers are currently experiencing issues or rate limiting. "
                   "This is a temporary problem on X's side. Please try again in a few minutes or hours. "
                   "You can also try a different space to see if the issue affects all spaces.")
        
        # Check for space-specific issues
        if any(indicator in combined_output for indicator in [
            'private', 'not found', '404', 'unavailable', 'deleted'
        ]):
            return ("This space may be private, deleted, or no longer available. "
                   "Please check that the space URL is correct and the space is still accessible.")
        
        # Check for network connectivity issues
        if any(indicator in combined_output for indicator in [
            'connection refused', 'network unreachable', 'no route to host',
            'connection timed out', 'dns'
        ]):
            return ("Network connectivity issue detected. Please check your internet connection and try again.")
        
        # Check for authentication issues
        if any(indicator in combined_output for indicator in [
            'unauthorized', 'authentication', 'login required'
        ]):
            return ("Authentication issue with X (Twitter). This may be due to API changes or access restrictions.")
        
        # Check for yt-dlp specific issues
        if any(indicator in combined_output for indicator in [
            'unsupported url', 'no video formats found', 'extractor'
        ]):
            return ("The space format is not supported or yt-dlp needs an update. Please try updating yt-dlp.")
        
        # For other errors, provide a generic but helpful message
        if 'http error' in combined_output:
            return ("X (Twitter) returned an error. This is usually temporary. Please try again later.")
        
        # Fallback for unknown errors - still more user-friendly than raw output
        return (f"Download failed (error code {return_code}). This may be due to X (Twitter) server issues "
               "or changes to their system. Please try again later or contact support if the problem persists.")
    
    def download(self, space_url, file_type="mp3", async_mode=True, user_id=0):
        """
        Download X space audio.
        
        Args:
            space_url (str): The X space URL
            file_type (str, optional): The output file type. Defaults to "mp3".
            async_mode (bool, optional): Whether to download asynchronously. Defaults to True.
            user_id (int, optional): User ID for tracking. Defaults to 0.
            
        Returns:
            If async_mode is True: int (job ID) or None on error
            If async_mode is False: str (output file path) or None on error
        """
        logger.info(f"Starting download: URL={space_url}, file_type={file_type}, async_mode={async_mode}, user_id={user_id}")
        
        try:
            # Validate file type
            file_type = file_type.lower()
            if file_type not in self.SUPPORTED_FORMATS:
                error_msg = f"Unsupported file type '{file_type}'. Supported formats: {', '.join(self.SUPPORTED_FORMATS)}"
                logger.error(error_msg)
                print(f"Error: {error_msg}")
                return None
            
            # Check if yt-dlp is installed
            if not self._check_yt_dlp_installed():
                logger.error("yt-dlp is not installed or not available")
                return None
            
            # Extract space_id from URL
            space_id = self.extract_space_id(space_url)
            if not space_id:
                error_msg = f"Could not extract space ID from URL: {space_url}"
                logger.error(error_msg)
                print(f"Error: {error_msg}")
                return None
            
            logger.info(f"Extracted space_id: {space_id}")
            
            # Check if the file already exists
            # First check for exact space_id.file_type format
            exact_file_path = os.path.join(self.download_dir, f"{space_id}.{file_type}")
            if os.path.exists(exact_file_path):
                logger.info(f"File already exists: {exact_file_path}")
                print(f"File already exists: {os.path.basename(exact_file_path)}")
                return exact_file_path
            
            # Also check if any file containing the space_id with the requested extension exists
            existing_files = []
            if os.path.exists(self.download_dir):
                for file in os.listdir(self.download_dir):
                    if space_id in file and file.endswith(f".{file_type}"):
                        existing_files.append(file)
            
            if existing_files:
                existing_file = os.path.join(self.download_dir, existing_files[0])
                logger.info(f"File already exists with different name: {existing_file}")
                print(f"File already exists: {os.path.basename(existing_file)}")
                return existing_file
            
            # Get or create the space record in database
            try:
                if not self.space_component.get_space(space_id):
                    logger.info(f"Creating new space record for space_id: {space_id}")
                    self.space_component.create_space(
                        space_url,
                        title=f"X Space {space_id}",
                        notes=f"Downloaded at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        user_id=user_id
                    )
            except Exception as e:
                logger.error(f"Error getting/creating space record: {str(e)}")
                # Continue anyway, as this isn't critical
            
            # Generate output filename
            output_path = self._get_output_filename(space_id, file_type)
            logger.info(f"Output path: {output_path}")
            
            # Create a download job in the database
            try:
                job_id = self.space_component.create_download_job(
                    space_id=space_id,
                    user_id=user_id,
                    file_type=file_type
                )
                
                if not job_id:
                    error_msg = "Failed to create download job in the database."
                    logger.error(error_msg)
                    print(f"Error: {error_msg}")
                    return None
                
                logger.info(f"Created download job with ID: {job_id}")
                
                # Update job status to pending
                self.space_component.update_download_job(
                    job_id,
                    status='pending'
                )
            except Exception as e:
                error_msg = f"Error creating download job: {str(e)}"
                logger.error(error_msg)
                print(f"Error: {error_msg}")
                return None
                
            if async_mode:
                # Start download in a new process
                logger.info(f"Starting asynchronous download for job_id: {job_id}")
                return self._download_async(
                    space_url=space_url,
                    space_id=space_id,
                    job_id=job_id,
                    output_path=output_path,
                    file_type=file_type
                )
            else:
                # Download synchronously
                logger.info(f"Starting synchronous download for job_id: {job_id}")
                return self._download_sync(
                    space_url=space_url,
                    space_id=space_id,
                    job_id=job_id,
                    output_path=output_path,
                    file_type=file_type
                )
        except Exception as e:
            error_msg = f"Unexpected error in download: {str(e)}"
            logger.error(error_msg, exc_info=True)
            print(f"Error: {error_msg}")
            return None
    
    def _download_sync(self, space_url, space_id, job_id, output_path, file_type):
        """
        Download X space audio synchronously.
        
        Args:
            space_url (str): The X space URL
            space_id (str): The space ID
            job_id (int): The download job ID
            output_path (str): The output file path
            file_type (str): The output file type
            
        Returns:
            str: The output file path if successful, None otherwise
        """
        try:
            # Update job status to in_progress
            self.space_component.update_download_job(
                job_id,
                status='in_progress',
                process_id=os.getpid()
            )
            
            # Build the yt-dlp command
            command = self._build_yt_dlp_command(space_url, output_path, file_type)
            
            # Create a temporary directory for the download
            with tempfile.TemporaryDirectory() as temp_dir:
                # Modify the command to use the temporary directory
                temp_output_path = os.path.join(temp_dir, f"{space_id}.%(ext)s")
                command[command.index("-o") + 1] = temp_output_path
                
                # Run the command with enhanced debugging
                print(f"Running yt-dlp command: {' '.join(command)}")
                print(f"Working directory: {temp_dir}")
                print(f"Space URL: {space_url}")
                print("=" * 50)
                
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                # Initialize progress tracking variables
                last_progress_update = time.time()
                progress_update_interval = 1.0  # seconds
                
                # Read output line by line to track progress
                while True:
                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break
                    
                    # Parse progress from yt-dlp output
                    if "[download]" in line and "%" in line:
                        try:
                            # Extract percentage and size
                            percent_match = re.search(r"(\d+\.\d+)%", line)
                            size_match = re.search(r"(\d+\.\d+)(\w+)", line)
                            
                            if percent_match and size_match:
                                percent = float(percent_match.group(1))
                                size_value = float(size_match.group(1))
                                size_unit = size_match.group(2)
                                
                                # Convert size to MB
                                if size_unit == "KiB":
                                    size_mb = size_value / 1024
                                elif size_unit == "MiB":
                                    size_mb = size_value
                                elif size_unit == "GiB":
                                    size_mb = size_value * 1024
                                else:
                                    size_mb = 0
                                
                                # Update progress in database at intervals
                                current_time = time.time()
                                if current_time - last_progress_update >= progress_update_interval:
                                    self._progress_hook(
                                        {
                                            'status': 'downloading',
                                            'downloaded_bytes': size_mb * 1024 * 1024,
                                            'total_bytes': (size_mb * 1024 * 1024) / (percent / 100) if percent > 0 else 0
                                        },
                                        job_id=job_id,
                                        space_id=space_id
                                    )
                                    last_progress_update = current_time
                        except Exception as e:
                            print(f"Error parsing progress: {e}")
                    
                    # Print the output
                    print(line, end="")
                
                # Get the return code
                return_code = process.poll()
                
                # Check for errors
                if return_code != 0:
                    try:
                        stdout_output = process.stdout.read() if process.stdout else ""
                        stderr_output = process.stderr.read() if process.stderr else ""
                    except Exception as e:
                        stdout_output = f"Error reading stdout: {e}"
                        stderr_output = f"Error reading stderr: {e}"
                    
                    print(f"Error during download (exit code {return_code}): {stderr_output}")
                    
                    # Create user-friendly error message
                    error_message = self._create_user_friendly_error_message(stdout_output, stderr_output, return_code)
                    
                    # Update job status to failed
                    self.space_component.update_download_job(
                        job_id,
                        status='failed',
                        error_message=error_message
                    )
                    
                    return None
                
                # Find the downloaded file in the temporary directory
                downloaded_files = [f for f in os.listdir(temp_dir) if f.startswith(space_id)]
                
                if not downloaded_files:
                    print("Error: No downloaded file found.")
                    self.space_component.update_download_job(
                        job_id,
                        status='failed',
                        error_message="No downloaded file found after successful download."
                    )
                    return None
                
                # Move the downloaded file to the final location
                downloaded_file = os.path.join(temp_dir, downloaded_files[0])
                
                # Ensure the destination directory exists
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                # Move the file
                shutil.move(downloaded_file, output_path)
                
                # Update job status to completed
                self._progress_hook(
                    {
                        'status': 'finished',
                        'downloaded_bytes': os.path.getsize(output_path)
                    },
                    job_id=job_id,
                    space_id=space_id
                )
                
                print(f"Download completed: {output_path}")
                return output_path
                
        except Exception as e:
            print(f"Error during synchronous download: {e}")
            
            # Update job status to failed
            self.space_component.update_download_job(
                job_id,
                status='failed',
                error_message=str(e)
            )
            
            return None
    
    def _download_async(self, space_url, space_id, job_id, output_path, file_type):
        """
        Download X space audio asynchronously.
        
        Args:
            space_url (str): The X space URL
            space_id (str): The space ID
            job_id (int): The download job ID
            output_path (str): The output file path
            file_type (str): The output file type
            
        Returns:
            int: The download job ID if successful, None otherwise
        """
        try:
            # Update job to store the parent process ID initially
            try:
                self.space_component.update_download_job(
                    job_id,
                    process_id=os.getpid()
                )
            except Exception as e:
                logger.error(f"Error updating job before fork: {e}")
                print(f"Error updating download job: {e}")
                    
            # Fork a new process
            logger.info(f"Forking child process for job_id {job_id}")
            pid = os.fork()
            
            if pid == 0:
                # Child process
                try:
                    # Detach from parent
                    os.setsid()
                    
                    # Close standard file descriptors
                    os.close(0)
                    os.close(1)
                    os.close(2)
                    
                    # Create log directory if not exists
                    os.makedirs(self.download_dir, exist_ok=True)
                    
                    # Redirect stdout and stderr to a log file
                    log_file = os.path.join(self.download_dir, f"{space_id}_download.log")
                    sys.stdout = open(log_file, 'w')
                    sys.stderr = sys.stdout
                    
                    # We need to create a new database connection in the child process
                    # as the parent's connection can't be used after fork
                    child_space_component = Space()
                    
                    # Update job status to in_progress with new process ID
                    try:
                        child_space_component.update_download_job(
                            job_id,
                            status='in_progress',
                            process_id=os.getpid()
                        )
                        print(f"Child process started with PID {os.getpid()} for job {job_id}")
                    except Exception as e:
                        print(f"Error updating job status in child process: {e}")
                    
                    # Build the yt-dlp command
                    command = self._build_yt_dlp_command(space_url, output_path, file_type)
                    print(f"Download command: {' '.join(command if isinstance(command, list) else [command])}")
                    
                    # Create a temporary directory for the download
                    with tempfile.TemporaryDirectory() as temp_dir:
                        print(f"Created temporary directory: {temp_dir}")
                        
                        # Modify the command to use the temporary directory
                        temp_output_path = os.path.join(temp_dir, f"{space_id}.%(ext)s")
                        if isinstance(command, list) and "-o" in command:
                            command[command.index("-o") + 1] = temp_output_path
                        
                        print(f"Running command: {' '.join(command if isinstance(command, list) else [command])}")
                        
                        # Run the command
                        # Enhanced debugging for async download
                        print(f"Async download - Running yt-dlp command: {' '.join(command)}")
                        print(f"Working directory: {temp_dir}")
                        print(f"Space URL: {space_url}")
                        print("=" * 50)
                        
                        process = subprocess.Popen(
                            command,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True
                        )
                        
                        # Initialize progress tracking variables
                        last_progress_update = time.time()
                        progress_update_interval = 1.0  # seconds
                        
                        # Read output line by line to track progress
                        while True:
                            line = process.stdout.readline()
                            if not line and process.poll() is not None:
                                break
                            
                            # Print the output to log with enhanced info
                            print(f"[yt-dlp] {line}", end="")
                            
                            # Parse progress from yt-dlp output
                            if "[download]" in line and "%" in line:
                                try:
                                    # Extract percentage and size
                                    percent_match = re.search(r"(\d+\.\d+)%", line)
                                    size_match = re.search(r"(\d+\.\d+)(\w+)", line)
                                    
                                    if percent_match and size_match:
                                        percent = float(percent_match.group(1))
                                        size_value = float(size_match.group(1))
                                        size_unit = size_match.group(2)
                                        
                                        # Convert size to MB
                                        if size_unit == "KiB":
                                            size_mb = size_value / 1024
                                        elif size_unit == "MiB":
                                            size_mb = size_value
                                        elif size_unit == "GiB":
                                            size_mb = size_value * 1024
                                        else:
                                            size_mb = 0
                                        
                                        # Update progress in database at intervals
                                        current_time = time.time()
                                        if current_time - last_progress_update >= progress_update_interval:
                                            try:
                                                # Update normal space progress for compatibility
                                                child_space_component.update_download_progress(
                                                    space_id, 
                                                    int(percent),
                                                    file_size=int(size_mb * 1024 * 1024)
                                                )
                                                
                                                # Update download job progress
                                                child_space_component.update_download_progress_by_space(
                                                    space_id,
                                                    size_mb,
                                                    int(percent)
                                                )
                                                print(f"Progress updated: {percent:.1f}% ({size_mb:.2f} MB)")
                                            except Exception as e:
                                                print(f"Error updating progress: {e}")
                                                
                                            last_progress_update = current_time
                                except Exception as e:
                                    print(f"Error parsing progress: {e}")
                        
                        # Get the return code
                        return_code = process.poll()
                        
                        # Check for errors and capture all output
                        if return_code != 0:
                            try:
                                stdout_output = process.stdout.read() if process.stdout else ""
                                stderr_output = process.stderr.read() if process.stderr else ""
                            except Exception as e:
                                stdout_output = f"Error reading stdout: {e}"
                                stderr_output = f"Error reading stderr: {e}"
                            
                            print(f"yt-dlp failed with exit code {return_code}")
                            print(f"STDOUT: {stdout_output}")
                            print(f"STDERR: {stderr_output}")
                            print("=" * 50)
                            
                            # Create user-friendly error message
                            error_message = self._create_user_friendly_error_message(stdout_output, stderr_output, return_code)
                            
                            # Update job status to failed
                            try:
                                child_space_component.update_download_job(
                                    job_id,
                                    status='failed',
                                    error_message=error_message
                                )
                            except Exception as e:
                                print(f"Error updating job status to failed: {e}")
                            
                            # Exit child process
                            os._exit(1)
                        
                        print("Download process completed successfully")
                        
                        # Find the downloaded file in the temporary directory
                        downloaded_files = [f for f in os.listdir(temp_dir) if f.startswith(space_id) or f.endswith(f".{file_type}")]
                        
                        if not downloaded_files:
                            print("Error: No downloaded file found.")
                            try:
                                child_space_component.update_download_job(
                                    job_id,
                                    status='failed',
                                    error_message="No downloaded file found after successful download."
                                )
                            except Exception as e:
                                print(f"Error updating job status: {e}")
                                
                            os._exit(1)
                        
                        print(f"Found downloaded files: {downloaded_files}")
                        
                        # Move the downloaded file to the final location
                        downloaded_file = os.path.join(temp_dir, downloaded_files[0])
                        
                        # Ensure the destination directory exists
                        os.makedirs(os.path.dirname(output_path), exist_ok=True)
                        
                        # Move the file
                        print(f"Moving file from {downloaded_file} to {output_path}")
                        shutil.move(downloaded_file, output_path)
                        
                        # Update job status to completed
                        try:
                            file_size = os.path.getsize(output_path)
                            file_size_mb = file_size / (1024 * 1024)
                            
                            # Update normal space progress for compatibility
                            child_space_component.update_download_progress(
                                space_id, 
                                100,  # 100%
                                file_size=file_size
                            )
                            
                            # Update download job progress
                            child_space_component.update_download_job(
                                job_id,
                                progress_in_size=file_size_mb,
                                progress_in_percent=100,
                                status='completed'
                            )
                            
                            print(f"Download completed: {output_path} ({file_size_mb:.2f} MB)")
                        except Exception as e:
                            print(f"Error updating job status to completed: {e}")
                        
                    # Exit child process
                    os._exit(0)
                    
                except Exception as e:
                    print(f"Error in child process: {e}")
                    import traceback
                    traceback.print_exc()
                    
                    try:
                        # Create a new Space component for database connection
                        error_space_component = Space()
                        
                        # Update job status to failed
                        error_space_component.update_download_job(
                            job_id,
                            status='failed',
                            error_message=str(e)
                        )
                    except Exception as update_error:
                        print(f"Error updating job status after error: {update_error}")
                    
                    # Exit child process
                    os._exit(1)
            else:
                # Parent process
                logger.info(f"Child process forked with PID {pid} for job_id {job_id}")
                
                # Record the child process ID in the database
                try:
                    self.space_component.update_download_job(
                        job_id,
                        process_id=pid
                    )
                    logger.info(f"Updated job {job_id} with child PID {pid}")
                except Exception as e:
                    logger.error(f"Error updating job with child PID: {e}")
                    print(f"Error updating job with child PID: {e}")
                
                # Return the job ID
                return job_id
                
        except Exception as e:
            logger.error(f"Error starting asynchronous download: {e}", exc_info=True)
            print(f"Error starting asynchronous download: {e}")
            
            # Update job status to failed
            try:
                self.space_component.update_download_job(
                    job_id,
                    status='failed',
                    error_message=str(e)
                )
            except Exception as update_error:
                logger.error(f"Error updating job status after error: {update_error}")
                print(f"Error updating job status after error: {update_error}")
            
            return None
    
    def get_download_status(self, job_id):
        """
        Get the status of a download job.
        
        Args:
            job_id (int): The download job ID
            
        Returns:
            dict: Job details or None if not found
        """
        return self.space_component.get_download_job(job_id)
    
    def cancel_download(self, job_id):
        """
        Cancel a download job.
        
        Args:
            job_id (int): The download job ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get the job details
            job = self.space_component.get_download_job(job_id)
            
            if not job:
                print(f"Error: Download job {job_id} not found.")
                return False
                
            # If the job is already completed or failed, just return True
            if job['status'] in ['completed', 'failed']:
                return True
                
            # If the job has a process ID, try to kill the process
            if job['process_id']:
                try:
                    # Send SIGTERM to the process
                    os.kill(job['process_id'], signal.SIGTERM)
                    
                    # Wait a bit for the process to terminate
                    time.sleep(0.5)
                    
                    # Check if the process is still running
                    try:
                        os.kill(job['process_id'], 0)
                        # Process is still running, send SIGKILL
                        os.kill(job['process_id'], signal.SIGKILL)
                    except OSError:
                        # Process is no longer running
                        pass
                        
                except OSError as e:
                    # Process might not exist anymore
                    pass
                    
            # Update job status to failed
            self.space_component.update_download_job(
                job_id,
                status='failed',
                error_message="Download canceled by user."
            )
            
            return True
            
        except Exception as e:
            print(f"Error canceling download: {e}")
            return False
    
    def list_downloads(self, user_id=None, status=None, limit=10, offset=0):
        """
        List download jobs.
        
        Args:
            user_id (int, optional): Filter by user ID. Defaults to None.
            status (str, optional): Filter by status. Defaults to None.
            limit (int, optional): Maximum number of results. Defaults to 10.
            offset (int, optional): Pagination offset. Defaults to 0.
            
        Returns:
            list: List of download jobs
        """
        return self.space_component.list_download_jobs(user_id, status, limit, offset)


# Direct execution for testing
if __name__ == "__main__":
    # Test code
    if len(sys.argv) < 2:
        print("Usage: python3 DownloadSpace.py [URL] [file_type] [async_mode]")
        sys.exit(1)
        
    url = sys.argv[1]
    file_type = sys.argv[2] if len(sys.argv) > 2 else "mp3"
    async_mode = True if len(sys.argv) <= 3 else sys.argv[3].lower() == "true"
    
    downloader = DownloadSpace()
    result = downloader.download(url, file_type, async_mode)
    
    if async_mode:
        print(f"Download job started with ID: {result}")
    else:
        print(f"Download completed: {result}")