#!/usr/bin/env python3
# components/NotificationHelper.py
"""
Notification Helper for XSpace Downloader

This component handles email notifications for various job completions
(MP3 downloads, transcriptions, translations, video generation).

Features:
- Email notifications with job completion details
- Include user credit balance
- Include recent transactions
- HTML formatted emails with branding
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from .Email import Email
from .DatabaseManager import DatabaseManager
from .User import User

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class NotificationHelper:
    """Helper class for sending notification emails."""
    
    def __init__(self, site_url: str = "https://xspacedownload.com"):
        """
        Initialize the notification helper.
        
        Args:
            site_url (str): The base URL of the site
        """
        self.site_url = site_url.rstrip('/')
        self.db_manager = DatabaseManager()
        self.email = Email()
        self.user = User()
        
        # Load branding from mainconfig.json
        try:
            with open('mainconfig.json', 'r') as f:
                config = json.load(f)
                self.brand_name = config.get('brand_name', 'XSpace')
                self.brand_color = config.get('brand_color', '#ff6b35')
                self.brand_logo_url = config.get('brand_logo_url', '')
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.brand_name = 'XSpace'
            self.brand_color = '#ff6b35'
            self.brand_logo_url = ''
    
    def get_user_info(self, user_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Get user information including email and credit balance.
        
        Args:
            user_id (int): The user ID
            
        Returns:
            Tuple of (user_info dict, error message)
        """
        try:
            with self.db_manager.get_connection() as connection:
                cursor = connection.cursor(dictionary=True)
                
                query = """
                SELECT id, email, credits, status
                FROM users
                WHERE id = %s
                """
                cursor.execute(query, (user_id,))
                user_info = cursor.fetchone()
                
                if not user_info:
                    return None, "User not found"
                
                if user_info['status'] != 1:
                    return None, "User account is not active"
                
                return user_info, None
                
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return None, str(e)
    
    def get_recent_transactions(self, user_id: int, limit: int = 5) -> List[Dict]:
        """
        Get recent transactions for a user.
        
        Args:
            user_id (int): The user ID
            limit (int): Number of recent transactions to fetch
            
        Returns:
            List of transaction dictionaries
        """
        try:
            with self.db_manager.get_connection() as connection:
                cursor = connection.cursor(dictionary=True)
                
                query = """
                SELECT 
                    t.id,
                    t.user_id,
                    t.space_id,
                    t.action,
                    t.cost,
                    t.created_at,
                    s.title as space_title
                FROM transactions t
                LEFT JOIN spaces s ON t.space_id = s.space_id
                WHERE t.user_id = %s
                ORDER BY t.created_at DESC
                LIMIT %s
                """
                cursor.execute(query, (user_id, limit))
                transactions = cursor.fetchall()
                
                return transactions
                
        except Exception as e:
            logger.error(f"Error getting transactions: {e}")
            return []
    
    def format_transaction_html(self, transactions: List[Dict]) -> str:
        """
        Format transactions as HTML table.
        
        Args:
            transactions (List[Dict]): List of transaction dictionaries
            
        Returns:
            HTML string for transactions table
        """
        if not transactions:
            return "<p>No recent transactions</p>"
        
        html = """
        <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
            <thead>
                <tr style="background-color: #f5f5f5;">
                    <th style="padding: 8px; text-align: left; border-bottom: 2px solid #ddd;">Date</th>
                    <th style="padding: 8px; text-align: left; border-bottom: 2px solid #ddd;">Action</th>
                    <th style="padding: 8px; text-align: left; border-bottom: 2px solid #ddd;">Space</th>
                    <th style="padding: 8px; text-align: right; border-bottom: 2px solid #ddd;">Cost</th>
                </tr>
            </thead>
            <tbody>
        """
        
        for tx in transactions:
            date_str = tx['created_at'].strftime('%Y-%m-%d %H:%M')
            space_title = tx.get('space_title', 'N/A')[:50]
            if len(space_title) == 50:
                space_title += '...'
            
            html += f"""
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">{date_str}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">{tx['action'].title()}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">{space_title}</td>
                    <td style="padding: 8px; text-align: right; border-bottom: 1px solid #eee;">${tx['cost']:.2f}</td>
                </tr>
            """
        
        html += """
            </tbody>
        </table>
        """
        
        return html
    
    def send_job_completion_email(self, user_id: int, job_type: str, space_id: str, 
                                space_title: str = None, additional_info: Dict = None) -> bool:
        """
        Send job completion email to user.
        
        Args:
            user_id (int): The user ID
            job_type (str): Type of job ('download', 'transcription', 'translation', 'video')
            space_id (str): The space ID
            space_title (str): The space title (optional)
            additional_info (Dict): Additional information for the email (optional)
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            # Get user info
            user_info, error = self.get_user_info(user_id)
            if error:
                logger.error(f"Failed to get user info: {error}")
                return False
            
            # Get recent transactions
            transactions = self.get_recent_transactions(user_id)
            
            # Build space URL
            space_url = f"{self.site_url}/spaces/{space_id}"
            
            # Format job type for display
            job_type_display = {
                'download': 'MP3 Download',
                'transcription': 'Transcription',
                'translation': 'Translation',
                'video': 'Video Generation'
            }.get(job_type, job_type.title())
            
            # Build email subject
            subject = f"{self.brand_name} - {job_type_display} Complete"
            if space_title:
                subject += f": {space_title[:50]}"
            
            # Build email body
            body = f"""
            <html>
            <head>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                    }}
                    .header {{
                        background-color: {self.brand_color};
                        color: white;
                        padding: 20px;
                        text-align: center;
                        border-radius: 5px 5px 0 0;
                    }}
                    .content {{
                        background-color: #f9f9f9;
                        padding: 20px;
                        border-radius: 0 0 5px 5px;
                    }}
                    .button {{
                        display: inline-block;
                        padding: 12px 24px;
                        background-color: {self.brand_color};
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        margin: 15px 0;
                    }}
                    .credit-balance {{
                        background-color: #e8f5e9;
                        padding: 15px;
                        border-radius: 5px;
                        margin: 15px 0;
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 20px;
                        font-size: 12px;
                        color: #666;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
            """
            
            if self.brand_logo_url:
                body += f'<img src="{self.brand_logo_url}" alt="{self.brand_name}" style="max-height: 50px; margin-bottom: 10px;"><br>'
            
            body += f"""
                        <h1>{job_type_display} Complete!</h1>
                    </div>
                    <div class="content">
                        <h2>Hi there!</h2>
                        <p>Your {job_type_display.lower()} for the following space has been completed successfully:</p>
                        
                        <h3>{space_title or space_id}</h3>
            """
            
            # Add job-specific information
            if job_type == 'translation' and additional_info:
                target_lang = additional_info.get('target_lang', 'N/A')
                body += f"<p><strong>Translated to:</strong> {target_lang}</p>"
            elif job_type == 'video' and additional_info:
                video_style = additional_info.get('style', 'N/A')
                body += f"<p><strong>Video Style:</strong> {video_style}</p>"
            
            body += f"""
                        <p>You can view and manage your space by clicking the button below:</p>
                        
                        <center>
                            <a href="{space_url}" class="button">View Space</a>
                        </center>
                        
                        <div class="credit-balance">
                            <h3>Your Credit Balance</h3>
                            <p style="font-size: 24px; margin: 5px 0;"><strong>${user_info['credits']:.2f}</strong></p>
                        </div>
                        
                        <h3>Recent Transactions</h3>
                        {self.format_transaction_html(transactions)}
                        
                        <p style="margin-top: 20px;">Thank you for using {self.brand_name}!</p>
                    </div>
                    <div class="footer">
                        <p>This is an automated notification from {self.brand_name}.</p>
                        <p>© {datetime.now().year} {self.brand_name}. All rights reserved.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Send email
            success, message = self.email.send(
                to=user_info['email'],
                subject=subject,
                body=body
            )
            
            if success:
                logger.info(f"Sent {job_type} completion email to user {user_id} for space {space_id}")
            else:
                logger.error(f"Failed to send email: {message}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending job completion email: {e}")
            return False

# Example usage
if __name__ == "__main__":
    # Test the notification helper
    helper = NotificationHelper()
    
    # Test sending a download completion email
    success = helper.send_job_completion_email(
        user_id=1,
        job_type='download',
        space_id='test123',
        space_title='Test Space Title'
    )
    
    print(f"Email sent: {success}")