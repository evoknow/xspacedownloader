#!/usr/bin/env python3
"""
Script to analyze a transcript to see what tags should be generated.
"""

import json
import mysql.connector
import sys

# Load database config
with open('db_config.json', 'r') as f:
    config = json.load(f)

db_config = config["mysql"].copy()
if 'use_ssl' in db_config:
    del db_config['use_ssl']

connection = mysql.connector.connect(**db_config)
cursor = connection.cursor(dictionary=True)

space_id = sys.argv[1] if len(sys.argv) > 1 else '1dRJZEpyjlNGB'

# Get transcript
cursor.execute("""
    SELECT transcript, language 
    FROM space_transcripts 
    WHERE space_id = %s
    ORDER BY created_at DESC
    LIMIT 1
""", (space_id,))

transcript_data = cursor.fetchone()
if transcript_data:
    print(f"Language: {transcript_data['language']}")
    print(f"Transcript length: {len(transcript_data['transcript'])} characters")
    print("\nFirst 500 characters:")
    print(transcript_data['transcript'][:500])
    print("\n...")
    print("\nLast 500 characters:")
    print(transcript_data['transcript'][-500:])
else:
    print(f"No transcript found for space {space_id}")

cursor.close()
connection.close()