#!/usr/bin/env python3
"""
Test the AI prompt for tag generation by showing what would be sent to OpenAI.
"""

import sys
import json
import mysql.connector
from pathlib import Path

# Add parent directory to path for importing components
sys.path.append(str(Path(__file__).parent))

def test_ai_prompt():
    """Show the actual AI prompt that would be sent for existing transcripts."""
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
        
        # Get a real transcript from the database
        cursor.execute("""
            SELECT space_id, transcript, language
            FROM space_transcripts 
            WHERE transcript IS NOT NULL 
            AND LENGTH(transcript) > 500
            LIMIT 1
        """)
        
        space = cursor.fetchone()
        
        if space:
            space_id = space['space_id']
            transcript = space['transcript']
            language = space['language']
            
            print(f"=== AI PROMPT FOR SPACE {space_id} ===")
            print(f"Language: {language}")
            print(f"Transcript length: {len(transcript)} characters")
            print()
            
            # Show the actual prompt that would be sent to AI
            prompt = f"""Analyze the following transcript and generate 5-10 relevant topic tags.

Rules for tags:
1. Tags should be about the main topics, subjects, or themes discussed
2. Use proper nouns when relevant (names of technologies, companies, concepts)
3. Prefer compound terms when they represent a specific concept (e.g., "machine learning", "cyber security")
4. Avoid generic conversational words (talk, discussion, people, good, etc.)
5. Tags should be lowercase unless they are proper nouns
6. Each tag should be 1-3 words maximum
7. Focus on what the conversation is ABOUT, not how it's conducted

Return ONLY a JSON array of tags, nothing else. Example: ["artificial intelligence", "python", "web development"]

Transcript (first 3000 characters):
{transcript[:3000]}..."""

            print("SYSTEM MESSAGE:")
            print("You are a helpful assistant that extracts topic tags from transcripts.")
            print()
            print("USER MESSAGE:")
            print(prompt)
            print()
            
            # Show what manual analysis would suggest
            print("=== MANUAL ANALYSIS ===")
            print("Looking at this transcript, good tags might be:")
            
            # Simple keyword analysis for demonstration
            import re
            from collections import Counter
            
            # Look for capitalized words (likely proper nouns)
            capitalized = re.findall(r'\b[A-Z][a-z]+\b', transcript)
            cap_freq = Counter(capitalized)
            
            print("Most frequent capitalized words (potential names/brands):")
            for word, count in cap_freq.most_common(10):
                if count > 1:
                    print(f"  {word}: {count} times")
            
            # Look for compound terms
            business_terms = re.findall(r'\b(?:business|sales|marketing|customer|client|revenue|profit|strategy|growth|company|startup|entrepreneur)\b', transcript.lower())
            if business_terms:
                print(f"\nBusiness-related terms found: {len(business_terms)} times")
                
            tech_terms = re.findall(r'\b(?:technology|software|digital|online|platform|app|website|data|analytics|ai|artificial intelligence)\b', transcript.lower())
            if tech_terms:
                print(f"Technology-related terms found: {len(tech_terms)} times")
            
            print("\nTo use AI tag generation, set your OpenAI API key:")
            print("export OPENAI_API_KEY='your-api-key-here'")
            print("\nThen run: python regenerate_all_tags.py")
            
        else:
            print("No transcripts found in database")
        
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_ai_prompt()