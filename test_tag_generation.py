#!/usr/bin/env python3
"""
Test script to generate tags for spaces that have transcripts but no tags.
"""

import sys
import json
import mysql.connector
from pathlib import Path

# Add parent directory to path for importing components
sys.path.append(str(Path(__file__).parent))

from background_transcribe import generate_and_save_tags_with_ai
from components.Tag import Tag

def test_tag_generation():
    """Test tag generation for spaces with transcripts."""
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
        
        # Find spaces with transcripts but no tags
        query = """
        SELECT st.space_id, st.transcript, COUNT(stg.id) as tag_count
        FROM space_transcripts st
        LEFT JOIN space_tags stg ON CONVERT(st.space_id USING utf8mb4) COLLATE utf8mb4_0900_ai_ci = stg.space_id
        WHERE st.transcript IS NOT NULL 
        AND st.transcript != ''
        AND LENGTH(st.transcript) > 100
        GROUP BY st.space_id, st.transcript
        HAVING tag_count = 0
        LIMIT 5
        """
        
        cursor.execute(query)
        spaces_without_tags = cursor.fetchall()
        
        print(f"Found {len(spaces_without_tags)} spaces with transcripts but no tags")
        
        if spaces_without_tags:
            print("\nGenerating tags for these spaces...")
            
            for space in spaces_without_tags:
                space_id = space['space_id']
                transcript = space['transcript']
                
                print(f"\nSpace {space_id}:")
                print(f"  Transcript length: {len(transcript)} characters")
                print(f"  First 200 chars: {transcript[:200]}...")
                
                # Generate and save tags
                generate_and_save_tags_with_ai(space_id, transcript)
                
                # Verify tags were added
                tag_component = Tag(connection)
                tags = tag_component.get_space_tags(space_id)
                
                if tags:
                    print(f"  Generated {len(tags)} tags:")
                    for tag in tags:
                        print(f"    - {tag.get('name', tag.get('tag_name', 'Unknown'))}")
                else:
                    print("  No tags generated")
        
        # Also show spaces that already have tags
        query2 = """
        SELECT st.space_id, COUNT(DISTINCT stg.id) as tag_count
        FROM space_transcripts st
        INNER JOIN space_tags stg ON CONVERT(st.space_id USING utf8mb4) COLLATE utf8mb4_0900_ai_ci = stg.space_id
        WHERE st.transcript IS NOT NULL
        GROUP BY st.space_id
        ORDER BY tag_count DESC
        LIMIT 5
        """
        
        cursor.execute(query2)
        spaces_with_tags = cursor.fetchall()
        
        if spaces_with_tags:
            print(f"\n\nSpaces that already have tags:")
            for space in spaces_with_tags:
                print(f"  Space {space['space_id']}: {space['tag_count']} tags")
                
                # Show the tags
                tag_component = Tag(connection)
                tags = tag_component.get_space_tags(space['space_id'])
                for tag in tags[:5]:  # Show first 5 tags
                    print(f"    - {tag.get('name', tag.get('tag_name', 'Unknown'))}")
                if len(tags) > 5:
                    print(f"    ... and {len(tags) - 5} more")
        
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_tag_generation()