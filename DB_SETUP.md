# Database Setup Guide

This document explains how to set up the database for the XSpace Downloader application.

## Prerequisites

- MySQL server (5.7 or higher)
- MySQL client tools (for the schema dump script)

## Schema Management

### Creating a new database

The repository includes a SQL schema file that can be used to create the database structure:

```bash
# Connect to your MySQL server and create the database
mysql -u your_username -p < mysql.schema
```

This will:
1. Create the `xspacedownloader` database if it doesn't exist
2. Create all necessary tables with appropriate relationships
3. Add a default admin user for initial access
4. Create a default API key for testing

### Updating the schema file

If you make changes to the database structure, you should update the schema file. The repository includes several scripts for this purpose:

#### Option 1: Using Python (Recommended)

```bash
# Simple method that works with limited permissions
./dump_schema.sh
```

This script:
1. Uses Python to connect to the database
2. Reads credentials from `db_config.json`
3. Extracts table structure using SQL queries
4. Works even with limited database permissions
5. Saves the result to `mysql.schema`

#### Option 2: Using mysqldump

```bash
# Traditional method using mysqldump
# Requires more database permissions
./dump_sql_schema.sh
```

This script:
1. Reads database credentials from `db_config.json`
2. Tries multiple methods to extract the schema
3. Falls back to simpler approaches if permissions are limited
4. Saves the result to `mysql.schema`

#### Option 3: Direct Python Extraction

```bash
# Run the Python script directly
./extract_schema.py
```

This script provides detailed output during extraction and handles various error conditions.

## Configuration

The application looks for database connection information in the `db_config.json` file:

```json
{
    "type": "mysql",
    "mysql": {
        "host": "localhost",
        "port": 3306,
        "database": "xspacedownloader",
        "user": "your_username",
        "password": "your_password",
        "use_ssl": false
    }
}
```

Make sure to update this file with your actual database credentials.

## Tables Overview

The database structure includes the following tables:

| Table | Description |
|-------|-------------|
| `users` | User accounts for the system |
| `verification_tokens` | Tokens for email verification and password reset |
| `spaces` | X Space recordings metadata |
| `space_metadata` | Additional metadata for spaces |
| `space_notes` | User notes for spaces |
| `tags` | Tags for categorizing spaces |
| `space_tags` | Many-to-many relationship between spaces and tags |
| `email_config` | Email provider configuration |
| `space_download_scheduler` | Queue for background downloading of spaces |
| `api_keys` | API access keys for external applications |

## Default Admin Access

The schema creates a default admin user:
- Email: admin@xspacedownload.com
- Password: admin123

**IMPORTANT**: Change this password immediately after first login.

## Troubleshooting

### Can't connect to the database

1. Verify the credentials in `db_config.json`
2. Ensure the MySQL server is running and accessible
3. Check firewall settings if connecting to a remote server

### Schema import errors

1. Make sure you have appropriate MySQL permissions
2. Check for syntax errors if you've modified the schema file
3. Try importing tables individually to identify specific issues

### Schema extraction errors

The `dump_sql_schema.sh` script attempts to extract schema using several methods:

1. **Primary method**: Uses `mysqldump` with full options
2. **Fallback method 1**: Uses `mysqldump` with more restrictive options
3. **Fallback method 2**: Uses direct SQL queries to extract CREATE TABLE statements
4. **Last resort**: Uses Python to extract schema via SQL queries

If you see permission errors like "Access denied; you need the PROCESS privilege", don't worry - the script should fall back to a method that works with your permission level.