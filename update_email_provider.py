#!/usr/bin/env python3
"""
Script to update the active email provider

Usage:
  python update_email_provider.py [provider] [email] [password]
  
Example:
  python update_email_provider.py default-smtp your.email@gmail.com your_app_password
  python update_email_provider.py sendgrid
  python update_email_provider.py mailgun
"""
import mysql.connector
import json
import sys

# Get provider to activate from command line
provider = "default-smtp"
email = None
password = None

if len(sys.argv) > 1:
    provider = sys.argv[1]
    
if len(sys.argv) > 2:
    email = sys.argv[2]

if len(sys.argv) > 3:
    password = sys.argv[3]

# Load database configuration
with open('db_config.json', 'r') as f:
    config = json.load(f)

# Create a copy of the mysql config and remove unsupported params
db_config = config['mysql'].copy()
if 'use_ssl' in db_config:
    del db_config['use_ssl']

try:
    # Connect to the database
    db = mysql.connector.connect(**db_config)
    cursor = db.cursor()
    
    # First disable all providers
    print("Disabling all email providers...")
    cursor.execute("UPDATE email_config SET status = 0")
    
    # Then enable the specified provider
    print(f"Enabling {provider} provider...")
    cursor.execute("UPDATE email_config SET status = 1 WHERE provider = %s", (provider,))
    
    # Check if any rows were affected
    if cursor.rowcount == 0:
        print(f"Error: Provider '{provider}' not found in the database")
    else:
        print(f"Successfully enabled '{provider}' provider")
    
    # Commit the changes
    db.commit()
    
    # Show current config
    print("\nCurrent email_config status:")
    cursor.execute("SELECT id, provider, status FROM email_config")
    for row in cursor.fetchall():
        print(f"ID: {row[0]}, Provider: {row[1]}, Status: {row[2]}")
    
    # Additional updates if using default-smtp
    if provider == "default-smtp" and email and password:
        print("\nUpdating SMTP configuration...")
        
        # Update to use Gmail SMTP with app password
        smtp_config = {
            "from_email": email,
            "from_name": "X Space Downloader",
            "server": "smtp.gmail.com",
            "port": 587,
            "username": email,
            "password": password,
            "use_tls": 1
        }
        
        # Update the configuration
        cursor.execute("""
            UPDATE email_config 
            SET from_email = %s, from_name = %s, server = %s, port = %s, 
                username = %s, password = %s, use_tls = %s
            WHERE provider = 'default-smtp'
        """, (
            smtp_config["from_email"],
            smtp_config["from_name"],
            smtp_config["server"],
            smtp_config["port"],
            smtp_config["username"],
            smtp_config["password"],
            smtp_config["use_tls"]
        ))
        
        db.commit()
        print("SMTP configuration updated successfully")
    
except Exception as e:
    print(f"Error: {e}")
finally:
    if 'cursor' in locals():
        cursor.close()
    if 'db' in locals():
        db.close()