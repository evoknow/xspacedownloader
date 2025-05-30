#!/bin/bash
# Stop the background progress watcher

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

if [ -f "logs/bg_progress_watcher.pid" ]; then
    PID=$(cat logs/bg_progress_watcher.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "Stopping progress watcher (PID $PID)..."
        kill -TERM $PID
        
        # Wait for graceful shutdown
        for i in {1..10}; do
            if ! ps -p $PID > /dev/null 2>&1; then
                echo "Progress watcher stopped successfully"
                rm -f logs/bg_progress_watcher.pid
                exit 0
            fi
            sleep 1
        done
        
        # Force kill if still running
        echo "Progress watcher didn't stop gracefully, forcing..."
        kill -9 $PID
        rm -f logs/bg_progress_watcher.pid
        echo "Progress watcher forcefully stopped"
    else
        echo "Progress watcher not running (stale PID file)"
        rm -f logs/bg_progress_watcher.pid
    fi
else
    echo "Progress watcher is not running (no PID file)"
fi