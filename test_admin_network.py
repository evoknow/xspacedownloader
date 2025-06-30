#!/usr/bin/env python3
"""Test admin API network request like a browser would."""

import requests
import json

def test_admin_api():
    """Test admin API call with session."""
    # This won't work without proper session auth,
    # but let's see what the response structure looks like
    
    url = 'http://localhost:5000/admin/api/system_messages'
    
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {response.headers}")
        
        if response.status_code == 403:
            print("Expected 403 - Authentication required")
        else:
            print(f"Response content: {response.text}")
            
        # Test the JSON parsing
        try:
            json_data = response.json()
            print(f"JSON Response: {json.dumps(json_data, indent=2)}")
        except:
            print("Response is not valid JSON")
            
    except requests.exceptions.ConnectionError:
        print("Connection error - server might not be running")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_admin_api()