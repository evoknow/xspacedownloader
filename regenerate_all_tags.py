#!/usr/bin/env python3
"""
Script to regenerate ALL tags for spaces with transcripts using AI.
"""

import sys
import json
import mysql.connector
from pathlib import Path

# Add parent directory to path for importing components
sys.path.append(str(Path(__file__).parent))

from background_transcribe import generate_and_save_tags_with_ai
from components.Tag import Tag

def regenerate_all_tags():
    """Remove all existing tags and regenerate using AI."""
    try:
        # Load database config
        with open("db_config.json", 'r') as f:
            config = json.load(f)
        
        db_config = config["mysql"].copy()
        if 'use_ssl' in db_config:
            del db_config['use_ssl']
        
        # Connect to database
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)
        
        print("Finding all spaces with transcripts...")
        
        # Get all spaces with transcripts
        cursor.execute("""
            SELECT st.space_id, st.transcript, st.language,
                   COUNT(stg.id) as current_tag_count
            FROM space_transcripts st
            LEFT JOIN space_tags stg ON CONVERT(st.space_id USING utf8mb4) COLLATE utf8mb4_0900_ai_ci = stg.space_id
            WHERE st.transcript IS NOT NULL 
            AND st.transcript != ''
            AND LENGTH(st.transcript) > 200
            GROUP BY st.space_id, st.transcript, st.language
            ORDER BY LENGTH(st.transcript) DESC
            LIMIT 10
        """)
        
        spaces_with_transcripts = cursor.fetchall()
        print(f"Found {len(spaces_with_transcripts)} spaces with transcripts")
        
        for space in spaces_with_transcripts:
            space_id = space['space_id']
            transcript = space['transcript']
            current_tag_count = space['current_tag_count']
            
            print(f"\nSpace {space_id}:")
            print(f"  Transcript length: {len(transcript)} characters")
            print(f"  Current tags: {current_tag_count}")
            print(f"  Language: {space['language']}")
            
            # Show current tags
            if current_tag_count > 0:
                tag_component = Tag(connection)
                current_tags = tag_component.get_space_tags(space_id)
                print(f"  Current tags: {[tag.get('name', 'Unknown') for tag in current_tags]}")
            
            # Remove existing tags
            cursor.execute("DELETE FROM space_tags WHERE space_id = %s", (space_id,))
            connection.commit()
            print(f"  Removed {current_tag_count} existing tags")
            
            # Generate new tags using AI
            print(f"  Generating new tags...")
            print(f"  Sample text: {transcript[:200]}...")
            
            generate_and_save_tags_with_ai(space_id, transcript)
            
            # Show new tags - need to create a fresh connection since Tag component might have closed it
            try:
                fresh_connection = mysql.connector.connect(**db_config)
                tag_component = Tag(fresh_connection)
                new_tags = tag_component.get_space_tags(space_id)
                fresh_connection.close()
                
                if new_tags:
                    print(f"  ✅ Generated {len(new_tags)} new tags:")
                    for tag in new_tags:
                        print(f"    - {tag.get('name', tag.get('tag_name', 'Unknown'))}")
                else:
                    print("  ❌ No tags generated")
            except Exception as e:
                print(f"  ✅ Tags were saved (display error: {e})")
        
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    regenerate_all_tags()