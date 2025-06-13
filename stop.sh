#!/bin/bash
# stop.sh - Stop all background services for XSpace Downloader

echo "Stopping XSpace Downloader background services..."

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Stop background downloader
echo "Stopping background downloader..."
pkill -f bg_downloader.py
if [ $? -eq 0 ]; then
    echo "✓ Background downloader stopped"
else
    echo "ℹ Background downloader was not running"
fi

# Stop transcription worker
echo "Stopping transcription worker..."
pkill -f background_transcribe.py
if [ $? -eq 0 ]; then
    echo "✓ Transcription worker stopped"
else
    echo "ℹ Transcription worker was not running"
fi

# Stop progress watcher
echo "Stopping progress watcher..."
pkill -f bg_progress_watcher.py
if [ $? -eq 0 ]; then
    echo "✓ Progress watcher stopped"
else
    echo "ℹ Progress watcher was not running"
fi

# Remove PID files if they exist
echo "Cleaning up PID files..."
rm -f logs/bg_downloader.pid
rm -f logs/bg_transcribe.pid
rm -f logs/bg_progress_watcher.pid

# Wait a moment for processes to fully terminate
sleep 2

# Check if any processes are still running
REMAINING_PROCESSES=$(ps aux | grep -E "(bg_downloader|background_transcribe|bg_progress_watcher)" | grep -v grep | wc -l)

if [ $REMAINING_PROCESSES -eq 0 ]; then
    echo "✅ All background services stopped successfully"
else
    echo "⚠️  Warning: $REMAINING_PROCESSES process(es) may still be running"
    echo "Running processes:"
    ps aux | grep -E "(bg_downloader|background_transcribe|bg_progress_watcher)" | grep -v grep
fi

echo "Stop complete."