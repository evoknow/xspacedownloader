#!/usr/bin/env python3
"""
Script to clean up poor quality tags and regenerate them from transcripts.
"""

import sys
import json
import mysql.connector
from pathlib import Path

# Add parent directory to path for importing components
sys.path.append(str(Path(__file__).parent))

from background_transcribe import generate_and_save_tags_with_ai
from components.Tag import Tag

def cleanup_bad_tags():
    """Remove poor quality tags and regenerate from transcripts."""
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
        
        # List of tags to remove (poor quality tags)
        bad_tags = [
            'doesn', 'good', 'talk', 'welcome', 'last year', 'welcome, kabir.',
            'anna', 'people', 'topic', 'thing', 'things', 'actually', 'really',
            'going', 'talking', 'saying', 'looking', 'making', 'having',
            'getting', 'coming', 'doing', 'being', 'thinking'
        ]
        
        print("Cleaning up poor quality tags...")
        
        # Delete bad tags and their associations
        for tag_name in bad_tags:
            # Get tag ID
            cursor.execute("SELECT id FROM tags WHERE LOWER(name) = LOWER(%s)", (tag_name,))
            tag = cursor.fetchone()
            
            if tag:
                tag_id = tag['id']
                
                # Get spaces associated with this tag
                cursor.execute("""
                    SELECT DISTINCT space_id 
                    FROM space_tags 
                    WHERE tag_id = %s
                """, (tag_id,))
                affected_spaces = [row['space_id'] for row in cursor.fetchall()]
                
                # Delete tag associations
                cursor.execute("DELETE FROM space_tags WHERE tag_id = %s", (tag_id,))
                
                # Delete the tag itself
                cursor.execute("DELETE FROM tags WHERE id = %s", (tag_id,))
                
                print(f"  Removed tag '{tag_name}' (ID: {tag_id}) from {len(affected_spaces)} spaces")
        
        connection.commit()
        
        # Now regenerate tags for spaces that have transcripts
        print("\nRegenerating tags for spaces with transcripts...")
        
        # Find spaces with transcripts that need tag regeneration
        cursor.execute("""
            SELECT DISTINCT st.space_id, st.transcript
            FROM space_transcripts st
            LEFT JOIN space_tags stg ON CONVERT(st.space_id USING utf8mb4) COLLATE utf8mb4_0900_ai_ci = stg.space_id
            WHERE st.transcript IS NOT NULL 
            AND st.transcript != ''
            AND LENGTH(st.transcript) > 500
            GROUP BY st.space_id, st.transcript
            HAVING COUNT(stg.id) < 3  -- Spaces with fewer than 3 tags
            LIMIT 20
        """)
        
        spaces_to_retag = cursor.fetchall()
        print(f"Found {len(spaces_to_retag)} spaces that need tag regeneration")
        
        for space in spaces_to_retag:
            space_id = space['space_id']
            transcript = space['transcript']
            
            print(f"\nRegenerating tags for space {space_id}...")
            
            # First, remove any existing tags for this space
            cursor.execute("DELETE FROM space_tags WHERE space_id = %s", (space_id,))
            connection.commit()
            
            # Generate new tags
            generate_and_save_tags_with_ai(space_id, transcript)
            
            # Show the new tags
            tag_component = Tag(connection)
            new_tags = tag_component.get_space_tags(space_id)
            
            if new_tags:
                print(f"  Generated {len(new_tags)} new tags:")
                for tag in new_tags:
                    print(f"    - {tag.get('name', tag.get('tag_name', 'Unknown'))}")
            else:
                print("  No tags generated (transcript might be too short or generic)")
        
        # Show statistics
        print("\n\nTag Statistics After Cleanup:")
        
        # Total tags
        cursor.execute("SELECT COUNT(*) as count FROM tags")
        total_tags = cursor.fetchone()['count']
        print(f"  Total tags: {total_tags}")
        
        # Most used tags
        cursor.execute("""
            SELECT t.name, COUNT(st.space_id) as usage_count
            FROM tags t
            JOIN space_tags st ON t.id = st.tag_id
            GROUP BY t.id, t.name
            ORDER BY usage_count DESC
            LIMIT 10
        """)
        
        print("\n  Top 10 most used tags:")
        for row in cursor.fetchall():
            print(f"    {row['name']}: {row['usage_count']} spaces")
        
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    cleanup_bad_tags()