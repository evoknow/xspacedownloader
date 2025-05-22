#!/usr/bin/env python3
import mysql.connector
import json

# Load database configuration
with open('db_config.json', 'r') as f:
    config = json.load(f)

# Create a copy of the mysql config and remove unsupported params
db_config = config['mysql'].copy()
if 'use_ssl' in db_config:
    del db_config['use_ssl']

# Connect to the database
db = mysql.connector.connect(**db_config)
cursor = db.cursor(dictionary=True)

# Query the email_config table
cursor.execute('SELECT * FROM email_config')
results = cursor.fetchall()

# Print the results
for row in results:
    # Convert non-serializable items to strings
    for key, value in row.items():
        if isinstance(value, (bytes, bytearray)):
            row[key] = value.decode('utf-8')
    
    print(json.dumps(row, indent=2, default=str))

# Close connections
cursor.close()
db.close()