#!/bin/bash
# Setup script for monthly credit reset cron job

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Create the cron job entry
CRON_JOB="0 0 1 * * cd $SCRIPT_DIR && /usr/bin/python3 $SCRIPT_DIR/monthly_credit_reset.py >> $SCRIPT_DIR/logs/credit_reset_cron.log 2>&1"

# Check if the cron job already exists
if crontab -l 2>/dev/null | grep -q "monthly_credit_reset.py"; then
    echo "Credit reset cron job already exists. Skipping..."
else
    # Add the cron job
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "Credit reset cron job added successfully!"
    echo "The job will run on the 1st of every month at midnight."
fi

# Display current crontab
echo ""
echo "Current crontab entries:"
crontab -l