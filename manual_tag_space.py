#!/usr/bin/env python3
"""
Script to manually add appropriate tags to a space based on its content.
"""

import json
import mysql.connector
import sys
from components.Space import Space

# Load database config
with open('db_config.json', 'r') as f:
    config = json.load(f)

db_config = config["mysql"].copy()
if 'use_ssl' in db_config:
    del db_config['use_ssl']

connection = mysql.connector.connect(**db_config)
cursor = connection.cursor(dictionary=True)

space_id = sys.argv[1] if len(sys.argv) > 1 else '1dRJZEpyjlNGB'

# Based on the transcript content about cybersecurity, these are appropriate tags
appropriate_tags = ['Cybersecurity', 'Online Safety', 'Email Security', 'Mac Security', 'Spam Protection']

# Initialize Space component
space = Space()

# Remove existing poor quality tags
cursor.execute("DELETE FROM space_tags WHERE space_id = %s", (space_id,))
connection.commit()
print(f"Removed existing tags for space {space_id}")

# Add appropriate tags
for tag in appropriate_tags:
    try:
        # Create or get tag
        cursor.execute("SELECT id FROM tags WHERE LOWER(name) = LOWER(%s)", (tag,))
        result = cursor.fetchone()
        
        if result:
            tag_id = result['id']
        else:
            cursor.execute("INSERT INTO tags (name) VALUES (%s)", (tag,))
            tag_id = cursor.lastrowid
            connection.commit()
            print(f"Created tag: {tag}")
        
        # Add to space
        try:
            cursor.execute("INSERT INTO space_tags (space_id, tag_id, user_id) VALUES (%s, %s, %s)", 
                          (space_id, tag_id, 0))
            connection.commit()
            print(f"Added tag '{tag}' to space")
        except:
            print(f"Tag '{tag}' already linked to space")
            
    except Exception as e:
        print(f"Error with tag '{tag}': {e}")

cursor.close()
connection.close()
print("\nTags updated successfully!")