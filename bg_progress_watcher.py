#!/usr/bin/env python3
"""
Background Progress Watcher
Monitors .part files in the downloads directory and updates progress_in_size in the spaces table.
This is a dedicated service that only watches file sizes and reports to the database.
"""

import os
import sys
import time
import json
import logging
import signal
import mysql.connector
from pathlib import Path
from datetime import datetime

# Setup logging
# Ensure logs directory exists
log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)

# Configure logging
log_file = log_dir / 'bg_progress_watcher.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(log_file)),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('bg_progress_watcher')

class ProgressWatcher:
    def __init__(self):
        self.running = True
        self.db_config = None
        self.connection = None
        self.downloads_dir = None
        self.watched_files = {}  # Track file sizes to detect changes
        self.update_interval = 10  # seconds
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
        
    def load_config(self):
        """Load database configuration"""
        try:
            with open('db_config.json', 'r') as f:
                config = json.load(f)
                self.db_config = config['mysql'].copy()
                # Remove unsupported keys
                for key in ['use_ssl', 'autocommit', 'sql_mode', 'use_unicode', 'raise_on_warnings']:
                    self.db_config.pop(key, None)
                    
            # Get downloads directory from mainconfig
            downloads_dir = 'downloads'  # default
            try:
                with open('mainconfig.json', 'r') as f:
                    main_config = json.load(f)
                    downloads_dir = main_config.get('download_directory', 'downloads')
            except:
                pass
                
            self.downloads_dir = Path(downloads_dir)
            if not self.downloads_dir.exists():
                self.downloads_dir.mkdir(parents=True, exist_ok=True)
                
            logger.info(f"Watching directory: {self.downloads_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            return False
            
    def connect_db(self):
        """Create database connection"""
        try:
            if self.connection:
                try:
                    self.connection.close()
                except:
                    pass
                    
            self.connection = mysql.connector.connect(**self.db_config)
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False
            
    def find_part_files(self):
        """Find all .part files in downloads directory"""
        part_files = {}
        
        try:
            # Look for .part files with various extensions
            for pattern in ['*.part', '*.m4a.part', '*.mp4.part', '*.mp3.part', '*.webm.part']:
                for part_file in self.downloads_dir.glob(pattern):
                    if part_file.is_file():
                        # Extract space_id from filename
                        # Handles: spaceid.ext.part or spaceid.part
                        filename = part_file.stem  # removes .part
                        if filename.endswith(('.m4a', '.mp4', '.mp3', '.webm')):
                            space_id = Path(filename).stem
                        else:
                            space_id = filename
                            
                        try:
                            file_size = part_file.stat().st_size
                            part_files[space_id] = {
                                'path': part_file,
                                'size': file_size
                            }
                        except Exception as e:
                            logger.warning(f"Could not stat file {part_file}: {e}")
                            
        except Exception as e:
            logger.error(f"Error scanning for part files: {e}")
            
        return part_files
        
    def update_progress(self, space_id, file_size):
        """Update progress_in_size in space_download_scheduler table"""
        try:
            if not self.connection or not self.connection.is_connected():
                if not self.connect_db():
                    return False
                    
            cursor = self.connection.cursor()
            
            # Update the space_download_scheduler table for active downloads
            # We update all in_progress or downloading jobs for this space_id
            update_query = """
                UPDATE space_download_scheduler 
                SET progress_in_size = %s,
                    updated_at = NOW()
                WHERE space_id = %s 
                AND status IN ('in_progress', 'downloading', 'pending')
            """
            
            cursor.execute(update_query, (file_size, space_id))
            self.connection.commit()
            
            if cursor.rowcount > 0:
                logger.debug(f"Updated {cursor.rowcount} job(s) for space {space_id}: size = {file_size} bytes")
                return True
            else:
                # No active jobs found, which is fine
                logger.debug(f"No active jobs found for space {space_id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to update progress for {space_id}: {e}")
            try:
                self.connection.rollback()
            except:
                pass
            return False
        finally:
            try:
                cursor.close()
            except:
                pass
                
    def run(self):
        """Main watching loop"""
        logger.info("Starting progress watcher...")
        
        if not self.load_config():
            logger.error("Failed to load configuration, exiting")
            return
            
        if not self.connect_db():
            logger.error("Initial database connection failed, exiting")
            return
            
        logger.info("Progress watcher started successfully")
        last_update_time = {}
        
        while self.running:
            try:
                # Find all current part files
                current_files = self.find_part_files()
                current_time = time.time()
                
                # Check each file
                for space_id, file_info in current_files.items():
                    file_size = file_info['size']
                    last_size = self.watched_files.get(space_id, {}).get('size', 0)
                    last_update = last_update_time.get(space_id, 0)
                    
                    # Update if size changed or every update_interval seconds
                    if (file_size != last_size or 
                        current_time - last_update >= self.update_interval):
                        
                        if self.update_progress(space_id, file_size):
                            last_update_time[space_id] = current_time
                            
                            # Log significant changes
                            if file_size != last_size:
                                size_mb = file_size / (1024 * 1024)
                                logger.info(f"Progress update: {space_id} = {size_mb:.1f} MB")
                                
                        self.watched_files[space_id] = file_info
                        
                # Clean up completed downloads
                for space_id in list(self.watched_files.keys()):
                    if space_id not in current_files:
                        logger.info(f"File completed or removed: {space_id}")
                        self.watched_files.pop(space_id, None)
                        last_update_time.pop(space_id, None)
                        
                # Sleep for a short interval before next scan
                time.sleep(1)
                
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")
                self.running = False
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(5)  # Wait before retrying
                
        # Cleanup
        logger.info("Shutting down progress watcher...")
        if self.connection:
            try:
                self.connection.close()
            except:
                pass
                
        logger.info("Progress watcher stopped")

def main():
    """Main entry point"""
    # Check if already running
    pid_file = Path('logs/bg_progress_watcher.pid')
    
    # Create logs directory if it doesn't exist
    Path('logs').mkdir(exist_ok=True)
    
    if pid_file.exists():
        try:
            with open(pid_file, 'r') as f:
                old_pid = int(f.read().strip())
                
            # Check if process is still running
            try:
                os.kill(old_pid, 0)
                logger.error(f"Progress watcher already running with PID {old_pid}")
                sys.exit(1)
            except OSError:
                # Process not running, remove stale PID file
                pid_file.unlink()
        except:
            pid_file.unlink()
            
    # Write PID file
    with open(pid_file, 'w') as f:
        f.write(str(os.getpid()))
        
    try:
        # Run the watcher
        watcher = ProgressWatcher()
        watcher.run()
    finally:
        # Clean up PID file
        try:
            pid_file.unlink()
        except:
            pass

if __name__ == '__main__':
    main()