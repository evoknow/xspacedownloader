#!/bin/bash
# dump_sql_schema.sh - Extract MySQL database schema
#
# This script extracts the database schema from the XSpace Downloader MySQL database
# and saves it to mysql.schema file. This can be used to recreate the database
# structure in a new environment.

set -e  # Exit on error

# Text colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
RESET='\033[0m'

echo -e "${BLUE}XSpace Downloader - Database Schema Extraction${RESET}"
echo -e "This script will extract the database schema and save it to mysql.schema"
echo

# Get database credentials from db_config.json
if [ ! -f "db_config.json" ]; then
    echo -e "${RED}Error: db_config.json file not found${RESET}"
    exit 1
fi

# Extract credentials using jq if available, or python as fallback
if command -v jq &> /dev/null; then
    echo -e "${GREEN}Using jq to parse config file${RESET}"
    DB_HOST=$(jq -r '.mysql.host' db_config.json)
    DB_PORT=$(jq -r '.mysql.port' db_config.json)
    DB_NAME=$(jq -r '.mysql.database' db_config.json)
    DB_USER=$(jq -r '.mysql.user' db_config.json)
    DB_PASS=$(jq -r '.mysql.password' db_config.json)
else
    echo -e "${YELLOW}jq not found, using Python to parse config file${RESET}"
    DB_HOST=$(python -c "import json; print(json.load(open('db_config.json'))['mysql']['host'])")
    DB_PORT=$(python -c "import json; print(json.load(open('db_config.json'))['mysql']['port'])")
    DB_NAME=$(python -c "import json; print(json.load(open('db_config.json'))['mysql']['database'])")
    DB_USER=$(python -c "import json; print(json.load(open('db_config.json'))['mysql']['user'])")
    DB_PASS=$(python -c "import json; print(json.load(open('db_config.json'))['mysql']['password'])")
fi

# Check if mysqldump is available
if ! command -v mysqldump &> /dev/null; then
    echo -e "${RED}Error: mysqldump command not found${RESET}"
    echo -e "Please install MySQL client tools:"
    echo -e "  - On macOS: brew install mysql-client"
    echo -e "  - On Ubuntu: sudo apt-get install mysql-client"
    exit 1
fi

echo -e "${BLUE}Database Configuration:${RESET}"
echo -e "  Host:     ${DB_HOST}"
echo -e "  Port:     ${DB_PORT}"
echo -e "  Database: ${DB_NAME}"
echo -e "  User:     ${DB_USER}"
echo

# Create a temporary password file for mysqldump
PASSFILE=$(mktemp)
echo "[client]
password=\"${DB_PASS}\"
" > "${PASSFILE}"
chmod 600 "${PASSFILE}"

echo -e "${BLUE}Dumping database schema...${RESET}"

# Dump database schema (no data)
mysqldump --defaults-extra-file="${PASSFILE}" \
    --host="${DB_HOST}" \
    --port="${DB_PORT}" \
    --user="${DB_USER}" \
    --no-data \
    --skip-comments \
    --routines \
    --skip-triggers \
    --skip-opt \
    --create-options \
    "${DB_NAME}" > mysql.schema.tmp

# Add header information to the schema file
cat > mysql.schema << EOF
-- MySQL Schema for XSpace Downloader
-- Generated on $(date)
-- This file contains the database schema only (no data)
-- Run this script to create the database structure:
--   mysql -u your_username -p < mysql.schema

-- Create the database if it doesn't exist
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE \`${DB_NAME}\`;

EOF

# Append the schema dump to the file
cat mysql.schema.tmp >> mysql.schema

# Add instructions for creating default admin user
cat >> mysql.schema << EOF

-- Add default admin user if it doesn't exist
INSERT INTO \`users\` (\`email\`, \`password\`, \`status\`)
SELECT 'admin@xspacedownload.com', '\$2b\$10\$VGm5DFCi/zXlCH7qeP5m0.WGM/WHxfHEA8lBZ1DC3HqZUi0L.oEUG', 'active'
WHERE NOT EXISTS (SELECT 1 FROM \`users\` WHERE \`email\` = 'admin@xspacedownload.com');

-- Insert a default admin API key
INSERT INTO \`api_keys\` (\`user_id\`, \`key\`, \`name\`, \`permissions\`, \`created_at\`, \`expires_at\`, \`is_active\`)
SELECT 
    (SELECT \`id\` FROM \`users\` WHERE \`email\` = 'admin@xspacedownload.com' LIMIT 1),
    'DEV_API_KEY_DO_NOT_USE_IN_PRODUCTION',
    'Default Admin API Key',
    JSON_ARRAY(
        'view_users', 'manage_users',
        'view_spaces', 'create_spaces', 'edit_spaces', 'delete_spaces', 'view_all_spaces', 'edit_all_spaces', 'delete_all_spaces',
        'download_spaces', 'download_all_spaces', 'view_downloads', 'manage_downloads', 'view_all_downloads', 'manage_all_downloads',
        'view_tags', 'manage_tags',
        'manage_api_keys',
        'view_stats'
    ),
    NOW(),
    DATE_ADD(NOW(), INTERVAL 1 YEAR),
    1
WHERE EXISTS (SELECT 1 FROM \`users\` WHERE \`email\` = 'admin@xspacedownload.com') 
AND NOT EXISTS (SELECT 1 FROM \`api_keys\` WHERE \`name\` = 'Default Admin API Key');
EOF

# Clean up
rm "${PASSFILE}" mysql.schema.tmp

# Check the file size to make sure we got something
FILESIZE=$(wc -c < mysql.schema)
if [ "$FILESIZE" -lt 100 ]; then
    echo -e "${RED}Error: Schema dump is too small or empty (${FILESIZE} bytes)${RESET}"
    echo -e "This may indicate a problem connecting to the database"
    exit 1
fi

echo -e "${GREEN}Successfully created schema file: mysql.schema (${FILESIZE} bytes)${RESET}"
echo -e "${BLUE}Use this file to recreate the database structure:${RESET}"
echo -e "  mysql -u your_username -p < mysql.schema"