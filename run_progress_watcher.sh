#!/bin/bash
# Start the background progress watcher

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "No virtual environment found, using system Python"
fi

# Create logs directory if it doesn't exist
mkdir -p logs

# Check if already running
if [ -f "logs/bg_progress_watcher.pid" ]; then
    PID=$(cat logs/bg_progress_watcher.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "Progress watcher already running with PID $PID"
        exit 1
    else
        echo "Removing stale PID file"
        rm -f logs/bg_progress_watcher.pid
    fi
fi

# Start the progress watcher
echo "Starting background progress watcher..."
nohup python3 bg_progress_watcher.py > logs/bg_progress_watcher.out 2> logs/bg_progress_watcher.err &

# Wait a moment and check if it started
sleep 2
if [ -f "logs/bg_progress_watcher.pid" ]; then
    PID=$(cat logs/bg_progress_watcher.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "Progress watcher started successfully with PID $PID"
        echo "Logs: logs/bg_progress_watcher.log"
        echo "Output: logs/bg_progress_watcher.out"
        echo "Errors: logs/bg_progress_watcher.err"
    else
        echo "Progress watcher failed to start"
        exit 1
    fi
else
    echo "Progress watcher failed to create PID file"
    exit 1
fi