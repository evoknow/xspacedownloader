#!/usr/bin/env python3
"""
Test script to check if testers are properly loaded and used
"""
import json
import mysql.connector
from components.Email import Email

def print_separator():
    print("-" * 60)

# First check the testers JSON in the database
try:
    # Create a copy of the mysql config and remove unsupported params
    with open('db_config.json', 'r') as f:
        config = json.load(f)
    
    db_config = config['mysql'].copy()
    if 'use_ssl' in db_config:
        del db_config['use_ssl']
    
    # Connect to the database
    db = mysql.connector.connect(**db_config)
    cursor = db.cursor(dictionary=True)
    
    # Get the sendgrid provider
    cursor.execute('SELECT * FROM email_config WHERE provider = "sendgrid" AND status = 1')
    result = cursor.fetchone()
    
    if result and 'testers' in result:
        print("Testers field from database:")
        testers = result['testers']
        print(f"Type: {type(testers)}")
        print(f"Value: {testers}")
        
        # Try to parse if it's a string
        if isinstance(testers, str):
            try:
                parsed_testers = json.loads(testers)
                print(f"Parsed testers: {json.dumps(parsed_testers, indent=2)}")
                print(f"Number of testers: {len(parsed_testers)}")
                print(f"Enabled testers: {[t for t in parsed_testers if t.get('enabled')]}")
            except Exception as e:
                print(f"Failed to parse testers JSON: {e}")
    else:
        print("No sendgrid provider found or testers field missing")
    
    cursor.close()
    db.close()
    
except Exception as e:
    print(f"Error checking database: {e}")

print_separator()

# Now use the Email component to test getting testers
try:
    print("Testing Email._get_testers()")
    email = Email()
    testers = email._get_testers()
    
    print(f"Type: {type(testers)}")
    print(f"Value: {json.dumps(testers, indent=2, default=str)}")
    print(f"Number of testers: {len(testers)}")
    
    # Test the send method with debug output
    print_separator()
    print("Testing Email.send() without specifying recipients (should use testers)")
    
    current_time = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = f"Test Email to Testers - {current_time}"
    body = f"""
    <h1>Test Email to Testers</h1>
    <p>This email should be sent to all enabled testers.</p>
    <p>Time: {current_time}</p>
    """
    
    result = email.send(subject=subject, body=body)
    print(f"Send result: {result}")
    
except Exception as e:
    print(f"Error testing Email component: {e}")
    import traceback
    traceback.print_exc()