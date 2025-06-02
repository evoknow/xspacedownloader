#!/usr/bin/env python3
"""
XSpace Downloader - Update Script

This script automates the deployment of code updates from the git repository
to the production environment. It pulls the latest code and syncs it to the
production directory specified in the .env file.

Usage:
    ./update.py [--dry-run] [--restart-services] [--backup]

Options:
    --dry-run          Show what would be done without making changes
    --restart-services Restart services after update (default: true)
    --no-restart-services Skip restarting services after update
    --backup          Create backup before update (default: false)
    --force           Force update even if working directory is not clean

Examples:
    ./update.py                    # Basic update
    ./update.py --dry-run          # Preview changes
    ./update.py # Update and restart services (default)
    ./update.py --no-restart-services # Update without restarting services
    ./update.py --backup           # Create backup before update
"""

import os
import sys
import argparse
import subprocess
import shutil
import json
from pathlib import Path
from datetime import datetime

class UpdateManager:
    def __init__(self, args):
        self.dry_run = args.dry_run
        # Restart services by default unless explicitly disabled
        self.restart_services_enabled = not args.no_restart_services
        self.backup_enabled = args.backup
        self.force = args.force
        
        # Get current directory (should be the git repo)
        self.repo_dir = Path(__file__).parent.absolute()
        
        # Load configuration
        self.load_config()
        
    def load_config(self):
        """Load configuration from .env file."""
        print("Loading configuration...")
        
        # Try to load from current directory first
        env_file = self.repo_dir / '.env'
        if not env_file.exists():
            # If not found, check if we can determine it from git repo
            print(f".env file not found in {self.repo_dir}")
            print("Please ensure the .env file exists with PRODUCTION_DIR configured")
            sys.exit(1)
        
        # Load environment variables from .env file
        self.env_vars = {}
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        self.env_vars[key.strip()] = value.strip()
        except Exception as e:
            print(f"Error reading .env file: {e}")
            sys.exit(1)
        
        # Get production directory
        self.production_dir = Path(self.env_vars.get('PRODUCTION_DIR', ''))
        if not self.production_dir or not self.production_dir.exists():
            print(f"PRODUCTION_DIR not found or invalid: {self.production_dir}")
            print("Please set PRODUCTION_DIR in .env file")
            sys.exit(1)
        
        # Get other config
        self.nginx_user = self.env_vars.get('NGINX_USER', 'nginx')
        
        print(f"Repository: {self.repo_dir}")
        print(f"Production: {self.production_dir}")
        print(f"Nginx User: {self.nginx_user}")
        
    def run_command(self, cmd, shell=False, check=True, cwd=None):
        """Execute a command, respecting dry-run mode."""
        if self.dry_run:
            print(f"[DRY RUN] Would execute: {cmd}")
            return None
        
        try:
            result = subprocess.run(
                cmd, 
                shell=shell, 
                check=check, 
                capture_output=True, 
                text=True,
                cwd=cwd or self.repo_dir
            )
            
            if result.stdout:
                print(result.stdout.strip())
            if result.stderr:
                print(result.stderr.strip(), file=sys.stderr)
                
            return result
        except subprocess.CalledProcessError as e:
            print(f"Error executing command: {e}")
            if e.stdout:
                print(f"stdout: {e.stdout}")
            if e.stderr:
                print(f"stderr: {e.stderr}")
            raise
    
    def check_git_status(self):
        """Check git repository status."""
        print("\n=== Checking git repository status ===")
        
        # Check if we're in a git repository
        if not (self.repo_dir / '.git').exists():
            print("Error: Current directory is not a git repository")
            sys.exit(1)
        
        # Check for uncommitted changes
        result = self.run_command(['git', 'status', '--porcelain'])
        if result and result.stdout.strip():
            print("Warning: Working directory has uncommitted changes:")
            print(result.stdout)
            if not self.force:
                print("Use --force to proceed anyway, or commit your changes first")
                sys.exit(1)
        
        # Get current branch
        result = self.run_command(['git', 'branch', '--show-current'])
        if result:
            current_branch = result.stdout.strip()
            print(f"Current branch: {current_branch}")
        
        return True
    
    def pull_latest_code(self):
        """Pull the latest code from remote repository."""
        print("\n=== Pulling latest code ===")
        
        # Fetch latest changes
        self.run_command(['git', 'fetch', 'origin'])
        
        # Pull latest changes
        self.run_command(['git', 'pull', 'origin', 'main'])
        
        # Show latest commit
        result = self.run_command(['git', 'log', '--oneline', '-1'])
        if result:
            print(f"Latest commit: {result.stdout.strip()}")
    
    def create_backup(self):
        """Create backup of production directory."""
        if not self.create_backup:
            return
            
        print("\n=== Creating backup ===")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.production_dir.parent / f"backup_{self.production_dir.name}_{timestamp}"
        
        if self.dry_run:
            print(f"[DRY RUN] Would create backup: {backup_dir}")
        else:
            print(f"Creating backup: {backup_dir}")
            shutil.copytree(self.production_dir, backup_dir, symlinks=True)
            print(f"Backup created successfully")
    
    def sync_code(self):
        """Sync code from repository to production directory."""
        print("\n=== Syncing code to production ===")
        
        # Define excludes
        excludes = [
            '--exclude=venv/',
            '--exclude=.git/',
            '--exclude=*.pyc',
            '--exclude=__pycache__/',
            '--exclude=.pytest_cache/',
            '--exclude=.coverage',
            '--exclude=*.log',
            '--exclude=downloads/',
            '--exclude=transcript_jobs/',
            '--exclude=logs/',
        ]
        
        # Prepare rsync command
        rsync_cmd = [
            'rsync', 
            '-av', 
            '--delete',  # Delete files in destination that don't exist in source
        ] + excludes + [
            f"{self.repo_dir}/",  # Source (note the trailing slash)
            f"{self.production_dir}/"  # Destination
        ]
        
        print(f"Syncing from {self.repo_dir} to {self.production_dir}")
        self.run_command(rsync_cmd)
        
        # Set ownership
        print(f"Setting ownership to {self.nginx_user}:{self.nginx_user}")
        self.run_command([
            'chown', '-R', 
            f'{self.nginx_user}:{self.nginx_user}', 
            str(self.production_dir)
        ])
        
        # Ensure logs directory exists with proper permissions
        logs_dir = self.production_dir / 'logs'
        if self.dry_run:
            print(f"[DRY RUN] Would ensure logs directory exists: {logs_dir}")
        else:
            logs_dir.mkdir(exist_ok=True)
            self.run_command([
                'chown', 
                f'{self.nginx_user}:{self.nginx_user}', 
                str(logs_dir)
            ])
        
        # Set secure permissions on .env file
        env_file = self.production_dir / '.env'
        if env_file.exists():
            self.run_command(['chmod', '640', str(env_file)])
            print("Set .env file permissions to 640")
    
    def restart_services(self):
        """Restart application services."""
        if not self.restart_services_enabled:
            return
            
        print("\n=== Restarting services ===")
        
        services = [
            'xspacedownloader-gunicorn',
            'xspacedownloader-transcribe'
        ]
        
        for service in services:
            print(f"Restarting {service}...")
            self.run_command(['systemctl', 'restart', service])
            
            # Check service status
            result = self.run_command(['systemctl', 'is-active', service], check=False)
            if result and result.stdout.strip() == 'active':
                print(f"✓ {service} is running")
            else:
                print(f"✗ {service} failed to start")
        
        # Handle bg_downloader manually
        print("\n=== Restarting background downloader (manual) ===")
        
        # Kill existing bg_downloader processes
        print("Stopping existing bg_downloader processes...")
        self.run_command(['pkill', '-f', 'bg_downloader.py'], check=False)
        
        # Wait a moment for processes to stop
        import time
        time.sleep(2)
        
        # Start bg_downloader manually
        print("Starting bg_downloader...")
        bg_cmd = [
            'sudo', '-u', self.nginx_user, 'nohup',
            f'{self.production_dir}/venv/bin/python',
            f'{self.production_dir}/bg_downloader.py'
        ]
        
        if self.dry_run:
            print(f"[DRY RUN] Would execute: {' '.join(bg_cmd)} > /dev/null 2>&1 &")
        else:
            # Use subprocess to start in background
            subprocess.Popen(
                bg_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=self.production_dir
            )
            
            # Check if it started
            time.sleep(3)
            result = self.run_command(['pgrep', '-f', 'bg_downloader.py'], check=False)
            if result and result.stdout.strip():
                print(f"✓ bg_downloader is running (PID: {result.stdout.strip()})")
            else:
                print("✗ bg_downloader failed to start")
    
    def update(self):
        """Run the complete update process."""
        print("XSpace Downloader Update Script")
        print("==============================")
        print(f"Dry Run: {self.dry_run}")
        print(f"Restart Services: {self.restart_services_enabled}")
        print(f"Create Backup: {self.backup_enabled}")
        
        if not self.dry_run:
            # Check if running as root
            if os.geteuid() != 0:
                print("\nERROR: This script must be run as root (use sudo)")
                sys.exit(1)
        
        # Check git status
        self.check_git_status()
        
        # Create backup if requested
        if self.backup_enabled:
            self.create_backup()
        
        # Pull latest code
        self.pull_latest_code()
        
        # Sync code to production
        self.sync_code()
        
        # Restart services if requested
        if self.restart_services_enabled:
            self.restart_services()
        
        print("\n=== Update completed successfully! ===")
        if not self.restart_services_enabled:
            print("\nRemember to restart services if needed:")
            print("  sudo systemctl restart xspacedownloader-gunicorn")
            print("  sudo systemctl restart xspacedownloader-bg")
            print("  sudo systemctl restart xspacedownloader-transcribe")


def main():
    parser = argparse.ArgumentParser(
        description='Update XSpace Downloader production deployment',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sudo ./update.py                    # Basic update
  sudo ./update.py --dry-run          # Preview changes
  sudo ./update.py                     # Update and restart services (default)
  sudo ./update.py --no-restart-services # Update without restarting services
  sudo ./update.py --backup           # Create backup before update
        """
    )
    
    parser.add_argument('--dry-run',
                        action='store_true',
                        help='Show what would be done without making changes')
    
    parser.add_argument('--no-restart-services',
                        action='store_true',
                        help='Skip restarting services after update')
    
    parser.add_argument('--restart-services',
                        action='store_true',
                        help='Restart services after update (default: true)')
    
    parser.add_argument('--backup',
                        action='store_true', 
                        help='Create backup before update')
    
    parser.add_argument('--force',
                        action='store_true',
                        help='Force update even if working directory is not clean')
    
    args = parser.parse_args()
    
    # Create updater and run
    updater = UpdateManager(args)
    updater.update()


if __name__ == '__main__':
    main()