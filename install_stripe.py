#!/usr/bin/env python3
"""
Install Stripe dependency for payment processing.
"""

import subprocess
import sys
import os

def main():
    """Install Stripe package in production environment."""
    try:
        # Change to htdocs directory
        htdocs_dir = "/var/www/production/xspacedownload.com/website/htdocs"
        os.chdir(htdocs_dir)
        
        # Activate virtual environment and install stripe
        cmd = ["venv/bin/pip", "install", "stripe>=7.0.0"]
        
        print("Installing Stripe package...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✓ Stripe package installed successfully")
            print(result.stdout)
        else:
            print("✗ Failed to install Stripe package")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return 1
            
        return 0
        
    except Exception as e:
        print(f"Error installing Stripe: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())