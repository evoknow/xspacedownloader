#!/bin/bash

# bg_downloader_wrapper.sh
# Wrapper script to ensure bg_downloader runs as a proper daemon

# Set working directory
cd /var/www/production/xspacedowoad.com/website/htdocs

# Set environment variables
export PATH="/var/www/production/xspacedowoad.com/website/htdocs/venv/bin:$PATH"
export PYTHONPATH="/var/www/production/xspacedowoad.com/website/htdocs"

# Create logs directory if it doesn't exist
mkdir -p logs

# Run the background downloader
exec /var/www/production/xspacedowoad.com/website/htdocs/venv/bin/python bg_downloader.py