#!/bin/bash
# setup.sh - Set up the development environment for XSpace Downloader

echo "XSpace Downloader - Setup Script"
echo "--------------------------------"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "Error: Failed to create virtual environment."
        echo "Please make sure Python 3 is installed and try again."
        exit 1
    fi
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "Error: Failed to activate virtual environment."
    exit 1
fi

# Install required packages
echo "Installing required packages..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "Error: Failed to install required packages."
    exit 1
fi

# Install yt-dlp if not available
if ! command -v yt-dlp &> /dev/null; then
    echo "Installing yt-dlp..."
    pip install yt-dlp
    if [ $? -ne 0 ]; then
        echo "Error: Failed to install yt-dlp."
        exit 1
    fi
fi

# Create required directories
echo "Creating required directories..."
mkdir -p downloads
mkdir -p logs

# Check for database configuration
if [ ! -f "db_config.json" ]; then
    echo "Creating sample db_config.json file..."
    cat > db_config.json << EOF
{
    "type": "mysql",
    "mysql": {
        "host": "localhost",
        "port": 3306,
        "database": "xspacedownloader",
        "user": "your_mysql_user",
        "password": "your_mysql_password",
        "use_ssl": false
    }
}
EOF
    echo "Please edit db_config.json with your MySQL database credentials."
fi

# Make scripts executable
echo "Making scripts executable..."
chmod +x app.py
chmod +x bg_downloader.py
chmod +x run.sh
chmod +x fix_jobs.py

echo ""
echo "Setup complete! You can now run the application with:"
echo "./run.sh"
echo ""