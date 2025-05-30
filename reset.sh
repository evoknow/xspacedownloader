#!/bin/bash

# MySQL credentials via login-path
DB="xspacedownloader"
LOGIN="--login-path=xspaceuser"

# Tables to truncate
TABLES=("spaces" "space_download_scheduler" "space_transcripts" "space_metadata" "space_tags" "space_transcripts tags")

echo "Cleaning MySQL tables..."
for TABLE in "${TABLES[@]}"; do
    echo "DELETE FROM $TABLE;" | mysql $LOGIN -D $DB
done

# Stop background downloader process
echo "Killing bg_downloader.py processes..."
pkill -f bg_downloader.py

# Cleanup logs and downloaded files
echo "Removing logs and downloaded media..."
rm -f *.log *.logs
rm -rf logs
rm -f downloads/*.{mp3,log,m4a,part}

# Confirm remaining files
echo "Remaining files in downloads/:"
ls -l downloads/
