#!/usr/bin/env python3
# transcribe.py - Transcribe an audio file to text using the SpeechToText component

import argparse
import logging
import os
import sys
import warnings
import io
import contextlib
from pathlib import Path
from components.SpeechToText import SpeechToText

# Define a context manager to suppress stdout and stderr
class SuppressOutput:
    def __init__(self, suppress_stdout=True, suppress_stderr=False):
        self.suppress_stdout = suppress_stdout
        self.suppress_stderr = suppress_stderr
        self.original_stdout = None
        self.original_stderr = None

    def __enter__(self):
        # Save original stdout/stderr
        if self.suppress_stdout:
            self.original_stdout = sys.stdout
            sys.stdout = open(os.devnull, 'w')
            
        if self.suppress_stderr:
            self.original_stderr = sys.stderr
            sys.stderr = open(os.devnull, 'w')

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore original stdout/stderr
        if self.suppress_stdout:
            sys.stdout.close()
            sys.stdout = self.original_stdout
            
        if self.suppress_stderr:
            sys.stderr.close()
            sys.stderr = self.original_stderr

# Set up logging - default to WARNING level to suppress info messages
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("transcribe")

# Suppress warnings
warnings.filterwarnings("ignore")

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
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress all non-essential output")
    parser.add_argument("--batch", "-b", action="store_true", 
                       help="Treat audio_file as a directory and transcribe all audio files")
    parser.add_argument("--timecodes", "-tc", action="store_true",
                       help="Include timecodes in the transcript output")
    
    args = parser.parse_args()
    
    # Set up logging levels based on verbosity/quiet flags
    if args.quiet:
        # Set all loggers to ERROR level to suppress INFO and WARNING
        logging.getLogger().setLevel(logging.ERROR)
        logging.getLogger('components').setLevel(logging.ERROR)
        
        # Set environment variables to disable progress bars
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        os.environ["TQDM_DISABLE"] = "1"
    elif args.verbose:
        # If verbose is requested, set to INFO level
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger('components').setLevel(logging.INFO)
    
    # Create the SpeechToText component
    stt = SpeechToText(model_name=args.model)
    
    # If we're doing batch processing
    if args.batch:
        if not os.path.isdir(args.audio_file):
            # No need to restore stdout since we're using a context manager
            logger.error(f"Batch mode requires a directory: {args.audio_file} is not a directory")
            return 1
            
        # Use batch_transcribe method with output suppression in quiet mode
        output_dir = args.output if args.output else None
        
        if args.quiet:
            with SuppressOutput(suppress_stdout=True, suppress_stderr=True):
                results = stt.batch_transcribe(
                    args.audio_file,
                    output_directory=output_dir,
                    language=args.language,
                    recursive=True,
                    verbose=False,  # Force verbose to False in quiet mode
                    include_timecodes=args.timecodes
                )
        else:
            results = stt.batch_transcribe(
                args.audio_file,
                output_directory=output_dir,
                language=args.language,
                recursive=True,
                verbose=args.verbose,
                include_timecodes=args.timecodes
            )
        
        # Print summary of results
        logger.info(f"Batch transcription completed. Processed {len(results)} files.")
        
        # No need to restore stdout since we're using a context manager
            
        return 0
        
    # Otherwise, transcribe a single file
    else:
        if not os.path.isfile(args.audio_file):
            # No need to restore stdout since we're using a context manager
            logger.error(f"Audio file not found: {args.audio_file}")
            return 1
            
        # Determine output file path
        output_file = None
        if args.output:
            output_file = args.output
        
        # Use the SuppressOutput context manager in quiet mode
        if args.quiet:
            with SuppressOutput(suppress_stdout=True, suppress_stderr=True):
                result = stt.transcribe(
                    args.audio_file,
                    language=args.language,
                    task=args.task,
                    verbose=False,  # Force verbose to False in quiet mode
                    output_file=output_file,
                    output_format=args.format,
                    include_timecodes=args.timecodes
                )
        else:
            # Normal mode - no suppression
            result = stt.transcribe(
                args.audio_file,
                language=args.language,
                task=args.task,
                verbose=args.verbose,
                output_file=output_file,
                output_format=args.format,
                include_timecodes=args.timecodes
            )
        
        if result is None:
            # No need to restore stdout since we're using a context manager
            logger.error("Transcription failed")
            return 1
            
        # If no output file was specified, print the result to stdout
        if output_file is None:
            # No need to restore stdout since we're using a context manager
            print(result)
            
        # No need to restore stdout since we're using a context manager
            
        return 0

if __name__ == "__main__":
    sys.exit(main())