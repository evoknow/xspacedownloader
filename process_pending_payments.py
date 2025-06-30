#!/usr/bin/env python3
"""Process pending credit transactions and apply credits."""

import json
import mysql.connector
import stripe
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Process all pending transactions."""
    # Load database configuration
    with open('db_config.json', 'r') as f:
        config = json.load(f)
    
    db_config = config["mysql"].copy()
    if 'use_ssl' in db_config:
        del db_config['use_ssl']
    
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get all pending transactions
        cursor.execute("""
            SELECT ct.*, p.credits, p.name, u.email, u.id as user_email
            FROM credit_txn ct
            JOIN products p ON ct.product_id = p.id
            JOIN users u ON ct.user_id = u.id
            WHERE ct.payment_status = 'pending'
            ORDER BY ct.created_at DESC
        """)
        
        pending_txns = cursor.fetchall()
        
        if not pending_txns:
            logger.info("No pending transactions found.")
            return
        
        logger.info(f"Found {len(pending_txns)} pending transactions")
        
        # Load Stripe configuration
        from components.EnvManager import EnvManager
        env_manager = EnvManager()
        stripe_config = env_manager.get_stripe_config()
        
        if stripe_config['mode'] == 'live':
            stripe.api_key = stripe_config['live']['secret_key']
        else:
            stripe.api_key = stripe_config['test']['secret_key']
        
        processed = 0
        failed = 0
        
        for txn in pending_txns:
            try:
                logger.info(f"\nProcessing transaction {txn['id']} for user {txn['email']} ({txn['user_id']})")
                logger.info(f"  Product: {txn['name']} - {txn['credits']} credits for ${txn['amount']}")
                
                # Try to verify with Stripe if we have a session ID
                payment_verified = False
                if txn['stripe_session_id']:
                    try:
                        session = stripe.checkout.Session.retrieve(txn['stripe_session_id'])
                        if session.payment_status == 'paid':
                            payment_verified = True
                            logger.info(f"  ✓ Payment verified with Stripe (session: {session.id})")
                    except Exception as e:
                        logger.warning(f"  ! Could not verify with Stripe: {e}")
                
                # Ask for manual confirmation if not verified
                if not payment_verified:
                    response = input(f"  Process this transaction? (y/n): ").lower().strip()
                    if response != 'y':
                        logger.info("  Skipped by user")
                        continue
                
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
                    WHERE id = %s
                """, (txn['id'],))
                
                # Record in transactions table
                cursor.execute("""
                    INSERT INTO transactions 
                    (user_id, type, change_amount, description, date_time)
                    VALUES (%s, 'credit_purchase', %s, %s, NOW())
                """, (
                    txn['user_id'],
                    txn['credits'],
                    f"Credit purchase: {txn['credits']} credits for ${txn['amount']} (manually processed)"
                ))
                
                connection.commit()
                processed += 1
                logger.info(f"  ✓ Successfully processed: {txn['credits']} credits added")
                
            except Exception as e:
                logger.error(f"  ✗ Error processing transaction {txn['id']}: {e}")
                failed += 1
                connection.rollback()
        
        logger.info(f"\n{'='*50}")
        logger.info(f"Summary: Processed {processed} transactions, {failed} failed")
        
    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    main()