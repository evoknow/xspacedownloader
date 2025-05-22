#!/bin/bash
# restart_downloader.sh - Fix pending jobs and restart the background downloader

# Exit on error
set -e

# Set script directory as working directory
SCRIPT_DIR=$(dirname "$(realpath "$0")")
cd "$SCRIPT_DIR"

# Create logs directory if it doesn't exist
mkdir -p logs

# Kill any existing bg_downloader.py processes
echo "Stopping existing background downloader processes..."
pkill -f "python bg_downloader.py" || true
sleep 1

# Activate virtual environment
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "Error: Virtual environment not found."
    exit 1
fi

# Verify Python path
PYTHON_PATH=$(which python)
echo "Using Python: $PYTHON_PATH"

# Reset any stuck jobs
echo "Resetting any stuck jobs..."
python fix_pending_jobs.py --reset-all-in-progress
python fix_pending_jobs.py --reset-all-failed

# List pending jobs
echo "Current pending jobs:"
python fix_pending_jobs.py --list-pending

# Start the background downloader with debug mode and no daemon
echo "Starting background downloader in debug mode..."
./bg_downloader.py.sh --debug --no-daemon