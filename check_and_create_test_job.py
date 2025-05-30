#!/usr/bin/env python3

import json
import mysql.connector
from datetime import datetime
import uuid

# Load database config
with open('db_config.json', 'r') as f:
    config = json.load(f)

# Filter out unsupported MySQL connection keys
mysql_config = config['mysql'].copy()
unsupported_keys = ['use_ssl', 'connect_timeout', 'autocommit', 'sql_mode', 
                    'charset', 'use_unicode', 'raise_on_warnings']
for key in unsupported_keys:
    mysql_config.pop(key, None)

# Connect to database
conn = mysql.connector.connect(**mysql_config)
cursor = conn.cursor()

# 1. Check if space '1MYxNgdQwgdxw' exists
space_id = '1MYxNgdQwgdxw'
cursor.execute("SELECT id, url, title FROM spaces WHERE space_id = %s", (space_id,))
result = cursor.fetchone()

if result:
    print(f"Space '{space_id}' already exists in database:")
    print(f"  ID: {result[0]}")
    print(f"  URL: {result[1]}")
    print(f"  Title: {result[2]}")
else:
    print(f"Space '{space_id}' does not exist in database")

# 2. Find a recent space that doesn't exist yet
# Let's check a few recent space IDs
test_space_ids = [
    '1BdxYrqQqQqxX',  # Example format
    '1DXxyRqMRMRxM',
    '1YqxoRqZRqZxo',
    '1MYGNgqXwgqxw',
    '1YpGkgqYkgqxY'
]

new_space_id = None
for test_id in test_space_ids:
    cursor.execute("SELECT id FROM spaces WHERE space_id = %s", (test_id,))
    if not cursor.fetchone():
        new_space_id = test_id
        print(f"\nFound unused space ID: {new_space_id}")
        break

if not new_space_id:
    # Generate a random one if none found
    import random
    import string
    new_space_id = '1' + ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    print(f"\nGenerated new space ID: {new_space_id}")

# 3. Create test download job
job_id = str(uuid.uuid4())
space_url = f"https://twitter.com/i/spaces/{new_space_id}"

insert_query = """
INSERT INTO space_download_scheduler 
(id, space_url, status, priority, created_at, updated_at, 
 scheduled_at, notification_email, user_id)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

values = (
    job_id,
    space_url,
    'pending',
    1,  # priority
    datetime.now(),
    datetime.now(),
    datetime.now(),
    'test@example.com',
    1  # assuming user_id 1 exists
)

try:
    cursor.execute(insert_query, values)
    conn.commit()
    print(f"\nSuccessfully created test download job:")
    print(f"  Job ID: {job_id}")
    print(f"  Space URL: {space_url}")
    print(f"  Status: pending")
    print(f"  Priority: 1")
except mysql.connector.Error as e:
    print(f"\nError creating job: {e}")
    conn.rollback()

# Close connection
cursor.close()
conn.close()