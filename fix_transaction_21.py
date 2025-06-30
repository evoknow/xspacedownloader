#!/usr/bin/env python3
"""Fix transaction 21 - add credits and mark as completed."""

import json
import mysql.connector
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Process transaction 21 specifically."""
    # Load database configuration
    with open('db_config.json', 'r') as f:
        config = json.load(f)
    
    db_config = config["mysql"].copy()
    if 'use_ssl' in db_config:
        del db_config['use_ssl']
    
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get transaction 21 details
        cursor.execute("""
            SELECT ct.*, p.credits, p.name, u.email
            FROM credit_txn ct
            JOIN products p ON ct.product_id = p.id
            JOIN users u ON ct.user_id = u.id
            WHERE ct.id = 21
        """)
        
        txn = cursor.fetchone()
        
        if not txn:
            logger.error("Transaction 21 not found")
            return
        
        if txn['payment_status'] == 'completed':
            logger.info("Transaction 21 already completed")
            return
        
        logger.info(f"Processing transaction 21:")
        logger.info(f"  User: {txn['email']} (ID: {txn['user_id']})")
        logger.info(f"  Product: {txn['name']}")
        logger.info(f"  Credits: {txn['credits']}")
        logger.info(f"  Amount: ${txn['amount']}")
        logger.info(f"  Status: {txn['payment_status']}")
        
        # Apply credits
        cursor.execute("""
            UPDATE users 
            SET credits = credits + %s
            WHERE id = %s
        """, (txn['credits'], txn['user_id']))
        
        # Update transaction status
        cursor.execute("""
            UPDATE credit_txn 
            SET payment_status = 'completed',
                paid_date = NOW()
            WHERE id = 21
        """)
        
        connection.commit()
        
        logger.info(f"✓ Successfully processed: {txn['credits']} credits added to user {txn['user_id']}")
        
        # Check user's current balance
        cursor.execute("SELECT credits FROM users WHERE id = %s", (txn['user_id'],))
        balance = cursor.fetchone()
        logger.info(f"User's current credit balance: {balance['credits']}")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        connection.rollback()
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    main()