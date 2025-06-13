#!/bin/bash
# start.sh - Start all background services for XSpace Downloader

echo "Starting XSpace Downloader background services..."

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

# Start background downloader if needed
echo "Starting background downloader..."
chmod +x bg_downloader.sh
if ./bg_downloader.sh --debug; then
    echo "✓ Background downloader started successfully"
else
    echo "❌ Background downloader failed to start or is already running"
fi

# Start transcription worker if needed
echo "Starting transcription worker..."
chmod +x run_transcribe_worker.sh
if ./run_transcribe_worker.sh; then
    echo "✓ Transcription worker started successfully"
else
    echo "❌ Transcription worker failed to start or is already running"
fi

# Start progress watcher if needed
echo "Starting progress watcher..."
chmod +x run_progress_watcher.sh
if ./run_progress_watcher.sh; then
    echo "✓ Progress watcher started successfully"
else
    echo "❌ Progress watcher failed to start or is already running"
fi

# Wait a moment for processes to fully start
sleep 3

# Check status of all processes
echo ""
echo "📊 Service Status:"
echo "=================="

# Check background downloader
if pgrep -f bg_downloader.py > /dev/null; then
    DOWNLOADER_PID=$(pgrep -f bg_downloader.py)
    echo "✅ Background Downloader: Running (PID: $DOWNLOADER_PID)"
else
    echo "❌ Background Downloader: Not running"
fi

# Check transcription worker
if pgrep -f background_transcribe.py > /dev/null; then
    TRANSCRIBE_PIDS=$(pgrep -f background_transcribe.py | tr '\n' ' ')
    TRANSCRIBE_COUNT=$(pgrep -f background_transcribe.py | wc -l)
    echo "✅ Transcription Worker: Running ($TRANSCRIBE_COUNT process(es), PIDs: $TRANSCRIBE_PIDS)"
else
    echo "❌ Transcription Worker: Not running"
fi

# Check progress watcher
if pgrep -f bg_progress_watcher.py > /dev/null; then
    WATCHER_PID=$(pgrep -f bg_progress_watcher.py)
    echo "✅ Progress Watcher: Running (PID: $WATCHER_PID)"
else
    echo "❌ Progress Watcher: Not running"
fi

echo ""
echo "📁 Log files available in: $SCRIPT_DIR/logs/"
echo "   - bg_downloader.log"
echo "   - bg_transcribe.log"  
echo "   - bg_progress_watcher.log"
echo ""
echo "🔄 To stop all services, run: ./stop.sh"
echo "🔍 To check queue status, visit: /queue"

echo "Start complete."