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
        
        # Initialize Stripe with mode-specific keys
        self._load_stripe_keys()
        
        if not stripe.api_key:
            logger.error("Stripe secret key not found or not configured properly")
        if not self.stripe_publishable_key:
            logger.error("Stripe publishable key not found or not configured properly")
    
    def _load_stripe_keys(self):
        """Load appropriate Stripe keys based on current mode."""
        try:
            from components.EnvManager import EnvManager
            env_manager = EnvManager()
            config = env_manager.get_stripe_config()
            
            current_mode = config['mode']
            
            if current_mode == 'live':
                stripe.api_key = config['live']['secret_key'] or os.getenv('STRIPE_SECRET_KEY')
                self.stripe_publishable_key = config['live']['publishable_key'] or os.getenv('STRIPE_PUBLISHABLE_KEY')
                self.webhook_secret = config['live']['webhook_secret'] or os.getenv('STRIPE_WEBHOOK_SECRET')
            else:  # test mode (default)
                stripe.api_key = config['test']['secret_key'] or os.getenv('STRIPE_SECRET_KEY')
                self.stripe_publishable_key = config['test']['publishable_key'] or os.getenv('STRIPE_PUBLISHABLE_KEY')
                self.webhook_secret = config['test']['webhook_secret'] or os.getenv('STRIPE_WEBHOOK_SECRET')
            
            self.current_mode = current_mode
            logger.info(f"Stripe initialized in {current_mode.upper()} mode")
            
        except Exception as e:
            logger.error(f"Error loading Stripe keys: {e}")
            # Fallback to environment variables
            stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
            self.stripe_publishable_key = os.getenv('STRIPE_PUBLISHABLE_KEY')
            self.webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
            self.current_mode = 'unknown'
    
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
            cursor = connection.cursor(dictionary=True)
            
            # Check for recent pending transactions to prevent duplicates
            cursor.execute("""
                SELECT id, created_at 
                FROM credit_txn 
                WHERE user_id = %s 
                AND product_id = %s 
                AND payment_status = 'pending'
                AND created_at > DATE_SUB(NOW(), INTERVAL 30 MINUTE)
                ORDER BY created_at DESC
                LIMIT 1
            """, (user_id, product_id))
            
            recent_pending = cursor.fetchone()
            
            if recent_pending:
                # Reuse the existing pending transaction
                txn_id = recent_pending['id']
                logger.info(f"Reusing existing pending transaction {txn_id} for user {user_id}, product {product_id}")
            else:
                # Create new transaction
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
            # Use webhook secret from current configuration
            webhook_secret = self.webhook_secret
            if not webhook_secret:
                logger.error("Webhook secret not configured for current Stripe mode")
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
                SELECT ct.*, p.credits, p.recurring_credits, p.name
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
            
            # Check if this is a lifetime product (one-time payment with recurring credits)
            is_lifetime_product = (txn['recurring_credits'] == 'no' and 
                                 'lifetime' in txn['name'].lower() and 
                                 txn['credits'] > 0)
            
            if is_lifetime_product:
                # For lifetime products, set recurring_credits and reset date
                cursor.execute("""
                    UPDATE users 
                    SET credits = credits + %s,
                        recurring_credits = %s,
                        last_credit_reset = NOW()
                    WHERE id = %s
                """, (txn['credits'], txn['credits'], txn['user_id']))
                
                logger.info(f"Lifetime product purchased: Set recurring_credits to {txn['credits']} for user {txn['user_id']}")
            else:
                # For regular products, just add credits
                cursor.execute("""
                    UPDATE users 
                    SET credits = credits + %s
                    WHERE id = %s
                """, (txn['credits'], txn['user_id']))
            
            # Credit transaction is already recorded in credit_txn table
            # No need to duplicate in transactions table which is for AI usage tracking
            
            connection.commit()
            
            # Get user email for receipt
            cursor.execute("SELECT email FROM users WHERE id = %s", (txn['user_id'],))
            user = cursor.fetchone()
            
            cursor.close()
            connection.close()
            
            logger.info(f"Payment completed for transaction {txn_id}: {txn['credits']} credits added to user {txn['user_id']}")
            
            # Send email receipt
            if user and user['email']:
                self.send_receipt_email({
                    'success': True,
                    'credits': txn['credits'],
                    'amount': float(txn['amount']),
                    'product_name': txn['name'],
                    'user_email': user['email'],
                    'transaction_id': txn_id,
                    'paid_date': datetime.now()
                })
            
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
                
                # Recurring credit renewal logged in user account changes
                # No need to use transactions table which is for AI usage tracking
                
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
    
    def process_successful_payment(self, session_id):
        """Process a successful payment immediately when user returns from Stripe."""
        try:
            # Retrieve the checkout session from Stripe
            session = stripe.checkout.Session.retrieve(session_id)
            
            if session.payment_status != 'paid':
                return {'error': 'Payment not completed'}
            
            # Get transaction ID from session metadata
            txn_id = session.metadata.get('txn_id')
            if not txn_id:
                logger.error(f"No transaction ID found in session {session_id} metadata")
                return {'error': 'Transaction ID not found'}
            
            connection = mysql.connector.connect(**self.db_config)
            cursor = connection.cursor(dictionary=True)
            
            # Check if already processed
            cursor.execute("""
                SELECT payment_status FROM credit_txn WHERE id = %s
            """, (txn_id,))
            txn_status = cursor.fetchone()
            
            if txn_status and txn_status['payment_status'] == 'completed':
                cursor.close()
                connection.close()
                return {'error': 'Payment already processed'}
            
            # Get transaction details
            cursor.execute("""
                SELECT ct.*, p.credits, p.recurring_credits, p.name, u.email
                FROM credit_txn ct
                JOIN products p ON ct.product_id = p.id
                JOIN users u ON ct.user_id = u.id
                WHERE ct.id = %s
            """, (txn_id,))
            
            txn = cursor.fetchone()
            if not txn:
                cursor.close()
                connection.close()
                logger.error(f"Transaction {txn_id} not found")
                return {'error': 'Transaction not found'}
            
            # Update transaction status
            cursor.execute("""
                UPDATE credit_txn 
                SET payment_status = 'completed',
                    paid_date = NOW(),
                    stripe_session_id = %s,
                    stripe_payment_intent_id = %s
                WHERE id = %s
            """, (session.id, session.payment_intent, txn_id))
            
            # Check if this is a lifetime product
            is_lifetime_product = (txn['recurring_credits'] == 'no' and 
                                 'lifetime' in txn['name'].lower() and 
                                 txn['credits'] > 0)
            
            if is_lifetime_product:
                # For lifetime products, set recurring_credits and reset date
                cursor.execute("""
                    UPDATE users 
                    SET credits = credits + %s,
                        recurring_credits = %s,
                        last_credit_reset = NOW()
                    WHERE id = %s
                """, (txn['credits'], txn['credits'], txn['user_id']))
                
                logger.info(f"Lifetime product purchased: Set recurring_credits to {txn['credits']} for user {txn['user_id']}")
            else:
                # For regular products, just add credits
                cursor.execute("""
                    UPDATE users 
                    SET credits = credits + %s
                    WHERE id = %s
                """, (txn['credits'], txn['user_id']))
            
            # Credit transaction is already recorded in credit_txn table
            # No need to duplicate in transactions table which is for AI usage tracking
            
            connection.commit()
            cursor.close()
            connection.close()
            
            logger.info(f"Payment processed immediately for transaction {txn_id}: {txn['credits']} credits added to user {txn['user_id']}")
            
            return {
                'success': True,
                'credits': txn['credits'],
                'amount': float(txn['amount']),
                'product_name': txn['name'],
                'user_email': txn['email'],
                'transaction_id': txn_id,
                'paid_date': datetime.now()
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error processing payment: {e}")
            return {'error': f'Payment verification error: {str(e)}'}
        except Exception as e:
            logger.error(f"Error processing successful payment: {e}")
            return {'error': 'Payment processing error'}
    
    def send_receipt_email(self, payment_data):
        """Send email receipt for successful payment."""
        try:
            from components.NotificationHelper import NotificationHelper
            notification = NotificationHelper()
            
            # Format the receipt email
            subject = f"Receipt for your XSpace Downloader purchase"
            
            body = f"""
Thank you for your purchase!

Order Details:
--------------
Product: {payment_data['product_name']}
Credits: {payment_data['credits']}
Amount: ${payment_data['amount']:.2f}
Transaction ID: {payment_data['transaction_id']}
Date: {payment_data['paid_date'].strftime('%B %d, %Y at %I:%M %p')}

Your credits have been added to your account and are available for immediate use.

You can view your credit balance and transaction history at:
https://xspacedownload.com/profile

Thank you for using XSpace Downloader!

Best regards,
XSpace Downloader Team
"""
            
            # Send the email
            notification.send_email(
                to_email=payment_data['user_email'],
                subject=subject,
                body=body
            )
            
            logger.info(f"Receipt email sent to {payment_data['user_email']} for transaction {payment_data['transaction_id']}")
            
        except Exception as e:
            logger.error(f"Error sending receipt email: {e}")
            # Don't fail the payment process if email fails