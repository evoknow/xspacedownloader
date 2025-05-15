#!/bin/bash
# dump_schema.sh - Extract MySQL database schema using Python
#
# This simplified script uses Python to extract the database schema
# which works better with limited database permissions

set -e  # Exit on error

# Text colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
RESET='\033[0m'

echo -e "${BLUE}XSpace Downloader - Database Schema Extraction (Simple Version)${RESET}"
echo -e "This script will extract the database schema using Python"
echo

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 not found${RESET}"
    echo -e "Please install Python 3 to use this script"
    exit 1
fi

# Check if mysql-connector-python is installed
echo -e "${BLUE}Checking for required Python packages...${RESET}"
python3 -c "import mysql.connector" 2>/dev/null || {
    echo -e "${YELLOW}mysql-connector-python is not installed. Attempting to install...${RESET}"
    pip3 install mysql-connector-python || {
        echo -e "${RED}Failed to install mysql-connector-python${RESET}"
        echo -e "Please install it manually with: pip3 install mysql-connector-python"
        exit 1
    }
}

echo -e "${GREEN}All requirements satisfied${RESET}"

# Run the Python script
echo -e "${BLUE}Running schema extraction...${RESET}"
python3 extract_schema.py