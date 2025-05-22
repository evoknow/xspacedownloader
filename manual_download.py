#!/usr/bin/env python3
# manual_download.py - Manually download a space without the background downloader

import sys
import os
import time
from components.DownloadSpace import DownloadSpace

def main():
    """Manually download a space"""
    if len(sys.argv) < 2:
        print("Usage: python manual_download.py <space_id|space_url>")
        sys.exit(1)
        
    space_url_or_id = sys.argv[1]
    
    # If it's just an ID, convert to URL
    if '/' not in space_url_or_id:
        space_url = f"https://x.com/i/spaces/{space_url_or_id}"
    else:
        space_url = space_url_or_id
        
    print(f"Downloading space: {space_url}")
    
    # Create downloader
    downloader = DownloadSpace()
    
    # Download synchronously
    output_file = downloader.download(space_url, async_mode=False)
    
    if output_file:
        print(f"Download completed successfully: {output_file}")
        file_size = os.path.getsize(output_file)
        print(f"File size: {file_size} bytes")
    else:
        print("Download failed")

if __name__ == "__main__":
    main()