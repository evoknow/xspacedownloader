#!/usr/bin/env python3
# download.py - Simple quiet downloader for X Spaces

import sys
import os
import time
from datetime import datetime

# Handle virtual environment setup quietly
if not (hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)):
    venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "bin", "python")
    if os.path.exists(venv_python):
        os.execv(venv_python, [venv_python] + sys.argv)
        sys.exit(0)

# Create downloads directory if needed
os.makedirs("downloads", exist_ok=True)

# Print minimal usage info if no URL provided
if len(sys.argv) < 2:
    print("Usage: download.py [URL] [file_type]")
    sys.exit(1)

# Get arguments
url = sys.argv[1]
file_type = sys.argv[2] if len(sys.argv) > 2 else "mp3"

# Import the component
from components.DownloadSpace import DownloadSpace

# Create downloader and turn off verbose logging
import logging
logging.getLogger('DownloadSpace').setLevel(logging.ERROR)

# Extract space ID for reporting
space_id = None
import re
match = re.search(r'spaces/([a-zA-Z0-9]+)(?:\?|$)', url)
if match:
    space_id = match.group(1)

if space_id:
    print(f"Space: {space_id} ({file_type})")
else:
    print(f"Downloading: {url}")

# Download the space
try:
    downloader = DownloadSpace()
    output_file = downloader.download(url, file_type=file_type, async_mode=False)
    
    if output_file and os.path.exists(output_file):
        file_size = os.path.getsize(output_file) / (1024 * 1024)
        print(f"File: {os.path.basename(output_file)} ({file_size:.2f} MB)")
    else:
        print("Failed to download.")
except Exception as e:
    print(f"Error: {str(e)}")
    sys.exit(1)