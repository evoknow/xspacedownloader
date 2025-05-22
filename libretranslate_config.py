#!/usr/bin/env python3
"""
Simple LibreTranslate server for local use.
"""

from libretranslatepy import LibreTranslateLocal
import sys
import time
import os

PORT = 5000
HOST = "localhost"

def main():
    print("Starting LibreTranslate server...")
    print("This may take a while to download language models on first run.")
    
    # Change to the script directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Initialize LibreTranslate
    lt = LibreTranslateLocal()
    
    # Start server
    lt.start_server(host=HOST, port=PORT)
    
    print(f"LibreTranslate server running at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping server...")
        sys.exit(0)

if __name__ == "__main__":
    main()
