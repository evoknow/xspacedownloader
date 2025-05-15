#!/usr/bin/env python3
# components/SpeechToText.py

import os
import json
import logging
import whisper
from datetime import datetime
from pathlib import Path

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class SpeechToText:
    """
    Class for converting speech audio files to text using OpenAI's Whisper model.
    """
    
    def __init__(self, model_name='base', device=None):
        """
        Initialize the SpeechToText component.
        
        Args:
            model_name (str): The Whisper model to use ('tiny', 'base', 'small', 'medium', 'large').
                              Default is 'base' which offers a good balance of accuracy and speed.
            device (str): Device to run the model on ('cpu', 'cuda', etc.). Default is None (auto-detect).
        """
        self.model_name = model_name
        self.device = device
        self.model = None
        
        # Log initialization
        logger.info(f"Initializing SpeechToText with model: {model_name}")
    
    def load_model(self):
        """
        Load the Whisper model if it's not already loaded.
        
        Returns:
            bool: True if the model was loaded successfully, False otherwise.
        """
        if self.model is None:
            try:
                logger.info(f"Loading Whisper model: {self.model_name}")
                self.model = whisper.load_model(self.model_name, device=self.device)
                logger.info(f"Successfully loaded Whisper model: {self.model_name}")
                return True
            except Exception as e:
                logger.error(f"Error loading Whisper model: {e}")
                return False
        
        return True
    
    def transcribe(self, audio_file, language=None, task="transcribe", verbose=False, 
                   output_file=None, output_format='txt'):
        """
        Transcribe an audio file to text.
        
        Args:
            audio_file (str): Path to the audio file to transcribe.
            language (str, optional): Language code (e.g., 'en', 'fr'). If None, auto-detected.
            task (str, optional): Task to perform ('transcribe' or 'translate'). Default is 'transcribe'.
            verbose (bool, optional): Whether to print progress information. Default is False.
            output_file (str, optional): Path to save the transcription output. Default is None.
            output_format (str, optional): Format to save the output ('txt', 'json', 'vtt', 'srt').
                                         Default is 'txt'.
                                         
        Returns:
            str or dict: Transcription result as text or as a dictionary with more details.
        """
        # Ensure the model is loaded
        if not self.load_model():
            logger.error("Failed to load Whisper model, cannot transcribe")
            return None
            
        # Check if the audio file exists
        audio_path = Path(audio_file)
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_file}")
            return None
            
        try:
            logger.info(f"Starting transcription of: {audio_file}")
            
            # Transcribe the audio file
            transcribe_options = {
                "fp16": False,  # Use FP16 precision if available
                "language": language,
                "task": task,
                "verbose": verbose
            }
            
            result = self.model.transcribe(str(audio_path), **transcribe_options)
            
            # Log some stats about the transcription
            duration = result.get("duration", 0)
            detected_language = result.get("language", "unknown")
            logger.info(f"Transcription completed. Audio duration: {duration:.2f}s, "
                         f"Detected language: {detected_language}")
            
            # Save the output if an output file is specified
            if output_file:
                self._save_output(result, output_file, output_format)
            
            # Return the result based on the requested format
            if output_format == 'txt' or output_file is None:
                return result["text"]
            else:
                return result
                
        except Exception as e:
            logger.error(f"Error transcribing audio file: {e}")
            return None
            
    def _save_output(self, result, output_file, output_format):
        """
        Save the transcription result to a file.
        
        Args:
            result (dict): The transcription result.
            output_file (str): Path to save the output.
            output_format (str): Format to save the output ('txt', 'json', 'vtt', 'srt').
            
        Returns:
            bool: True if the output was saved successfully, False otherwise.
        """
        try:
            output_path = Path(output_file)
            
            # Create parent directory if it doesn't exist
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            if output_format == 'txt':
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(result["text"])
                    
            elif output_format == 'json':
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=4, ensure_ascii=False)
                    
            elif output_format in ['vtt', 'srt']:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(self._get_subtitles(result, output_format))
                    
            logger.info(f"Saved transcription output to: {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving transcription output: {e}")
            return False
            
    def _get_subtitles(self, result, format_type):
        """
        Generate subtitles from the transcription result.
        
        Args:
            result (dict): The transcription result.
            format_type (str): The subtitle format ('vtt' or 'srt').
            
        Returns:
            str: The formatted subtitles.
        """
        segments = result["segments"]
        
        if format_type == 'vtt':
            output = "WEBVTT\n\n"
            for segment in segments:
                start = self._format_timestamp(segment["start"], vtt=True)
                end = self._format_timestamp(segment["end"], vtt=True)
                text = segment["text"].strip()
                output += f"{start} --> {end}\n{text}\n\n"
                
        elif format_type == 'srt':
            output = ""
            for i, segment in enumerate(segments, 1):
                start = self._format_timestamp(segment["start"], vtt=False)
                end = self._format_timestamp(segment["end"], vtt=False)
                text = segment["text"].strip()
                output += f"{i}\n{start} --> {end}\n{text}\n\n"
                
        return output
            
    def _format_timestamp(self, seconds, vtt=True):
        """
        Format a timestamp in seconds to either VTT or SRT format.
        
        Args:
            seconds (float): The timestamp in seconds.
            vtt (bool): Whether to use VTT format (True) or SRT format (False).
            
        Returns:
            str: The formatted timestamp.
        """
        hours = int(seconds // 3600)
        seconds %= 3600
        minutes = int(seconds // 60)
        seconds %= 60
        milliseconds = int((seconds - int(seconds)) * 1000)
        seconds = int(seconds)
        
        if vtt:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
        else:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def batch_transcribe(self, audio_directory, output_directory=None, 
                         language=None, file_extensions=None, recursive=False):
        """
        Transcribe multiple audio files in a directory.
        
        Args:
            audio_directory (str): Directory containing audio files to transcribe.
            output_directory (str, optional): Directory to save transcriptions. Default is None,
                which saves in the same directory as each audio file.
            language (str, optional): Language code. Default is None (auto-detect).
            file_extensions (list, optional): List of file extensions to include.
                Default is None, which includes common audio formats.
            recursive (bool, optional): Whether to search subdirectories. Default is False.
            
        Returns:
            dict: Dictionary mapping audio file paths to their transcription results.
        """
        if file_extensions is None:
            file_extensions = ['.mp3', '.wav', '.m4a', '.flac', '.ogg']
            
        audio_dir = Path(audio_directory)
        if not audio_dir.exists() or not audio_dir.is_dir():
            logger.error(f"Audio directory not found: {audio_directory}")
            return {}
            
        # Find all audio files
        audio_files = []
        if recursive:
            for ext in file_extensions:
                audio_files.extend(audio_dir.glob(f"**/*{ext}"))
        else:
            for ext in file_extensions:
                audio_files.extend(audio_dir.glob(f"*{ext}"))
                
        if not audio_files:
            logger.warning(f"No audio files found in: {audio_directory}")
            return {}
            
        logger.info(f"Found {len(audio_files)} audio files to transcribe")
        
        # Ensure the model is loaded
        if not self.load_model():
            logger.error("Failed to load Whisper model, cannot transcribe")
            return {}
            
        # Process each audio file
        results = {}
        for audio_file in audio_files:
            logger.info(f"Processing: {audio_file}")
            
            # Determine output file path
            if output_directory:
                rel_path = audio_file.relative_to(audio_dir) if recursive else audio_file.name
                output_file = Path(output_directory) / rel_path.with_suffix('.txt')
                output_file.parent.mkdir(parents=True, exist_ok=True)
            else:
                output_file = audio_file.with_suffix('.txt')
                
            # Transcribe the audio file
            result = self.transcribe(
                str(audio_file),
                language=language,
                output_file=str(output_file),
                output_format='txt'
            )
            
            if result:
                results[str(audio_file)] = result
                
        logger.info(f"Batch transcription completed. Processed {len(results)} files.")
        return results