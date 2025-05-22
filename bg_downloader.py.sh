#!/bin/bash
# bg_downloader.py.sh - Run background downloader in the virtual environment

# Exit on error
set -e

# Set script directory as working directory
SCRIPT_DIR=$(dirname "$(realpath "$0")")
cd "$SCRIPT_DIR"

# Create logs directory if it doesn't exist
mkdir -p logs

# Set up log file
DEBUG_LOG="logs/bg_downloader_debug.log"

# Kill any existing bg_downloader.py processes
echo "Checking for existing processes..."
pkill -f "python bg_downloader.py" || true
sleep 1

# Start with debug mode off
DEBUG_MODE=0
NO_DAEMON=0
SCAN_INTERVAL=""

# Process command line arguments
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

# Start the background downloader
echo "Starting background downloader with Python: $PYTHON_PATH"
if [ $DEBUG_MODE -eq 1 ]; then
    # In debug mode, output to console and log file
    python bg_downloader.py $ARGS 2>&1 | tee -a "$DEBUG_LOG"
else
    # Otherwise just run normally
    python bg_downloader.py $ARGS
fi