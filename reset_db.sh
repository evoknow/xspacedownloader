#!/bin/bash
# reset_db.sh - Script to clear all test data from the database

# Text colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
RESET='\033[0m'

echo -e "${BLUE}${BOLD}XSpace Downloader - Database Reset Utility${RESET}"
echo -e "This script clears test data and resets the space_download_scheduler table"
echo

# Load database configuration
if [ ! -f "db_config.json" ]; then
    echo -e "${RED}Error: db_config.json not found${RESET}"
    exit 1
fi

# Try to use jq for better JSON parsing if available
if command -v jq &> /dev/null; then
    echo -e "${GREEN}Using jq to parse config file${RESET}"
    DB_HOST=$(jq -r '.mysql.host' db_config.json)
    DB_PORT=$(jq -r '.mysql.port' db_config.json)
    DB_USER=$(jq -r '.mysql.user' db_config.json)
    DB_PASS=$(jq -r '.mysql.password' db_config.json)
    DB_NAME=$(jq -r '.mysql.database' db_config.json)
else
    # Fall back to grep/cut
    echo -e "${YELLOW}jq not found, using fallback parsing method${RESET}"
    DB_HOST=$(grep -o '"host": "[^"]*"' db_config.json | cut -d'"' -f4)
    DB_PORT=$(grep -o '"port": [0-9]*' db_config.json | awk '{print $2}')
    DB_USER=$(grep -o '"user": "[^"]*"' db_config.json | cut -d'"' -f4)
    DB_PASS=$(grep -o '"password": "[^"]*"' db_config.json | cut -d'"' -f4)
    DB_NAME=$(grep -o '"database": "[^"]*"' db_config.json | cut -d'"' -f4)
fi

if [ -z "$DB_HOST" ] || [ -z "$DB_PORT" ] || [ -z "$DB_USER" ] || [ -z "$DB_PASS" ] || [ -z "$DB_NAME" ]; then
    echo -e "${RED}Error: Could not extract all required database connection parameters${RESET}"
    exit 1
fi

echo -e "${BLUE}Database Configuration:${RESET}"
echo -e "  Host:     ${DB_HOST}"
echo -e "  Port:     ${DB_PORT}"
echo -e "  Database: ${DB_NAME}"
echo -e "  User:     ${DB_USER}"
echo

# Ask for confirmation
read -p "Are you sure you want to reset the database? (y/N) " -n 1 -r CONFIRM
echo

if [[ ! $CONFIRM =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Operation cancelled${RESET}"
    exit 0
fi

# Create a secure temporary file for the password
PASSFILE=$(mktemp)
echo "[client]
password=${DB_PASS}
" > "$PASSFILE"
chmod 600 "$PASSFILE"

# Test database connection
echo -e "${BLUE}Testing database connection...${RESET}"
if ! mysql --defaults-extra-file="$PASSFILE" -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -e "USE \`$DB_NAME\`; SELECT 1" > /dev/null 2>&1; then
    echo -e "${RED}Error: Could not connect to database${RESET}"
    rm -f "$PASSFILE"
    exit 1
fi

echo -e "${GREEN}Database connection successful${RESET}"
echo -e "${BLUE}Starting database reset...${RESET}"

# Create the SQL commands file
SQL_FILE=$(mktemp)
cat > "$SQL_FILE" << EOF
-- Disable foreign key checks temporarily
SET FOREIGN_KEY_CHECKS = 0;

-- Delete test data from tables in reverse order of dependency
DELETE FROM verification_tokens WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%');

-- Clear the space_download_scheduler table completely
DELETE FROM space_download_scheduler;

-- Delete test data from related tables
DELETE FROM space_tags WHERE space_id IN (SELECT id FROM spaces WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%'));
DELETE FROM space_notes WHERE space_id IN (SELECT id FROM spaces WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%'));
DELETE FROM space_metadata WHERE space_id IN (SELECT id FROM spaces WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%'));
DELETE FROM spaces WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%');
DELETE FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%';

-- Delete test tags
DELETE FROM tags WHERE name LIKE '%test%' OR name LIKE '%uniquesearchprefix%' OR name LIKE '%UniqueSearchPrefix%';

-- Enable foreign key checks again
SET FOREIGN_KEY_CHECKS = 1;
EOF

# Execute the SQL commands
mysql --defaults-extra-file="$PASSFILE" -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" "$DB_NAME" < "$SQL_FILE"

# Check exit status
if [ $? -eq 0 ]; then
    echo -e "${GREEN}${BOLD}Database reset completed successfully${RESET}"
    echo -e "${GREEN}✓${RESET} Cleared test data"
    echo -e "${GREEN}✓${RESET} Reset space_download_scheduler table"
else
    echo -e "${RED}Error resetting database${RESET}"
    rm -f "$PASSFILE" "$SQL_FILE"
    exit 1
fi

# Clean up temporary files
rm -f "$PASSFILE" "$SQL_FILE"

echo -e "\n${BLUE}Note: Normal user accounts and existing spaces have been preserved.${RESET}"
echo -e "${BLUE}Only test data and the space_download_scheduler table have been cleared.${RESET}"