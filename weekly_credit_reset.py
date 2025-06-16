#!/usr/bin/env python3
"""
Weekly Credit Reset Script
Adds $5.00 to every user's credits once per week.

This script should be run via cron job every Sunday at midnight.
Cron example: 0 0 * * 0 /path/to/weekly_credit_reset.py
"""

import logging
import sys
import os
from datetime import datetime
from components.DatabaseManager import DatabaseManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/weekly_credit_reset.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def add_weekly_credits():
    """
    Add $5.00 to every user's credits.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Initialize database connection
        db = DatabaseManager()
        cursor = db.connection.cursor()
        
        logger.info("Starting weekly credit reset...")
        
        # Get current user count for logging
        cursor.execute("SELECT COUNT(*) as user_count FROM users WHERE status = 'active'")
        result = cursor.fetchone()
        user_count = result['user_count'] if result else 0
        
        logger.info(f"Found {user_count} active users")
        
        # Add $5.00 to all active users
        credit_amount = 5.00
        update_query = """
            UPDATE users 
            SET credits = credits + %s,
                updated_at = NOW()
            WHERE status = 'active'
        """
        
        cursor.execute(update_query, (credit_amount,))
        affected_rows = cursor.rowcount
        
        # Commit the changes
        db.connection.commit()
        cursor.close()
        
        total_credits_added = affected_rows * credit_amount
        
        logger.info(f"Weekly credit reset completed successfully:")
        logger.info(f"- Users updated: {affected_rows}")
        logger.info(f"- Credits per user: ${credit_amount:.2f}")
        logger.info(f"- Total credits added: ${total_credits_added:.2f}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error during weekly credit reset: {e}")
        if 'cursor' in locals():
            cursor.close()
        return False

def log_credit_statistics():
    """
    Log some statistics about user credits after the reset.
    """
    try:
        db = DatabaseManager()
        cursor = db.connection.cursor()
        
        # Get credit statistics
        stats_query = """
            SELECT 
                COUNT(*) as total_users,
                AVG(credits) as avg_credits,
                MIN(credits) as min_credits,
                MAX(credits) as max_credits,
                SUM(credits) as total_credits
            FROM users 
            WHERE status = 'active'
        """
        
        cursor.execute(stats_query)
        stats = cursor.fetchone()
        
        if stats:
            logger.info("Post-reset credit statistics:")
            logger.info(f"- Total active users: {stats['total_users']}")
            logger.info(f"- Average credits: ${stats['avg_credits']:.2f}")
            logger.info(f"- Minimum credits: ${stats['min_credits']:.2f}")
            logger.info(f"- Maximum credits: ${stats['max_credits']:.2f}")
            logger.info(f"- Total credits in system: ${stats['total_credits']:.2f}")
        
        cursor.close()
        
    except Exception as e:
        logger.warning(f"Error getting credit statistics: {e}")

def main():
    """Main function to run the weekly credit reset."""
    logger.info("=" * 60)
    logger.info("Starting weekly credit reset")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 60)
    
    # Add weekly credits
    success = add_weekly_credits()
    if not success:
        logger.error("Weekly credit reset failed. Exiting.")
        sys.exit(1)
    
    # Log statistics
    log_credit_statistics()
    
    logger.info("Weekly credit reset completed successfully")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()