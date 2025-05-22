#!/bin/bash
# Setup script for LibreTranslate without Docker

echo "Setting up LibreTranslate without Docker..."

# Create a directory for LibreTranslate
mkdir -p libretranslate
cd libretranslate

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Please install Python first."
    exit 1
fi

# Create virtual environment
echo "Creating virtual environment for LibreTranslate..."
python3 -m venv venv
source venv/bin/activate

# Install LibreTranslate
echo "Installing LibreTranslate from PyPI..."
pip install libretranslate

# Update mainconfig.json to use the local server
echo "Updating configuration to use local LibreTranslate server..."
cd ..
sed -i.bak 's/"self_hosted_url": "http:\/\/localhost:5000\/translate"/"self_hosted_url": "http:\/\/localhost:5000\/translate"/g' mainconfig.json
sed -i.bak 's/"self_hosted": false/"self_hosted": true/g' mainconfig.json

echo ""
echo "LibreTranslate has been installed. To start the server, run:"
echo ""
echo "cd libretranslate"
echo "source venv/bin/activate"
echo "libretranslate --host localhost --port 5000"
echo ""
echo "Once the server is running, restart your application to use translation features."