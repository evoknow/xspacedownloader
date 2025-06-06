#!/usr/bin/env python3
# components/SpeechToText.py

import os
import json
import logging
import whisper
import warnings
from datetime import datetime
from pathlib import Path
from pydub import AudioSegment
from pydub.utils import make_chunks
import tempfile

# Set up logging
logger = logging.getLogger(__name__)

class SpeechToText:
    """
    Class for converting speech audio files to text using OpenAI's Whisper model.
    """
    
    def __init__(self, model_name='tiny', device=None, chunk_length_ms=30000):
        """
        Initialize the SpeechToText component.
        
        Args:
            model_name (str): The Whisper model to use ('tiny', 'base', 'small', 'medium', 'large').
                              Default is 'base' which offers a good balance of accuracy and speed.
            device (str): Device to run the model on ('cpu', 'cuda', etc.). Default is None (auto-detect).
            chunk_length_ms (int): Length of audio chunks in milliseconds for large files. Default is 30000 (30 seconds).
        """
        self.model_name = model_name
        self.device = device
        self.model = None
        self.chunk_length_ms = chunk_length_ms
        
        # Log initialization
        logger.info(f"Initializing SpeechToText with model: {model_name}, chunk length: {chunk_length_ms}ms")
    
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
                   output_file=None, output_format='txt', detect_language=False,
                   translate_to=None, include_timecodes=False):
        """
        Transcribe an audio file to text, with options for language detection and translation.
        
        Args:
            audio_file (str): Path to the audio file to transcribe.
            language (str, optional): Language code (e.g., 'en', 'fr'). If None, auto-detected.
                                     Note: Only use primary language codes like 'en', not locale codes like 'en-US'.
            task (str, optional): Task to perform ('transcribe' or 'translate'). Default is 'transcribe'.
            verbose (bool, optional): Whether to print progress information. Default is False.
            output_file (str, optional): Path to save the transcription output. Default is None.
            output_format (str, optional): Format to save the output ('txt', 'json', 'vtt', 'srt').
                                         Default is 'txt'.
            detect_language (bool, optional): Whether to explicitly detect the language first before transcription.
                                         Default is False. If True, the 'language' parameter is ignored.
            translate_to (str, optional): Language code to translate the content to after transcription.
                                     If provided, transcription will be done in two steps: first transcribe
                                     in the original language, then translate to the target language.
                                     This requires running multiple passes of the model.
            include_timecodes (bool, optional): Whether to include timecodes in the transcript text.
                                              Default is False. When True, each segment will be prefixed
                                              with its timestamp in [HH:MM:SS] format.
                                         
        Returns:
            dict: Transcription result with transcript text, detected language, and translation if requested.
        """
        # Suppress warnings if TQDM_DISABLE is set (quiet mode)
        if os.environ.get("TQDM_DISABLE"):
            warnings.filterwarnings("ignore")
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
            
            # Track results and detected language for multi-step processing
            final_result = {}
            detected_language_code = None
            original_transcript = None

            # STEP 1: Detect language if requested
            if detect_language:
                logger.info("First pass: Detecting language from audio")
                # Run initial transcription with language detection only
                detect_options = {
                    "fp16": False,
                    "verbose": verbose
                }
                detection_result = self.model.transcribe(str(audio_path), **detect_options)
                detected_language_code = detection_result.get("language")
                
                if detected_language_code:
                    logger.info(f"Detected language: {detected_language_code} - {whisper.tokenizer.LANGUAGES.get(detected_language_code, 'Unknown')}")
                    final_result["detected_language"] = {
                        "code": detected_language_code,
                        "name": whisper.tokenizer.LANGUAGES.get(detected_language_code, "Unknown")
                    }
                else:
                    logger.warning("Language detection failed, will use auto-detection in transcription")
            
            # STEP 2: Main transcription
            # For Whisper, language code must be a simple code like 'en', not 'en-US'
            whisper_language = None
            
            # Priority for language selection:
            # 1. Use detected language if detect_language is True
            # 2. Use provided language if specified
            # 3. Otherwise, let Whisper auto-detect
            if detect_language and detected_language_code:
                whisper_language = detected_language_code
                logger.info(f"Using detected language: {whisper_language}")
            elif language:
                # Check if language has a hyphen and extract just the primary language code
                if '-' in language:
                    whisper_language = language.split('-')[0].lower()
                    logger.info(f"Converted language code '{language}' to '{whisper_language}' for Whisper")
                else:
                    whisper_language = language.lower()
                logger.info(f"Using specified language: {whisper_language}")
            
            # Verify language code is supported
            if whisper_language and whisper_language not in whisper.tokenizer.LANGUAGES:
                logger.warning(f"Language {whisper_language} not in Whisper supported languages. Will use auto-detection.")
                whisper_language = None
            
            # Set up transcription options
            transcribe_options = {
                "fp16": False,  # Use FP16 precision if available
                "verbose": verbose
            }
            
            # Add language if we have a valid one
            if whisper_language:
                transcribe_options["language"] = whisper_language
                logger.info(f"Forcing transcription in language: {whisper_language}")
            
            # Determine task based on parameters
            current_task = task
            if translate_to:  # For multi-step translation, first step is always 'transcribe'
                current_task = "transcribe"
            
            transcribe_options["task"] = current_task
            logger.info(f"Using task: {current_task}")
            
            # Check if we should chunk the audio file
            audio_duration = self._get_audio_duration(str(audio_path))
            if audio_duration and audio_duration > 600:  # 10 minutes threshold for chunking
                logger.info(f"Audio duration {audio_duration:.1f}s exceeds threshold, using chunked transcription")
                result = self._transcribe_chunked(str(audio_path), transcribe_options, include_timecodes)
            else:
                # Perform single transcription for shorter files
                result = self.model.transcribe(str(audio_path), **transcribe_options)
            
            # Store the original transcript
            original_transcript = result["text"]
            
            # Generate timecoded transcript if requested
            if include_timecodes and "segments" in result:
                original_transcript = self._format_transcript_with_timecodes(result["segments"])
            
            # Update result with detected language if not already set
            if not detected_language_code:
                detected_language_code = result.get("language", "unknown")
                final_result["detected_language"] = {
                    "code": detected_language_code,
                    "name": whisper.tokenizer.LANGUAGES.get(detected_language_code, "Unknown")
                }
            
            # Set the transcript based on the current step
            final_result["text"] = original_transcript
            final_result["original_text"] = original_transcript
            final_result["original_language"] = detected_language_code
            
            # Log some stats about the transcription
            duration = result.get("duration", 0)
            logger.info(f"Transcription completed. Audio duration: {duration:.2f}s, "
                       f"Detected language: {detected_language_code}")
            
            # Print language info if in verbose mode
            if verbose and not os.environ.get("TQDM_DISABLE"):
                print(f"Detected language: {detected_language_code} - {whisper.tokenizer.LANGUAGES.get(detected_language_code, 'Unknown')}")
            
            # STEP 3: Translation to target language if requested
            if translate_to:
                # Convert target language code if needed
                target_lang = translate_to
                if '-' in target_lang:
                    target_lang = target_lang.split('-')[0].lower()
                
                # Check if target language is different from source and is supported
                if target_lang != detected_language_code and target_lang in whisper.tokenizer.LANGUAGES:
                    logger.info(f"Translating from {detected_language_code} to {target_lang}")
                    
                    # IMPORTANT NOTE: Whisper's "translate" task only translates TO ENGLISH, not to other languages
                    translated_text = None
                    
                    # Simplifying our approach - Whisper only supports translating to English
                    if target_lang == "en":
                        # Translation to English using Whisper's built-in capabilities
                        try:
                            translate_options = {
                                "fp16": False,
                                "task": "translate",  # Translate to English
                                "verbose": verbose
                            }
                            translate_result = self.model.transcribe(str(audio_path), **translate_options)
                            translated_text = translate_result["text"]
                            
                            # Apply timecodes to translated text if requested
                            if include_timecodes and "segments" in translate_result:
                                translated_text = self._format_transcript_with_timecodes(translate_result["segments"])
                            
                            logger.info(f"Successfully translated to English")
                        except Exception as e:
                            logger.error(f"Failed to translate to English: {e}")
                            translated_text = result["text"]  # Fallback to original text
                    else:
                        # For non-English target languages (not fully supported yet)
                        logger.warning(f"Translation to {target_lang} not supported. Whisper only translates to English.")
                        translated_text = f"[Translation to {target_lang} ({whisper.tokenizer.LANGUAGES.get(target_lang, 'Unknown')}) is not yet supported. Whisper only translates to English.]"
                    
                    # Add translation to result
                    final_result["translated_text"] = translated_text
                    final_result["target_language"] = {
                        "code": target_lang,
                        "name": whisper.tokenizer.LANGUAGES.get(target_lang, "Unknown")
                    }
                    
                    # Update the main text to be the translation
                    # Keep both fields for compatibility
                    final_result["text"] = translated_text
                    
                    logger.info(f"Translation completed successfully")
                else:
                    logger.info(f"Translation not performed: target language {target_lang} is same as source or not supported")
                    final_result["translation_status"] = "skipped"
            
            # Copy other useful info from the original result
            for key in ["segments", "duration"]:
                if key in result:
                    final_result[key] = result[key]
            
            # Save the output if an output file is specified
            if output_file:
                self._save_output(final_result, output_file, output_format)
            
            # Return the result with all the information
            return final_result
                
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
                    # Use main text which might be original or translated depending on process
                    main_text = result.get("text", "")
                    
                    # If we have both original and translated, include both with headers
                    if "original_text" in result and "translated_text" in result:
                        original_lang = result.get("original_language", "unknown")
                        target_lang = result.get("target_language", {}).get("code", "unknown")
                        
                        # Format with language info
                        f.write(f"=== ORIGINAL TRANSCRIPT ({original_lang}) ===\n\n")
                        f.write(result["original_text"])
                        f.write(f"\n\n=== TRANSLATED TRANSCRIPT ({target_lang}) ===\n\n")
                        f.write(result["translated_text"])
                    else:
                        # Just write the main text
                        f.write(main_text)
                    
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

    def _format_transcript_with_timecodes(self, segments):
        """
        Format transcript segments with timecodes.
        
        Args:
            segments (list): List of segment dictionaries with 'start', 'end', and 'text' keys.
            
        Returns:
            str: Formatted transcript with timecodes.
        """
        transcript_lines = []
        
        for segment in segments:
            start_time = segment.get("start", 0)
            text = segment.get("text", "").strip()
            
            if text:  # Only include segments with actual text
                # Format timestamp as [HH:MM:SS]
                hours = int(start_time // 3600)
                minutes = int((start_time % 3600) // 60)
                seconds = int(start_time % 60)
                
                timecode = f"[{hours:02d}:{minutes:02d}:{seconds:02d}]"
                transcript_lines.append(f"{timecode} {text}")
        
        return "\n".join(transcript_lines)

    def batch_transcribe(self, audio_directory, output_directory=None, 
                         language=None, file_extensions=None, recursive=False, verbose=False,
                         detect_language=False, translate_to=None, include_timecodes=False):
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
            verbose (bool, optional): Whether to print progress information. Default is False.
            detect_language (bool, optional): Whether to explicitly detect language first.
                Default is False.
            translate_to (str, optional): Language code to translate content to after transcription.
                If provided, transcription will be done in the original language, then translated.
            include_timecodes (bool, optional): Whether to include timecodes in the transcript text.
                Default is False.
            
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
                output_format='txt',
                verbose=verbose,
                detect_language=detect_language,
                translate_to=translate_to,
                include_timecodes=include_timecodes
            )
            
            if result:
                # For backward compatibility, use the text field as string result
                if isinstance(result, dict) and "text" in result:
                    results[str(audio_file)] = result["text"]
                else:
                    results[str(audio_file)] = result
                
        logger.info(f"Batch transcription completed. Processed {len(results)} files.")
        return results
    
    def _get_audio_duration(self, audio_file):
        """
        Get the duration of an audio file using pydub.
        
        Args:
            audio_file (str): Path to the audio file
            
        Returns:
            float: Duration in seconds, or None if unable to determine
        """
        try:
            audio = AudioSegment.from_file(audio_file)
            return len(audio) / 1000.0  # Convert milliseconds to seconds
        except Exception as e:
            logger.warning(f"Could not determine audio duration for {audio_file}: {e}")
            return None
    
    def _transcribe_chunked(self, audio_file, transcribe_options, include_timecodes=False):
        """
        Transcribe a large audio file by splitting it into chunks using pydub.
        This prevents context loss that can occur with simple text chunking.
        
        Args:
            audio_file (str): Path to the audio file
            transcribe_options (dict): Options for transcription
            include_timecodes (bool): Whether to include timecodes in the output text
            
        Returns:
            dict: Combined transcription result
        """
        try:
            logger.info(f"Loading audio file for chunking: {audio_file}")
            audio = AudioSegment.from_file(audio_file)
            
            # Create chunks using pydub - this preserves audio boundaries
            chunks = make_chunks(audio, self.chunk_length_ms)
            logger.info(f"Split audio into {len(chunks)} chunks of {self.chunk_length_ms/1000:.1f}s each")
            
            all_segments = []
            full_text_parts = []
            total_duration = 0
            
            # Process each chunk
            with tempfile.TemporaryDirectory() as temp_dir:
                for i, chunk in enumerate(chunks):
                    chunk_start_time = i * (self.chunk_length_ms / 1000.0)
                    
                    # Export chunk to temporary file
                    chunk_file = os.path.join(temp_dir, f"chunk_{i:03d}.wav")
                    chunk.export(chunk_file, format="wav")
                    
                    logger.info(f"Transcribing chunk {i+1}/{len(chunks)} (start: {chunk_start_time:.1f}s)")
                    
                    # Transcribe the chunk
                    chunk_result = self.model.transcribe(chunk_file, **transcribe_options)
                    
                    # Adjust segment timestamps to account for chunk position
                    if "segments" in chunk_result:
                        for segment in chunk_result["segments"]:
                            segment["start"] += chunk_start_time
                            segment["end"] += chunk_start_time
                            all_segments.append(segment)
                    
                    # Collect text
                    if "text" in chunk_result and chunk_result["text"].strip():
                        full_text_parts.append(chunk_result["text"].strip())
                    
                    total_duration += len(chunk) / 1000.0
            
            # Combine results
            text_output = " ".join(full_text_parts)
            
            # Generate timecoded text if requested
            if include_timecodes and all_segments:
                text_output = self._format_transcript_with_timecodes(all_segments)
            
            combined_result = {
                "text": text_output,
                "segments": all_segments,
                "duration": total_duration,
                "language": transcribe_options.get("language", "unknown")
            }
            
            # Try to get language from first chunk if not specified
            if combined_result["language"] == "unknown" and all_segments:
                # Use the language detected in the first chunk
                first_chunk_file = os.path.join(temp_dir, "chunk_000.wav")
                if os.path.exists(first_chunk_file):
                    detection_result = self.model.transcribe(first_chunk_file, task="transcribe")
                    combined_result["language"] = detection_result.get("language", "unknown")
            
            logger.info(f"Chunked transcription completed: {len(all_segments)} segments, {total_duration:.1f}s total")
            return combined_result
            
        except Exception as e:
            logger.error(f"Error in chunked transcription: {e}")
            # Fallback to regular transcription
            logger.info("Falling back to regular transcription")
            return self.model.transcribe(audio_file, **transcribe_options)