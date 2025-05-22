#!/usr/bin/env python3
# tests/test_email_real.py

"""
Real-world Email Component Tests

This module contains tests that perform actual email sending to verify
the end-to-end functionality of the Email component with real providers.

These tests are marked as skipped by default to avoid sending emails
during automated testing. To run these tests, set the environment
variable SEND_REAL_EMAILS=1.

Example:
    SEND_REAL_EMAILS=1 python3 -m unittest tests/test_email_real.py
"""

import unittest
import sys
import os
import json
import time
from datetime import datetime
from unittest.mock import patch

# Add parent directory to path for importing components
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.Email import Email

# Check if this test should actually send emails
SEND_REAL_EMAILS = os.environ.get('SEND_REAL_EMAILS', '0') == '1'

@unittest.skipUnless(SEND_REAL_EMAILS, "Skipping real email tests (set SEND_REAL_EMAILS=1 to run)")
class EmailRealTest(unittest.TestCase):
    """
    Real-world test case for Email component.
    Actually sends emails to verify end-to-end functionality.
    """
    
    def setUp(self):
        """Set up test fixtures."""
        # Create Email instance with real database connection
        self.email = Email()
        
        # Skip test if no active provider is configured
        if not self.email.email_config:
            self.skipTest("No active email provider configured in database")
        
        # Add a timestamp to make emails unique and identifiable
        self.timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.provider_name = self.email.email_config.get('provider', 'unknown')
        
        print(f"\nUsing email provider: {self.provider_name}")
        print(f"From email: {self.email.email_config.get('from_email')}")
        print(f"From name: {self.email.email_config.get('from_name')}")
    
    def get_test_info(self):
        """Get info about current test for logging."""
        test_name = self.id().split('.')[-1]
        return f"{test_name} ({self.provider_name} @ {self.timestamp})"
    
    def test_01_send_to_testers(self):
        """Test sending email to configured testers."""
        # Get testers
        testers = self.email._get_testers()
        if not testers:
            self.skipTest("No enabled testers configured in database")
        
        print(f"Sending to testers: {[t['email'] for t in testers]}")
        
        # Send test email
        subject = f"Test Email to Testers [{self.provider_name}] {self.timestamp}"
        body = f"""
        <h1>Test Email to Testers</h1>
        <p>This is a test email sent to all enabled testers.</p>
        <p><strong>Provider:</strong> {self.provider_name}</p>
        <p><strong>Time:</strong> {self.timestamp}</p>
        <p>This email was sent during automated testing.</p>
        """
        
        result = self.email.send(
            subject=subject,
            body=body
        )
        
        self.assertTrue(result, f"Failed to send email to testers via {self.provider_name}")
        print(f"✓ Email sent to testers via {self.provider_name}")
        
        # Short pause to avoid rate limiting
        time.sleep(1)
    
    def test_02_send_direct_email(self):
        """Test sending email to specific recipient."""
        # Send direct email to first tester
        testers = self.email._get_testers()
        if not testers:
            self.skipTest("No enabled testers configured in database")
        
        first_tester = testers[0]
        print(f"Sending direct email to: {first_tester['email']}")
        
        # Send test email
        subject = f"Direct Test Email [{self.provider_name}] {self.timestamp}"
        body = f"""
        <h1>Direct Test Email</h1>
        <p>This is a direct test email sent to {first_tester['name']}.</p>
        <p><strong>Provider:</strong> {self.provider_name}</p>
        <p><strong>Time:</strong> {self.timestamp}</p>
        <p>This email was sent during automated testing.</p>
        """
        
        result = self.email.send(
            to=first_tester,
            subject=subject,
            body=body
        )
        
        self.assertTrue(result, f"Failed to send direct email via {self.provider_name}")
        print(f"✓ Direct email sent via {self.provider_name}")
        
        # Short pause to avoid rate limiting
        time.sleep(1)
    
    def test_03_send_custom_sender(self):
        """Test sending email with custom sender."""
        # Get testers
        testers = self.email._get_testers()
        if not testers:
            self.skipTest("No enabled testers configured in database")
        
        first_tester = testers[0]
        custom_sender = {
            "name": f"Custom Sender [{self.provider_name}]",
            "email": self.email.email_config.get('from_email')  # Use same domain for deliverability
        }
        
        print(f"Sending with custom sender: {custom_sender['name']} <{custom_sender['email']}>")
        
        # Send test email
        subject = f"Custom Sender Test [{self.provider_name}] {self.timestamp}"
        body = f"""
        <h1>Custom Sender Test</h1>
        <p>This is a test email sent with a custom sender name.</p>
        <p><strong>Provider:</strong> {self.provider_name}</p>
        <p><strong>Sender:</strong> {custom_sender['name']} &lt;{custom_sender['email']}&gt;</p>
        <p><strong>Time:</strong> {self.timestamp}</p>
        <p>This email was sent during automated testing.</p>
        """
        
        result = self.email.send(
            to=first_tester,
            from_addr=custom_sender,
            subject=subject,
            body=body
        )
        
        self.assertTrue(result, f"Failed to send email with custom sender via {self.provider_name}")
        print(f"✓ Email with custom sender sent via {self.provider_name}")
    
    def test_04_use_test_method(self):
        """Test the built-in test() method."""
        result = self.email.test()
        self.assertTrue(result, f"Failed to send test email via {self.provider_name}")
        print(f"✓ Test email sent using test() method via {self.provider_name}")

if __name__ == '__main__':
    unittest.main()