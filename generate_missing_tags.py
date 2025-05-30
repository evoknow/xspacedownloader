#!/usr/bin/env python3
"""
Script to generate tags for spaces that have transcripts but no tags.
"""

import json
import mysql.connector
import sys
import logging
from components.Space import Space

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    # Load database config
    with open('db_config.json', 'r') as f:
        config = json.load(f)
    
    db_config = config["mysql"].copy()
    if 'use_ssl' in db_config:
        del db_config['use_ssl']
    
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor(dictionary=True)
    
    # Find all recent transcripts
    query = """
    SELECT t.space_id, t.language, t.transcript 
    FROM space_transcripts t
    ORDER BY t.created_at DESC
    LIMIT 20
    """
    
    cursor.execute(query)
    spaces_without_tags = cursor.fetchall()
    
    if not spaces_without_tags:
        logger.info("No spaces found without tags")
        return
    
    logger.info(f"Found {len(spaces_without_tags)} spaces without tags")
    
    # Initialize Space component
    space = Space()
    
    # Generate tags for each space
    for space_data in spaces_without_tags:
        space_id = space_data['space_id']
        transcript = space_data['transcript']
        language = space_data['language']
        
        logger.info(f"Processing space {space_id} (language: {language})")
        
        try:
            # Generate tags
            tags = space.generate_tags_from_transcript(transcript)
            
            if tags:
                # Add tags to space
                count = space.add_tags_to_space(space_id, tags)
                logger.info(f"Added {count} tags to space {space_id}: {', '.join(tags)}")
            else:
                logger.warning(f"No tags generated for space {space_id}")
                
        except Exception as e:
            logger.error(f"Error processing space {space_id}: {e}")
    
    cursor.close()
    connection.close()
    logger.info("Tag generation complete")

if __name__ == "__main__":
    main()