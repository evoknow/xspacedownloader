#!/bin/bash
# run_webapp.sh - Run only the Flask web app

# Make sure the script is executable
chmod +x app.py

# Create logs directory if it doesn't exist
mkdir -p logs

# Kill any existing Flask processes
echo "Checking for existing processes..."
pkill -f "python app.py" || true
sleep 1

# Check if we're in a virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Activating virtual environment..."
    if [ -d "venv" ]; then
        source venv/bin/activate
    else
        echo "Virtual environment not found. Creating one..."
        python3 -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt || (echo "No requirements.txt found. Installing Flask manually..." && pip install flask==2.0.3 werkzeug==2.0.3 flask-cors==3.0.10)
    fi
fi

# Start the Flask app in the foreground (not backgrounded)
echo "Starting Flask web app..."
echo "You can access the web interface at: http://127.0.0.1:5000 or http://localhost:5000"
python app.py