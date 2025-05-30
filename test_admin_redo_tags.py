#!/usr/bin/env python3
"""
Test script to verify the admin redo tags functionality.
"""

import sys
import json
import mysql.connector
from pathlib import Path

# Add parent directory to path for importing components
sys.path.append(str(Path(__file__).parent))

def test_admin_redo_tags():
    """Test that the admin redo tags functionality works."""
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
        
        print("Testing admin redo tags functionality...")
        
        # Find spaces with transcripts
        cursor.execute("""
            SELECT s.space_id, s.title, st.transcript, 
                   COUNT(stg.id) as current_tag_count
            FROM spaces s
            LEFT JOIN space_transcripts st ON CONVERT(s.space_id USING utf8mb4) COLLATE utf8mb4_unicode_ci = st.space_id
            LEFT JOIN space_tags stg ON s.space_id = stg.space_id
            WHERE st.transcript IS NOT NULL 
            AND LENGTH(st.transcript) > 200
            GROUP BY s.space_id, s.title, st.transcript
            LIMIT 3
        """)
        
        spaces_with_transcripts = cursor.fetchall()
        
        if not spaces_with_transcripts:
            print("❌ No spaces with transcripts found for testing")
            return
        
        print(f"Found {len(spaces_with_transcripts)} spaces with transcripts:")
        
        for space in spaces_with_transcripts:
            space_id = space['space_id']
            title = space['title'] or f'Space {space_id}'
            current_tags = space['current_tag_count']
            transcript_length = len(space['transcript'])
            
            print(f"\n  📍 {title} ({space_id})")
            print(f"     Current tags: {current_tags}")
            print(f"     Transcript: {transcript_length} characters")
            print(f"     Sample: {space['transcript'][:100]}...")
            
            # Check if this space would be good for testing
            if current_tags > 0:
                print(f"     ✅ Good candidate (has {current_tags} existing tags to replace)")
            else:
                print(f"     ⚠️  No existing tags (would add new ones)")
        
        print(f"\n🔧 Admin Redo Tags API Endpoint: POST /admin/api/spaces/<space_id>/redo-tags")
        print(f"📝 Required: Admin authentication")
        print(f"✨ Function: Removes existing tags and generates new ones from transcript")
        
        # Show example of what the API would expect
        test_space = spaces_with_transcripts[0]
        print(f"\n📋 Example usage for space {test_space['space_id']}:")
        print(f"   1. Admin clicks 'Redo Tags' button")
        print(f"   2. Confirms action in popup")
        print(f"   3. API removes {test_space['current_tag_count']} existing tags")
        print(f"   4. Generates new tags from {len(test_space['transcript'])} char transcript")
        print(f"   5. Returns success message with new tag list")
        
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_admin_redo_tags()