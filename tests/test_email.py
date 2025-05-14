#!/usr/bin/env python3
# tests/test_email.py

import unittest
import sys
import os
import json
from unittest.mock import patch, MagicMock

# Add parent directory to path for importing components
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.Email import Email

class EmailTest(unittest.TestCase):
    """
    Test case for Email component.
    Tests the Email functionality using mocks to avoid actual email sending.
    """
    
    def setUp(self):
        """Set up test fixtures."""
        # Mock database connection and cursor
        self.mock_connection = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_connection.cursor.return_value = self.mock_cursor
        
        # Mock fetchone to return a fake email config
        self.mock_cursor.fetchone.return_value = {
            'id': 1,
            'provider': 'sendgrid',
            'api_key': 'fake_api_key',
            'from_email': 'test@example.com',
            'from_name': 'Test Sender',
            'server': None,
            'port': None,
            'username': None,
            'password': None,
            'use_tls': True,
            'status': 1,
            'templates': None,
            'testers': [
                {
                    'name': 'Test User',
                    'email': 'test@example.com',
                    'enabled': True
                },
                {
                    'name': 'Disabled User',
                    'email': 'disabled@example.com',
                    'enabled': False
                }
            ]
        }
        
        # Create Email instance with mocked connection
        self.email = Email(db_connection=self.mock_connection)
    
    def test_load_email_config(self):
        """Test loading email configuration."""
        config = self.email._load_email_config()
        
        # Verify query was executed correctly
        self.mock_cursor.execute.assert_called_with(
            "SELECT * FROM email_config WHERE status = 1 ORDER BY id LIMIT 1"
        )
        
        # Verify config was loaded
        self.assertIsNotNone(config)
        self.assertEqual(config['provider'], 'sendgrid')
        self.assertEqual(config['from_email'], 'test@example.com')
    
    def test_get_testers(self):
        """Test getting testers from config."""
        testers = self.email._get_testers()
        
        # Should only return enabled testers
        self.assertEqual(len(testers), 1)
        self.assertEqual(testers[0]['name'], 'Test User')
        self.assertEqual(testers[0]['email'], 'test@example.com')
        self.assertTrue(testers[0]['enabled'])
    
    def test_format_recipient_string(self):
        """Test formatting recipient as string."""
        recipient = 'test@example.com'
        formatted = self.email._format_recipient(recipient)
        
        self.assertEqual(formatted, 'test@example.com')
    
    def test_format_recipient_dict(self):
        """Test formatting recipient as dict with name and email."""
        recipient = {
            'name': 'Test User',
            'email': 'test@example.com'
        }
        formatted = self.email._format_recipient(recipient)
        
        # Should format as "Name <email>"
        self.assertIn('Test User', formatted)
        self.assertIn('test@example.com', formatted)
    
    @patch('requests.post')
    def test_send_via_sendgrid(self, mock_post):
        """Test sending email via SendGrid."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response
        
        # Test sending
        result = self.email._send_via_sendgrid(
            to_list=[{'name': 'Test User', 'email': 'test@example.com'}],
            from_addr=None,
            subject='Test Subject',
            body='Test Body'
        )
        
        # Verify request was made correctly
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        
        # Check URL
        self.assertEqual(args[0], 'https://api.sendgrid.com/v3/mail/send')
        
        # Check headers
        self.assertIn('Authorization', kwargs['headers'])
        self.assertIn('Bearer fake_api_key', kwargs['headers']['Authorization'])
        
        # Check payload
        self.assertIn('personalizations', kwargs['json'])
        self.assertIn('from', kwargs['json'])
        self.assertEqual(kwargs['json']['subject'], 'Test Subject')
        
        # Check result
        self.assertTrue(result)
    
    @patch('smtplib.SMTP')
    def test_send_via_smtp(self, mock_smtp):
        """Test sending email via SMTP."""
        # Update mock config to use SMTP
        self.email.email_config = {
            'provider': 'default-smtp',
            'from_email': 'test@example.com',
            'from_name': 'Test Sender',
            'server': 'smtp.example.com',
            'port': 587,
            'username': 'test_user',
            'password': 'test_password',
            'use_tls': True
        }
        
        # Mock SMTP instance
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value = mock_smtp_instance
        
        # Test sending
        result = self.email._send_via_smtp(
            to_list=[{'name': 'Test User', 'email': 'test@example.com'}],
            from_addr=None,
            subject='Test Subject',
            body='Test Body'
        )
        
        # Verify SMTP was used correctly
        mock_smtp.assert_called_with('smtp.example.com', 587)
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.login.assert_called_with('test_user', 'test_password')
        mock_smtp_instance.send_message.assert_called_once()
        mock_smtp_instance.quit.assert_called_once()
        
        # Check result
        self.assertTrue(result)
    
    @patch('requests.post')
    def test_send_via_mailgun(self, mock_post):
        """Test sending email via Mailgun."""
        # Update mock config to use Mailgun
        self.email.email_config = {
            'provider': 'mailgun',
            'api_key': 'fake_mailgun_key',
            'from_email': 'test@example.com',
            'from_name': 'Test Sender'
        }
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Test sending
        result = self.email._send_via_mailgun(
            to_list=[{'name': 'Test User', 'email': 'test@example.com'}],
            from_addr=None,
            subject='Test Subject',
            body='Test Body'
        )
        
        # Verify request was made correctly
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        
        # Check URL (should include domain from from_email)
        self.assertIn('https://api.mailgun.net/v3/example.com/messages', args[0])
        
        # Check auth
        self.assertEqual(kwargs['auth'][0], 'api')
        self.assertEqual(kwargs['auth'][1], 'fake_mailgun_key')
        
        # Check data
        self.assertEqual(kwargs['data']['subject'], 'Test Subject')
        self.assertEqual(kwargs['data']['html'], 'Test Body')
        
        # Check result
        self.assertTrue(result)
    
    @patch.object(Email, '_send_via_sendgrid')
    def test_send(self, mock_send_via_sendgrid):
        """Test high-level send method."""
        # Mock successful sending
        mock_send_via_sendgrid.return_value = True
        
        # Test with default parameters
        result = self.email.send(
            subject='Test Subject',
            body='Test Body'
        )
        
        # Verify appropriate send method was called
        mock_send_via_sendgrid.assert_called_once()
        
        # Check result
        self.assertTrue(result)
    
    @patch.object(Email, 'send')
    def test_test_method(self, mock_send):
        """Test the test() method."""
        # Mock successful sending
        mock_send.return_value = True
        
        # Call test method
        result = self.email.test()
        
        # Verify send was called with appropriate parameters
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        
        # Subject should include provider name and timestamp
        self.assertIn('sendgrid', kwargs['subject'])
        
        # Body should include IP and provider
        self.assertIn('sendgrid', kwargs['body'])
        
        # Check result
        self.assertTrue(result)

if __name__ == '__main__':
    unittest.main()