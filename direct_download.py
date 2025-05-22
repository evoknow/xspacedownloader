#!/usr/bin/env python3
# direct_download.py - Directly download a space using yt-dlp

import sys
import os
import subprocess
import shutil
import argparse
from pathlib import Path

def main():
    """
    Directly download a space using yt-dlp without going through the database.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Directly download a space using yt-dlp')
    parser.add_argument('url', help='The URL of the space to download')
    parser.add_argument('--output', '-o', help='Output filename', default=None)
    parser.add_argument('--format', '-f', help='Audio format (mp3, wav, etc.)', default='mp3')
    args = parser.parse_args()
    
    # Ensure downloads directory exists
    downloads_dir = Path(os.path.dirname(os.path.abspath(__file__))) / "downloads"
    downloads_dir.mkdir(exist_ok=True)
    
    # Create default output filename if not provided
    if args.output:
        output_file = downloads_dir / args.output
        if not str(output_file).endswith(f".{args.format}"):
            output_file = Path(f"{output_file}.{args.format}")
    else:
        # Extract space ID from URL
        import re
        pattern = r'spaces/([a-zA-Z0-9]+)(?:\?|$)'
        match = re.search(pattern, args.url)
        space_id = match.group(1) if match else "unknown"
        output_file = downloads_dir / f"{space_id}.{args.format}"
    
    print(f"Space URL: {args.url}")
    print(f"Output file: {output_file}")
    print(f"Audio format: {args.format}")
    
    # Find yt-dlp
    yt_dlp_path = shutil.which('yt-dlp')
    if not yt_dlp_path:
        print("Error: yt-dlp not found in PATH")
        print("Installing yt-dlp...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp"], check=True)
            yt_dlp_path = shutil.which('yt-dlp')
            if not yt_dlp_path:
                print("Error: Failed to install yt-dlp")
                sys.exit(1)
        except Exception as e:
            print(f"Error installing yt-dlp: {e}")
            sys.exit(1)
    
    print(f"Using yt-dlp at: {yt_dlp_path}")
    
    # Prepare yt-dlp command
    yt_dlp_cmd = [
        yt_dlp_path,
        '-f', 'bestaudio',
        '-o', str(output_file),
        '--extract-audio',
        '--audio-format', args.format,
        '--audio-quality', '0',  # Best quality
        args.url
    ]
    
    print(f"Running command: {' '.join(yt_dlp_cmd)}")
    
    # Run yt-dlp
    try:
        subprocess.run(yt_dlp_cmd, check=True)
        print(f"Download successful! File saved to {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error downloading space: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()