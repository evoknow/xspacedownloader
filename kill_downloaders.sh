#!/bin/bash
# kill_downloaders.sh - Kill all running bg_downloader.py processes

echo "Stopping all background downloaders..."

# Find and kill all Python processes running bg_downloader.py
RUNNING_PIDS=$(pgrep -f "[p]ython.*bg_downloader.py"; pgrep -f "[P]ython.*bg_downloader.py")

if [ -n "$RUNNING_PIDS" ]; then
    echo "Found the following bg_downloader processes:"
    ps -o pid,command -p $RUNNING_PIDS
    
    echo "Killing processes..."
    echo "$RUNNING_PIDS" | xargs kill
    
    # Remove any PID files
    rm -f bg_downloader.pid
    
    echo "All background downloaders stopped."
else
    echo "No running background downloaders found."
fi