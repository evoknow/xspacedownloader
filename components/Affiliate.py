#!/usr/bin/env python3
"""Affiliate component for XSpace Downloader."""

import os
import json
import csv
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import mysql.connector
from mysql.connector import Error
from typing import Dict, List, Optional, Tuple
from contextlib import closing

# Import database manager if available
try:
    from components.DatabaseManager import db_manager
except ImportError:
    db_manager = None

# Set up logging
try:
    from components.Logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


class Affiliate:
    """Handles affiliate tracking, earnings, and payouts."""
    
    def __init__(self):
        """Initialize Affiliate component."""
        try:
            # Load database configuration
            with open("db_config.json", 'r') as f:
                config = json.load(f)
            
            if config["type"] != "mysql":
                raise ValueError(f"Unsupported database type: {config['type']}")
            
            db_config = config["mysql"].copy()
            if 'use_ssl' in db_config:
                del db_config['use_ssl']
            
            # Connect to the database
            self.connection = mysql.connector.connect(**db_config)
            logger.info("Affiliate component initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing Affiliate component: {e}")
            raise
    
    def _ensure_connection(self):
        """Ensure database connection is active."""
        try:
            if self.connection and self.connection.is_connected():
                cursor = self.connection.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                return True
        except:
            pass
        
        # Reconnect
        try:
            if self.connection:
                try:
                    self.connection.close()
                except:
                    pass
            
            with open("db_config.json", 'r') as f:
                config = json.load(f)
            
            db_config = config["mysql"].copy()
            if 'use_ssl' in db_config:
                del db_config['use_ssl']
            
            self.connection = mysql.connector.connect(**db_config)
            return True
        except Exception as e:
            logger.error(f"Failed to reconnect to database: {e}")
            return False
    
    def track_visit(self, affiliate_user_id: int, visitor_ip: str, 
                   visitor_user_agent: str) -> Optional[int]:
        """
        Track an affiliate visit.
        
        Args:
            affiliate_user_id: ID of the affiliate user
            visitor_ip: IP address of the visitor
            visitor_user_agent: User agent string of the visitor
            
        Returns:
            Tracking ID if successful, None otherwise
        """
        if not self._ensure_connection():
            return None
        
        try:
            cursor = self.connection.cursor()
            
            # Check if affiliate user exists and is verified
            cursor.execute("""
                SELECT id FROM users 
                WHERE id = %s AND email_verified = 1
            """, (affiliate_user_id,))
            
            if not cursor.fetchone():
                logger.warning(f"Invalid or unverified affiliate user ID: {affiliate_user_id}")
                return None
            
            # Insert tracking record
            cursor.execute("""
                INSERT INTO affiliate_tracking 
                (affiliate_user_id, visitor_ip, visitor_user_agent)
                VALUES (%s, %s, %s)
            """, (affiliate_user_id, visitor_ip, visitor_user_agent))
            
            tracking_id = cursor.lastrowid
            self.connection.commit()
            
            logger.info(f"Tracked affiliate visit for user {affiliate_user_id}, tracking ID: {tracking_id}")
            return tracking_id
            
        except Error as e:
            logger.error(f"Error tracking affiliate visit: {e}")
            self.connection.rollback()
            return None
        finally:
            cursor.close()
    
    def convert_visitor(self, converted_user_id: int, visitor_ip: str) -> bool:
        """
        Convert a visitor to a registered user and create earnings record.
        
        Args:
            converted_user_id: ID of the newly registered user
            visitor_ip: IP address to match with tracking
            
        Returns:
            True if conversion recorded successfully
        """
        if not self._ensure_connection():
            return False
        
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            # Find the most recent tracking record for this IP within last 30 days
            cursor.execute("""
                SELECT id, affiliate_user_id 
                FROM affiliate_tracking
                WHERE visitor_ip = %s 
                AND status = 'visited'
                AND visit_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                ORDER BY visit_time DESC
                LIMIT 1
            """, (visitor_ip,))
            
            tracking = cursor.fetchone()
            if not tracking:
                logger.info(f"No affiliate tracking found for IP {visitor_ip}")
                return False
            
            # Update tracking record
            cursor.execute("""
                UPDATE affiliate_tracking
                SET converted_user_id = %s,
                    conversion_time = NOW(),
                    status = 'registered'
                WHERE id = %s
            """, (converted_user_id, tracking['id']))
            
            # Get affiliate settings
            settings = self.get_affiliate_settings()
            
            # Create earnings record
            cursor.execute("""
                INSERT INTO affiliate_earnings
                (affiliate_user_id, referred_user_id, credits_earned, money_earned)
                VALUES (%s, %s, %s, %s)
            """, (tracking['affiliate_user_id'], converted_user_id, 
                  settings['credits_per_registration'], 
                  settings['money_per_registration']))
            
            self.connection.commit()
            
            logger.info(f"Recorded affiliate conversion: affiliate {tracking['affiliate_user_id']} "
                       f"referred user {converted_user_id}")
            return True
            
        except Error as e:
            logger.error(f"Error recording affiliate conversion: {e}")
            self.connection.rollback()
            return False
        finally:
            cursor.close()
    
    def verify_conversion(self, converted_user_id: int) -> bool:
        """
        Mark a conversion as verified when user verifies email.
        
        Args:
            converted_user_id: ID of the user who verified email
            
        Returns:
            True if updated successfully
        """
        if not self._ensure_connection():
            return False
        
        try:
            cursor = self.connection.cursor()
            
            # Update tracking status
            cursor.execute("""
                UPDATE affiliate_tracking
                SET status = 'verified'
                WHERE converted_user_id = %s AND status = 'registered'
            """, (converted_user_id,))
            
            self.connection.commit()
            
            if cursor.rowcount > 0:
                logger.info(f"Verified affiliate conversion for user {converted_user_id}")
                return True
            
            return False
            
        except Error as e:
            logger.error(f"Error verifying affiliate conversion: {e}")
            self.connection.rollback()
            return False
        finally:
            cursor.close()
    
    def get_affiliate_stats(self, user_id: int) -> Dict:
        """
        Get affiliate statistics for a user.
        
        Args:
            user_id: ID of the affiliate user
            
        Returns:
            Dictionary with affiliate stats
        """
        if not self._ensure_connection():
            return {}
        
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            # Get settings
            settings = self.get_affiliate_settings()
            
            # Get total earnings
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_referrals,
                    SUM(credits_earned) as total_credits_earned,
                    SUM(money_earned) as total_money_earned,
                    SUM(CASE WHEN credit_status = 'pending' THEN credits_earned ELSE 0 END) as pending_credits,
                    SUM(CASE WHEN money_status = 'pending' THEN money_earned ELSE 0 END) as pending_money,
                    SUM(CASE WHEN credit_status = 'paid' THEN credits_earned ELSE 0 END) as paid_credits,
                    SUM(CASE WHEN money_status = 'paid' THEN money_earned ELSE 0 END) as paid_money
                FROM affiliate_earnings
                WHERE affiliate_user_id = %s
            """, (user_id,))
            
            stats = cursor.fetchone() or {}
            
            # Convert Decimal to float for JSON serialization
            for key in stats:
                if isinstance(stats[key], Decimal):
                    stats[key] = float(stats[key] or 0)
            
            # Add settings
            stats['credits_per_registration'] = float(settings['credits_per_registration'])
            stats['money_per_registration'] = float(settings['money_per_registration'])
            stats['minimum_payout_amount'] = float(settings['minimum_payout_amount'])
            
            # Get recent referrals
            cursor.execute("""
                SELECT 
                    ae.referred_user_id,
                    u.email,
                    ae.earned_date,
                    ae.credits_earned,
                    ae.money_earned,
                    ae.credit_status,
                    ae.money_status
                FROM affiliate_earnings ae
                JOIN users u ON ae.referred_user_id = u.id
                WHERE ae.affiliate_user_id = %s
                ORDER BY ae.earned_date DESC
                LIMIT 10
            """, (user_id,))
            
            recent_referrals = cursor.fetchall()
            
            # Convert Decimal values
            for referral in recent_referrals:
                referral['credits_earned'] = float(referral['credits_earned'])
                referral['money_earned'] = float(referral['money_earned'])
            
            stats['recent_referrals'] = recent_referrals
            
            return stats
            
        except Error as e:
            logger.error(f"Error getting affiliate stats: {e}")
            return {}
        finally:
            cursor.close()
    
    def get_affiliate_settings(self) -> Dict:
        """Get current affiliate settings."""
        if not self._ensure_connection():
            return {
                'credits_per_registration': 10.0,
                'money_per_registration': 0.50,
                'minimum_payout_amount': 20.0,
                'tax_reporting_threshold': 600.0
            }
        
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM affiliate_settings WHERE id = 1")
            settings = cursor.fetchone()
            
            if settings:
                # Convert Decimal to float
                for key in ['credits_per_registration', 'money_per_registration', 
                           'minimum_payout_amount', 'tax_reporting_threshold']:
                    if key in settings and isinstance(settings[key], Decimal):
                        settings[key] = float(settings[key])
                return settings
            
            return {
                'credits_per_registration': 10.0,
                'money_per_registration': 0.50,
                'minimum_payout_amount': 20.0,
                'tax_reporting_threshold': 600.0
            }
            
        except Error as e:
            logger.error(f"Error getting affiliate settings: {e}")
            return {
                'credits_per_registration': 10.0,
                'money_per_registration': 0.50,
                'minimum_payout_amount': 20.0,
                'tax_reporting_threshold': 600.0
            }
        finally:
            cursor.close()
    
    def update_affiliate_settings(self, settings: Dict, admin_user_id: int) -> bool:
        """Update affiliate settings."""
        if not self._ensure_connection():
            return False
        
        try:
            cursor = self.connection.cursor()
            
            cursor.execute("""
                UPDATE affiliate_settings
                SET credits_per_registration = %s,
                    money_per_registration = %s,
                    minimum_payout_amount = %s,
                    tax_reporting_threshold = %s,
                    updated_by_user_id = %s
                WHERE id = 1
            """, (settings.get('credits_per_registration', 10),
                  settings.get('money_per_registration', 0.50),
                  settings.get('minimum_payout_amount', 20),
                  settings.get('tax_reporting_threshold', 600),
                  admin_user_id))
            
            self.connection.commit()
            logger.info(f"Affiliate settings updated by admin {admin_user_id}")
            return True
            
        except Error as e:
            logger.error(f"Error updating affiliate settings: {e}")
            self.connection.rollback()
            return False
        finally:
            cursor.close()
    
    def get_pending_earnings(self, earning_type: str = 'all') -> List[Dict]:
        """
        Get all pending affiliate earnings.
        
        Args:
            earning_type: 'all', 'credit', or 'money'
            
        Returns:
            List of pending earnings
        """
        if not self._ensure_connection():
            return []
        
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            query = """
                SELECT 
                    ae.id,
                    ae.affiliate_user_id,
                    au.email as affiliate_email,
                    ae.referred_user_id,
                    ru.email as referred_email,
                    ae.credits_earned,
                    ae.money_earned,
                    ae.earned_date,
                    ae.credit_status,
                    ae.money_status
                FROM affiliate_earnings ae
                JOIN users au ON ae.affiliate_user_id = au.id
                JOIN users ru ON ae.referred_user_id = ru.id
                WHERE 1=1
            """
            
            params = []
            
            if earning_type == 'credit':
                query += " AND ae.credit_status = 'pending'"
            elif earning_type == 'money':
                query += " AND ae.money_status = 'pending'"
            else:
                query += " AND (ae.credit_status = 'pending' OR ae.money_status = 'pending')"
            
            query += " ORDER BY ae.earned_date DESC"
            
            cursor.execute(query, params)
            earnings = cursor.fetchall()
            
            # Convert Decimal values
            for earning in earnings:
                earning['credits_earned'] = float(earning['credits_earned'])
                earning['money_earned'] = float(earning['money_earned'])
            
            return earnings
            
        except Error as e:
            logger.error(f"Error getting pending earnings: {e}")
            return []
        finally:
            cursor.close()
    
    def approve_earnings(self, earning_ids: List[int], earning_type: str, 
                        admin_user_id: int) -> Tuple[bool, str]:
        """
        Approve affiliate earnings.
        
        Args:
            earning_ids: List of earning IDs to approve
            earning_type: 'credit' or 'money'
            admin_user_id: ID of admin performing the action
            
        Returns:
            Tuple of (success, message)
        """
        if not self._ensure_connection():
            return False, "Database connection failed"
        
        if earning_type not in ['credit', 'money']:
            return False, "Invalid earning type"
        
        try:
            cursor = self.connection.cursor()
            
            # Update earnings status
            status_field = f"{earning_type}_status"
            approved_date_field = f"{earning_type}_approved_date"
            
            placeholders = ','.join(['%s'] * len(earning_ids))
            query = f"""
                UPDATE affiliate_earnings
                SET {status_field} = 'approved',
                    {approved_date_field} = NOW()
                WHERE id IN ({placeholders})
                AND {status_field} = 'pending'
            """
            
            cursor.execute(query, earning_ids)
            approved_count = cursor.rowcount
            
            self.connection.commit()
            
            message = f"Approved {approved_count} {earning_type} earnings"
            logger.info(f"{message} by admin {admin_user_id}")
            
            return True, message
            
        except Error as e:
            logger.error(f"Error approving earnings: {e}")
            self.connection.rollback()
            return False, f"Database error: {str(e)}"
        finally:
            cursor.close()
    
    def pay_credits(self, admin_user_id: int) -> Tuple[bool, str]:
        """
        Pay all approved credit earnings to affiliates.
        
        Args:
            admin_user_id: ID of admin performing the action
            
        Returns:
            Tuple of (success, message)
        """
        if not self._ensure_connection():
            return False, "Database connection failed"
        
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            # Get all approved credit earnings
            cursor.execute("""
                SELECT 
                    affiliate_user_id,
                    SUM(credits_earned) as total_credits,
                    GROUP_CONCAT(id) as earning_ids
                FROM affiliate_earnings
                WHERE credit_status = 'approved'
                GROUP BY affiliate_user_id
            """)
            
            credit_payouts = cursor.fetchall()
            
            if not credit_payouts:
                return True, "No approved credits to pay"
            
            paid_users = 0
            total_credits = 0
            
            for payout in credit_payouts:
                user_id = payout['affiliate_user_id']
                credits = float(payout['total_credits'])
                earning_ids = [int(id) for id in payout['earning_ids'].split(',')]
                
                # Update user's credit balance
                cursor.execute("""
                    UPDATE users
                    SET credits_balance = credits_balance + %s
                    WHERE id = %s
                """, (credits, user_id))
                
                # Mark earnings as paid
                placeholders = ','.join(['%s'] * len(earning_ids))
                cursor.execute(f"""
                    UPDATE affiliate_earnings
                    SET credit_status = 'paid',
                        credit_paid_date = NOW()
                    WHERE id IN ({placeholders})
                """, earning_ids)
                
                paid_users += 1
                total_credits += credits
                
                logger.info(f"Paid {credits} credits to affiliate {user_id}")
            
            # Create payout record
            cursor.execute("""
                INSERT INTO affiliate_payouts
                (payout_type, created_by_user_id, total_amount, user_count, status)
                VALUES ('credit', %s, %s, %s, 'completed')
            """, (admin_user_id, total_credits, paid_users))
            
            self.connection.commit()
            
            message = f"Paid {total_credits} credits to {paid_users} affiliates"
            logger.info(f"{message} by admin {admin_user_id}")
            
            return True, message
            
        except Error as e:
            logger.error(f"Error paying credits: {e}")
            self.connection.rollback()
            return False, f"Database error: {str(e)}"
        finally:
            cursor.close()
    
    def create_money_payout_csv(self, admin_user_id: int) -> Tuple[bool, str, Optional[str]]:
        """
        Create CSV file for money payouts.
        
        Args:
            admin_user_id: ID of admin creating the payout
            
        Returns:
            Tuple of (success, message, csv_filename)
        """
        if not self._ensure_connection():
            return False, "Database connection failed", None
        
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            # Get all approved money earnings grouped by user
            cursor.execute("""
                SELECT 
                    ae.affiliate_user_id as user_id,
                    u.email,
                    SUM(ae.money_earned) as money_earned,
                    GROUP_CONCAT(ae.id) as earning_ids
                FROM affiliate_earnings ae
                JOIN users u ON ae.affiliate_user_id = u.id
                WHERE ae.money_status = 'approved'
                GROUP BY ae.affiliate_user_id
                HAVING SUM(ae.money_earned) >= (
                    SELECT minimum_payout_amount 
                    FROM affiliate_settings 
                    WHERE id = 1
                )
            """)
            
            payouts = cursor.fetchall()
            
            if not payouts:
                return True, "No affiliates have reached minimum payout amount", None
            
            # Create CSV file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            csv_filename = f"affiliate_payout_{timestamp}.csv"
            csv_path = Path(f"/tmp/{csv_filename}")
            
            with open(csv_path, 'w', newline='') as csvfile:
                fieldnames = ['user_id', 'email', 'money_earned']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                
                total_amount = 0
                user_count = 0
                all_earning_ids = []
                
                for payout in payouts:
                    money_earned = float(payout['money_earned'])
                    writer.writerow({
                        'user_id': payout['user_id'],
                        'email': payout['email'],
                        'money_earned': f"{money_earned:.2f}"
                    })
                    
                    total_amount += money_earned
                    user_count += 1
                    
                    # Collect earning IDs
                    earning_ids = [int(id) for id in payout['earning_ids'].split(',')]
                    all_earning_ids.extend(earning_ids)
            
            # Create payout record
            cursor.execute("""
                INSERT INTO affiliate_payouts
                (payout_type, created_by_user_id, total_amount, user_count, 
                 status, csv_filename)
                VALUES ('money', %s, %s, %s, 'created', %s)
            """, (admin_user_id, total_amount, user_count, csv_filename))
            
            payout_id = cursor.lastrowid
            
            # Create payout details
            for payout in payouts:
                cursor.execute("""
                    INSERT INTO affiliate_payout_details
                    (payout_id, user_id, amount)
                    VALUES (%s, %s, %s)
                """, (payout_id, payout['user_id'], payout['money_earned']))
            
            # Mark earnings as in processing
            placeholders = ','.join(['%s'] * len(all_earning_ids))
            cursor.execute(f"""
                UPDATE affiliate_earnings
                SET money_status = 'paid',
                    money_paid_date = NOW()
                WHERE id IN ({placeholders})
            """, all_earning_ids)
            
            self.connection.commit()
            
            message = f"Created payout CSV for ${total_amount:.2f} to {user_count} affiliates"
            logger.info(f"{message} by admin {admin_user_id}")
            
            return True, message, str(csv_path)
            
        except Error as e:
            logger.error(f"Error creating money payout CSV: {e}")
            self.connection.rollback()
            return False, f"Database error: {str(e)}", None
        finally:
            cursor.close()
    
    def get_admin_dashboard_stats(self) -> Dict:
        """Get affiliate statistics for admin dashboard."""
        if not self._ensure_connection():
            return {}
        
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            # Get overall statistics
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT affiliate_user_id) as total_affiliates,
                    COUNT(*) as total_referrals,
                    SUM(credits_earned) as total_credits_earned,
                    SUM(money_earned) as total_money_earned,
                    SUM(CASE WHEN credit_status = 'pending' THEN credits_earned ELSE 0 END) as pending_credits,
                    SUM(CASE WHEN money_status = 'pending' THEN money_earned ELSE 0 END) as pending_money,
                    SUM(CASE WHEN credit_status = 'paid' THEN credits_earned ELSE 0 END) as paid_credits,
                    SUM(CASE WHEN money_status = 'paid' THEN money_earned ELSE 0 END) as paid_money
                FROM affiliate_earnings
            """)
            
            stats = cursor.fetchone() or {}
            
            # Convert Decimal to float
            for key in stats:
                if isinstance(stats[key], Decimal):
                    stats[key] = float(stats[key] or 0)
            
            # Get pending counts
            cursor.execute("""
                SELECT 
                    COUNT(CASE WHEN credit_status = 'pending' THEN 1 END) as pending_credit_count,
                    COUNT(CASE WHEN money_status = 'pending' THEN 1 END) as pending_money_count
                FROM affiliate_earnings
            """)
            
            counts = cursor.fetchone()
            stats.update(counts)
            
            # Get top affiliates
            cursor.execute("""
                SELECT 
                    ae.affiliate_user_id,
                    u.email,
                    COUNT(*) as referral_count,
                    SUM(ae.credits_earned) as total_credits,
                    SUM(ae.money_earned) as total_money
                FROM affiliate_earnings ae
                JOIN users u ON ae.affiliate_user_id = u.id
                GROUP BY ae.affiliate_user_id
                ORDER BY referral_count DESC
                LIMIT 10
            """)
            
            top_affiliates = cursor.fetchall()
            
            # Convert Decimal values
            for affiliate in top_affiliates:
                affiliate['total_credits'] = float(affiliate['total_credits'])
                affiliate['total_money'] = float(affiliate['total_money'])
            
            stats['top_affiliates'] = top_affiliates
            
            return stats
            
        except Error as e:
            logger.error(f"Error getting admin dashboard stats: {e}")
            return {}
        finally:
            cursor.close()
    
    def __del__(self):
        """Clean up database connection."""
        if hasattr(self, 'connection') and self.connection:
            try:
                self.connection.close()
            except:
                pass