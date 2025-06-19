#!/bin/bash
# Script to run the background translation worker

cd "$(dirname "$0")"

# Create logs directory if it doesn't exist
mkdir -p logs

# Kill any existing background translation processes
pkill -f "background_translate.py" 2>/dev/null || true

# Start the background translation worker
echo "Starting background translation worker..."
nohup python3 background_translate.py > logs/background_translate_startup.log 2>&1 &

# Get the PID
PID=$!
echo $PID > background_translate.pid

echo "Background translation worker started with PID: $PID"
echo "Check logs/background_translate.log for worker output"