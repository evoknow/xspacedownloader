#!/usr/bin/env python3
"""Test script to verify spaces caching functionality."""

import time
import requests
import json

# Base URL of the app
BASE_URL = "http://localhost:8080"

def test_cache():
    print("Testing caching functionality...\n")
    
    # Test /spaces endpoint
    print("=== Testing /spaces endpoint ===")
    
    # First request - should generate fresh data
    print("1. First request to /spaces (cache miss expected):")
    start_time = time.time()
    response1 = requests.get(f"{BASE_URL}/spaces")
    time1 = time.time() - start_time
    print(f"   Status: {response1.status_code}")
    print(f"   Time: {time1:.2f} seconds")
    print(f"   Response size: {len(response1.text)} bytes\n")
    
    # Second request - should use cache
    print("2. Second request to /spaces (cache hit expected):")
    start_time = time.time()
    response2 = requests.get(f"{BASE_URL}/spaces")
    time2 = time.time() - start_time
    print(f"   Status: {response2.status_code}")
    print(f"   Time: {time2:.2f} seconds")
    print(f"   Response size: {len(response2.text)} bytes")
    if time1 > 0 and time2 > 0:
        print(f"   Speed improvement: {time1/time2:.1f}x faster\n")
    
    # Verify content is the same
    if response1.text == response2.text:
        print("✓ /spaces cache is working correctly - content matches\n")
    else:
        print("✗ Warning: /spaces content differs between requests\n")
    
    # Test index endpoint
    print("=== Testing index (/) endpoint ===")
    
    # First request - should generate fresh data
    print("1. First request to / (cache miss expected):")
    start_time = time.time()
    response3 = requests.get(f"{BASE_URL}/")
    time3 = time.time() - start_time
    print(f"   Status: {response3.status_code}")
    print(f"   Time: {time3:.2f} seconds")
    print(f"   Response size: {len(response3.text)} bytes\n")
    
    # Second request - should use cache
    print("2. Second request to / (cache hit expected):")
    start_time = time.time()
    response4 = requests.get(f"{BASE_URL}/")
    time4 = time.time() - start_time
    print(f"   Status: {response4.status_code}")
    print(f"   Time: {time4:.2f} seconds")
    print(f"   Response size: {len(response4.text)} bytes")
    if time3 > 0 and time4 > 0:
        print(f"   Speed improvement: {time3/time4:.1f}x faster\n")
    
    # Verify content is the same
    if response3.text == response4.text:
        print("✓ Index cache is working correctly - content matches\n")
    else:
        print("✗ Warning: Index content differs between requests\n")
    
    # Wait for cache to expire (for testing, you might want to reduce TTL temporarily)
    print("=== Cache Information ===")
    print("   Cache TTL is 600 seconds (10 minutes)")
    print("   To test expiration, you would need to wait 10 minutes")
    print("   or temporarily modify the TTL in app.py for testing")
    
    print("\n=== Cache Invalidation ===")
    print("   Both caches are invalidated when:")
    print("   - Add/update/delete a space via the admin panel")
    print("   - Add/remove tags from a space")
    print("   - The next request to either / or /spaces will show fresh data")

if __name__ == "__main__":
    try:
        test_cache()
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to the app. Make sure it's running on port 8080")
    except Exception as e:
        print(f"Error: {e}")