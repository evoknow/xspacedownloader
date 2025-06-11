#!/usr/bin/env python3
# fix_direct_spaces.py
# Fix spaces that are missing from the database but have physical files

import os
import sys
import json
import logging
import mysql.connector
from pathlib import Path
from typing import Dict, List, Optional, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('fix_spaces')

def load_db_config() -> Dict:
    """Load database configuration from db_config.json"""
    try:
        with open('db_config.json', 'r') as config_file:
            config = json.load(config_file)
            if config["type"] == "mysql":
                mysql_config = config["mysql"].copy()
                # Remove unsupported parameters
                if 'use_ssl' in mysql_config:
                    del mysql_config['use_ssl']
                return mysql_config
            else:
                raise ValueError(f"Unsupported database type: {config['type']}")
    except Exception as e:
        logger.error(f"Error loading database config: {e}")
        sys.exit(1)

def ensure_space_record(space_id: str, file_path: Optional[str] = None) -> bool:
    """
    Ensures a space record exists in the database with status='completed'.
    
    Args:
        space_id: The space ID to check and add
        file_path: Optional path to the audio file
        
    Returns:
        bool: True if the record was created or updated, False otherwise
    """
    db_config = load_db_config()
    conn = None
    
    try:
        # Create database connection
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        # Check if space exists
        cursor.execute("SELECT * FROM spaces WHERE space_id = %s", (space_id,))
        space_record = cursor.fetchone()
        
        # If file_path is not provided, try to find it
        if not file_path:
            downloads_dir = Path("./downloads")
            for ext in ['mp3', 'm4a', 'wav']:
                check_path = downloads_dir / f"{space_id}.{ext}"
                if check_path.exists() and check_path.stat().st_size > 1024*1024:  # > 1MB
                    file_path = str(check_path)
                    break
        
        # Get file info if available
        file_size = 0
        file_extension = 'mp3'  # Default extension
        
        if file_path:
            file_size = os.path.getsize(file_path)
            file_extension = os.path.splitext(file_path)[1].lstrip('.')
            logger.info(f"Found file {file_path} with size {file_size} bytes")
        
        # Create or update record
        if space_record:
            # Update existing record
            if space_record.get('status') != 'completed':
                logger.info(f"Updating existing record for space {space_id} to completed status")
                
                # Check which columns exist in the table
                try:
                    cursor.execute("DESCRIBE spaces")
                    columns_data = cursor.fetchall()
                    
                    # Handle both dictionary and tuple cursor results
                    if columns_data and isinstance(columns_data[0], dict):
                        columns = [col['Field'] for col in columns_data]
                    else:
                        # If tuple format, Field is the first item
                        columns = [col[0] for col in columns_data]
                    
                    has_updated_at = 'updated_at' in columns
                    has_downloaded_at = 'downloaded_at' in columns
                    
                    if has_updated_at and has_downloaded_at:
                        update_query = """
                        UPDATE spaces
                        SET status = 'completed', format = %s, 
                            updated_at = NOW(), downloaded_at = NOW()
                        WHERE space_id = %s
                        """
                    elif has_updated_at:
                        update_query = """
                        UPDATE spaces
                        SET status = 'completed', format = %s, 
                            updated_at = NOW()
                        WHERE space_id = %s
                        """
                    else:
                        update_query = """
                        UPDATE spaces
                        SET status = 'completed', format = %s
                        WHERE space_id = %s
                        """
                    
                    cursor.execute(update_query, (str(file_size), space_id))
                    conn.commit()
                    return True
                except Exception as col_err:
                    logger.error(f"Error checking columns: {col_err}")
                    
                    # Fallback to simple update without timestamp fields
                    try:
                        simple_update = """
                        UPDATE spaces
                        SET status = 'completed', download_cnt = 100
                        WHERE space_id = %s
                        """
                        cursor.execute(simple_update, (space_id,))
                        conn.commit()
                        return True
                    except Exception as simple_err:
                        logger.error(f"Error with simple update: {simple_err}")
                        return False
            else:
                logger.info(f"Space {space_id} already exists with completed status")
                return True
        else:
            # Create new record
            logger.info(f"Creating new record for space {space_id}")
            space_url = f"https://x.com/i/spaces/{space_id}"
            filename = f"{space_id}.{file_extension}"
            
            # Check table structure first
            try:
                cursor.execute("DESCRIBE spaces")
                columns_data = cursor.fetchall()
                
                # Handle both dictionary and tuple cursor results
                if isinstance(columns_data[0], dict):
                    columns = [col['Field'] for col in columns_data]
                else:
                    # If tuple format, Field is the first item
                    columns = [col[0] for col in columns_data]
                
                # Check which timestamp columns exist
                has_created_at = 'created_at' in columns
                has_updated_at = 'updated_at' in columns
                has_downloaded_at = 'downloaded_at' in columns
                
                logger.info(f"Table columns: created_at={has_created_at}, updated_at={has_updated_at}, downloaded_at={has_downloaded_at}")
                
                # Build query based on which columns exist
                if has_created_at and has_updated_at and has_downloaded_at:
                    # Full version with all timestamp columns
                    insert_query = """
                    INSERT INTO spaces 
                    (space_id, space_url, filename, status, download_cnt, format, created_at, updated_at, downloaded_at)
                    VALUES (%s, %s, %s, 'completed', 0, %s, NOW(), NOW(), NOW())
                    """
                    values = [space_id, space_url, filename, str(file_size)]
                elif has_created_at:
                    # Version with just created_at
                    insert_query = """
                    INSERT INTO spaces 
                    (space_id, space_url, filename, status, download_cnt, format, created_at)
                    VALUES (%s, %s, %s, 'completed', 0, %s, NOW())
                    """
                    values = [space_id, space_url, filename, str(file_size)]
                else:
                    # Basic version with no timestamp columns
                    insert_query = """
                    INSERT INTO spaces 
                    (space_id, space_url, filename, status, download_cnt, format)
                    VALUES (%s, %s, %s, 'completed', 0, %s)
                    """
                    values = [space_id, space_url, filename, str(file_size)]
                
                logger.info(f"Using dynamic INSERT: {insert_query}")
                cursor.execute(insert_query, values)
                conn.commit()
                
                # Invalidate cache since we added a new space
                try:
                    from app import invalidate_spaces_cache
                    invalidate_spaces_cache()
                    logger.info("Invalidated spaces cache after creating space record")
                except ImportError:
                    logger.warning("Could not import cache invalidation function")
                except Exception as cache_err:
                    logger.warning(f"Error invalidating cache: {cache_err}")
                
                logger.info(f"Successfully created space record for {space_id}")
                return True
                
            except Exception as describe_err:
                logger.error(f"Error checking table structure: {describe_err}")
                
                # Fallback to most basic insert
                try:
                    logger.info("Trying minimal INSERT query")
                    # Try to check what columns are actually in the table
                    try:
                        cursor.execute("SELECT * FROM spaces LIMIT 0")
                        column_names = [desc[0] for desc in cursor.description]
                        logger.info(f"Actual columns in spaces table: {column_names}")
                        
                        # Build a minimal query using only the columns we know exist
                        minimal_fields = []
                        minimal_placeholders = []
                        minimal_values = []
                        
                        # Add core fields if they exist
                        for field, value in [
                            ('space_id', space_id),
                            ('space_url', space_url),
                            ('filename', filename),
                            ('status', 'completed'),
                            ('download_cnt', 0),
                            ('format', str(file_size))
                        ]:
                            if field in column_names:
                                minimal_fields.append(field)
                                minimal_placeholders.append('%s')
                                minimal_values.append(value)
                        
                        # Create truly minimal insert with just what we found
                        minimal_insert = f"""
                        INSERT INTO spaces 
                        ({', '.join(minimal_fields)})
                        VALUES ({', '.join(minimal_placeholders)})
                        """
                        
                        logger.info(f"Using truly minimal query: {minimal_insert} with values {minimal_values}")
                        cursor.execute(minimal_insert, minimal_values)
                        conn.commit()
                        
                        # Invalidate cache since we added a new space
                        try:
                            from app import invalidate_spaces_cache
                            invalidate_spaces_cache()
                            logger.info("Invalidated spaces cache after creating minimal space record")
                        except ImportError:
                            logger.warning("Could not import cache invalidation function")
                        except Exception as cache_err:
                            logger.warning(f"Error invalidating cache: {cache_err}")
                        
                        logger.info(f"Successfully created minimal space record for {space_id}")
                        return True
                    except Exception as col_err:
                        logger.error(f"Error getting actual columns: {col_err}")
                        
                        # Last resort - just try the most basic insert with only required fields
                        try:
                            basic_insert = """
                            INSERT INTO spaces 
                            (space_id, status, download_cnt)
                            VALUES (%s, 'completed', 0)
                            """
                            cursor.execute(basic_insert, (space_id,))
                            conn.commit()
                            
                            # Invalidate cache since we added a new space
                            try:
                                from app import invalidate_spaces_cache
                                invalidate_spaces_cache()
                                logger.info("Invalidated spaces cache after creating basic space record")
                            except ImportError:
                                logger.warning("Could not import cache invalidation function")
                            except Exception as cache_err:
                                logger.warning(f"Error invalidating cache: {cache_err}")
                            
                            logger.info(f"Created most basic space record for {space_id}")
                            return True
                        except Exception as basic_err:
                            logger.error(f"Even basic insert failed: {basic_err}")
                            return False
                except Exception as minimal_err:
                    logger.error(f"Error with minimal insert: {minimal_err}")
                    return False
    
    except Exception as e:
        logger.error(f"Error ensuring space record: {e}")
        return False
    finally:
        if conn:
            if cursor:
                cursor.close()
            conn.close()

def scan_downloads_dir():
    """Scan downloads directory and ensure all files have database records"""
    downloads_dir = Path("./downloads")
    
    if not downloads_dir.exists():
        logger.error(f"Downloads directory {downloads_dir} not found")
        return
    
    # Count files processed and fixed
    total_files = 0
    fixed_records = 0
    already_ok = 0
    errors = 0
    
    # Scan all files
    for file_path in downloads_dir.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in ['.mp3', '.m4a', '.wav']:
            file_stem = file_path.stem
            total_files += 1
            
            # Try to extract space_id from filename
            space_id = file_stem
            
            # Skip if filename doesn't look like a space_id
            if len(space_id) < 8 or not space_id.isalnum():
                logger.warning(f"Skipping file with invalid space ID format: {file_path}")
                continue
                
            # Ensure space record exists
            result = ensure_space_record(space_id, str(file_path))
            
            if result:
                logger.info(f"Space {space_id} record is now in sync with file {file_path}")
                fixed_records += 1
            else:
                logger.error(f"Failed to ensure record for space {space_id} with file {file_path}")
                errors += 1
    
    logger.info(f"Scan complete. Processed {total_files} files, fixed {fixed_records} records, {errors} errors")

if __name__ == "__main__":
    """Run the tool directly from command line"""
    if len(sys.argv) > 1:
        # Process specific space ID
        space_id = sys.argv[1]
        logger.info(f"Processing specific space ID: {space_id}")
        ensure_space_record(space_id)
    else:
        # Scan entire downloads directory
        logger.info("Scanning downloads directory for missing records")
        scan_downloads_dir()