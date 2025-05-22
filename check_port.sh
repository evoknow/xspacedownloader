#!/bin/bash
# check_port.sh - Check which process is using port 5000

echo "=== Checking port 5000 usage ==="

# Check if lsof is installed
if ! command -v lsof &> /dev/null; then
    echo "lsof command not found. Installing..."
    # This would normally install lsof but since we're on macOS, it should already be there
    echo "Cannot install lsof automatically. Please install it manually."
    exit 1
fi

# Check if port 5000 is in use
PORT_PROCESS=$(lsof -i :5000 -t 2>/dev/null)
if [ -z "$PORT_PROCESS" ]; then
    echo "Port 5000 is not in use."
    exit 0
fi

echo "Port 5000 is in use by the following process(es):"
for PID in $PORT_PROCESS; do
    echo "PID: $PID"
    PS_INFO=$(ps -p $PID -o command= 2>/dev/null)
    if [ ! -z "$PS_INFO" ]; then
        echo "Command: $PS_INFO"
    else
        echo "Process details not available."
    fi
done

echo ""
echo "To kill these processes, run:"
echo "sudo kill -9 $PORT_PROCESS"
echo ""
echo "Or you can use a different port for the Flask app:"
echo "./run_different_port.sh"