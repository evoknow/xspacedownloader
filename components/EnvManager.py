#!/usr/bin/env python3
"""Environment variable management component for XSpace Downloader."""

import os
import logging
import shutil
from pathlib import Path

logger = logging.getLogger('webapp')

class EnvManager:
    """Handles reading and writing environment variables to .env files."""
    
    def __init__(self):
        """Initialize EnvManager component."""
        # Primary .env file locations
        self.env_paths = [
            '/var/www/production/xspacedownload.com/website/htdocs/.env',
            '/var/www/production/xspacedownload.com/website/xspacedownloader/.env'
        ]
        
        # Find the active .env file
        self.active_env_path = None
        for path in self.env_paths:
            if os.path.exists(path):
                self.active_env_path = path
                break
        
        if not self.active_env_path:
            # Create .env file in htdocs if none exists
            self.active_env_path = self.env_paths[0]
            self._create_env_file()
    
    def _create_env_file(self):
        """Create a new .env file with basic structure."""
        try:
            os.makedirs(os.path.dirname(self.active_env_path), exist_ok=True)
            
            with open(self.active_env_path, 'w') as f:
                f.write("# XSpace Downloader Environment Configuration\n")
                f.write("# Generated automatically\n\n")
                f.write("# Stripe Configuration\n")
                f.write("STRIPE_PUBLISHABLE_KEY=\n")
                f.write("STRIPE_SECRET_KEY=\n")
                f.write("STRIPE_WEBHOOK_SECRET=\n\n")
            
            # Set proper permissions
            os.chmod(self.active_env_path, 0o640)
            
            logger.info(f"Created new .env file at {self.active_env_path}")
            
        except Exception as e:
            logger.error(f"Error creating .env file: {e}")
            raise
    
    def read_env_file(self):
        """Read all environment variables from .env file."""
        try:
            env_vars = {}
            
            if not os.path.exists(self.active_env_path):
                return env_vars
            
            with open(self.active_env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    
                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue
                    
                    # Parse key=value pairs
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Remove quotes if present
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        
                        env_vars[key] = value
            
            return env_vars
            
        except Exception as e:
            logger.error(f"Error reading .env file: {e}")
            return {}
    
    def get_stripe_config(self):
        """Get current Stripe configuration from .env file."""
        try:
            env_vars = self.read_env_file()
            
            return {
                'publishable_key': env_vars.get('STRIPE_PUBLISHABLE_KEY', ''),
                'secret_key': env_vars.get('STRIPE_SECRET_KEY', ''),
                'webhook_secret': env_vars.get('STRIPE_WEBHOOK_SECRET', ''),
                'has_publishable_key': bool(env_vars.get('STRIPE_PUBLISHABLE_KEY', '').strip()),
                'has_secret_key': bool(env_vars.get('STRIPE_SECRET_KEY', '').strip()),
                'has_webhook_secret': bool(env_vars.get('STRIPE_WEBHOOK_SECRET', '').strip())
            }
            
        except Exception as e:
            logger.error(f"Error getting Stripe config: {e}")
            return {
                'publishable_key': '',
                'secret_key': '',
                'webhook_secret': '',
                'has_publishable_key': False,
                'has_secret_key': False,
                'has_webhook_secret': False
            }
    
    def update_stripe_config(self, publishable_key=None, secret_key=None, webhook_secret=None):
        """Update Stripe configuration in .env file."""
        try:
            # Validate key formats
            if publishable_key and not (publishable_key.startswith('pk_test_') or publishable_key.startswith('pk_live_')):
                return {'error': 'Invalid publishable key format. Must start with pk_test_ or pk_live_'}
            
            if secret_key and not (secret_key.startswith('sk_test_') or secret_key.startswith('sk_live_')):
                return {'error': 'Invalid secret key format. Must start with sk_test_ or sk_live_'}
            
            if webhook_secret and not webhook_secret.startswith('whsec_'):
                return {'error': 'Invalid webhook secret format. Must start with whsec_'}
            
            # Read current .env file
            env_vars = self.read_env_file()
            
            # Update Stripe keys if provided
            if publishable_key is not None:
                env_vars['STRIPE_PUBLISHABLE_KEY'] = publishable_key
            if secret_key is not None:
                env_vars['STRIPE_SECRET_KEY'] = secret_key
            if webhook_secret is not None:
                env_vars['STRIPE_WEBHOOK_SECRET'] = webhook_secret
            
            # Write updated .env file
            self._write_env_file(env_vars)
            
            logger.info("Stripe configuration updated successfully")
            return {'success': True, 'message': 'Stripe configuration updated successfully'}
            
        except Exception as e:
            logger.error(f"Error updating Stripe config: {e}")
            return {'error': str(e)}
    
    def _write_env_file(self, env_vars):
        """Write environment variables to .env file."""
        try:
            # Create backup
            if os.path.exists(self.active_env_path):
                backup_path = f"{self.active_env_path}.backup"
                shutil.copy2(self.active_env_path, backup_path)
            
            # Write new .env file
            with open(self.active_env_path, 'w') as f:
                f.write("# XSpace Downloader Environment Configuration\n")
                f.write("# Updated automatically\n\n")
                
                # Group Stripe variables together
                stripe_vars = {
                    'STRIPE_PUBLISHABLE_KEY': 'Stripe Publishable Key (Frontend)',
                    'STRIPE_SECRET_KEY': 'Stripe Secret Key (Backend)',
                    'STRIPE_WEBHOOK_SECRET': 'Stripe Webhook Secret'
                }
                
                f.write("# Stripe Configuration\n")
                for key, description in stripe_vars.items():
                    value = env_vars.get(key, '')
                    f.write(f"# {description}\n")
                    f.write(f"{key}={value}\n\n")
                
                # Write other variables
                f.write("# Other Configuration\n")
                for key, value in env_vars.items():
                    if key not in stripe_vars:
                        f.write(f"{key}={value}\n")
            
            # Set proper permissions
            os.chmod(self.active_env_path, 0o640)
            
        except Exception as e:
            logger.error(f"Error writing .env file: {e}")
            raise
    
    def get_env_file_path(self):
        """Get the path to the active .env file."""
        return self.active_env_path