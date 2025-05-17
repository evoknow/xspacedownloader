#!/bin/bash
# fix_db_job_status.sh - Fix inconsistent job statuses in the database

# Exit on error
set -e

# Set script directory as working directory
SCRIPT_DIR=$(dirname "$(realpath "$0")")
cd "$SCRIPT_DIR"

# Load credentials from db_config.json
if [ ! -f "db_config.json" ]; then
    echo "Error: db_config.json not found!"
    exit 1
fi

# Extract MySQL credentials
DB_HOST=$(grep -o '"host": *"[^"]*"' db_config.json | cut -d'"' -f4)
DB_USER=$(grep -o '"user": *"[^"]*"' db_config.json | cut -d'"' -f4)
DB_PASS=$(grep -o '"password": *"[^"]*"' db_config.json | cut -d'"' -f4)
DB_NAME=$(grep -o '"database": *"[^"]*"' db_config.json | cut -d'"' -f4)

if [ -z "$DB_HOST" ] || [ -z "$DB_USER" ] || [ -z "$DB_PASS" ] || [ -z "$DB_NAME" ]; then
    echo "Error: Could not extract all required database credentials from db_config.json"
    exit 1
fi

echo "Checking and fixing database job statuses..."

# Fix inconsistent statuses - Find and update stalled jobs
SQL_QUERY="
-- Update jobs that are in 'in_progress' status but have null process_id
UPDATE space_download_scheduler 
SET status = 'pending', process_id = NULL, updated_at = NOW() 
WHERE status = 'in_progress' AND (process_id IS NULL OR process_id = 0);

-- Update jobs that are in 'pending' status for more than 24 hours
UPDATE space_download_scheduler 
SET status = 'failed', error_message = 'Job timed out after 24 hours', updated_at = NOW() 
WHERE status = 'pending' AND created_at < DATE_SUB(NOW(), INTERVAL 24 HOUR);

-- De-duplicate pending jobs for the same space
-- Keep the oldest job for each space and mark others as in_progress with NULL process_id
UPDATE space_download_scheduler a
JOIN (
    SELECT space_id, MIN(id) as min_id 
    FROM space_download_scheduler 
    WHERE status = 'pending' 
    GROUP BY space_id
    HAVING COUNT(*) > 1
) b ON a.space_id = b.space_id AND a.id != b.min_id
SET a.status = 'in_progress', a.process_id = NULL, a.updated_at = NOW()
WHERE a.status = 'pending';

-- For jobs that are in_progress but have an active process_id, check if process exists
SELECT id, process_id FROM space_download_scheduler WHERE status = 'in_progress' AND process_id IS NOT NULL;
"

# Execute the SQL query
RESULT=$(mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "$SQL_QUERY")

# Extract process IDs from the result
PROCESS_IDS=$(echo "$RESULT" | awk 'NR>1 {print $2}')

# Check if processes are still running and update database accordingly
if [ -n "$PROCESS_IDS" ]; then
    for ROW in $(echo "$RESULT" | awk 'NR>1 {print $1 "," $2}'); do
        JOB_ID=$(echo $ROW | cut -d',' -f1)
        PID=$(echo $ROW | cut -d',' -f2)
        
        # Check if process exists
        if ! ps -p $PID > /dev/null; then
            echo "Process $PID for job $JOB_ID is not running. Marking job as 'pending'."
            mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "
                UPDATE space_download_scheduler 
                SET status = 'pending', process_id = NULL, updated_at = NOW() 
                WHERE id = $JOB_ID AND status = 'in_progress'
            "
        else
            echo "Process $PID for job $JOB_ID is still running."
        fi
    done
fi

# Look for part files in the downloads directory and update jobs
DOWNLOADS_DIR="$SCRIPT_DIR/downloads"
if [ -d "$DOWNLOADS_DIR" ]; then
    echo "Checking for part files in downloads directory..."
    
    for PART_FILE in $(find "$DOWNLOADS_DIR" -name "*.part"); do
        FILENAME=$(basename "$PART_FILE")
        SPACE_ID=$(echo "$FILENAME" | cut -d'.' -f1)
        
        if [ -n "$SPACE_ID" ]; then
            # Check if there's a job for this space
            JOB_COUNT=$(mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -se "
                SELECT COUNT(*) FROM space_download_scheduler WHERE space_id = '$SPACE_ID' AND status NOT IN ('completed', 'failed')
            ")
            
            if [ "$JOB_COUNT" -eq 0 ]; then
                echo "Found part file for space $SPACE_ID with no active job. Creating a new pending job."
                mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "
                    INSERT INTO space_download_scheduler (space_id, status, file_type, created_at, updated_at)
                    SELECT '$SPACE_ID', 'pending', 'mp3', NOW(), NOW()
                    FROM dual
                    WHERE EXISTS (SELECT 1 FROM spaces WHERE space_id = '$SPACE_ID')
                "
            elif [ "$JOB_COUNT" -gt 0 ]; then
                # Update jobs that are stuck in 'pending' status
                mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "
                    UPDATE space_download_scheduler 
                    SET status = 'in_progress', updated_at = NOW() 
                    WHERE space_id = '$SPACE_ID' AND status = 'pending'
                "
                echo "Updated status for space $SPACE_ID with part file to 'in_progress'."
            fi
        fi
    done
fi

echo "Database job status check and fix completed."