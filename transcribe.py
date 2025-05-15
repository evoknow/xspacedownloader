#!/usr/bin/env python3
# transcribe.py - Transcribe an audio file to text using the SpeechToText component

import argparse
import logging
import os
import sys
from pathlib import Path
from components.SpeechToText import SpeechToText

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("transcribe")

def main():
    """Main function to handle command-line arguments and transcribe an audio file."""
    parser = argparse.ArgumentParser(
        description="Transcribe an audio file to text using Whisper AI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Add required arguments
    parser.add_argument("audio_file", help="Path to the audio file to transcribe")
    
    # Add optional arguments
    parser.add_argument("--output", "-o", help="Path to save the transcription output")
    parser.add_argument("--format", "-f", choices=["txt", "json", "vtt", "srt"], default="txt",
                       help="Output format (txt, json, vtt, srt)")
    parser.add_argument("--model", "-m", default="base",
                       choices=["tiny", "base", "small", "medium", "large"],
                       help="Whisper model to use")
    parser.add_argument("--language", "-l", help="Language code (e.g., 'en', 'fr'). Auto-detected if not specified.")
    parser.add_argument("--task", "-t", choices=["transcribe", "translate"], default="transcribe",
                       help="Task to perform (transcribe or translate to English)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print verbose output")
    parser.add_argument("--batch", "-b", action="store_true", 
                       help="Treat audio_file as a directory and transcribe all audio files")
    
    args = parser.parse_args()
    
    # Create the SpeechToText component
    stt = SpeechToText(model_name=args.model)
    
    # If we're doing batch processing
    if args.batch:
        if not os.path.isdir(args.audio_file):
            logger.error(f"Batch mode requires a directory: {args.audio_file} is not a directory")
            return 1
            
        # Use batch_transcribe method
        output_dir = args.output if args.output else None
        results = stt.batch_transcribe(
            args.audio_file,
            output_directory=output_dir,
            language=args.language,
            recursive=True
        )
        
        # Print summary of results
        logger.info(f"Batch transcription completed. Processed {len(results)} files.")
        return 0
        
    # Otherwise, transcribe a single file
    else:
        if not os.path.isfile(args.audio_file):
            logger.error(f"Audio file not found: {args.audio_file}")
            return 1
            
        # Determine output file path
        output_file = None
        if args.output:
            output_file = args.output
        
        # Transcribe the audio file
        result = stt.transcribe(
            args.audio_file,
            language=args.language,
            task=args.task,
            verbose=args.verbose,
            output_file=output_file,
            output_format=args.format
        )
        
        if result is None:
            logger.error("Transcription failed")
            return 1
            
        # If no output file was specified, print the result to stdout
        if output_file is None:
            print(result)
            
        return 0

if __name__ == "__main__":
    sys.exit(main())