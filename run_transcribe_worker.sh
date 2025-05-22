#!/bin/bash
# run_transcribe_worker.sh - Start and monitor the background transcription worker

# Check if the worker is already running
check_worker() {
  if ps aux | grep -q "[p]ython.*background_transcribe\.py"; then
    return 0  # Worker is running
  else
    return 1  # Worker is not running
  fi
}

# Activate virtual environment if it exists
if [ -d "venv" ]; then
  echo "Activating virtual environment..."
  source venv/bin/activate
fi

# Ensure the transcript_jobs directory exists
mkdir -p transcript_jobs

# Start the worker if it's not running
if ! check_worker; then
  echo "Starting background transcription worker..."
  python background_transcribe.py &
  sleep 2
  
  # Check if it started successfully
  if check_worker; then
    echo "Background transcription worker started successfully."
  else
    echo "Failed to start background transcription worker."
    exit 1
  fi
else
  echo "Background transcription worker is already running."
fi

echo "Worker is monitoring transcript_jobs directory for new jobs."