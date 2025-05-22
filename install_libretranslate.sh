#!/bin/bash
# Script to install LibreTranslate and its dependencies

set -e  # Exit on error

echo "Installing LibreTranslate and dependencies..."

# Install dependencies
pip install libretranslatepy

# Create a basic config file
cat > libretranslate_config.py << 'EOL'
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
EOL

# Make the config file executable
chmod +x libretranslate_config.py

# Update mainconfig.json to use local server
sed -i.bak 's/"api_url": ".*"/"api_url": "http:\/\/localhost:5000\/translate"/g' mainconfig.json
sed -i.bak 's/"self_hosted": false/"self_hosted": true/g' mainconfig.json

echo ""
echo "LibreTranslate has been installed!"
echo ""
echo "To start the LibreTranslate server, run:"
echo ""
echo "python libretranslate_config.py"
echo ""
echo "Leave that terminal window open while using the application."
echo "The first run will download language models which may take some time."