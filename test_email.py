#!/usr/bin/env python3

import sys
import os
import json
import subprocess
import importlib.util

# Add parent directory to path for importing components
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Check if running in virtual environment
in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)

if not in_venv:
    venv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv")
    
    # Create virtual environment if it doesn't exist
    if not os.path.exists(venv_path):
        print("Creating virtual environment...")
        subprocess.call([sys.executable, "-m", "venv", venv_path])
    
    # Get the path to the virtual environment's Python interpreter
    if sys.platform == 'win32':
        venv_python = os.path.join(venv_path, "Scripts", "python.exe")
    else:
        venv_python = os.path.join(venv_path, "bin", "python")
    
    # Install requests in the virtual environment if not already installed
    subprocess.call([venv_python, "-m", "pip", "install", "requests"])
    
    # Re-run this script using the virtual environment's Python interpreter
    print(f"Restarting script in virtual environment...")
    os.execv(venv_python, [venv_python] + sys.argv)
    sys.exit(0)

# Import after virtual environment setup
from components.Email import Email

def main():
    print("Testing Email Component...")
    
    # Create Email component
    email = Email()
    
    # Print email configuration for debugging
    print(f"Email config: {email.email_config}")
    if email.email_config and 'testers' in email.email_config:
        print(f"Testers field type: {type(email.email_config['testers'])}")
        print(f"Testers: {email.email_config['testers']}")
    
    # Test sending to default testers
    print("\nTesting with default testers...")
    try:
        if email.test():
            print("Test email sent successfully to default testers!")
        else:
            print("Failed to send test email to default testers.")
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()
    
    # Test with custom recipient if provided
    if len(sys.argv) > 1:
        test_recipient = sys.argv[1]
        print(f"\nTesting with custom recipient: {test_recipient}...")
        
        # Send test email
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S")
        date_str = now.strftime("%Y-%m-%d")
        
        subject = f"Custom recipient test {time_str} {date_str}"
        body = f"<h1>This is a test email</h1><p>Hello from the XSpace Downloader application!</p>"
        
        if email.send(to=test_recipient, subject=subject, body=body):
            print(f"Test email sent successfully to {test_recipient}!")
        else:
            print(f"Failed to send test email to {test_recipient}.")
    
    print("\nEmail test completed.")

if __name__ == "__main__":
    # Add parent directory to path for importing components
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    try:
        from datetime import datetime
        main()
    except Exception as e:
        print(f"Error testing email: {e}")
        sys.exit(1)