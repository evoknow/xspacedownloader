#!/bin/bash
# yt-dlp-wrapper.sh - Wrapper script for yt-dlp to debug issues

echo "yt-dlp wrapper script - arguments: $@"
echo "PATH: $PATH"
echo "Python executable: /Volumes/KabirArchive1/projects/xspacedownload/venv/bin/python"

# Find yt-dlp
YT_DLP="/Volumes/KabirArchive1/projects/xspacedownload/venv/bin/yt-dlp"

if [ ! -f "$YT_DLP" ]; then
    echo "Error: yt-dlp not found at $YT_DLP"
    exit 1
fi

echo "Using yt-dlp at: $YT_DLP"
echo "-------------------------------------"

# Execute yt-dlp with all arguments
"$YT_DLP" "$@"
