#!/bin/bash
# force-quit.sh - Forcefully terminate all related processes

echo "=== XSpace Downloader - Force Quit ==="
echo "Terminating all related processes..."

# Kill any Python process named app.py or bg_downloader.py
pkill -9 -f "python app.py" || true
pkill -9 -f "python bg_downloader.py" || true

# Find and kill any process using port 5000
PORT_PROCESS=$(lsof -i :5000 -t 2>/dev/null)
if [ ! -z "$PORT_PROCESS" ]; then
    echo "Killing process(es) using port 5000..."
    kill -9 $PORT_PROCESS 2>/dev/null || true
fi

# Check if any other port in the range is being used (for auto-selected ports)
for PORT in {5001..5010}; do
    PORT_PROCESS=$(lsof -i :$PORT -t 2>/dev/null)
    if [ ! -z "$PORT_PROCESS" ]; then
        echo "Killing process(es) using port $PORT..."
        kill -9 $PORT_PROCESS 2>/dev/null || true
    fi
done

# Wait for processes to fully terminate
echo "Waiting for processes to terminate..."
sleep 2

# Verify all processes are stopped
if pgrep -f "python app.py" > /dev/null || pgrep -f "python bg_downloader.py" > /dev/null; then
    echo "Warning: Some processes could not be terminated."
    echo "You may need to manually kill them with: killall python"
else
    echo "All processes terminated successfully."
fi

# Check if ports are now free
if lsof -i :5000 -t 2>/dev/null; then
    echo "Warning: Port 5000 is still in use."
    echo "You may need to restart your system to free this port."
else
    echo "Port 5000 is now free."
fi

echo "Done!"