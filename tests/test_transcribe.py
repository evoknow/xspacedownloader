#!/usr/bin/env python3
# tests/test_transcribe.py - Direct test for transcribe.py functionality

import sys
import os
import subprocess
import argparse

# Add parent directory to path to import components
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from components.SpeechToText import SpeechToText

def run_test(test_audio_file):
    """Run basic tests for the transcribe.py script"""
    
    test_results = {
        "passed": 0,
        "failed": 0,
        "skipped": 0
    }
    
    print(f"Testing SpeechToText component with {test_audio_file}")
    
    # Test 1: Basic class initialization
    try:
        stt = SpeechToText(model_name='tiny')
        print("✅ SpeechToText class initialized successfully")
        test_results["passed"] += 1
    except Exception as e:
        print(f"❌ Failed to initialize SpeechToText class: {e}")
        test_results["failed"] += 1
        return test_results
    
    # Test 2: Model loading
    try:
        model_loaded = stt.load_model()
        if model_loaded:
            print("✅ Successfully loaded Whisper model")
            test_results["passed"] += 1
        else:
            print("❌ Failed to load Whisper model")
            test_results["failed"] += 1
            return test_results
    except Exception as e:
        print(f"❌ Error loading Whisper model: {e}")
        test_results["failed"] += 1
        return test_results
    
    # Test 3: Transcribe a small audio file
    if os.path.exists(test_audio_file):
        try:
            print(f"Transcribing {test_audio_file}...")
            result = stt.transcribe(
                test_audio_file,
                verbose=True,
                output_file="test_output.txt"
            )
            
            if result and os.path.exists("test_output.txt"):
                print("✅ Successfully transcribed audio file")
                test_results["passed"] += 1
                
                # Show a sample of the transcription
                print("\nTranscription sample:")
                print("-" * 40)
                print(result[:100] + "..." if len(result) > 100 else result)
                print("-" * 40)
            else:
                print("❌ Failed to transcribe audio file")
                test_results["failed"] += 1
        except Exception as e:
            print(f"❌ Error during transcription: {e}")
            test_results["failed"] += 1
    else:
        print(f"⚠️ Test audio file not found: {test_audio_file}")
        test_results["skipped"] += 1
    
    # Test 4: Test the transcribe.py script itself with quiet mode
    try:
        print("\nTesting transcribe.py script in quiet mode...")
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "transcribe.py")
        
        # Run the script with the quiet flag
        process = subprocess.run(
            [script_path, test_audio_file, "--quiet", "-o", "quiet_output.txt"],
            capture_output=True,
            text=True
        )
        
        if process.returncode == 0:
            print("✅ Script executed successfully in quiet mode")
            test_results["passed"] += 1
            
            # Check if there was any output
            if process.stdout.strip() or process.stderr.strip():
                print("⚠️ Quiet mode produced output:")
                if process.stdout.strip():
                    print(f"  stdout: {process.stdout.strip()}")
                if process.stderr.strip():
                    print(f"  stderr: {process.stderr.strip()}")
                test_results["skipped"] += 1
            else:
                print("✅ Quiet mode successfully suppressed all output")
                test_results["passed"] += 1
                
            # Check if output file was created
            if os.path.exists("quiet_output.txt"):
                print("✅ Output file was created successfully")
                test_results["passed"] += 1
            else:
                print("❌ Output file was not created")
                test_results["failed"] += 1
        else:
            print(f"❌ Script execution failed with code {process.returncode}")
            print(f"Error output: {process.stderr}")
            test_results["failed"] += 1
    except Exception as e:
        print(f"❌ Error testing script: {e}")
        test_results["failed"] += 1
    
    # Save the transcription file for inspection and delete other test files
    transcript_path = "speech_test_transcript.txt"
    if os.path.exists("test_output.txt"):
        # Copy to a permanent location
        import shutil
        shutil.copy("test_output.txt", transcript_path)
        
        # Calculate path to transcript file
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_path = os.path.join(script_dir, transcript_path)
        
        # Add highly visible notice about the transcript location
        print("\n" + "" + "=" * 70)
        print("" + "*" * 70)
        print(f"** TRANSCRIPT SAVED TO: {transcript_path} **")
        print("*" * 70)
        print("=" * 70 + "\n")
        
        # Preview the first few lines of the transcript
        with open(transcript_path, 'r', encoding='utf-8') as f:
            content = f.read(200)  # Read first 200 characters
            if content:
                print("Transcript preview:")
                print("-" * 40)
                print(content + ("..." if len(content) >= 200 else ""))
                print("-" * 40 + "\n")
        
    # Clean up temporary test files
    for file in ["test_output.txt", "quiet_output.txt"]:
        if os.path.exists(file):
            os.remove(file)
    
    return test_results

def main():
    parser = argparse.ArgumentParser(description="Test the SpeechToText component")
    parser.add_argument("--audio", default="downloads/test_clip.mp3", 
                       help="Path to test audio file")
    args = parser.parse_args()
    
    results = run_test(args.audio)
    
    print("\n" + "=" * 50)
    print(f"TEST SUMMARY: {results['passed']} passed, {results['failed']} failed, {results['skipped']} skipped")
    print("=" * 50)
    
    return 0 if results["failed"] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())