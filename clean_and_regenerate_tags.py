#!/usr/bin/env python3
"""
Script to clean up poor quality tags and regenerate better ones.
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

# List of poor quality tags to remove
POOR_TAGS = ['your', 'good', 'anna', 'nice', 'really', 'very', 'much', 
             'thing', 'things', 'stuff', 'people', 'person', 'time',
             'right', 'yeah', 'okay', 'well', 'just', 'like', 'know']

def main():
    # Load database config
    with open('db_config.json', 'r') as f:
        config = json.load(f)
    
    db_config = config["mysql"].copy()
    if 'use_ssl' in db_config:
        del db_config['use_ssl']
    
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor(dictionary=True)
    
    # First, remove poor quality tags
    logger.info("Removing poor quality tags...")
    for tag in POOR_TAGS:
        cursor.execute("DELETE FROM tags WHERE LOWER(name) = %s", (tag.lower(),))
        if cursor.rowcount > 0:
            logger.info(f"Removed tag: {tag}")
    
    connection.commit()
    
    # Find spaces that now have fewer than 3 tags
    query = """
    SELECT s.space_id, COUNT(st.tag_id) as tag_count
    FROM spaces s
    LEFT JOIN space_tags st ON s.space_id = st.space_id
    WHERE s.status = 'completed'
    GROUP BY s.space_id
    HAVING tag_count < 3
    ORDER BY s.created_at DESC
    LIMIT 50
    """
    
    cursor.execute(query)
    spaces_needing_tags = cursor.fetchall()
    
    logger.info(f"Found {len(spaces_needing_tags)} spaces needing more tags")
    
    # Initialize Space component
    space = Space()
    
    # For each space, regenerate tags
    for space_data in spaces_needing_tags:
        space_id = space_data['space_id']
        
        # Get transcript
        cursor.execute("""
            SELECT transcript, language 
            FROM space_transcripts 
            WHERE space_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (space_id,))
        
        transcript_data = cursor.fetchone()
        if not transcript_data:
            continue
            
        logger.info(f"Processing space {space_id} (current tags: {space_data['tag_count']})")
        
        try:
            # Generate new tags
            tags = space.generate_tags_from_transcript(transcript_data['transcript'])
            
            if tags:
                # Remove existing tags first
                cursor.execute("DELETE FROM space_tags WHERE space_id = %s", (space_id,))
                connection.commit()
                
                # Add new tags
                result = space.add_tags_to_space(space_id, tags)
                if isinstance(result, dict):
                    count = len(result.get('added_tags', []))
                else:
                    count = result
                logger.info(f"Added {count} tags to space {space_id}: {', '.join(tags)}")
            else:
                logger.warning(f"No tags generated for space {space_id}")
                
        except Exception as e:
            logger.error(f"Error processing space {space_id}: {e}")
    
    cursor.close()
    connection.close()
    logger.info("Tag cleanup and regeneration complete")

if __name__ == "__main__":
    main()