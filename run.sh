#!/bin/bash
# run.sh - Run both the Flask app and the background downloader
# Usage: ./run.sh [dev|prod]
# dev  - Development mode (opens browser automatically)
# prod - Production mode (does not open browser)

# Make the script exit on any error
set -e

# Parse command line arguments
MODE="${1:-dev}"  # Default to dev mode if no argument provided

# Validate mode
if [[ "$MODE" != "dev" && "$MODE" != "prod" ]]; then
    echo "Usage: $0 [dev|prod]"
    echo "  dev  - Development mode (opens browser automatically)"
    echo "  prod - Production mode (does not open browser)"
    exit 1
fi

echo "Running in $MODE mode..."

# Make sure the script is executable
chmod +x app.py
chmod +x bg_downloader.py

# Create logs directory if it doesn't exist
mkdir -p logs

# Create downloads directory if it doesn't exist
mkdir -p downloads

# Kill any existing Flask processes
echo "Checking for existing processes..."
pkill -f "python app.py" || true
sleep 1

# This section is now handled by bg_downloader.sh
# The check below is just for informational purposes
if pgrep -f "[p]ython.*bg_downloader.py" > /dev/null || pgrep -f "[P]ython.*bg_downloader.py" > /dev/null; then
    echo "Background downloader is already running. Will be managed by bg_downloader.sh."
    
    # List all running downloader processes for debugging
    RUNNING_PIDS=$(pgrep -f "[p]ython.*bg_downloader.py"; pgrep -f "[P]ython.*bg_downloader.py")
    echo "Found running bg_downloader processes:"
    ps -o pid,command -p $RUNNING_PIDS
fi

# Use port 5001 for this application
PORT=5001
if nc -z localhost $PORT 2>/dev/null; then
    echo "Warning: Port $PORT is already in use!"
    echo "Will try to stop the process using that port..."
    PORT_PROCESS=$(lsof -i :$PORT -t 2>/dev/null)
    if [ ! -z "$PORT_PROCESS" ]; then
        echo "Killing process(es) using port $PORT..."
        kill -9 $PORT_PROCESS 2>/dev/null || true
        sleep 2
    fi
    
    # Verify port is now available
    if nc -z localhost $PORT 2>/dev/null; then
        echo "Port $PORT is still in use, trying to find another port..."
        PORT=5000
        while nc -z localhost $PORT 2>/dev/null; do
            echo "Port $PORT is already in use, trying next port..."
            PORT=$((PORT+1))
        done
    fi
fi
echo "Using port $PORT for the web interface"

# Export port for Flask app
export PORT=$PORT

# Ensure we're using the virtual environment
# Activate virtual environment
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "Virtual environment not found. Creating one..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
fi

# Verify we're in the virtual environment
PYTHON_PATH=$(which python)
echo "Using Python: $PYTHON_PATH"

# Check if yt-dlp is installed and install it if not
if ! python -m pip list | grep -q yt-dlp; then
    echo "yt-dlp not found. Installing yt-dlp..."
    python -m pip install yt-dlp
fi

# Verify yt-dlp is installed
python -c "import shutil; print(f'yt-dlp path: {shutil.which(\"yt-dlp\")}')" || echo "Warning: yt-dlp not found!"

# If the status column needs to be converted, do it
if [ -f "convert_status.py" ]; then
    echo "Checking and fixing database status column..."
    python convert_status.py
fi

# Fix any inconsistent job statuses in the database
if [ -f "fix_db_job_status.sh" ]; then
    echo "Checking and fixing inconsistent job statuses..."
    chmod +x fix_db_job_status.sh
    ./fix_db_job_status.sh
fi

# Start the background downloader using the new bg_downloader.sh script
echo "Checking and starting background downloader if needed..."
chmod +x bg_downloader.sh
./bg_downloader.sh --debug
echo "Background downloader check complete"

# Start transcription worker if needed
echo "Checking and starting transcription worker if needed..."
chmod +x run_transcribe_worker.sh
./run_transcribe_worker.sh
echo "Transcription worker check complete"

# Start progress watcher if needed
echo "Checking and starting progress watcher if needed..."
chmod +x run_progress_watcher.sh
./run_progress_watcher.sh 2>/dev/null || echo "Progress watcher already running or failed to start"
echo "Progress watcher check complete"

BG_PID=""

# Start the Flask app
echo "Starting Flask app on port $PORT with Python: $PYTHON_PATH"
python app.py &
FLASK_PID=$!

# Function to handle script termination
function cleanup {
    echo "Shutting down..."
    kill $FLASK_PID 2>/dev/null || true
    
    # We're not killing the background downloader anymore
    # It now runs independently and is managed by bg_downloader.sh
    # If you want to stop it, you need to use 'pkill -f "python bg_downloader.py"'
    echo "Flask app stopped. Background downloader (if running) will continue in the background."
    exit
}

# Setup trap for SIGINT (Ctrl+C) and SIGTERM
trap cleanup SIGINT SIGTERM

# Keep the script running
echo "Flask app is now running. Press Ctrl+C to stop."
echo "Background downloader is running independently and will continue even if Flask is stopped."
echo "You can access the web interface at: http://127.0.0.1:$PORT or http://localhost:$PORT"

# Open browser in dev mode
if [[ "$MODE" == "dev" ]]; then
    echo "Opening browser in development mode..."
    
    # Wait a moment for the server to start
    sleep 2
    
    # Check if Flask is actually running
    if kill -0 $FLASK_PID 2>/dev/null; then
        # Detect the operating system and open browser accordingly
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            open "http://localhost:$PORT"
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            # Linux
            if command -v xdg-open > /dev/null; then
                xdg-open "http://localhost:$PORT"
            elif command -v gnome-open > /dev/null; then
                gnome-open "http://localhost:$PORT"
            elif command -v kde-open > /dev/null; then
                kde-open "http://localhost:$PORT"
            else
                echo "Could not detect a way to open the browser on this Linux system."
                echo "Please manually open: http://localhost:$PORT"
            fi
        elif [[ "$OSTYPE" == "cygwin" || "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
            # Windows
            start "http://localhost:$PORT"
        else
            echo "Unknown operating system. Please manually open: http://localhost:$PORT"
        fi
    else
        echo "Flask app failed to start. Not opening browser."
    fi
else
    echo "Production mode - browser will not open automatically."
fi

wait $FLASK_PID
