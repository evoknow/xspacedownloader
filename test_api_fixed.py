#!/usr/bin/env python3
# test_api_fixed.py - Test script for API endpoints that were fixed

import requests
import json
import sys

BASE_URL = 'http://127.0.0.1:5000'  # Default API URL

def get_api_key():
    # This is a simple test to get an API key
    # In a real scenario, you would have a proper API key management system
    try:
        with open('test_api_key.txt', 'r') as f:
            return f.read().strip()
    except:
        print("No API key found in test_api_key.txt")
        print("Create a key first or use an existing one")
        sys.exit(1)

def test_list_users_endpoint():
    """Test the users endpoint that was failing with 'User' object has no attribute 'list_users'"""
    api_key = get_api_key()
    url = f"{BASE_URL}/api/users"
    headers = {
        'X-API-Key': api_key,
        'Content-Type': 'application/json'
    }
    
    response = requests.get(url, headers=headers)
    print("\n--- Testing List Users API Endpoint ---")
    print(f"Status code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Success! Found {len(data.get('data', []))} users")
        print(f"Total: {data.get('total', 0)}")
    else:
        print(f"Error: {response.text}")

def test_list_spaces_endpoint():
    """Test the spaces endpoint that was failing with 'Space.list_spaces() got an unexpected keyword argument 'search_term''"""
    api_key = get_api_key()
    url = f"{BASE_URL}/api/spaces?search=test"  # Now with search term
    headers = {
        'X-API-Key': api_key,
        'Content-Type': 'application/json'
    }
    
    response = requests.get(url, headers=headers)
    print("\n--- Testing List Spaces API Endpoint with Search Term ---")
    print(f"Status code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Success! Found {len(data.get('data', []))} spaces")
        print(f"Total: {data.get('total', 0)}")
    else:
        print(f"Error: {response.text}")

def test_tag_assignment_endpoint():
    """Test the tag assignment endpoint that was failing with 'Tag' object has no attribute 'get_tag_by_name'"""
    api_key = get_api_key()
    # First create a space to tag
    create_space_url = f"{BASE_URL}/api/spaces"
    headers = {
        'X-API-Key': api_key,
        'Content-Type': 'application/json'
    }
    
    # Create a test space
    space_data = {
        'space_url': 'https://x.com/i/spaces/1dRJZEpyjlNGB',  # Test space URL
        'title': 'Test Space for Tag Assignment',
        'notes': 'Testing the tag assignment endpoint'
    }
    
    print("\n--- Testing Tag Assignment API Endpoint ---")
    # Create the space
    response = requests.post(create_space_url, headers=headers, json=space_data)
    if response.status_code not in [201, 409]:  # 201 Created or 409 Already exists
        print(f"Failed to create test space: {response.text}")
        return
        
    # Get the space ID
    space_id = None
    if response.status_code == 201:
        space_id = response.json().get('space_id')
        print(f"Created test space with ID: {space_id}")
    elif response.status_code == 409:
        space_id = response.json().get('space', {}).get('space_id')
        print(f"Using existing space with ID: {space_id}")
    
    if not space_id:
        print("Could not get space ID")
        return
        
    # Now test the tag assignment endpoint
    tag_url = f"{BASE_URL}/api/spaces/{space_id}/tags"
    tag_data = {
        'tag_name': 'test_tag'
    }
    
    response = requests.post(tag_url, headers=headers, json=tag_data)
    print(f"Status code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Success! Tag added to space")
        print(f"Tags: {data.get('tags', [])}")
    else:
        print(f"Error: {response.text}")

if __name__ == '__main__':
    print("Testing API endpoints that were fixed")
    test_list_users_endpoint()
    test_list_spaces_endpoint()
    test_tag_assignment_endpoint()
    print("\nAll tests complete")