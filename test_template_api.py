#!/usr/bin/env python3
"""Test template API endpoint directly."""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app
from flask import session

# Create a test client
with app.test_client() as client:
    # Try without session
    print("Testing without session:")
    response = client.get('/admin/api/templates')
    print(f"Status: {response.status_code}")
    print(f"Response: {response.get_data(as_text=True)[:100]}")
    
    # Try with session
    print("\nTesting with admin session:")
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['is_admin'] = True
    
    response = client.get('/admin/api/templates')
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        import json
        data = json.loads(response.get_data(as_text=True))
        print(f"Templates count: {len(data['templates'])}")
        print(f"First template: {data['templates'][0]['name'] if data['templates'] else 'None'}")
    else:
        print(f"Response: {response.get_data(as_text=True)}")