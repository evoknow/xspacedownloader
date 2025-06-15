#!/bin/bash
#
# XSpace Downloader - Auto Update Script
# 
# This script checks for git updates and automatically runs update.py if changes are found.
# Can be run manually or set up as a cron job for automatic updates.
#
# Usage:
#   ./auto_update.sh [options]
#
# Options:
#   --force    Force update even if no changes detected
#   --dry-run  Show what would be done without making changes
#   --silent   Suppress all output except errors
#

# Configuration
REPO_DIR="/var/www/production/xspacedownload.com/website/xspacedownloader"
LOG_FILE="$REPO_DIR/logs/auto_update.log"
UPDATE_SCRIPT="$REPO_DIR/update.py"
LOCK_FILE="/tmp/xspacedownloader_update.lock"

# Parse command line arguments
FORCE_UPDATE=false
DRY_RUN=false
SILENT=false

for arg in "$@"; do
    case $arg in
        --force)
            FORCE_UPDATE=true
            ;;
        --dry-run)
            DRY_RUN=true
            ;;
        --silent)
            SILENT=true
            ;;
        *)
            echo "Unknown option: $arg"
            echo "Usage: $0 [--force] [--dry-run] [--silent]"
            exit 1
            ;;
    esac
done

# Functions
log_message() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    if [ "$SILENT" != true ]; then
        echo "[$timestamp] $message"
    fi
    
    # Always write to log file
    echo "[$timestamp] $message" >> "$LOG_FILE"
}

error_exit() {
    local message="$1"
    log_message "ERROR: $message"
    remove_lock
    exit 1
}

create_lock() {
    if [ -f "$LOCK_FILE" ]; then
        local pid=$(cat "$LOCK_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            error_exit "Another update process is already running (PID: $pid)"
        else
            log_message "Removing stale lock file"
            rm -f "$LOCK_FILE"
        fi
    fi
    
    echo $$ > "$LOCK_FILE"
}

remove_lock() {
    rm -f "$LOCK_FILE"
}

check_requirements() {
    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        error_exit "This script must be run as root (use sudo)"
    fi
    
    # Check if repo directory exists
    if [ ! -d "$REPO_DIR" ]; then
        error_exit "Repository directory not found: $REPO_DIR"
    fi
    
    # Check if update.py exists
    if [ ! -f "$UPDATE_SCRIPT" ]; then
        error_exit "Update script not found: $UPDATE_SCRIPT"
    fi
    
    # Check if git is available
    if ! command -v git &> /dev/null; then
        error_exit "git command not found"
    fi
}

check_for_updates() {
    cd "$REPO_DIR" || error_exit "Failed to change to repository directory"
    
    # Fetch latest changes from origin
    log_message "Fetching latest changes from origin..."
    if [ "$DRY_RUN" = true ]; then
        log_message "[DRY RUN] Would execute: git fetch origin"
    else
        git fetch origin > /dev/null 2>&1 || error_exit "Failed to fetch from origin"
    fi
    
    # Check if there are any differences
    local LOCAL=$(git rev-parse HEAD)
    local REMOTE=$(git rev-parse origin/main)
    
    if [ "$LOCAL" = "$REMOTE" ]; then
        if [ "$FORCE_UPDATE" = true ]; then
            log_message "No updates found, but forcing update due to --force flag"
            return 0
        else
            log_message "Already up to date"
            return 1
        fi
    else
        # Get commit count difference
        local BEHIND=$(git rev-list HEAD..origin/main --count)
        log_message "Found $BEHIND new commit(s) to pull"
        
        # Show what commits will be pulled
        if [ "$SILENT" != true ]; then
            log_message "New commits:"
            git log HEAD..origin/main --oneline | while read line; do
                log_message "  $line"
            done
        fi
        
        return 0
    fi
}

run_update() {
    log_message "Running update process..."
    
    if [ "$DRY_RUN" = true ]; then
        log_message "[DRY RUN] Would execute: python3 $UPDATE_SCRIPT"
        return 0
    fi
    
    # Run update.py
    cd "$REPO_DIR" || error_exit "Failed to change to repository directory"
    
    # Capture update.py output
    local update_output=$(python3 "$UPDATE_SCRIPT" 2>&1)
    local update_exit_code=$?
    
    if [ $update_exit_code -eq 0 ]; then
        log_message "Update completed successfully"
        if [ "$SILENT" != true ]; then
            echo "$update_output" | while IFS= read -r line; do
                log_message "  $line"
            done
        fi
    else
        error_exit "Update failed with exit code $update_exit_code. Output: $update_output"
    fi
}

check_services() {
    log_message "Checking service status..."
    
    services=("xspacedownloader-gunicorn" "nginx")
    
    for service in "${services[@]}"; do
        if systemctl is-active --quiet "$service"; then
            log_message "  ✓ $service is running"
        else
            log_message "  ✗ $service is not running"
        fi
    done
}

send_notification() {
    local subject="$1"
    local message="$2"
    
    # Check if mail command exists
    if command -v mail &> /dev/null; then
        # Try to get admin email from mainconfig.json
        if [ -f "$REPO_DIR/mainconfig.json" ]; then
            local admin_email=$(python3 -c "import json; print(json.load(open('$REPO_DIR/mainconfig.json')).get('admin_email', ''))" 2>/dev/null)
            if [ ! -z "$admin_email" ]; then
                echo "$message" | mail -s "$subject" "$admin_email"
                log_message "Notification sent to $admin_email"
            fi
        fi
    fi
}

# Main execution
main() {
    log_message "=== Starting XSpace Downloader Auto Update ==="
    
    # Create lock file
    create_lock
    
    # Set up cleanup trap
    trap remove_lock EXIT
    
    # Check requirements
    check_requirements
    
    # Check for updates
    if check_for_updates; then
        # Run update
        run_update
        
        # Check services after update
        check_services
        
        # Send notification if configured
        send_notification "XSpace Downloader Updated" "The application has been updated successfully on $(hostname)"
        
        log_message "=== Update process completed successfully ==="
    else
        log_message "=== No updates required ==="
    fi
    
    # Remove lock file (also handled by trap)
    remove_lock
}

# Create log directory if it doesn't exist
mkdir -p "$(dirname "$LOG_FILE")"

# Run main function
main

# Exit successfully
exit 0