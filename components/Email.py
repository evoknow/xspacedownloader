#!/usr/bin/env python3
# components/Email.py
"""
Email Component for XSpace Downloader

This component handles email operations using configurable email providers.
It supports SendGrid, Mailgun, and standard SMTP for sending emails.

Features:
- Automatic selection of the first active provider (status = 1)
- Support for HTML and plain text emails
- File attachment handling
- Default to testers in configuration if no recipients specified
- Custom sender name and email

Usage Examples:
    
    # Basic Usage - Send to testers
    from components.Email import Email
    email = Email()
    email.test()  # Sends test email to enabled testers
    
    # Send to specific recipient
    email.send(
        to="user@example.com",
        subject="Hello from XSpace",
        body="<h1>Welcome</h1><p>This is an HTML email</p>"
    )
    
    # Send with custom sender
    email.send(
        to="user@example.com",
        from_addr={"name": "Custom Sender", "email": "sender@example.com"},
        subject="Custom Sender",
        body="Email with custom sender"
    )
    
    # Send with attachment
    email.send(
        to={"name": "John Doe", "email": "john@example.com"},
        subject="Report Attached",
        body="Please find the attached report",
        attachments=["/path/to/report.pdf"]
    )
"""

import json
import smtplib
import socket
import mysql.connector

# Try to import requests, but continue if not available
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    print("Warning: requests module not available, SendGrid and Mailgun providers will not work")
    REQUESTS_AVAILABLE = False
from mysql.connector import Error
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import formataddr
import os.path

class Email:
    """
    Class to handle email operations using the configured email provider.
    Supports multiple email providers (sendgrid, mailgun, default-smtp).
    """
    
    def __init__(self, db_connection=None):
        """Initialize the Email component with a database connection."""
        self.connection = db_connection
        if not self.connection:
            try:
                with open('db_config.json', 'r') as config_file:
                    config = json.load(config_file)
                    if config["type"] == "mysql":
                        db_config = config["mysql"].copy()
                        # Remove unsupported parameters
                        if 'use_ssl' in db_config:
                            del db_config['use_ssl']
                        # Add JSON converter
                        db_config['converter_class'] = mysql.connector.conversion.MySQLConverter
                    else:
                        raise ValueError(f"Unsupported database type: {config['type']}")
                self.connection = mysql.connector.connect(**db_config)
            except Error as e:
                print(f"Error connecting to MySQL Database: {e}")
                raise
        
        # Load active email provider configuration
        self.email_config = self._load_email_config()
    
    def __del__(self):
        """Close the database connection when the object is destroyed."""
        if hasattr(self, 'connection') and self.connection and self.connection.is_connected():
            self.connection.close()
    
    def _load_email_config(self):
        """
        Load the first active email provider configuration from the database.
        
        Returns:
            dict: Email provider configuration or None if no active provider found
        """
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            # Get the first active email provider
            query = "SELECT * FROM email_config WHERE status = 1 ORDER BY id LIMIT 1"
            cursor.execute(query)
            config = cursor.fetchone()
            
            if not config:
                print("No active email provider found.")
                return None
            
            return config
            
        except Error as e:
            print(f"Error loading email configuration: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
    
    def _get_testers(self):
        """
        Get the list of testers from the email configuration.
        
        Returns:
            list: List of tester dictionaries with name, email, and enabled status
        """
        if not self.email_config or 'testers' not in self.email_config:
            return []
        
        testers = self.email_config['testers']
        
        # If testers is a string (JSON string), parse it
        if isinstance(testers, str):
            try:
                testers = json.loads(testers)
            except json.JSONDecodeError:
                print("Failed to parse testers JSON string")
                return []
        
        # Make sure testers is a list
        if not isinstance(testers, list):
            print(f"Testers field is not a list: {type(testers)}")
            return []
        
        # Return only enabled testers
        return [tester for tester in testers if isinstance(tester, dict) and tester.get('enabled', False)]
    
    def _format_recipient(self, recipient):
        """
        Format a recipient for use in email headers.
        
        Args:
            recipient: Can be a string (email only) or dict with 'name' and 'email' keys
            
        Returns:
            str: Formatted recipient string
        """
        if isinstance(recipient, str):
            return recipient
        elif isinstance(recipient, dict) and 'email' in recipient:
            if 'name' in recipient and recipient['name']:
                return formataddr((recipient['name'], recipient['email']))
            return recipient['email']
        return None
    
    def _send_via_sendgrid(self, to_list, from_addr, subject, body, attachments=None, content_type='text/html'):
        """
        Send email using SendGrid API.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not REQUESTS_AVAILABLE:
            print("SendGrid provider requires the requests module which is not available.")
            return False
            
        if not self.email_config or self.email_config['provider'] != 'sendgrid':
            return False
        
        api_key = self.email_config.get('api_key')
        if not api_key:
            print("SendGrid API key not found in configuration.")
            return False
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Format from address
        from_name = self.email_config.get('from_name', '')
        from_email = self.email_config.get('from_email', '')
        
        if isinstance(from_addr, dict) and 'email' in from_addr:
            from_email = from_addr['email']
            if 'name' in from_addr:
                from_name = from_addr['name']
        
        # Prepare personalization (recipients)
        personalization = {
            "to": []
        }
        
        for recipient in to_list:
            if isinstance(recipient, dict) and 'email' in recipient:
                to_entry = {"email": recipient['email']}
                if 'name' in recipient and recipient['name']:
                    to_entry["name"] = recipient['name']
                personalization["to"].append(to_entry)
            elif isinstance(recipient, str):
                personalization["to"].append({"email": recipient})
        
        # Prepare attachments if any
        payload_attachments = []
        if attachments:
            for attachment_path in attachments:
                if os.path.isfile(attachment_path):
                    with open(attachment_path, "rb") as file:
                        encoded_file = file.read()
                        import base64
                        encoded_content = base64.b64encode(encoded_file).decode('utf-8')
                        
                        filename = os.path.basename(attachment_path)
                        payload_attachments.append({
                            "content": encoded_content,
                            "filename": filename,
                            "type": "application/octet-stream",
                            "disposition": "attachment"
                        })
        
        # Prepare the request payload
        payload = {
            "personalizations": [personalization],
            "from": {
                "email": from_email,
                "name": from_name
            },
            "subject": subject,
            "content": [
                {
                    "type": content_type,
                    "value": body
                }
            ]
        }
        
        if payload_attachments:
            payload["attachments"] = payload_attachments
        
        try:
            response = requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 202:
                print(f"Email sent successfully via SendGrid")
                return True
            else:
                print(f"SendGrid API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Error sending email via SendGrid: {e}")
            return False
    
    def _send_via_mailgun(self, to_list, from_addr, subject, body, attachments=None, content_type='text/html'):
        """
        Send email using Mailgun API.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not REQUESTS_AVAILABLE:
            print("Mailgun provider requires the requests module which is not available.")
            return False
            
        if not self.email_config or self.email_config['provider'] != 'mailgun':
            return False
        
        api_key = self.email_config.get('api_key')
        if not api_key:
            print("Mailgun API key not found in configuration.")
            return False
        
        # Format from address
        from_name = self.email_config.get('from_name', '')
        from_email = self.email_config.get('from_email', '')
        
        if isinstance(from_addr, dict) and 'email' in from_addr:
            from_email = from_addr['email']
            if 'name' in from_addr:
                from_name = from_addr['name']
        
        from_header = from_email
        if from_name:
            from_header = f"{from_name} <{from_email}>"
        
        # Format recipients
        to_headers = []
        for recipient in to_list:
            formatted = self._format_recipient(recipient)
            if formatted:
                to_headers.append(formatted)
        
        # Prepare the request data
        data = {
            "from": from_header,
            "to": to_headers,
            "subject": subject,
            "html" if content_type == 'text/html' else "text": body
        }
        
        files = []
        if attachments:
            for attachment_path in attachments:
                if os.path.isfile(attachment_path):
                    filename = os.path.basename(attachment_path)
                    files.append(("attachment", (filename, open(attachment_path, "rb"))))
        
        try:
            # Extract domain from from_email for API URL
            domain = from_email.split('@')[1] if '@' in from_email else None
            if not domain:
                print("Invalid from_email in configuration, cannot determine domain for Mailgun API.")
                return False
            
            response = requests.post(
                f"https://api.mailgun.net/v3/{domain}/messages",
                auth=("api", api_key),
                data=data,
                files=files
            )
            
            if response.status_code == 200:
                print(f"Email sent successfully via Mailgun")
                return True
            else:
                print(f"Mailgun API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Error sending email via Mailgun: {e}")
            return False
        finally:
            # Close file handles
            for _, file_tuple in files:
                if hasattr(file_tuple[1], 'close'):
                    file_tuple[1].close()
    
    def _send_via_smtp(self, to_list, from_addr, subject, body, attachments=None, content_type='text/html'):
        """
        Send email using SMTP.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.email_config or self.email_config['provider'] != 'default-smtp':
            return False
        
        server = self.email_config.get('server')
        port = self.email_config.get('port')
        username = self.email_config.get('username')
        password = self.email_config.get('password')
        use_tls = self.email_config.get('use_tls', True)
        
        if not server or not port:
            print("SMTP server or port not found in configuration.")
            return False
        
        # Format from address
        from_name = self.email_config.get('from_name', '')
        from_email = self.email_config.get('from_email', '')
        
        if isinstance(from_addr, dict) and 'email' in from_addr:
            from_email = from_addr['email']
            if 'name' in from_addr:
                from_name = from_addr['name']
        
        # Create message
        msg = MIMEMultipart()
        msg['Subject'] = subject
        
        # Set From header
        if from_name:
            msg['From'] = formataddr((from_name, from_email))
        else:
            msg['From'] = from_email
        
        # Set To header
        to_addresses = []
        for recipient in to_list:
            formatted = self._format_recipient(recipient)
            if formatted:
                to_addresses.append(formatted)
        
        msg['To'] = ', '.join(to_addresses)
        
        # Attach body
        if content_type == 'text/html':
            msg.attach(MIMEText(body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))
        
        # Attach files if any
        if attachments:
            for attachment_path in attachments:
                if os.path.isfile(attachment_path):
                    with open(attachment_path, "rb") as file:
                        part = MIMEApplication(file.read(), Name=os.path.basename(attachment_path))
                    
                    part['Content-Disposition'] = f'attachment; filename="{os.path.basename(attachment_path)}"'
                    msg.attach(part)
        
        try:
            # Connect to SMTP server
            smtp = smtplib.SMTP(server, port)
            
            if use_tls:
                smtp.starttls()
            
            # Login if credentials provided
            if username and password:
                smtp.login(username, password)
            
            # Send the email
            smtp.send_message(msg)
            smtp.quit()
            
            print(f"Email sent successfully via SMTP")
            return True
            
        except Exception as e:
            print(f"Error sending email via SMTP: {e}")
            return False
    
    def send(self, to=None, from_addr=None, subject="", body="", attachments=None, content_type='text/html'):
        """
        Send an email using the active email provider.
        
        Args:
            to: Recipient(s) - can be a string, dict with 'name' and 'email', or a list of either.
                If None, will send to enabled testers from configuration.
            from_addr: Sender - can be None (use config), a dict with 'name' and 'email', or a string.
            subject (str): Email subject
            body (str): Email body
            attachments (list, optional): List of file paths to attach
            content_type (str, optional): Content type, defaults to 'text/html'
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.email_config:
            print("No active email provider configuration found.")
            return False
        
        # Prepare recipient list
        to_list = []
        
        if to is None:
            # Use testers from configuration
            to_list = self._get_testers()
        elif isinstance(to, list):
            to_list = to
        else:
            to_list = [to]
        
        # If still no recipients, fail
        if not to_list:
            print("No recipients specified and no enabled testers found.")
            return False
        
        # Use the appropriate sending method based on the provider
        provider = self.email_config.get('provider', '').lower()
        
        if provider == 'sendgrid':
            return self._send_via_sendgrid(to_list, from_addr, subject, body, attachments, content_type)
        elif provider == 'mailgun':
            return self._send_via_mailgun(to_list, from_addr, subject, body, attachments, content_type)
        elif provider == 'default-smtp':
            return self._send_via_smtp(to_list, from_addr, subject, body, attachments, content_type)
        else:
            print(f"Unsupported email provider: {provider}")
            return False
    
    def test(self):
        """
        Send a test email using the active email provider.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.email_config:
            print("No active email provider configuration found.")
            return False
        
        # Get current time and date
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S")
        date_str = now.strftime("%Y-%m-%d")
        
        # Get server IP
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except:
            ip = "unknown"
        
        provider = self.email_config.get('provider', 'unknown')
        
        subject = f"This is a email test {time_str} {date_str} [{provider}]"
        body = f"Hello from {ip} - mail sent by {provider}"
        
        # Send to testers only
        return self.send(subject=subject, body=body)