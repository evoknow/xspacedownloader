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
            
            # Determine current mode based on active keys
            live_keys_set = bool(env_vars.get('STRIPE_LIVE_PUBLISHABLE_KEY', '').strip() and 
                                env_vars.get('STRIPE_LIVE_SECRET_KEY', '').strip())
            test_keys_set = bool(env_vars.get('STRIPE_TEST_PUBLISHABLE_KEY', '').strip() and 
                                env_vars.get('STRIPE_TEST_SECRET_KEY', '').strip())
            
            # Current mode from env or default to test
            current_mode = env_vars.get('STRIPE_MODE', 'test').lower()
            
            # If mode is set to live but no live keys, fallback to test
            if current_mode == 'live' and not live_keys_set:
                current_mode = 'test'
            
            return {
                'mode': current_mode,
                'test': {
                    'publishable_key': env_vars.get('STRIPE_TEST_PUBLISHABLE_KEY', ''),
                    'secret_key': env_vars.get('STRIPE_TEST_SECRET_KEY', ''),
                    'webhook_secret': env_vars.get('STRIPE_TEST_WEBHOOK_SECRET', ''),
                    'has_publishable_key': bool(env_vars.get('STRIPE_TEST_PUBLISHABLE_KEY', '').strip()),
                    'has_secret_key': bool(env_vars.get('STRIPE_TEST_SECRET_KEY', '').strip()),
                    'has_webhook_secret': bool(env_vars.get('STRIPE_TEST_WEBHOOK_SECRET', '').strip())
                },
                'live': {
                    'publishable_key': env_vars.get('STRIPE_LIVE_PUBLISHABLE_KEY', ''),
                    'secret_key': env_vars.get('STRIPE_LIVE_SECRET_KEY', ''),
                    'webhook_secret': env_vars.get('STRIPE_LIVE_WEBHOOK_SECRET', ''),
                    'has_publishable_key': bool(env_vars.get('STRIPE_LIVE_PUBLISHABLE_KEY', '').strip()),
                    'has_secret_key': bool(env_vars.get('STRIPE_LIVE_SECRET_KEY', '').strip()),
                    'has_webhook_secret': bool(env_vars.get('STRIPE_LIVE_WEBHOOK_SECRET', '').strip())
                },
                # Legacy keys (for backward compatibility)
                'legacy': {
                    'publishable_key': env_vars.get('STRIPE_PUBLISHABLE_KEY', ''),
                    'secret_key': env_vars.get('STRIPE_SECRET_KEY', ''),
                    'webhook_secret': env_vars.get('STRIPE_WEBHOOK_SECRET', ''),
                    'has_publishable_key': bool(env_vars.get('STRIPE_PUBLISHABLE_KEY', '').strip()),
                    'has_secret_key': bool(env_vars.get('STRIPE_SECRET_KEY', '').strip()),
                    'has_webhook_secret': bool(env_vars.get('STRIPE_WEBHOOK_SECRET', '').strip())
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting Stripe config: {e}")
            return {
                'mode': 'test',
                'test': {
                    'publishable_key': '', 'secret_key': '', 'webhook_secret': '',
                    'has_publishable_key': False, 'has_secret_key': False, 'has_webhook_secret': False
                },
                'live': {
                    'publishable_key': '', 'secret_key': '', 'webhook_secret': '',
                    'has_publishable_key': False, 'has_secret_key': False, 'has_webhook_secret': False
                },
                'legacy': {
                    'publishable_key': '', 'secret_key': '', 'webhook_secret': '',
                    'has_publishable_key': False, 'has_secret_key': False, 'has_webhook_secret': False
                }
            }
    
    def update_stripe_config(self, mode=None, test_keys=None, live_keys=None):
        """Update Stripe configuration in .env file."""
        try:
            # Read current .env file - this should have ALL variables
            env_vars = self.read_env_file()
            
            # Critical safety check - ensure we have non-Stripe variables
            critical_keys = ['OPENAI_API_KEY', 'X_API_KEY', 'X_API_KEY_SECRET', 'SENDGRID_API_KEY']
            missing_critical = [key for key in critical_keys if key not in env_vars or not env_vars[key]]
            if missing_critical:
                logger.error(f"CRITICAL: Missing essential API keys in current env: {missing_critical}")
                # Try to read from backup
                backup_files = sorted([f for f in os.listdir(os.path.dirname(self.active_env_path)) 
                                     if f.startswith('.env.backup') or f == '.env.emergency_backup'], reverse=True)
                if backup_files:
                    backup_path = os.path.join(os.path.dirname(self.active_env_path), backup_files[0])
                    logger.info(f"Reading from backup file: {backup_path}")
                    with open(backup_path, 'r') as f:
                        backup_content = f.read()
                    # Parse backup for missing keys
                    for line in backup_content.split('\n'):
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            if key in missing_critical and key not in env_vars:
                                env_vars[key] = value.strip()
                                logger.info(f"Recovered {key} from backup")
            
            # Update mode if provided
            if mode is not None:
                if mode.lower() not in ['test', 'live']:
                    return {'error': 'Invalid mode. Must be "test" or "live"'}
                env_vars['STRIPE_MODE'] = mode.lower()
            
            # Update test keys if provided
            if test_keys:
                if test_keys.get('publishable_key'):
                    key = test_keys['publishable_key'].strip()
                    if key and not key.startswith('pk_test_'):
                        return {'error': 'Test publishable key must start with pk_test_'}
                    env_vars['STRIPE_TEST_PUBLISHABLE_KEY'] = key
                
                if test_keys.get('secret_key'):
                    key = test_keys['secret_key'].strip()
                    if key and not key.startswith('sk_test_'):
                        return {'error': 'Test secret key must start with sk_test_'}
                    env_vars['STRIPE_TEST_SECRET_KEY'] = key
                
                if test_keys.get('webhook_secret'):
                    key = test_keys['webhook_secret'].strip()
                    if key and not key.startswith('whsec_'):
                        return {'error': 'Webhook secret must start with whsec_'}
                    env_vars['STRIPE_TEST_WEBHOOK_SECRET'] = key
            
            # Update live keys if provided
            if live_keys:
                if live_keys.get('publishable_key'):
                    key = live_keys['publishable_key'].strip()
                    if key and not key.startswith('pk_live_'):
                        return {'error': 'Live publishable key must start with pk_live_'}
                    env_vars['STRIPE_LIVE_PUBLISHABLE_KEY'] = key
                
                if live_keys.get('secret_key'):
                    key = live_keys['secret_key'].strip()
                    if key and not key.startswith('sk_live_'):
                        return {'error': 'Live secret key must start with sk_live_'}
                    env_vars['STRIPE_LIVE_SECRET_KEY'] = key
                
                if live_keys.get('webhook_secret'):
                    key = live_keys['webhook_secret'].strip()
                    if key and not key.startswith('whsec_'):
                        return {'error': 'Webhook secret must start with whsec_'}
                    env_vars['STRIPE_LIVE_WEBHOOK_SECRET'] = key
            
            # Write updated .env file
            self._write_env_file(env_vars)
            
            logger.info("Stripe configuration updated successfully")
            return {'success': True, 'message': 'Stripe configuration updated successfully'}
            
        except Exception as e:
            logger.error(f"Error updating Stripe config: {e}")
            return {'error': str(e)}
    
    def _write_env_file(self, env_vars):
        """Write environment variables to .env file - preserving ALL existing variables."""
        try:
            # Create backup with timestamp
            if os.path.exists(self.active_env_path):
                import time
                backup_path = f"{self.active_env_path}.backup.{int(time.time())}"
                shutil.copy2(self.active_env_path, backup_path)
                logger.info(f"Created backup at: {backup_path}")
            
            # Define all Stripe-related keys
            stripe_vars = {
                'STRIPE_MODE', 
                'STRIPE_TEST_PUBLISHABLE_KEY', 
                'STRIPE_TEST_SECRET_KEY', 
                'STRIPE_TEST_WEBHOOK_SECRET',
                'STRIPE_LIVE_PUBLISHABLE_KEY', 
                'STRIPE_LIVE_SECRET_KEY', 
                'STRIPE_LIVE_WEBHOOK_SECRET',
                'STRIPE_PUBLISHABLE_KEY', 
                'STRIPE_SECRET_KEY', 
                'STRIPE_WEBHOOK_SECRET'
            }
            
            # Important: Ensure we have ALL variables, not just Stripe ones
            if not any(key for key in env_vars if key not in stripe_vars):
                logger.error("CRITICAL: Attempting to write .env with only Stripe variables!")
                raise ValueError("Cannot write .env file with only Stripe variables - would lose other API keys")
            
            # Write new .env file
            with open(self.active_env_path, 'w') as f:
                f.write("# XSpace Downloader Environment Configuration\n")
                f.write("# Updated automatically - DO NOT EDIT MANUALLY\n\n")
                
                # Write critical API keys first (if they exist)
                critical_keys = ['OPENAI_API_KEY', 'X_API_KEY', 'X_API_KEY_SECRET', 'SENDGRID_API_KEY', 'PRODUCTION_DIR']
                critical_written = False
                for key in critical_keys:
                    if key in env_vars and env_vars[key]:
                        if not critical_written:
                            f.write("# Critical API Keys\n")
                            critical_written = True
                        f.write(f"{key}={env_vars[key]}\n")
                
                if critical_written:
                    f.write("\n")
                
                # Group Stripe variables together
                f.write("# Stripe Configuration\n")
                f.write(f"STRIPE_MODE={env_vars.get('STRIPE_MODE', 'test')}\n\n")
                
                f.write("# Stripe Test Keys\n")
                test_vars = {
                    'STRIPE_TEST_PUBLISHABLE_KEY': 'Stripe Test Publishable Key',
                    'STRIPE_TEST_SECRET_KEY': 'Stripe Test Secret Key',
                    'STRIPE_TEST_WEBHOOK_SECRET': 'Stripe Test Webhook Secret'
                }
                for key, description in test_vars.items():
                    value = env_vars.get(key, '')
                    if value:  # Only write if not empty
                        f.write(f"# {description}\n")
                        f.write(f"{key}={value}\n")
                if any(env_vars.get(key) for key in test_vars):
                    f.write("\n")
                
                f.write("# Stripe Live Keys\n")
                live_vars = {
                    'STRIPE_LIVE_PUBLISHABLE_KEY': 'Stripe Live Publishable Key',
                    'STRIPE_LIVE_SECRET_KEY': 'Stripe Live Secret Key',
                    'STRIPE_LIVE_WEBHOOK_SECRET': 'Stripe Live Webhook Secret'
                }
                for key, description in live_vars.items():
                    value = env_vars.get(key, '')
                    if value:  # Only write if not empty
                        f.write(f"# {description}\n")
                        f.write(f"{key}={value}\n")
                if any(env_vars.get(key) for key in live_vars):
                    f.write("\n")
                
                # Legacy keys for backward compatibility
                legacy_written = False
                legacy_vars = {
                    'STRIPE_PUBLISHABLE_KEY': 'Legacy Stripe Publishable Key',
                    'STRIPE_SECRET_KEY': 'Legacy Stripe Secret Key',
                    'STRIPE_WEBHOOK_SECRET': 'Legacy Stripe Webhook Secret'
                }
                for key, description in legacy_vars.items():
                    value = env_vars.get(key, '')
                    if value:  # Only write legacy keys if they exist
                        if not legacy_written:
                            f.write("# Legacy Stripe Keys (for backward compatibility)\n")
                            legacy_written = True
                        f.write(f"# {description}\n")
                        f.write(f"{key}={value}\n")
                if legacy_written:
                    f.write("\n")
                
                # Write any other variables that aren't Stripe or critical
                other_vars = []
                all_handled = stripe_vars.union(set(critical_keys))
                for key, value in sorted(env_vars.items()):
                    if key not in all_handled and value:
                        other_vars.append((key, value))
                
                if other_vars:
                    f.write("# Other Configuration\n")
                    for key, value in other_vars:
                        f.write(f"{key}={value}\n")
            
            # Set proper permissions
            os.chmod(self.active_env_path, 0o640)
            logger.info("Successfully wrote .env file with all variables preserved")
            
        except Exception as e:
            logger.error(f"Error writing .env file: {e}")
            # Try to restore from backup
            backup_files = sorted([f for f in os.listdir(os.path.dirname(self.active_env_path)) 
                                 if f.startswith('.env.backup.')], reverse=True)
            if backup_files:
                latest_backup = os.path.join(os.path.dirname(self.active_env_path), backup_files[0])
                logger.info(f"Attempting to restore from backup: {latest_backup}")
                shutil.copy2(latest_backup, self.active_env_path)
            raise
    
    def get_env_file_path(self):
        """Get the path to the active .env file."""
        return self.active_env_path