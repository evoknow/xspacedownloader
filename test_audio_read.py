#!/usr/bin/env python3
"""
Test if we can read the audio file that's failing.
"""

import os
import wave
import subprocess

file_path = "./downloads/1OyKAWmLDqyJb.mp3"

print(f"Testing file: {file_path}")
print(f"File exists: {os.path.exists(file_path)}")
print(f"File size: {os.path.getsize(file_path)} bytes")
print(f"File readable: {os.access(file_path, os.R_OK)}")

# Try to get audio info using ffmpeg
try:
    result = subprocess.run([
        'ffprobe', '-v', 'quiet', '-print_format', 'json', 
        '-show_format', '-show_streams', file_path
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        print("FFprobe can read the file successfully")
    else:
        print(f"FFprobe error: {result.stderr}")
except Exception as e:
    print(f"Error running ffprobe: {e}")

# Try to copy a small portion of the file
try:
    with open(file_path, 'rb') as f:
        data = f.read(1024 * 1024)  # Read 1MB
        print(f"Successfully read {len(data)} bytes from file")
except Exception as e:
    print(f"Error reading file: {e}")

# Check if temp directory is writable
temp_dir = "./transcript_jobs/temp"
try:
    test_file = os.path.join(temp_dir, "test_write.txt")
    with open(test_file, 'w') as f:
        f.write("test")
    os.remove(test_file)
    print(f"Temp directory {temp_dir} is writable")
except Exception as e:
    print(f"Error writing to temp directory: {e}")