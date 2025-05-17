#!/bin/bash
# bg_downloader.sh - Check if a downloader is already running and start one if needed

# Exit on error
set -e

# Set script directory as working directory
SCRIPT_DIR=$(dirname "$(realpath "$0")")
cd "$SCRIPT_DIR"

# Create logs directory if it doesn't exist
mkdir -p logs

# PID file to keep track of running instance
PID_FILE="$SCRIPT_DIR/bg_downloader.pid"

# Check if daemon is already running via PID file
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null; then
        echo "Background downloader is already running with PID: $PID"
        exit 0
    else
        echo "Stale PID file found. Previous instance might have crashed."
        rm -f "$PID_FILE"
    fi
fi

# Also check if the process is running without a PID file - using broader patterns
# The check needs to find Python processes running bg_downloader.py regardless of the Python path
if pgrep -f "[p]ython.*bg_downloader.py" > /dev/null || pgrep -f "[P]ython.*bg_downloader.py" > /dev/null; then
    echo "Background downloader is already running (no PID file). Will not start a new instance."
    
    # Get all running bg_downloader processes
    RUNNING_PIDS=$(pgrep -f "[p]ython.*bg_downloader.py"; pgrep -f "[P]ython.*bg_downloader.py")
    
    # Get the first PID
    BG_PID=$(echo "$RUNNING_PIDS" | head -n 1)
    
    # List all existing processes for debugging
    echo "Found running bg_downloader processes:"
    ps -o pid,command -p $RUNNING_PIDS
    
    # Try to get the PID and create a PID file
    if [ -n "$BG_PID" ]; then
        echo "$BG_PID" > "$PID_FILE"
        echo "Created PID file with PID: $BG_PID"
    fi
    exit 0
fi

# Parse command line arguments
DEBUG_MODE=0
NO_DAEMON=0
SCAN_INTERVAL=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --debug)
            DEBUG_MODE=1
            shift
            ;;
        --no-daemon)
            NO_DAEMON=1
            shift
            ;;
        --scan-interval)
            SCAN_INTERVAL="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--debug] [--no-daemon] [--scan-interval SECONDS]"
            exit 1
            ;;
    esac
done

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

# Verify Python path
PYTHON_PATH=$(which python)
echo "Using Python: $PYTHON_PATH"

# Check if yt-dlp is installed
if ! python -m pip list | grep -q yt-dlp; then
    echo "yt-dlp not found. Installing yt-dlp..."
    python -m pip install yt-dlp
fi

# Verify yt-dlp installation
YT_DLP_PATH=$(python -c "import shutil; yt_dlp_path = shutil.which('yt-dlp'); print(f'Found yt-dlp at: {yt_dlp_path}' if yt_dlp_path else 'yt-dlp NOT FOUND!')")
echo "$YT_DLP_PATH"

# Build command arguments
ARGS=""
if [ $DEBUG_MODE -eq 1 ]; then
    ARGS="$ARGS --debug"
    DEBUG_LOG="logs/bg_downloader_debug.log"
    echo "Debug mode enabled, logs will be written to $DEBUG_LOG"
    # Create or clear the debug log file
    > "$DEBUG_LOG"
fi

if [ $NO_DAEMON -eq 1 ]; then
    ARGS="$ARGS --no-daemon"
    echo "Running in foreground mode (no daemon)"
fi

if [ ! -z "$SCAN_INTERVAL" ]; then
    ARGS="$ARGS --scan-interval $SCAN_INTERVAL"
    echo "Setting scan interval to $SCAN_INTERVAL seconds"
fi

# Make sure the script is executable
chmod +x bg_downloader.py

# Start the background downloader
echo "Starting background downloader with Python: $PYTHON_PATH"
if [ $DEBUG_MODE -eq 1 ] && [ $NO_DAEMON -eq 1 ]; then
    # In debug mode with no daemon, output to console and log file
    python bg_downloader.py $ARGS 2>&1 | tee -a "$DEBUG_LOG"
else
    # Otherwise run in background
    python bg_downloader.py $ARGS &
    BG_PID=$!
    echo "$BG_PID" > "$PID_FILE"
    echo "Background downloader started with PID: $BG_PID"
    
    # If no-daemon was specified, wait for the process
    if [ $NO_DAEMON -eq 1 ]; then
        wait $BG_PID
        rm -f "$PID_FILE"
    fi
fi