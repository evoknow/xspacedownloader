#!/bin/bash
#
# Setup script for XSpace Downloader Auto Update
#
# This script sets up automatic updates using systemd timer or cron
#

echo "XSpace Downloader - Auto Update Setup"
echo "====================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (use sudo)"
    exit 1
fi

# Configuration
REPO_DIR="/var/www/production/xspacedowoad.com/website/xspacedownloader"
AUTO_UPDATE_SCRIPT="$REPO_DIR/auto_update.sh"

# Check if auto_update.sh exists
if [ ! -f "$AUTO_UPDATE_SCRIPT" ]; then
    echo "Error: auto_update.sh not found at $AUTO_UPDATE_SCRIPT"
    echo "Please run update.py first to sync the latest files"
    exit 1
fi

# Make auto_update.sh executable
chmod +x "$AUTO_UPDATE_SCRIPT"
echo "✓ Made auto_update.sh executable"

# Ask user preference
echo ""
echo "How would you like to set up automatic updates?"
echo "1) Use systemd timer (recommended for systems with systemd)"
echo "2) Use cron job"
echo "3) Manual only (no automatic updates)"
echo ""
read -p "Enter your choice (1-3): " choice

case $choice in
    1)
        echo ""
        echo "Setting up systemd timer..."
        
        # Copy service and timer files
        cp "$REPO_DIR/deploy/systemd/xspacedownloader-update.service" /etc/systemd/system/
        cp "$REPO_DIR/deploy/systemd/xspacedownloader-update.timer" /etc/systemd/system/
        
        # Reload systemd
        systemctl daemon-reload
        
        # Enable and start timer
        systemctl enable xspacedownloader-update.timer
        systemctl start xspacedownloader-update.timer
        
        echo "✓ Systemd timer configured"
        echo ""
        echo "Auto-update will run every 6 hours"
        echo ""
        echo "Useful commands:"
        echo "  View timer status:    systemctl status xspacedownloader-update.timer"
        echo "  View next run time:   systemctl list-timers xspacedownloader-update.timer"
        echo "  Run update manually:  systemctl start xspacedownloader-update.service"
        echo "  View update logs:     journalctl -u xspacedownloader-update.service"
        echo "  Disable auto-update:  systemctl disable xspacedownloader-update.timer"
        ;;
        
    2)
        echo ""
        echo "Setting up cron job..."
        
        # Create cron job
        CRON_JOB="0 */6 * * * $AUTO_UPDATE_SCRIPT --silent >> /var/log/xspacedownloader-update.log 2>&1"
        
        # Check if cron job already exists
        if crontab -l 2>/dev/null | grep -q "auto_update.sh"; then
            echo "Warning: Cron job already exists for auto_update.sh"
            read -p "Replace existing cron job? (y/n): " replace
            if [ "$replace" != "y" ]; then
                echo "Keeping existing cron job"
            else
                # Remove existing and add new
                (crontab -l 2>/dev/null | grep -v "auto_update.sh"; echo "$CRON_JOB") | crontab -
                echo "✓ Cron job replaced"
            fi
        else
            # Add new cron job
            (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
            echo "✓ Cron job added"
        fi
        
        echo ""
        echo "Auto-update will run every 6 hours"
        echo ""
        echo "Useful commands:"
        echo "  View cron jobs:       crontab -l"
        echo "  Edit cron jobs:       crontab -e"
        echo "  Run update manually:  $AUTO_UPDATE_SCRIPT"
        echo "  View update logs:     tail -f /var/log/xspacedownloader-update.log"
        ;;
        
    3)
        echo ""
        echo "Manual update mode selected"
        echo ""
        echo "To run updates manually, use:"
        echo "  sudo $AUTO_UPDATE_SCRIPT"
        echo ""
        echo "Or continue using:"
        echo "  sudo $REPO_DIR/update.py"
        ;;
        
    *)
        echo "Invalid choice. Exiting."
        exit 1
        ;;
esac

echo ""
echo "Additional options for auto_update.sh:"
echo "  --force     Force update even if no changes detected"
echo "  --dry-run   Show what would be done without making changes"
echo "  --silent    Suppress output (useful for cron)"
echo ""
echo "Setup complete!"