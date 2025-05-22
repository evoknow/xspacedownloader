#!/usr/bin/env python3
# api_client.py - Example client for the XSpace Downloader API

"""
Example client for XSpace Downloader API
---------------------------------------

This script demonstrates how to use the API Controller to perform common operations.

Examples:
- List spaces
- Download a space
- Check download status
- Manage users and API keys

Usage:
  python3 api_client.py [api_key] [command] [arguments...]

Commands:
  spaces             List spaces
  space <id>         Get space details
  download <id>      Download a space
  status <job_id>    Check download status
  users              List users
  tags               List tags
  stats              Get system statistics

Example:
  python3 api_client.py DEV_API_KEY_DO_NOT_USE_IN_PRODUCTION spaces
"""

import sys
import json
import time
import argparse
import requests
from datetime import datetime

# Default settings
API_HOST = "127.0.0.1"
API_PORT = 5000
API_BASE_URL = f"http://{API_HOST}:{API_PORT}/api"

def make_request(endpoint, method="GET", data=None, api_key=None):
    """Make a request to the API."""
    url = f"{API_BASE_URL}/{endpoint}"
    
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "POST":
            response = requests.post(url, json=data, headers=headers)
        elif method == "PUT":
            response = requests.put(url, json=data, headers=headers)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        # Check for error responses
        if response.status_code >= 400:
            error_msg = response.json().get('error', f"Error {response.status_code}")
            print(f"API Error: {error_msg}")
            return None
        
        return response.json()
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to API server at {url}")
        print("Make sure the API server is running.")
        return None
    except Exception as e:
        print(f"Error making request: {e}")
        return None

def print_json(data):
    """Print data as formatted JSON."""
    print(json.dumps(data, indent=2, default=str))

def list_spaces(api_key, args):
    """List spaces."""
    params = {}
    if args.user_id:
        params['user_id'] = args.user_id
    if args.tag:
        params['tag'] = args.tag
    if args.search:
        params['search'] = args.search
    
    endpoint = f"spaces"
    if params:
        endpoint += "?" + "&".join([f"{k}={v}" for k, v in params.items()])
    
    response = make_request(endpoint, api_key=api_key)
    if response:
        print(f"Found {response['total']} spaces:")
        for space in response['data']:
            print(f"- {space['space_id']}: {space.get('title', 'Untitled')} (Status: {space.get('status', 'pending')})")
            
        if args.verbose:
            print("\nFull response:")
            print_json(response)

def get_space(api_key, args):
    """Get space details."""
    if not args.id:
        print("Error: Space ID is required")
        return
    
    response = make_request(f"spaces/{args.id}", api_key=api_key)
    if response:
        print(f"Space: {response['space_id']}")
        print(f"Title: {response.get('title', 'Untitled')}")
        print(f"URL: {response.get('url', 'Unknown')}")
        print(f"Status: {response.get('status', 'pending')}")
        
        if 'tags' in response and response['tags']:
            print(f"Tags: {', '.join(tag['name'] for tag in response['tags'])}")
        else:
            print("Tags: None")
            
        if 'notes' in response and response['notes']:
            print(f"\nNotes: {response['notes']}")
            
        if 'download' in response and response['download']:
            print("\nDownload Status:")
            download = response['download']
            print(f"  Status: {download.get('status', 'unknown')}")
            print(f"  Progress: {download.get('progress_in_percent', 0)}%")
            if 'file_path' in download and download['file_path']:
                print(f"  File: {download['file_path']}")
        
        if args.verbose:
            print("\nFull response:")
            print_json(response)

def download_space(api_key, args):
    """Download a space."""
    if not args.id:
        print("Error: Space ID is required")
        return
    
    data = {
        "file_type": args.format or "mp3",
        "async": not args.sync
    }
    
    response = make_request(f"spaces/{args.id}/download", method="POST", data=data, api_key=api_key)
    if response:
        print(f"Download request successful: {response['message']}")
        
        if 'job_id' in response:
            print(f"Job ID: {response['job_id']}")
            print("Use 'status' command to check progress")
            
            if args.wait:
                print("\nWaiting for download to complete...")
                wait_for_download(api_key, response['job_id'])
        elif 'file_path' in response:
            print(f"File downloaded to: {response['file_path']}")
        
        if args.verbose:
            print("\nFull response:")
            print_json(response)

def wait_for_download(api_key, job_id, timeout=300):
    """Wait for a download to complete."""
    start_time = time.time()
    last_progress = -1
    
    while time.time() - start_time < timeout:
        response = make_request(f"downloads/{job_id}", api_key=api_key)
        if not response:
            print("Error checking download status")
            return
        
        status = response.get('status', 'unknown')
        progress = response.get('progress_in_percent', 0)
        
        if progress != last_progress:
            print(f"Download progress: {progress}% ({status})")
            last_progress = progress
        
        if status in ['completed', 'failed']:
            if status == 'completed':
                print(f"Download completed: {response.get('file_path', 'Unknown')}")
            else:
                print(f"Download failed: {response.get('error_message', 'Unknown error')}")
            break
        
        time.sleep(2)
    else:
        print(f"Timeout waiting for download to complete after {timeout} seconds")

def check_download_status(api_key, args):
    """Check download status."""
    if not args.job_id:
        print("Error: Job ID is required")
        return
    
    response = make_request(f"downloads/{args.job_id}", api_key=api_key)
    if response:
        print(f"Download Job ID: {response['id']}")
        print(f"Space ID: {response['space_id']}")
        print(f"Status: {response.get('status', 'unknown')}")
        print(f"Progress: {response.get('progress_in_percent', 0)}%")
        
        if 'error_message' in response and response['error_message']:
            print(f"Error: {response['error_message']}")
        
        if args.verbose:
            print("\nFull response:")
            print_json(response)

def list_users(api_key, args):
    """List users."""
    response = make_request("users", api_key=api_key)
    if response:
        print(f"Found {response['total']} users:")
        for user in response['data']:
            print(f"- {user['id']}: {user['username']} ({user.get('email', 'No email')}, {user.get('status', 'unknown')})")
            
        if args.verbose:
            print("\nFull response:")
            print_json(response)

def list_tags(api_key, args):
    """List tags."""
    response = make_request("tags", api_key=api_key)
    if response:
        print(f"Found {len(response)} tags:")
        for tag in response:
            print(f"- {tag['id']}: {tag['name']}")
            
        if args.verbose:
            print("\nFull response:")
            print_json(response)

def get_stats(api_key, args):
    """Get system statistics."""
    response = make_request("stats", api_key=api_key)
    if response:
        print("System Statistics:")
        print(f"Total Users: {response.get('total_users', 0)}")
        print(f"Total Spaces: {response.get('total_spaces', 0)}")
        print(f"Total Downloads: {response.get('total_downloads', 0)}")
        
        if 'downloads_by_status' in response:
            print("\nDownloads by Status:")
            for status, count in response['downloads_by_status'].items():
                print(f"  {status}: {count}")
        
        if 'top_tags' in response:
            print("\nTop Tags:")
            for tag, count in response['top_tags'].items():
                print(f"  {tag}: {count} spaces")
        
        if 'recent_activity' in response:
            print("\nRecent Activity (spaces created):")
            for date, count in response['recent_activity'].items():
                print(f"  {date}: {count} spaces")
        
        if args.verbose:
            print("\nFull response:")
            print_json(response)

def main():
    parser = argparse.ArgumentParser(description="XSpace Downloader API Client")
    parser.add_argument("api_key", help="API key for authentication")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Spaces command
    spaces_parser = subparsers.add_parser("spaces", help="List spaces")
    spaces_parser.add_argument("--user-id", type=int, help="Filter by user ID")
    spaces_parser.add_argument("--tag", help="Filter by tag")
    spaces_parser.add_argument("--search", help="Search term")
    spaces_parser.add_argument("-v", "--verbose", action="store_true", help="Show full response")
    
    # Space command
    space_parser = subparsers.add_parser("space", help="Get space details")
    space_parser.add_argument("id", help="Space ID")
    space_parser.add_argument("-v", "--verbose", action="store_true", help="Show full response")
    
    # Download command
    download_parser = subparsers.add_parser("download", help="Download a space")
    download_parser.add_argument("id", help="Space ID")
    download_parser.add_argument("--format", choices=["mp3", "wav", "m4a", "ogg", "flac"], 
                               help="Output format (default: mp3)")
    download_parser.add_argument("--sync", action="store_true", help="Download synchronously")
    download_parser.add_argument("--wait", action="store_true", help="Wait for async download to complete")
    download_parser.add_argument("-v", "--verbose", action="store_true", help="Show full response")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Check download status")
    status_parser.add_argument("job_id", type=int, help="Download job ID")
    status_parser.add_argument("-v", "--verbose", action="store_true", help="Show full response")
    
    # Users command
    users_parser = subparsers.add_parser("users", help="List users")
    users_parser.add_argument("-v", "--verbose", action="store_true", help="Show full response")
    
    # Tags command
    tags_parser = subparsers.add_parser("tags", help="List tags")
    tags_parser.add_argument("-v", "--verbose", action="store_true", help="Show full response")
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Get system statistics")
    stats_parser.add_argument("-v", "--verbose", action="store_true", help="Show full response")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Execute the appropriate function based on the command
    if args.command == "spaces":
        list_spaces(args.api_key, args)
    elif args.command == "space":
        get_space(args.api_key, args)
    elif args.command == "download":
        download_space(args.api_key, args)
    elif args.command == "status":
        check_download_status(args.api_key, args)
    elif args.command == "users":
        list_users(args.api_key, args)
    elif args.command == "tags":
        list_tags(args.api_key, args)
    elif args.command == "stats":
        get_stats(args.api_key, args)
    else:
        print(f"Unknown command: {args.command}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())