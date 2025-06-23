#!/usr/bin/env python3
"""
Clean up common word tags from the database
"""

import mysql.connector
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# List of common words that should not be tags
COMMON_WORDS = [
    'going', 'because', 'think', 'about', 'would', 'doesn', 'really', 
    'maybe', 'probably', 'something', 'could', 'should', 'might', 
    'actually', 'basically', 'thing', 'stuff', 'people', 'good', 
    'nice', 'very', 'your', 'their', 'there', 'where', 'when',
    'what', 'which', 'while', 'since', 'being', 'having', 'doing',
    'saying', 'making', 'getting', 'giving', 'taking', 'coming',
    'going', 'looking', 'using', 'finding', 'trying', 'asking',
    'working', 'calling', 'feeling', 'becoming', 'leaving', 'bringing',
    'allowing', 'adding', 'including', 'continuing', 'setting', 'showing'
]

def cleanup_common_tags():
    """Remove common word tags from the database."""
    
    # Load database config
    with open('db_config.json', 'r') as f:
        db_config = json.load(f)
    
    # Get MySQL config from nested structure
    mysql_raw_config = db_config.get('mysql', {})
    
    # Filter to only supported mysql.connector parameters
    mysql_config = {
        'host': mysql_raw_config.get('host'),
        'port': mysql_raw_config.get('port', 3306),
        'database': mysql_raw_config.get('database'),
        'user': mysql_raw_config.get('user'),
        'password': mysql_raw_config.get('password'),
        'charset': mysql_raw_config.get('charset', 'utf8mb4'),
        'use_unicode': mysql_raw_config.get('use_unicode', True),
        'autocommit': mysql_raw_config.get('autocommit', False)
    }
    
    # Connect to database
    connection = mysql.connector.connect(**mysql_config)
    cursor = connection.cursor()
    
    try:
        # Find all common word tags
        placeholders = ', '.join(['%s'] * len(COMMON_WORDS))
        query = f"SELECT id, name FROM tags WHERE LOWER(name) IN ({placeholders})"
        cursor.execute(query, COMMON_WORDS)
        
        bad_tags = cursor.fetchall()
        logger.info(f"Found {len(bad_tags)} common word tags to remove")
        
        if bad_tags:
            # Remove tag associations
            tag_ids = [tag[0] for tag in bad_tags]
            placeholders = ', '.join(['%s'] * len(tag_ids))
            
            # Count associations before removal
            cursor.execute(f"SELECT COUNT(*) FROM space_tags WHERE tag_id IN ({placeholders})", tag_ids)
            association_count = cursor.fetchone()[0]
            logger.info(f"Removing {association_count} space-tag associations")
            
            # Remove from space_tags
            cursor.execute(f"DELETE FROM space_tags WHERE tag_id IN ({placeholders})", tag_ids)
            
            # Remove the tags themselves
            cursor.execute(f"DELETE FROM tags WHERE id IN ({placeholders})", tag_ids)
            
            connection.commit()
            
            # Log removed tags
            logger.info("Removed tags:")
            for tag_id, tag_name in bad_tags:
                logger.info(f"  - {tag_name} (ID: {tag_id})")
        else:
            logger.info("No common word tags found to remove")
            
    except Exception as e:
        logger.error(f"Error cleaning up tags: {e}")
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    cleanup_common_tags()