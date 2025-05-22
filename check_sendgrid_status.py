#!/usr/bin/env python3
"""
Script to check SendGrid account status
"""
import requests
import json

# SendGrid API key from the database record
API_KEY = "YOUR_SENDGRID_API_KEY"

# Set up headers for API requests
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Function to make a SendGrid API request
def make_sendgrid_request(endpoint):
    url = f"https://api.sendgrid.com/v3/{endpoint}"
    try:
        response = requests.get(url, headers=headers)
        return response
    except Exception as e:
        print(f"Error making request to {url}: {e}")
        return None

# Check account information
print("Checking SendGrid account info...")
account_info = make_sendgrid_request("user/profile")

if account_info:
    print(f"Status code: {account_info.status_code}")
    if account_info.status_code == 200:
        print(f"Account info: {json.dumps(account_info.json(), indent=2)}")
    else:
        print(f"Error response: {account_info.text}")

print("\n" + "-" * 50 + "\n")

# Check sender authentication (domains)
print("Checking authenticated domains...")
domains = make_sendgrid_request("whitelabel/domains")

if domains:
    print(f"Status code: {domains.status_code}")
    if domains.status_code == 200:
        domains_data = domains.json()
        if domains_data:
            print(f"Found {len(domains_data)} authenticated domains:")
            for domain in domains_data:
                print(f"- {domain.get('domain')}: verified={domain.get('valid')}")
        else:
            print("No authenticated domains found. This is likely the issue!")
            print("SendGrid requires domain authentication for reliable delivery.")
    else:
        print(f"Error response: {domains.text}")

print("\n" + "-" * 50 + "\n")

# Check sender identity
print("Checking sender identities...")
senders = make_sendgrid_request("senders")

if senders:
    print(f"Status code: {senders.status_code}")
    if senders.status_code == 200:
        senders_data = senders.json()
        if senders_data:
            print(f"Found {len(senders_data)} sender identities:")
            for sender in senders_data:
                print(f"- {sender.get('nickname')}: {sender.get('from_email')} (verified={sender.get('verified')})")
        else:
            print("No sender identities found. This could be an issue!")
    else:
        print(f"Error response: {senders.text}")

print("\n" + "-" * 50 + "\n")

# Check account level limitations
print("Checking account type and limitations...")
access = make_sendgrid_request("access_settings/activity")

if access:
    print(f"Status code: {access.status_code}")
    if access.status_code == 200:
        print(f"Access settings: {json.dumps(access.json(), indent=2)}")
    else:
        print(f"Error response: {access.text}")

# Summary
print("\n" + "-" * 50 + "\n")
print("Likely causes for emails not being received:")
print("1. Domain Authentication: 'xspacedownload.com' may not be verified in SendGrid")
print("2. Sandbox Mode: The account may be in sandbox/test mode where emails are accepted but not delivered")
print("3. Email Filtering: Your email provider may be filtering these messages")
print("\nRecommended actions:")
print("1. Verify the domain in SendGrid")
print("2. Check account restrictions/sandbox status")
print("3. Create a custom sender verification")
print("4. Check your spam folder")
print("5. Try using a different email provider like Gmail for testing")