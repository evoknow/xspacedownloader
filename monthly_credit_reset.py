#!/usr/bin/env python3
"""
Monthly credit reset cron job for XSpace Downloader.
This script resets user credits to their recurring_credits amount for lifetime subscriptions.
Should be run monthly via cron: 0 0 1 * * /path/to/monthly_credit_reset.py
"""

import json
import logging
import mysql.connector
from datetime import datetime, timedelta
import sys
import os

# Setup logging
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'credit_reset.log')),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('credit_reset')

def load_db_config():
    """Load database configuration from db_config.json."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db_config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    db_config = config["mysql"].copy()
    if 'use_ssl' in db_config:
        del db_config['use_ssl']
    
    return db_config

def reset_monthly_credits():
    """Reset credits for users with recurring_credits set."""
    try:
        db_config = load_db_config()
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)
        
        # Calculate the date threshold (users who haven't been reset in the last 28 days)
        threshold_date = datetime.now() - timedelta(days=28)
        
        # Find users eligible for credit reset
        cursor.execute("""
            SELECT id, email, credits, recurring_credits, last_credit_reset
            FROM users
            WHERE recurring_credits > 0
            AND (last_credit_reset IS NULL OR last_credit_reset <= %s)
        """, (threshold_date,))
        
        eligible_users = cursor.fetchall()
        reset_count = 0
        
        logger.info(f"Found {len(eligible_users)} users eligible for credit reset")
        
        for user in eligible_users:
            try:
                # Reset credits to recurring_credits amount
                cursor.execute("""
                    UPDATE users
                    SET credits = recurring_credits,
                        last_credit_reset = NOW()
                    WHERE id = %s
                """, (user['id'],))
                
                # Log the credit reset in transactions table
                cursor.execute("""
                    INSERT INTO transactions 
                    (user_id, type, change_amount, description, date_time)
                    VALUES (%s, 'monthly_reset', %s, %s, NOW())
                """, (
                    user['id'],
                    user['recurring_credits'],
                    f"Monthly credit reset: {user['recurring_credits']} credits (lifetime subscription)"
                ))
                
                connection.commit()
                reset_count += 1
                
                logger.info(f"Reset credits for user {user['id']} ({user['email']}): "
                          f"previous={user['credits']}, new={user['recurring_credits']}")
                
            except Exception as e:
                logger.error(f"Error resetting credits for user {user['id']}: {e}")
                connection.rollback()
                continue
        
        cursor.close()
        connection.close()
        
        logger.info(f"Successfully reset credits for {reset_count} users")
        return reset_count
        
    except Exception as e:
        logger.error(f"Error in monthly credit reset: {e}")
        return 0

def main():
    """Main function to run the credit reset."""
    logger.info("Starting monthly credit reset job")
    
    try:
        reset_count = reset_monthly_credits()
        logger.info(f"Monthly credit reset completed. Reset {reset_count} user accounts.")
    except Exception as e:
        logger.error(f"Fatal error in credit reset job: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()