#!/bin/bash
# Setup script for LibreTranslate self-hosted server

echo "Setting up LibreTranslate self-hosted server..."

# Create a directory for LibreTranslate
mkdir -p libretranslate
cd libretranslate

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Docker is not installed. Please install Docker first."
    echo "Visit https://docs.docker.com/get-docker/ for installation instructions."
    exit 1
fi

# Pull and run the LibreTranslate Docker image
echo "Pulling LibreTranslate Docker image..."
docker pull libretranslate/libretranslate

echo "Starting LibreTranslate server on port 5000..."
docker run -d -p 5000:5000 --name libretranslate libretranslate/libretranslate

echo "Checking if LibreTranslate server is running..."
sleep 5
if curl -s http://localhost:5000 > /dev/null; then
    echo "LibreTranslate server is running at http://localhost:5000"
    echo "The translation API is available at http://localhost:5000/translate"
    echo ""
    echo "You can now use the translation features without an API key."
    echo "The mainconfig.json has been updated to use the local server."
else
    echo "LibreTranslate server could not be started or is not responding."
    echo "Please check Docker logs with: docker logs libretranslate"
fi

echo ""
echo "To stop the server: docker stop libretranslate"
echo "To start the server again: docker start libretranslate"
echo "To remove the server: docker rm -f libretranslate"