#!/usr/bin/env python3
# test_audio_processing.py - Test script for audio processing methods in Space component

import os
import sys
import time
import argparse
from pathlib import Path
from components.Space import Space

# Ensure required directories exist
downloads_dir = Path(__file__).parent / "downloads"
downloads_dir.mkdir(exist_ok=True)

def print_section(text):
    """Print a section header with formatting."""
    print("\n" + "=" * 80)
    print(f" {text}")
    print("=" * 80)

def test_remove_leading_white_noise(space_id, threshold='-50dB', min_duration=1.0):
    """Test the removeLeadingWhiteNoise method."""
    print_section("Testing removeLeadingWhiteNoise")
    
    # Create Space instance
    space = Space()
    
    # List available files in downloads directory 
    available_files = list(downloads_dir.glob('*.*'))
    print(f"Looking for audio files in: {downloads_dir}")
    if not available_files:
        print("ERROR: Downloads directory is empty! No audio files found.")
        print("You must first download a space before testing audio processing.")
        print("Use one of these methods:")
        print("  1. Run the daemon test: ./test.sh daemon")
        print("  2. Run the add_test_space.py script and then the bg_downloader.py daemon")
        sys.exit(1)
    
    print(f"Available files in downloads directory:")
    for file in available_files:
        print(f"  - {file.name}")
    
    # Check if file exists
    file_path = space._get_audio_file_path(space_id)
    if not file_path:
        print(f"ERROR: Audio file for space {space_id} not found")
        print(f"The downloads directory ({downloads_dir}) does not contain any file matching space_id: {space_id}")
        print("Please download this space first using:")
        print(f"  1. Run the daemon test: ./test.sh daemon")
        print(f"  2. Or: ./add_test_space.py and then ./bg_downloader.py --no-daemon")
        return False
        
    print(f"Found audio file: {file_path}")
    
    # Get file size before
    size_before = os.path.getsize(file_path)
    print(f"File size before: {size_before} bytes")
    
    # Get file duration before
    try:
        import subprocess
        duration_cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(file_path)
        ]
        duration_before = float(subprocess.check_output(duration_cmd).decode('utf-8').strip())
        print(f"File duration before: {duration_before:.2f} seconds")
    except Exception as e:
        print(f"Warning: Could not get file duration: {e}")
        duration_before = None
    
    # Perform the noise removal
    print(f"Removing leading silence with threshold={threshold}, min_duration={min_duration}")
    print(f"Threshold type: {type(threshold)}, Min duration type: {type(min_duration)}")
    result = space.removeLeadingWhiteNoise(space_id, threshold, min_duration)
    
    # Check result
    if result:
        print("Successfully processed the file")
        
        # Get file size after
        size_after = os.path.getsize(file_path)
        print(f"File size after: {size_after} bytes")
        print(f"Size difference: {size_before - size_after} bytes")
        
        # Get file duration after
        if duration_before is not None:
            try:
                duration_after = float(subprocess.check_output(duration_cmd).decode('utf-8').strip())
                print(f"File duration after: {duration_after:.2f} seconds")
                print(f"Duration difference: {duration_before - duration_after:.2f} seconds")
            except Exception as e:
                print(f"Warning: Could not get file duration: {e}")
        
        return True
    else:
        print("Failed to process the file")
        return False
        
def test_clip(space_id, start_time, end_time, clip_name=None):
    """Test the clip method."""
    print_section("Testing clip")
    
    # Create Space instance
    space = Space()
    
    # List available files in downloads directory
    available_files = list(downloads_dir.glob('*.*'))
    print(f"Looking for audio files in: {downloads_dir}")
    if not available_files:
        print("ERROR: Downloads directory is empty! No audio files found.")
        print("You must first download a space before testing audio processing.")
        print("Use one of these methods:")
        print("  1. Run the daemon test: ./test.sh daemon")
        print("  2. Run the add_test_space.py script and then the bg_downloader.py daemon")
        sys.exit(1)
    
    print(f"Available files in downloads directory:")
    for file in available_files:
        print(f"  - {file.name}")
    
    # Check if file exists
    file_path = space._get_audio_file_path(space_id)
    if not file_path:
        print(f"ERROR: Audio file for space {space_id} not found")
        print(f"The downloads directory ({downloads_dir}) does not contain any file matching space_id: {space_id}")
        print("Please download this space first using:")
        print(f"  1. Run the daemon test: ./test.sh daemon")
        print(f"  2. Or: ./add_test_space.py and then ./bg_downloader.py --no-daemon")
        return False
        
    print(f"Found audio file: {file_path}")
    
    # Get file duration before
    try:
        import subprocess
        duration_cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(file_path)
        ]
        total_duration = float(subprocess.check_output(duration_cmd).decode('utf-8').strip())
        print(f"Original file duration: {total_duration:.2f} seconds")
    except Exception as e:
        print(f"Warning: Could not get file duration: {e}")
        total_duration = None
    
    # Create the clip
    print(f"Creating clip from {start_time} to {end_time}")
    result = space.clip(space_id, start_time, end_time, clip_name)
    
    # Check result
    if result:
        print(f"Successfully created clip: {result}")
        
        # Get clip duration
        if total_duration is not None:
            try:
                clip_duration_cmd = [
                    'ffprobe',
                    '-v', 'error',
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    result
                ]
                clip_duration = float(subprocess.check_output(clip_duration_cmd).decode('utf-8').strip())
                print(f"Clip duration: {clip_duration:.2f} seconds")
                
                # Calculate expected duration
                # Convert start and end times to seconds if they are strings
                def parse_time(time_str):
                    if isinstance(time_str, str) and ':' in time_str:
                        parts = time_str.split(':')
                        if len(parts) == 3:  # HH:MM:SS
                            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                        elif len(parts) == 2:  # MM:SS
                            return float(parts[0]) * 60 + float(parts[1])
                    return float(time_str)
                
                start_seconds = parse_time(start_time)
                end_seconds = parse_time(end_time)
                expected_duration = end_seconds - start_seconds
                
                print(f"Expected clip duration: {expected_duration:.2f} seconds")
                print(f"Actual vs Expected difference: {clip_duration - expected_duration:.2f} seconds")
                
            except Exception as e:
                print(f"Warning: Could not get clip duration: {e}")
        
        return True
    else:
        print("Failed to create the clip")
        return False

def main():
    """Main function to run the tests."""
    parser = argparse.ArgumentParser(description='Test audio processing methods in Space component')
    parser.add_argument('space_id', help='Space ID to test with')
    parser.add_argument('--test', choices=['noise', 'clip', 'all'], default='all',
                       help='Test to run: noise (removeLeadingWhiteNoise), clip, or all')
    parser.add_argument('--start', default='30',
                       help='Start time for clip test (in seconds or HH:MM:SS format)')
    parser.add_argument('--end', default='60',
                       help='End time for clip test (in seconds or HH:MM:SS format)')
    parser.add_argument('--clip-name', help='Custom name for the clip output file')
    parser.add_argument('--threshold', default='-50dB', type=str,
                       help='Silence threshold for noise removal (default: -50dB)')
    parser.add_argument('--min-duration', type=float, default=1.0,
                       help='Minimum silence duration for noise removal (default: 1.0)')
    
    # Print all arguments for debugging
    print(f"Command line arguments:")
    import sys
    print(f"  {' '.join(sys.argv)}")
                       
    args = parser.parse_args()
    
    # Check if space_id exists in the database
    space = Space()
    space_details = space.get_space(args.space_id)
    if not space_details:
        print(f"Warning: Space {args.space_id} not found in the database")
        print("The test will continue if an audio file with this ID exists in the downloads directory")
    
    # Run the requested tests
    if args.test in ['noise', 'all']:
        test_remove_leading_white_noise(args.space_id, args.threshold, args.min_duration)
    
    if args.test in ['clip', 'all']:
        test_clip(args.space_id, args.start, args.end, args.clip_name)
    
    print("\nTests completed!")

if __name__ == "__main__":
    main()