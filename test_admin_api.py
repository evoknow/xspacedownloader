#!/usr/bin/env python3
"""Test admin system messages API response."""

import json
import mysql.connector
from datetime import datetime

def simulate_admin_api():
    """Simulate what the admin API should return."""
    # Load database configuration
    with open('db_config.json', 'r') as f:
        config = json.load(f)
    
    db_config = config["mysql"].copy()
    if 'use_ssl' in db_config:
        del db_config['use_ssl']
    
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Same query as admin API
        cursor.execute("""
            SELECT id, message, start_date, end_date, status,
                   created_at, updated_at
            FROM system_messages
            WHERE status != -1
            ORDER BY start_date DESC
        """)
        messages = cursor.fetchall()
        print(f"Found {len(messages)} messages")
        
        # Convert datetime objects to strings (same as admin API)
        for msg in messages:
            print(f"\nProcessing message {msg['id']}:")
            print(f"  Raw start_date: {msg['start_date']} ({type(msg['start_date'])})")
            print(f"  Raw end_date: {msg['end_date']} ({type(msg['end_date'])})")
            
            msg['start_date'] = msg['start_date'].isoformat() if msg['start_date'] else None
            msg['end_date'] = msg['end_date'].isoformat() if msg['end_date'] else None
            msg['created_at'] = msg['created_at'].isoformat() if msg['created_at'] else None
            msg['updated_at'] = msg['updated_at'].isoformat() if msg['updated_at'] else None
            
            print(f"  Converted start_date: {msg['start_date']}")
            print(f"  Converted end_date: {msg['end_date']}")
        
        response = {'messages': messages}
        print(f"\nFinal response structure:")
        print(json.dumps(response, indent=2))
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    simulate_admin_api()