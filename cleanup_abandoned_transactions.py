#!/usr/bin/env python3
"""Clean up abandoned credit transactions older than 24 hours."""

import json
import mysql.connector
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Clean up old abandoned transactions."""
    # Load database configuration
    with open('db_config.json', 'r') as f:
        config = json.load(f)
    
    db_config = config["mysql"].copy()
    if 'use_ssl' in db_config:
        del db_config['use_ssl']
    
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()
    
    try:
        # Delete pending transactions older than 24 hours
        cursor.execute("""
            DELETE FROM credit_txn 
            WHERE payment_status = 'pending' 
            AND created_at < DATE_SUB(NOW(), INTERVAL 24 HOUR)
        """)
        
        deleted_count = cursor.rowcount
        connection.commit()
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} abandoned transactions")
        else:
            logger.info("No abandoned transactions to clean up")
        
        # Log current pending transactions count
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM credit_txn 
            WHERE payment_status = 'pending'
        """)
        result = cursor.fetchone()
        logger.info(f"Remaining pending transactions: {result[0]}")
        
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    main()