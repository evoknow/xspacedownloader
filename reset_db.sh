#!/bin/bash
# reset_db.sh - Script to clear all test data from the database

# Load database configuration
if [ ! -f "db_config.json" ]; then
    echo "Error: db_config.json not found"
    exit 1
fi

# Extract database connection info
DB_HOST=$(grep -o '"host": "[^"]*"' db_config.json | cut -d'"' -f4)
DB_PORT=$(grep -o '"port": [0-9]*' db_config.json | awk '{print $2}')
DB_USER=$(grep -o '"user": "[^"]*"' db_config.json | cut -d'"' -f4)
DB_PASSWORD=$(grep -o '"password": "[^"]*"' db_config.json | cut -d'"' -f4)
DB_NAME=$(grep -o '"database": "[^"]*"' db_config.json | cut -d'"' -f4)

if [ -z "$DB_HOST" ] || [ -z "$DB_PORT" ] || [ -z "$DB_USER" ] || [ -z "$DB_PASSWORD" ] || [ -z "$DB_NAME" ]; then
    echo "Error: Could not extract all required database connection parameters"
    exit 1
fi

echo "Resetting database: $DB_NAME on $DB_HOST:$DB_PORT"

# SQL commands to clear test data
mysql -h $DB_HOST -P $DB_PORT -u $DB_USER -p$DB_PASSWORD $DB_NAME << EOF
-- Disable foreign key checks temporarily
SET FOREIGN_KEY_CHECKS = 0;

-- Delete test data from tables in reverse order of dependency
DELETE FROM verification_tokens WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%');
DELETE FROM space_tags WHERE space_id IN (SELECT space_id FROM spaces WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%'));
DELETE FROM space_notes WHERE space_id IN (SELECT space_id FROM spaces WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%'));
DELETE FROM space_metadata WHERE space_id IN (SELECT space_id FROM spaces WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%'));
DELETE FROM spaces WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%');
DELETE FROM users WHERE email LIKE '%test%' OR email LIKE '%example.com%';
-- Delete test tags, including those with 'uniquesearchprefix' and 'test' patterns
DELETE FROM tags WHERE name LIKE '%test%' OR name LIKE '%uniquesearchprefix%' OR name LIKE '%UniqueSearchPrefix%';

-- Enable foreign key checks again
SET FOREIGN_KEY_CHECKS = 1;
EOF

# Check exit status
if [ $? -eq 0 ]; then
    echo "Database reset completed successfully"
else
    echo "Error resetting database"
    exit 1
fi