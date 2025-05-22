#!/usr/bin/env python3
# convert_to_mp3.py - Converts all non-MP3 files to MP3 format

import os
import sys
import subprocess
import json
import logging
import glob
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('convert_to_mp3')

def load_config():
    """Load configuration from mainconfig.json or use defaults."""
    config = {}
    try:
        with open('mainconfig.json', 'r') as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Could not load config, using defaults: {e}")
        config = {}
    
    # Set up default values
    config['download_dir'] = config.get('download_dir', 'downloads')
    return config

def convert_all_non_mp3_files():
    """Find and convert all non-MP3 audio files to MP3 format."""
    config = load_config()
    
    # Get downloads directory
    downloads_dir = Path(os.path.dirname(os.path.abspath(__file__))) / config['download_dir']
    logger.info(f"Scanning directory: {downloads_dir}")
    
    # Count files to convert
    m4a_files = list(downloads_dir.glob('*.m4a'))
    wav_files = list(downloads_dir.glob('*.wav'))
    non_mp3_files = m4a_files + wav_files
    
    if not non_mp3_files:
        logger.info("No non-MP3 files found to convert.")
        return
    
    logger.info(f"Found {len(non_mp3_files)} non-MP3 files to convert: {len(m4a_files)} m4a, {len(wav_files)} wav")
    
    # Convert each file
    for file_path in non_mp3_files:
        space_id = file_path.stem
        logger.info(f"Converting {file_path} to MP3...")
        
        # Create the mp3 output path
        mp3_path = file_path.with_suffix('.mp3')
        
        # Check if file already exists
        if mp3_path.exists():
            logger.warning(f"MP3 file already exists: {mp3_path}, checking file sizes...")
            
            # If MP3 file exists and is reasonably sized, skip conversion
            mp3_size = mp3_path.stat().st_size
            original_size = file_path.stat().st_size
            
            if mp3_size > 1024*1024:  # MP3 is at least 1MB
                logger.info(f"Existing MP3 file seems complete ({mp3_size} bytes vs original {original_size} bytes), skipping conversion")
                
                # Delete original file if it's a duplicate
                try:
                    logger.info(f"Removing original file: {file_path}")
                    os.remove(file_path)
                except OSError as e:
                    logger.error(f"Error removing original file: {e}")
                
                continue
            else:
                logger.warning(f"Existing MP3 file is too small ({mp3_size} bytes), overwriting...")
        
        # Use ffmpeg to convert to MP3
        try:
            convert_cmd = [
                'ffmpeg',
                '-y',  # Overwrite existing files
                '-i', str(file_path),  # Input file
                '-acodec', 'libmp3lame',  # Use LAME MP3 encoder
                '-q:a', '2',  # Use VBR quality 2 (high quality)
                str(mp3_path)  # Output file
            ]
            
            logger.info(f"Running: {' '.join(convert_cmd)}")
            result = subprocess.run(convert_cmd, 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE,
                                  text=True)
            
            if result.returncode == 0 and mp3_path.exists() and mp3_path.stat().st_size > 0:
                logger.info(f"Successfully converted to MP3: {mp3_path} ({mp3_path.stat().st_size} bytes)")
                
                # Delete the original file to save space
                try:
                    logger.info(f"Removing original file: {file_path}")
                    os.remove(file_path)
                except OSError as e:
                    logger.error(f"Error removing original file: {e}")
                
                # Update any database records to reflect the MP3 file
                update_database_records(space_id, str(mp3_path))
            else:
                logger.error(f"Error converting file: {result.stderr}")
                
        except Exception as e:
            logger.error(f"Error converting {file_path}: {e}")
    
    logger.info("Conversion complete.")

def update_database_records(space_id, mp3_path):
    """Update database to reflect the MP3 file instead of the original format."""
    try:
        # Load database configuration
        db_config_file = 'db_config.json'
        if not os.path.exists(db_config_file):
            logger.warning("No db_config.json file found, skipping database update")
            return
        
        with open(db_config_file, 'r') as f:
            db_config = json.load(f)
            if db_config.get("type") != "mysql":
                logger.warning("Database type is not MySQL, skipping database update")
                return
            
            mysql_config = db_config.get("mysql", {})
            
        # Connect to database
        import mysql.connector
        conn = mysql.connector.connect(**mysql_config)
        cursor = conn.cursor()
        
        # Update spaces table first
        spaces_query = """
        UPDATE spaces 
        SET filename = %s, format = 'mp3'
        WHERE space_id = %s
        """
        mp3_filename = os.path.basename(mp3_path)
        cursor.execute(spaces_query, (mp3_filename, space_id))
        
        # Update space_download_scheduler table for any job for this space
        scheduler_query = """
        UPDATE space_download_scheduler
        SET file_type = 'mp3'
        WHERE space_id = %s
        """
        cursor.execute(scheduler_query, (space_id,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"Updated database records for space {space_id} to use MP3 format")
    except Exception as e:
        logger.error(f"Error updating database records: {e}")

if __name__ == "__main__":
    logger.info("Starting conversion of all non-MP3 files to MP3 format")
    convert_all_non_mp3_files()
    logger.info("Conversion process complete")