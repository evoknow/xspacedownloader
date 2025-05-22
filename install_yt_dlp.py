#!/usr/bin/env python3
# install_yt_dlp.py - Install and verify yt-dlp installation

import sys
import subprocess
import shutil
import os

def main():
    """Install and verify yt-dlp installation."""
    print("XSpace Downloader - yt-dlp Installer and Verifier")
    print("------------------------------------------------")
    
    # Check if yt-dlp is already installed
    yt_dlp_path = shutil.which('yt-dlp')
    if yt_dlp_path:
        print(f"yt-dlp is already installed at: {yt_dlp_path}")
    else:
        print("yt-dlp not found in PATH. Installing now...")
        
        try:
            # Install yt-dlp using pip
            subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp"], check=True)
            print("yt-dlp installation successful")
            
            # Check again for yt-dlp
            yt_dlp_path = shutil.which('yt-dlp')
            if yt_dlp_path:
                print(f"yt-dlp is now installed at: {yt_dlp_path}")
            else:
                # Try to find yt-dlp in the Python scripts directory
                scripts_dir = os.path.join(os.path.dirname(sys.executable), 'Scripts')  # For Windows
                if not os.path.exists(scripts_dir):
                    scripts_dir = os.path.join(os.path.dirname(sys.executable), 'bin')  # For Unix
                
                if os.path.exists(scripts_dir):
                    for file in os.listdir(scripts_dir):
                        if file == 'yt-dlp' or file == 'yt-dlp.exe':
                            yt_dlp_path = os.path.join(scripts_dir, file)
                            print(f"Found yt-dlp at: {yt_dlp_path}")
                            break
                
                if not yt_dlp_path:
                    raise Exception("yt-dlp still not found after installation")
        except Exception as e:
            print(f"Error installing yt-dlp: {e}")
            sys.exit(1)
    
    # Create a simple wrapper script for yt-dlp to debug issues
    wrapper_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'yt-dlp-wrapper.sh')
    with open(wrapper_path, 'w') as f:
        f.write(f"""#!/bin/bash
# yt-dlp-wrapper.sh - Wrapper script for yt-dlp to debug issues

echo "yt-dlp wrapper script - arguments: $@"
echo "PATH: $PATH"
echo "Python executable: {sys.executable}"

# Find yt-dlp
YT_DLP="{yt_dlp_path}"

if [ ! -f "$YT_DLP" ]; then
    echo "Error: yt-dlp not found at $YT_DLP"
    exit 1
fi

echo "Using yt-dlp at: $YT_DLP"
echo "-------------------------------------"

# Execute yt-dlp with all arguments
"$YT_DLP" "$@"
""")
    os.chmod(wrapper_path, 0o755)  # Make executable
    
    print(f"Created wrapper script at: {wrapper_path}")
    print("This script can be used to debug yt-dlp issues.")
    print(f"Example usage: {wrapper_path} -f bestaudio URL")
    
    # Test yt-dlp version
    try:
        print("\nChecking yt-dlp version...")
        result = subprocess.run([yt_dlp_path, '--version'], capture_output=True, text=True)
        print(f"yt-dlp version: {result.stdout.strip()}")
    except Exception as e:
        print(f"Error checking yt-dlp version: {e}")
        sys.exit(1)
    
    print("\nyt-dlp is successfully installed and verified.")
    print("You can now use the background downloader to download spaces.")

if __name__ == "__main__":
    main()