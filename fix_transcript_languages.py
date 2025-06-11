#!/usr/bin/env python3
"""
Script to fix incorrect language detection in existing transcripts.
Re-analyzes transcript text to detect the correct language and updates the database.
"""

import sys
import os
import json
import mysql.connector
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from components.SpeechToText import SpeechToText

def load_db_config():
    """Load database configuration."""
    try:
        with open('db_config.json', 'r') as f:
            config = json.load(f)
            return config['mysql']
    except Exception as e:
        print(f"Error loading database config: {e}")
        return None

def detect_language_from_text(text):
    """Use SpeechToText component to detect language from text."""
    stt = SpeechToText()
    return stt._detect_language_from_text(text)

def fix_transcript_languages():
    """Fix incorrect language detection in existing transcripts."""
    print("Fixing transcript language detection...\n")
    
    # Load database config
    db_config = load_db_config()
    if not db_config:
        print("Failed to load database configuration")
        return
    
    try:
        # Connect to database
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)
        
        # Get all transcripts that might have incorrect language detection
        print("1. Finding transcripts with potential language issues...")
        query = """
            SELECT id, space_id, language, transcript, 
                   CHAR_LENGTH(transcript) as transcript_length
            FROM space_transcripts 
            WHERE transcript IS NOT NULL 
            AND CHAR_LENGTH(transcript) > 100
            ORDER BY created_at DESC
        """
        cursor.execute(query)
        transcripts = cursor.fetchall()
        
        print(f"   Found {len(transcripts)} transcripts to analyze\n")
        
        updates_made = 0
        languages_found = {}
        
        for i, transcript in enumerate(transcripts, 1):
            transcript_id = transcript['id']
            space_id = transcript['space_id']
            current_language = transcript['language']
            text = transcript['transcript']
            text_length = transcript['transcript_length']
            
            print(f"2. Analyzing transcript {i}/{len(transcripts)}: {space_id}")
            print(f"   Current language: {current_language}")
            print(f"   Text length: {text_length} characters")
            
            # Detect actual language from text
            detected_language = detect_language_from_text(text)
            
            print(f"   Detected language: {detected_language}")
            
            # Track language statistics
            if detected_language not in languages_found:
                languages_found[detected_language] = 0
            languages_found[detected_language] += 1
            
            # Update if language is different and detected language is not unknown
            if detected_language != current_language and detected_language != "unknown":
                print(f"   → Updating {space_id}: {current_language} → {detected_language}")
                
                update_query = """
                    UPDATE space_transcripts 
                    SET language = %s, updated_at = NOW()
                    WHERE id = %s
                """
                cursor.execute(update_query, (detected_language, transcript_id))
                updates_made += 1
                
                # Show sample text for verification
                sample_text = text[:200] + "..." if len(text) > 200 else text
                print(f"   Sample text: {sample_text}")
            else:
                print(f"   ✓ Language is correct")
            
            print()  # Empty line for readability
        
        # Commit changes
        connection.commit()
        
        print(f"3. Summary:")
        print(f"   Total transcripts analyzed: {len(transcripts)}")
        print(f"   Updates made: {updates_made}")
        print(f"   Languages found:")
        for lang, count in sorted(languages_found.items()):
            print(f"     {lang}: {count} transcripts")
        
        # Show transcripts that might need manual review
        print(f"\n4. Transcripts marked as 'unknown' (may need manual review):")
        unknown_query = """
            SELECT space_id, SUBSTRING(transcript, 1, 100) as sample_text
            FROM space_transcripts 
            WHERE language = 'unknown' 
            AND transcript IS NOT NULL 
            AND CHAR_LENGTH(transcript) > 50
            LIMIT 5
        """
        cursor.execute(unknown_query)
        unknown_transcripts = cursor.fetchall()
        
        for transcript in unknown_transcripts:
            print(f"   {transcript['space_id']}: {transcript['sample_text']}...")
        
        if len(unknown_transcripts) == 5:
            cursor.execute("SELECT COUNT(*) as total FROM space_transcripts WHERE language = 'unknown'")
            total_unknown = cursor.fetchone()['total']
            print(f"   ... and {total_unknown - 5} more")
        
        print(f"\n✓ Language detection fix completed successfully!")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'connection' in locals():
            cursor.close()
            connection.close()

if __name__ == "__main__":
    fix_transcript_languages()