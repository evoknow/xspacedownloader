#!/usr/bin/env python3
"""Payment processing component using Stripe for XSpace Downloader."""

import os
import json
import logging
import mysql.connector
import stripe
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger('webapp')

class Payment:
    """Handles payment processing operations using Stripe."""
    
    def __init__(self):
        """Initialize Payment component."""
        # Load database configuration
        with open('db_config.json', 'r') as f:
            config = json.load(f)
        
        self.db_config = config["mysql"].copy()
        if 'use_ssl' in self.db_config:
            del self.db_config['use_ssl']
        
        # Initialize Stripe
        stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
        self.stripe_publishable_key = os.getenv('STRIPE_PUBLISHABLE_KEY')
        
        if not stripe.api_key:
            logger.error("STRIPE_SECRET_KEY not found in environment variables")
        if not self.stripe_publishable_key:
            logger.error("STRIPE_PUBLISHABLE_KEY not found in environment variables")
    
    def create_checkout_session(self, user_id, product_id, success_url, cancel_url):
        """Create a Stripe checkout session for product purchase."""
        try:
            # Get product details
            from components.Product import Product
            product_component = Product()
            product = product_component.get_product_by_id(product_id)
            
            if not product:
                return {'error': 'Product not found'}
            
            if product['status'] != 'active':
                return {'error': 'Product is not available for purchase'}
            
            # Create credit transaction record
            connection = mysql.connector.connect(**self.db_config)
            cursor = connection.cursor()
            
            cursor.execute("""
                INSERT INTO credit_txn 
                (user_id, product_id, amount, credits_purchased, payment_status)
                VALUES (%s, %s, %s, %s, 'pending')
            """, (user_id, product_id, product['price'], product['credits']))
            
            txn_id = cursor.lastrowid
            connection.commit()
            
            # Create Stripe checkout session
            line_items = [{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': product['name'],
                        'description': product['description'],
                        'images': [product['image_url']] if product['image_url'] else [],
                    },
                    'unit_amount': int(float(product['price']) * 100),  # Convert to cents
                },
                'quantity': 1,
            }]
            
            # Handle recurring products
            if product['recurring_credits'] == 'yes':
                line_items[0]['price_data']['recurring'] = {
                    'interval': 'month'
                }
            
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=line_items,
                mode='subscription' if product['recurring_credits'] == 'yes' else 'payment',
                success_url=success_url + '?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=cancel_url,
                client_reference_id=str(txn_id),
                metadata={
                    'user_id': str(user_id),
                    'product_id': product_id,
                    'txn_id': str(txn_id),
                    'credits': str(product['credits'])
                }
            )
            
            # Update transaction with Stripe session ID
            cursor.execute("""
                UPDATE credit_txn 
                SET stripe_session_id = %s
                WHERE id = %s
            """, (session.id, txn_id))
            
            connection.commit()
            cursor.close()
            connection.close()
            
            logger.info(f"Created Stripe checkout session {session.id} for user {user_id}, product {product_id}")
            
            return {
                'success': True,
                'session_id': session.id,
                'session_url': session.url,
                'txn_id': txn_id
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating checkout session: {e}")
            return {'error': f'Payment system error: {str(e)}'}
        except Exception as e:
            logger.error(f"Error creating checkout session: {e}")
            return {'error': str(e)}
    
    def handle_webhook(self, payload, sig_header):
        """Handle Stripe webhook events."""
        try:
            webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
            if not webhook_secret:
                logger.error("STRIPE_WEBHOOK_SECRET not found in environment variables")
                return {'error': 'Webhook secret not configured'}
            
            # Verify webhook signature
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
            
            # Handle the event
            if event['type'] == 'checkout.session.completed':
                session = event['data']['object']
                self._handle_successful_payment(session)
            
            elif event['type'] == 'payment_intent.succeeded':
                payment_intent = event['data']['object']
                self._handle_payment_intent_succeeded(payment_intent)
            
            elif event['type'] == 'payment_intent.payment_failed':
                payment_intent = event['data']['object']
                self._handle_payment_failed(payment_intent)
            
            elif event['type'] == 'invoice.payment_succeeded':
                invoice = event['data']['object']
                self._handle_subscription_payment(invoice)
            
            else:
                logger.info(f"Unhandled webhook event type: {event['type']}")
            
            return {'success': True}
            
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Stripe webhook signature verification failed: {e}")
            return {'error': 'Invalid signature'}
        except Exception as e:
            logger.error(f"Error handling webhook: {e}")
            return {'error': str(e)}
    
    def _handle_successful_payment(self, session):
        """Handle successful payment completion."""
        try:
            txn_id = session.get('client_reference_id')
            if not txn_id:
                logger.error("No transaction ID found in session metadata")
                return
            
            connection = mysql.connector.connect(**self.db_config)
            cursor = connection.cursor(dictionary=True)
            
            # Get transaction details
            cursor.execute("""
                SELECT ct.*, p.credits, p.recurring_credits
                FROM credit_txn ct
                JOIN products p ON ct.product_id = p.id
                WHERE ct.id = %s
            """, (txn_id,))
            
            txn = cursor.fetchone()
            if not txn:
                logger.error(f"Transaction {txn_id} not found")
                return
            
            # Update transaction status
            cursor.execute("""
                UPDATE credit_txn 
                SET payment_status = 'completed',
                    paid_date = NOW(),
                    stripe_payment_intent_id = %s
                WHERE id = %s
            """, (session.get('payment_intent'), txn_id))
            
            # Add credits to user account
            cursor.execute("""
                UPDATE users 
                SET credits = credits + %s
                WHERE id = %s
            """, (txn['credits'], txn['user_id']))
            
            # Record transaction in main transactions table
            cursor.execute("""
                INSERT INTO transactions 
                (user_id, type, change_amount, description, date_time)
                VALUES (%s, 'credit_purchase', %s, %s, NOW())
            """, (
                txn['user_id'],
                txn['credits'],
                f"Credit purchase: {txn['credits']} credits for ${txn['amount']}"
            ))
            
            connection.commit()
            cursor.close()
            connection.close()
            
            logger.info(f"Payment completed for transaction {txn_id}: {txn['credits']} credits added to user {txn['user_id']}")
            
        except Exception as e:
            logger.error(f"Error handling successful payment: {e}")
    
    def _handle_payment_intent_succeeded(self, payment_intent):
        """Handle payment intent succeeded event."""
        try:
            # This can be used for additional payment confirmation logic
            logger.info(f"Payment intent succeeded: {payment_intent['id']}")
        except Exception as e:
            logger.error(f"Error handling payment intent succeeded: {e}")
    
    def _handle_payment_failed(self, payment_intent):
        """Handle failed payment."""
        try:
            connection = mysql.connector.connect(**self.db_config)
            cursor = connection.cursor()
            
            # Update transaction status to failed
            cursor.execute("""
                UPDATE credit_txn 
                SET payment_status = 'failed'
                WHERE stripe_payment_intent_id = %s
            """, (payment_intent['id'],))
            
            connection.commit()
            cursor.close()
            connection.close()
            
            logger.info(f"Payment failed for payment intent: {payment_intent['id']}")
            
        except Exception as e:
            logger.error(f"Error handling payment failure: {e}")
    
    def _handle_subscription_payment(self, invoice):
        """Handle recurring subscription payments."""
        try:
            # For recurring payments, we need to add credits each billing cycle
            customer_id = invoice['customer']
            subscription_id = invoice['subscription']
            
            # Get subscription details from Stripe
            subscription = stripe.Subscription.retrieve(subscription_id)
            
            # Find the transaction record
            connection = mysql.connector.connect(**self.db_config)
            cursor = connection.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT ct.*, p.credits
                FROM credit_txn ct
                JOIN products p ON ct.product_id = p.id
                WHERE ct.stripe_customer_id = %s
                AND p.recurring_credits = 'yes'
                ORDER BY ct.created_at DESC
                LIMIT 1
            """, (customer_id,))
            
            txn = cursor.fetchone()
            if txn:
                # Add recurring credits
                cursor.execute("""
                    UPDATE users 
                    SET credits = credits + %s
                    WHERE id = %s
                """, (txn['credits'], txn['user_id']))
                
                # Record transaction
                cursor.execute("""
                    INSERT INTO transactions 
                    (user_id, type, change_amount, description, date_time)
                    VALUES (%s, 'recurring_credits', %s, %s, NOW())
                """, (
                    txn['user_id'],
                    txn['credits'],
                    f"Monthly credit renewal: {txn['credits']} credits"
                ))
                
                connection.commit()
                
                logger.info(f"Recurring credits added for user {txn['user_id']}: {txn['credits']} credits")
            
            cursor.close()
            connection.close()
            
        except Exception as e:
            logger.error(f"Error handling subscription payment: {e}")
    
    def get_user_purchase_history(self, user_id, limit=50):
        """Get purchase history for a user."""
        try:
            connection = mysql.connector.connect(**self.db_config)
            cursor = connection.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT 
                    ct.*,
                    p.name as product_name,
                    p.sku as product_sku
                FROM credit_txn ct
                JOIN products p ON ct.product_id = p.id
                WHERE ct.user_id = %s
                AND ct.payment_status IN ('completed', 'pending')
                ORDER BY ct.created_at DESC
                LIMIT %s
            """, (user_id, limit))
            
            purchases = cursor.fetchall()
            
            # Convert datetime objects for JSON serialization
            for purchase in purchases:
                for field in ['paid_date', 'created_at', 'updated_at']:
                    if purchase[field]:
                        purchase[field] = purchase[field].isoformat()
                if purchase['amount']:
                    purchase['amount'] = float(purchase['amount'])
            
            cursor.close()
            connection.close()
            
            return purchases
            
        except Exception as e:
            logger.error(f"Error getting purchase history for user {user_id}: {e}")
            return []
    
    def get_stripe_publishable_key(self):
        """Get Stripe publishable key for frontend."""
        return self.stripe_publishable_key