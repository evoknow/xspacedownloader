#!/bin/bash
# Test script to diagnose progress watcher issues

echo "=== Progress Watcher Diagnostic ==="
echo "Current directory: $(pwd)"
echo "Date: $(date)"

# Check if script exists
if [ ! -f "run_progress_watcher.sh" ]; then
    echo "ERROR: run_progress_watcher.sh not found"
    exit 1
fi

# Check if Python script exists
if [ ! -f "bg_progress_watcher.py" ]; then
    echo "ERROR: bg_progress_watcher.py not found"
    exit 1
fi

# Check if downloads directory exists
if [ ! -d "downloads" ]; then
    echo "WARNING: downloads directory doesn't exist"
    mkdir -p downloads
    echo "Created downloads directory"
fi

# Check if logs directory exists
if [ ! -d "logs" ]; then
    echo "WARNING: logs directory doesn't exist"
    mkdir -p logs
    echo "Created logs directory"
fi

# Check for existing PID file
if [ -f "logs/bg_progress_watcher.pid" ]; then
    PID=$(cat logs/bg_progress_watcher.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "Progress watcher already running with PID $PID"
        exit 0
    else
        echo "Removing stale PID file"
        rm -f logs/bg_progress_watcher.pid
    fi
fi

# Check virtual environment
if [ -d "venv" ]; then
    echo "Virtual environment found"
    source venv/bin/activate
    echo "Using Python: $(which python)"
else
    echo "No virtual environment found, using system Python"
    echo "Using Python: $(which python3)"
fi

# Check database config
if [ ! -f "db_config.json" ]; then
    echo "ERROR: db_config.json not found"
    exit 1
else
    echo "Database config found"
fi

# Try to run the progress watcher with output
echo "=== Attempting to start progress watcher with full output ==="
echo "Running: python3 bg_progress_watcher.py"

# Run in foreground to see any errors
python3 bg_progress_watcher.py &
WATCHER_PID=$!

# Wait a moment and check if it's still running
sleep 3

if ps -p $WATCHER_PID > /dev/null 2>&1; then
    echo "Progress watcher started successfully with PID $WATCHER_PID"
    # Kill it since this is just a test
    kill $WATCHER_PID
    echo "Test completed - killed process"
else
    echo "Progress watcher failed to start or exited immediately"
    echo "Check logs/bg_progress_watcher.log for details"
    if [ -f "logs/bg_progress_watcher.log" ]; then
        echo "=== Last 10 lines of log ==="
        tail -10 logs/bg_progress_watcher.log
    fi
fi