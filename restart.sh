#!/bin/bash
# restart.sh - Completely restart all services

echo "=== XSpace Downloader - Complete Restart ==="

# Find and kill all Flask app and background downloader processes
echo "Stopping any existing processes..."
pkill -f "python app.py" || true
pkill -f "python bg_downloader.py" || true

# Also check for any process using port 5000 and 5001
PORT_PROCESS_5000=$(lsof -i :5000 -t 2>/dev/null)
if [ ! -z "$PORT_PROCESS_5000" ]; then
    echo "Killing process(es) using port 5000..."
    kill -9 $PORT_PROCESS_5000 2>/dev/null || true
fi

PORT_PROCESS_5001=$(lsof -i :5001 -t 2>/dev/null)
if [ ! -z "$PORT_PROCESS_5001" ]; then
    echo "Killing process(es) using port 5001..."
    kill -9 $PORT_PROCESS_5001 2>/dev/null || true
fi

# Wait for processes to fully terminate
echo "Waiting for processes to terminate..."
sleep 2

# Verify processes are stopped
if pgrep -f "python app.py" > /dev/null || pgrep -f "python bg_downloader.py" > /dev/null; then
    echo "Warning: Some processes could not be terminated."
    echo "Please manually kill them before continuing."
    echo "You can use: killall python"
    exit 1
fi

# Check if port 5000 or 5001 is still in use
if lsof -i :5000 -t 2>/dev/null; then
    echo "Error: Port 5000 is still in use by another process."
    echo "Please manually free the port before continuing."
    exit 1
fi

if lsof -i :5001 -t 2>/dev/null; then
    echo "Error: Port 5001 is still in use by another process."
    echo "Please manually free the port before continuing."
    exit 1
fi

# Check if we're in a virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Activating virtual environment..."
    if [ -d "venv" ]; then
        source venv/bin/activate
    else
        echo "Virtual environment not found. Creating one..."
        python3 -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt || (echo "No requirements.txt found. Installing Flask manually..." && pip install flask==2.0.3 werkzeug==2.0.3 flask-cors==3.0.10)
    fi
fi

# Check if yt-dlp is installed and install it if not
if ! command -v yt-dlp &> /dev/null; then
    echo "yt-dlp not found. Installing yt-dlp..."
    pip install yt-dlp
fi

# Create required directories
mkdir -p logs
mkdir -p downloads

# Make scripts executable
chmod +x app.py
chmod +x bg_downloader.py

# Start the application in a new terminal window if available
if command -v osascript &> /dev/null; then
    # On macOS, use AppleScript to open a new Terminal window
    echo "Starting services in a new terminal window..."
    osascript -e 'tell application "Terminal" to do script "cd \"'$(pwd)'\" && source venv/bin/activate && ./run.sh"'
    echo "Application started in a new terminal window."
    echo "You can access the web interface at: http://127.0.0.1:5000 or http://localhost:5000"
else
    # Otherwise start in the current terminal
    echo "Starting services..."
    ./run.sh
fi