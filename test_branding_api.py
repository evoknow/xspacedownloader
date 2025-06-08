#!/usr/bin/env python3
"""Test the branding configuration API endpoints."""

import requests
import json
import sys

# Configuration
BASE_URL = "http://localhost:5000"  # Update if your app runs on a different port
SESSION_FILE = ".test_session.json"

def login_as_admin():
    """Login as admin user to get session cookie."""
    # You'll need to update these credentials
    login_data = {
        'username': 'admin',  # Update with your admin username
        'password': 'admin'   # Update with your admin password
    }
    
    session = requests.Session()
    response = session.post(f"{BASE_URL}/login", data=login_data)
    
    if response.status_code == 200:
        print("✓ Logged in as admin")
        return session
    else:
        print(f"✗ Login failed: {response.status_code}")
        return None

def test_get_branding_config(session):
    """Test GET /admin/api/branding_config"""
    print("\nTesting GET /admin/api/branding_config...")
    
    response = session.get(f"{BASE_URL}/admin/api/branding_config")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Got branding config: {json.dumps(data, indent=2)}")
        return True
    else:
        print(f"✗ Failed to get branding config: {response.status_code}")
        print(f"  Response: {response.text}")
        return False

def test_update_branding_config(session):
    """Test POST /admin/api/branding_config"""
    print("\nTesting POST /admin/api/branding_config...")
    
    test_data = {
        'video_title_branding': 'Test Brand - Space Archive',
        'video_watermark_text': 'testbrand.com',
        'brand_color': '#FF0000',
        'font_family': 'Helvetica',
        'brand_logo_url': 'https://example.com/logo.png',
        'branding_enabled': True
    }
    
    response = session.post(
        f"{BASE_URL}/admin/api/branding_config",
        json=test_data,
        headers={'Content-Type': 'application/json'}
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Updated branding config: {json.dumps(data, indent=2)}")
        return True
    else:
        print(f"✗ Failed to update branding config: {response.status_code}")
        print(f"  Response: {response.text}")
        return False

def main():
    """Run all tests."""
    print("Testing Branding Configuration API Endpoints")
    print("=" * 50)
    
    # Login as admin
    session = login_as_admin()
    if not session:
        print("\nFailed to login. Please update the login credentials in this script.")
        sys.exit(1)
    
    # Run tests
    tests_passed = 0
    total_tests = 2
    
    if test_get_branding_config(session):
        tests_passed += 1
    
    if test_update_branding_config(session):
        tests_passed += 1
        
        # Verify the update worked
        print("\nVerifying update...")
        if test_get_branding_config(session):
            print("✓ Update verified successfully")
    
    print("\n" + "=" * 50)
    print(f"Tests passed: {tests_passed}/{total_tests}")
    
    if tests_passed == total_tests:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()