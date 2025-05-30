#!/usr/bin/env python3
"""
Test script to send an email directly using SendGrid API
"""
import requests
import json
import sys
import os

# SendGrid API key from environment variable
API_KEY = os.environ.get('SENDGRID_API_KEY')
if not API_KEY:
    print("Error: SENDGRID_API_KEY environment variable not set")
    exit(1)

# Email details
FROM_EMAIL = "noreply@xspacedownload.com"
FROM_NAME = "X Space Downloader"

# Get recipient email from command line or use default
if len(sys.argv) > 1:
    TO_EMAIL = sys.argv[1]
else:
    TO_EMAIL = "kabir@evoknow.com"

TO_NAME = "Test Recipient"

# Set up the API request
url = "https://api.sendgrid.com/v3/mail/send"
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Create the email payload with debug info
current_time = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
payload = {
    "personalizations": [
        {
            "to": [
                {
                    "email": TO_EMAIL,
                    "name": TO_NAME
                }
            ]
        }
    ],
    "from": {
        "email": FROM_EMAIL,
        "name": FROM_NAME
    },
    "subject": f"Test Email - {current_time}",
    "content": [
        {
            "type": "text/html",
            "value": f"""
            <h1>Test Email from X Space Downloader</h1>
            <p>This is a test email sent at {current_time}</p>
            <p>If you're seeing this, email delivery works!</p>
            <p><strong>API Key:</strong> {API_KEY[:5]}...</p>
            <p><strong>From:</strong> {FROM_NAME} &lt;{FROM_EMAIL}&gt;</p>
            <p><strong>To:</strong> {TO_NAME} &lt;{TO_EMAIL}&gt;</p>
            """
        }
    ],
    "mail_settings": {
        "sandbox_mode": {
            "enable": False
        }
    },
    "reply_to": {
        "email": FROM_EMAIL,
        "name": FROM_NAME
    }
}

print(f"Sending test email to {TO_EMAIL}...")
print(f"API Key (first 5 chars): {API_KEY[:5]}...")
print(f"Request URL: {url}")
print(f"Headers: {headers}")
print(f"Payload: {json.dumps(payload, indent=2)}")

try:
    response = requests.post(url, headers=headers, json=payload)
    
    print(f"\nSendGrid API response status: {response.status_code}")
    print(f"SendGrid API response headers: {dict(response.headers)}")
    
    if response.text:
        print(f"SendGrid API response body: {response.text}")
    
    if response.status_code == 202:
        print(f"Email sent successfully (202 Accepted)")
    else:
        print(f"Failed to send email: {response.status_code} - {response.text}")
        
        # Check for common SendGrid issues
        if response.status_code == 401:
            print("HINT: Your API key may be invalid or expired")
        elif response.status_code == 403:
            print("HINT: Your API key may not have the necessary permissions")
        elif "sandbox mode" in response.text.lower():
            print("HINT: Your SendGrid account may be in sandbox mode")
        elif "domain" in response.text.lower():
            print("HINT: The sending domain may not be verified in SendGrid")
            
except Exception as e:
    print(f"Error sending email: {e}")
    import traceback
    traceback.print_exc()