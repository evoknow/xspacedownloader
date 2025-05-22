#!/bin/bash
# run_with_venv.sh - Run both the Flask app and the background downloader with proper venv activation

# Make the script exit on any error
set -e

echo "=== XSpace Downloader with Virtual Environment ==="

# Kill any existing processes
echo "Stopping any existing processes..."
pkill -f "python app.py" || true
pkill -f "python bg_downloader.py" || true
sleep 1

# Activate virtual environment
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Creating one..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

# Verify Python path
PYTHON_PATH=$(which python)
echo "Using Python: $PYTHON_PATH"

# Install required packages
echo "Installing required packages..."
pip install -r requirements.txt

# Install yt-dlp specifically
echo "Installing yt-dlp..."
pip install yt-dlp --upgrade

# Verify yt-dlp installation
YT_DLP_PATH=$(python -c "import shutil; print(shutil.which('yt-dlp'))")
if [ -z "$YT_DLP_PATH" ]; then
    echo "ERROR: yt-dlp not found after installation!"
    echo "Make sure it's installed in the virtual environment."
    exit 1
else
    echo "yt-dlp found at: $YT_DLP_PATH"
fi

# Reset any failed jobs to pending status
echo "Resetting failed jobs..."
python bg_fix.py

# Create necessary directories
mkdir -p logs downloads

# Start the background downloader
echo "Starting background downloader with Python: $PYTHON_PATH"
python bg_downloader.py --no-daemon &
BG_PID=$!

# Start the Flask app
echo "Starting Flask app with Python: $PYTHON_PATH"
python app.py &
FLASK_PID=$!

# Function to handle script termination
function cleanup {
    echo "Shutting down..."
    kill $FLASK_PID 2>/dev/null || true
    kill $BG_PID 2>/dev/null || true
    exit
}

# Setup trap for SIGINT (Ctrl+C) and SIGTERM
trap cleanup SIGINT SIGTERM

# Keep the script running
echo "Both services are now running. Press Ctrl+C to stop."
echo "You can access the web interface at: http://127.0.0.1:5000 or http://localhost:5000"
wait $FLASK_PID $BG_PID