#!/bin/bash

# MySQL credentials via login-path
DB="xspacedownloader"
LOGIN="--login-path=xspace"

# Tables to truncate
TABLES=("space_clips" "space_cost" "space_download_history" "space_download_scheduler" "space_favs" "space_metadata" "space_notes" "space_play_history" "space_reviews" "space_tags" "space_transcripts" "spaces" "computes" "transactions")

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
rm -f downloads/*.{mp3,log,m4a,part,mp4}

# Confirm remaining files
echo "Remaining files in downloads/:"
ls -l downloads/
