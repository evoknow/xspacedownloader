#!/bin/bash
# run_different_port.sh - Run with a different port to avoid conflicts

# Make the script exit on any error
set -e

# Use a completely different port
FLASK_PORT=8080
export PORT=$FLASK_PORT

echo "=== XSpace Downloader (Port $FLASK_PORT) ==="

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

# Verify yt-dlp installation
YT_DLP_PATH=$(python -c "import shutil; yt_dlp_path = shutil.which('yt-dlp'); print(f'Found yt-dlp at: {yt_dlp_path}' if yt_dlp_path else 'yt-dlp NOT FOUND!')")
echo $YT_DLP_PATH

# Create necessary directories
mkdir -p logs downloads

# Modify the port in app.py for this session only (will restore on next restart)
echo "Setting Flask port to $FLASK_PORT..."
sed -i.bak "s/port = int(os.environ.get('PORT', 5000))/port = int(os.environ.get('PORT', $FLASK_PORT))/" app.py

# Start the background downloader
echo "Starting background downloader with Python: $PYTHON_PATH"
python bg_downloader.py --no-daemon > logs/bg_downloader_latest.log 2>&1 &
BG_PID=$!

# Start the Flask app
echo "Starting Flask app on port $FLASK_PORT with Python: $PYTHON_PATH"
python app.py > logs/flask_latest.log 2>&1 &
FLASK_PID=$!

# Function to handle script termination
function cleanup {
    echo "Shutting down..."
    kill $FLASK_PID 2>/dev/null || true
    kill $BG_PID 2>/dev/null || true
    # Restore original app.py
    if [ -f "app.py.bak" ]; then
        mv app.py.bak app.py
    fi
    exit
}

# Setup trap for SIGINT (Ctrl+C) and SIGTERM
trap cleanup SIGINT SIGTERM

# Keep the script running
echo "Both services are now running. Press Ctrl+C to stop."
echo "You can access the web interface at: http://127.0.0.1:$FLASK_PORT or http://localhost:$FLASK_PORT"

# Monitor logs in real-time
echo "Showing log output. Press Ctrl+C to stop..."
tail -f logs/bg_downloader_latest.log logs/flask_latest.log