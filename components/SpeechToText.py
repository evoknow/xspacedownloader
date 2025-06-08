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

# Optional OpenAI API import
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai = None

# Set up logging
logger = logging.getLogger(__name__)

class SpeechToText:
    """
    Class for converting speech audio files to text using local Whisper or OpenAI API.
    """
    
    def __init__(self, model_name='tiny', device=None, chunk_length_ms=30000, provider=None):
        """
        Initialize the SpeechToText component.
        
        Args:
            model_name (str): The Whisper model to use ('tiny', 'base', 'small', 'medium', 'large').
                              Default is 'tiny' for local, 'gpt-4o-mini-transcribe' for OpenAI API.
            device (str): Device to run the model on ('cpu', 'cuda', etc.). Default is None (auto-detect).
            chunk_length_ms (int): Length of audio chunks in milliseconds for large files. Default is 30000 (30 seconds).
            provider (str): Transcription provider ('local' or 'openai'). If None, loads from config.
        """
        self.model_name = model_name
        self.device = device
        self.model = None
        self.chunk_length_ms = chunk_length_ms
        
        # Load transcription configuration
        self.config = self._load_transcription_config()
        
        # Determine provider
        if provider:
            self.provider = provider
        else:
            self.provider = self.config.get('provider', 'local')
        
        # Validate provider and setup
        if self.provider == 'openai':
            if not OPENAI_AVAILABLE:
                logger.warning("OpenAI API not available, falling back to local Whisper")
                self.provider = 'local'
            elif not self.config.get('openai_api_key'):
                logger.warning("OpenAI API key not configured, falling back to local Whisper")
                self.provider = 'local'
        
        # Set appropriate model name for provider
        if self.provider == 'openai':
            self.model_name = self.config.get('openai_model', 'gpt-4o-mini-transcribe')
        else:
            # For local, use provided model_name or default from config
            if model_name == 'tiny':  # If using default, check config
                self.model_name = self.config.get('default_model', 'tiny')
        
        # Set device for local Whisper
        if self.provider == 'local' and not device:
            config_device = self.config.get('device', 'auto')
            if config_device != 'auto':
                self.device = config_device
        
        # Log initialization with clear provider indication
        provider_label = "OpenAI API" if self.provider == 'openai' else "Local Whisper"
        logger.info(f"[TRANSCRIPTION] Using {provider_label}, model: {self.model_name}")
        
    def _load_transcription_config(self):
        """Load transcription configuration from file and environment."""
        config_file = 'transcription_config.json'
        config = {
            'provider': 'local',
            'default_model': 'tiny',
            'device': 'auto',
            'openai_model': 'gpt-4o-mini-transcribe',
            'enable_corrective_filter': False,
            'correction_model': 'gpt-4o-mini'
        }
        
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    config.update(json.load(f))
        except Exception as e:
            logger.warning(f"Failed to load transcription config: {e}")
        
        # Check for OpenAI API key in environment variables
        openai_api_key = os.environ.get('OPENAI_API_KEY')
        if openai_api_key:
            config['openai_api_key'] = openai_api_key
        
        return config
    
    def load_model(self):
        """
        Load the Whisper model if using local provider, or set up OpenAI client.
        
        Returns:
            bool: True if the model/client was set up successfully, False otherwise.
        """
        if self.provider == 'openai':
            # For OpenAI API, we don't need to load a model, just verify the client can be created
            if OPENAI_AVAILABLE:
                try:
                    # Test that we can create a client with the API key
                    api_key = self.config.get('openai_api_key')
                    if not api_key:
                        logger.error("OpenAI API key not configured")
                        return False
                    
                    # Test client creation (new API >= 1.0.0)
                    from openai import OpenAI
                    test_client = OpenAI(api_key=api_key)
                    
                    logger.info(f"[TRANSCRIPTION] OpenAI API client ready")
                    self.model = "openai_client_ready"  # Mark as ready
                    return True
                except Exception as e:
                    logger.error(f"Error setting up OpenAI client: {e}")
                    return False
            else:
                logger.error("OpenAI library not available")
                return False
        else:
            # Local Whisper model loading
            if self.model is None:
                try:
                    logger.info(f"[TRANSCRIPTION] Loading Local Whisper model: {self.model_name}")
                    self.model = whisper.load_model(self.model_name, device=self.device)
                    logger.info(f"[TRANSCRIPTION] Local Whisper model loaded")
                    return True
                except Exception as e:
                    logger.error(f"Error loading Whisper model: {e}")
                    return False
        
        return True
    
    def _transcribe_with_openai(self, audio_file, language=None, verbose=False):
        """
        Transcribe audio using OpenAI API.
        
        Args:
            audio_file (str): Path to the audio file
            language (str, optional): Language code for transcription
            verbose (bool): Whether to log verbose output
            
        Returns:
            dict: Transcription result compatible with local Whisper format
        """
        try:
            logger.info(f"[TRANSCRIPTION] Starting OpenAI API transcription")
            
            # Validate audio file before sending to OpenAI
            audio_path = Path(audio_file)
            file_size = audio_path.stat().st_size
            file_size_mb = file_size / (1024 * 1024)
            
            logger.info(f"[TRANSCRIPTION] Audio file: {audio_file} ({file_size_mb:.1f}MB)")
            
            # Check file size (OpenAI has 25MB limit)
            if file_size_mb > 25:
                logger.info(f"Audio file larger than 25MB ({file_size_mb:.1f}MB), using chunked OpenAI transcription")
                
                # Use chunked transcription for large files
                try:
                    return self._transcribe_large_file_with_openai(audio_file, language, verbose)
                except Exception as chunk_error:
                    import traceback
                    logger.error(f"Chunked OpenAI transcription failed: {chunk_error}")
                    logger.error(f"Chunked traceback: {traceback.format_exc()}")
                    return None
            
            # Check if file is empty
            if file_size == 0:
                logger.error("Audio file is empty")
                return None
            
            # Validate audio file format using pydub
            try:
                audio_segment = AudioSegment.from_file(audio_file)
                duration = len(audio_segment) / 1000.0
                logger.info(f"[TRANSCRIPTION] Audio validation: {duration:.1f}s duration, {audio_segment.frame_rate}Hz, {audio_segment.channels} channels")
                
                # Check for very short audio (OpenAI requires at least some content)
                if duration < 0.1:
                    logger.error(f"Audio file too short: {duration:.2f}s")
                    return None
                    
            except Exception as e:
                logger.error(f"Audio file validation failed: {e}")
                return None
            
            # Create OpenAI client (new API >= 1.0.0)
            from openai import OpenAI
            client = OpenAI(api_key=self.config.get('openai_api_key'))
            
            # Determine response format
            if self.model_name == "gpt-4o-mini-transcribe":
                response_format = "json"
            else:
                response_format = "verbose_json"
            
            logger.info(f"[TRANSCRIPTION] Calling OpenAI API with model {self.model_name}, format {response_format}")
            
            # Try transcription with original file first
            response = None
            temp_file_path = None
            
            try:
                # First attempt with original file
                with open(audio_file, 'rb') as audio:
                    response = client.audio.transcriptions.create(
                        model=self.model_name,
                        file=audio,
                        language=language if language else None,
                        response_format=response_format
                    )
            except Exception as api_error:
                logger.warning(f"[TRANSCRIPTION] Direct upload failed for {audio_file}: {api_error}")
                logger.info(f"[TRANSCRIPTION] Attempting to convert audio to compatible format")
                
                # Try converting to a more compatible format (WAV, 16-bit, mono)
                try:
                    # Convert audio to WAV format for better compatibility
                    converted_audio = audio_segment.set_frame_rate(16000).set_channels(1).set_sample_width(2)
                    
                    # Create temporary file
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                        temp_file_path = temp_file.name
                        converted_audio.export(temp_file_path, format='wav')
                    
                    logger.info(f"[TRANSCRIPTION] Converted audio to {temp_file_path} (16kHz, mono, 16-bit WAV)")
                    
                    # Try again with converted file
                    with open(temp_file_path, 'rb') as audio:
                        response = client.audio.transcriptions.create(
                            model=self.model_name,
                            file=audio,
                            language=language if language else None,
                            response_format=response_format
                        )
                    
                    logger.info(f"[TRANSCRIPTION] Transcription succeeded with converted audio")
                    
                except Exception as convert_error:
                    logger.error(f"[TRANSCRIPTION] Audio conversion also failed: {convert_error}")
                    raise api_error  # Re-raise original error
                finally:
                    # Clean up temporary file
                    if temp_file_path and os.path.exists(temp_file_path):
                        try:
                            os.unlink(temp_file_path)
                        except:
                            pass
            
            if not response:
                logger.error("[TRANSCRIPTION] Failed to get response from OpenAI API")
                return None
            
            # Convert OpenAI response to our standard format
            # Different models return different response structures
            if response_format == "json":
                # For gpt-4o-mini-transcribe with json format
                raw_text = getattr(response, "text", "")
                
                # Get audio duration for timing
                try:
                    audio_duration = self._get_audio_duration(audio_file)
                except:
                    audio_duration = 0
                
                # Create artificial segments for timecode support
                segments = []
                if raw_text.strip():
                    sentences = self._split_text_into_sentences(raw_text.strip())
                    if sentences:
                        segment_duration = audio_duration / len(sentences) if audio_duration > 0 else 30
                        
                        for i, sentence in enumerate(sentences):
                            if sentence.strip():
                                segment_start = i * segment_duration
                                segment_end = (i + 1) * segment_duration
                                segments.append({
                                    "start": segment_start,
                                    "end": min(segment_end, audio_duration) if audio_duration > 0 else segment_end,
                                    "text": sentence.strip()
                                })
                
                result = {
                    "text": raw_text,
                    "language": language if language else "unknown",  # Model doesn't return language in json format
                    "duration": audio_duration,
                    "segments": segments
                }
            else:
                # For whisper-1 with verbose_json format
                result = {
                    "text": getattr(response, "text", ""),
                    "language": getattr(response, "language", "unknown"),
                    "duration": getattr(response, "duration", 0),
                    "segments": getattr(response, "segments", [])
                }
            
            logger.info(f"[TRANSCRIPTION] OpenAI API transcription completed ({result['duration']:.1f}s, {result['language']})")
            return result
            
        except Exception as e:
            import traceback
            logger.error(f"Error in OpenAI transcription: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    def _transcribe_large_file_with_openai(self, audio_file, language=None, verbose=False):
        """
        Transcribe large audio files (>25MB) by chunking them for OpenAI API.
        
        Args:
            audio_file (str): Path to the audio file
            language (str, optional): Language code for transcription
            verbose (bool): Whether to log verbose output
            
        Returns:
            dict: Combined transcription result
        """
        try:
            logger.info(f"[TRANSCRIPTION] Starting chunked OpenAI transcription")
            
            # Load the audio file using pydub
            audio_segment = AudioSegment.from_file(audio_file)
            total_duration = len(audio_segment) / 1000.0  # Convert to seconds
            
            logger.info(f"[TRANSCRIPTION] Audio duration: {total_duration:.1f}s")
            
            # Calculate chunk size based on file size and bitrate to stay under 25MB
            # Be more conservative and aim for ~20MB chunks
            file_size_bytes = os.path.getsize(audio_file)
            bitrate_bps = (file_size_bytes * 8) / total_duration  # bits per second
            
            # Calculate safe chunk duration to stay under 20MB (leaving 5MB buffer)
            target_chunk_bytes = 20 * 1024 * 1024  # 20MB
            safe_chunk_duration = (target_chunk_bytes * 8) / bitrate_bps  # seconds
            
            # Convert to milliseconds and ensure reasonable bounds (5-20 minutes)
            chunk_duration_ms = int(max(5 * 60, min(20 * 60, safe_chunk_duration)) * 1000)
            
            logger.info(f"[TRANSCRIPTION] Calculated chunk duration: {chunk_duration_ms/60000:.1f} minutes based on bitrate")
            
            # Split audio into chunks
            chunks = []
            current_start = 0
            
            while current_start < len(audio_segment):
                # Calculate this chunk's end
                chunk_end = min(current_start + chunk_duration_ms, len(audio_segment))
                chunk = audio_segment[current_start:chunk_end]
                
                # For all chunks except the last one, try to find a good break point
                if chunk_end < len(audio_segment):
                    # Look for silence in the last 30 seconds of the chunk to avoid mid-sentence breaks
                    silence_search_start = max(0, len(chunk) - 30000)  # Last 30 seconds
                    
                    try:
                        from pydub.silence import detect_silence
                        
                        # Search for silence in the last portion of the chunk
                        search_segment = chunk[silence_search_start:]
                        silence_ranges = detect_silence(
                            search_segment,
                            min_silence_len=500,  # At least 0.5 seconds of silence
                            silence_thresh=search_segment.dBFS - 16  # 16dB below average volume
                        )
                        
                        if silence_ranges:
                            # Use the last silence point found for a cleaner break
                            last_silence = silence_ranges[-1]
                            silence_end = silence_search_start + last_silence[1]
                            chunk = chunk[:silence_end]
                            chunk_end = current_start + silence_end
                            logger.debug(f"Found silence break at {silence_end/1000:.1f}s for chunk {len(chunks)+1}")
                    except Exception as silence_error:
                        logger.debug(f"Silence detection failed for chunk, using time-based split: {silence_error}")
                
                # Verify chunk isn't too small (at least 30 seconds)
                if len(chunk) >= 30000 or chunk_end >= len(audio_segment):  # 30 seconds or final chunk
                    chunks.append({
                        'audio': chunk,
                        'start_ms': current_start,
                        'end_ms': chunk_end,
                        'start_seconds': current_start / 1000.0,
                        'end_seconds': chunk_end / 1000.0,
                        'duration_seconds': len(chunk) / 1000.0
                    })
                    current_start = chunk_end
                else:
                    # Chunk too small, extend it
                    current_start = min(current_start + chunk_duration_ms, len(audio_segment))
            
            logger.info(f"[TRANSCRIPTION] Split audio into {len(chunks)} chunks")
            
            # Create OpenAI client
            from openai import OpenAI
            client = OpenAI(api_key=self.config.get('openai_api_key'))
            
            # Determine response format
            if self.model_name == "gpt-4o-mini-transcribe":
                response_format = "json"
            else:
                response_format = "verbose_json"
            
            # Transcribe each chunk
            all_text = []
            all_segments = []
            import tempfile
            
            for i, chunk_info in enumerate(chunks):
                chunk_start = chunk_info['start_seconds']
                chunk_end = chunk_info['end_seconds']
                chunk_duration = chunk_info['duration_seconds']
                
                logger.info(f"[TRANSCRIPTION] Processing chunk {i+1}/{len(chunks)} ({chunk_start:.1f}s - {chunk_end:.1f}s, {chunk_duration:.1f}s)")
                
                # Export chunk to temporary file with optimized settings for size
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
                    temp_path = temp_file.name
                    # Use a low bitrate to ensure we stay under 25MB
                    chunk_info['audio'].export(temp_path, format='mp3', bitrate='64k')
                    
                    # Check the actual file size
                    chunk_size_mb = os.path.getsize(temp_path) / (1024 * 1024)
                    logger.info(f"[TRANSCRIPTION] Chunk {i+1} exported: {chunk_size_mb:.1f}MB")
                
                try:
                    # Transcribe chunk
                    with open(temp_path, 'rb') as audio:
                        response = client.audio.transcriptions.create(
                            model=self.model_name,
                            file=audio,
                            language=language if language else None,
                            response_format=response_format
                        )
                    
                    # Process response based on format
                    if response_format == "json":
                        chunk_text = getattr(response, "text", "")
                        chunk_language = language if language else "unknown"
                        chunk_segments = []
                        
                        # For JSON format (gpt-4o-mini-transcribe), create artificial segments
                        # since OpenAI doesn't provide them, but we need them for timecodes
                        if chunk_text.strip():
                            # Split text into sentences for better timecode distribution
                            sentences = self._split_text_into_sentences(chunk_text.strip())
                            if sentences:
                                segment_duration = chunk_duration / len(sentences)
                                chunk_segments = []
                                
                                for j, sentence in enumerate(sentences):
                                    if sentence.strip():
                                        segment_start = chunk_start + (j * segment_duration)
                                        segment_end = chunk_start + ((j + 1) * segment_duration)
                                        
                                        # Don't exceed chunk boundary
                                        segment_end = min(segment_end, chunk_end)
                                        
                                        artificial_segment = {
                                            "start": segment_start,
                                            "end": segment_end,
                                            "text": sentence.strip()
                                        }
                                        chunk_segments.append(artificial_segment)
                            else:
                                # Fallback to single segment
                                artificial_segment = {
                                    "start": chunk_start,
                                    "end": chunk_end,
                                    "text": chunk_text.strip()
                                }
                                chunk_segments = [artificial_segment]
                    else:
                        chunk_text = getattr(response, "text", "")
                        chunk_language = getattr(response, "language", "unknown")
                        chunk_segments = getattr(response, "segments", [])
                        
                        # Adjust segment timestamps to account for chunk position
                        for segment in chunk_segments:
                            segment["start"] = segment.get("start", 0) + chunk_start
                            segment["end"] = segment.get("end", 0) + chunk_start
                    
                    # Add chunk text
                    if chunk_text.strip():
                        all_text.append(chunk_text.strip())
                    
                    # Add all segments (either real or artificial)
                    all_segments.extend(chunk_segments)
                    
                    logger.info(f"[TRANSCRIPTION] Chunk {i+1} completed: {len(chunk_text)} chars")
                    
                except Exception as chunk_error:
                    logger.error(f"Error transcribing chunk {i+1}: {chunk_error}")
                    # Continue with other chunks
                    
                finally:
                    # Clean up temporary file
                    try:
                        os.unlink(temp_path)
                    except:
                        pass
            
            # Combine all results
            combined_text = " ".join(all_text)
            
            # Create final result
            result = {
                "text": combined_text,
                "language": chunk_language if 'chunk_language' in locals() else (language if language else "unknown"),
                "duration": total_duration,
                "segments": all_segments
            }
            
            logger.info(f"[TRANSCRIPTION] Chunked OpenAI transcription completed: {len(combined_text)} chars, {len(all_segments)} segments, {total_duration:.1f}s")
            
            return result
            
        except Exception as e:
            import traceback
            logger.error(f"Error in chunked OpenAI transcription: {e}")
            logger.error(f"Chunked transcription traceback: {traceback.format_exc()}")
            return None
    
    def _translate_with_openai(self, text, source_lang, target_lang, segments=None, include_timecodes=False):
        """
        Translate text using OpenAI API while preserving timecodes.
        
        Args:
            text (str): Text to translate
            source_lang (str): Source language code
            target_lang (str): Target language code
            segments (list): Original segments with timing info
            include_timecodes (bool): Whether to preserve timecodes
            
        Returns:
            str: Translated text with preserved timecodes if requested
        """
        try:
            # Check if OpenAI API is available for translation
            if not OPENAI_AVAILABLE or not self.config.get('openai_api_key'):
                logger.warning("OpenAI API not available for translation")
                return None
            
            from openai import OpenAI
            client = OpenAI(api_key=self.config.get('openai_api_key'))
            
            # Get language names for better prompts
            source_name = whisper.tokenizer.LANGUAGES.get(source_lang, source_lang)
            target_name = whisper.tokenizer.LANGUAGES.get(target_lang, target_lang)
            
            logger.info(f"[TRANSCRIPTION] Translating from {source_name} to {target_name} using OpenAI")
            
            # Handle timecoded vs non-timecoded translation differently
            logger.info(f"[TRANSCRIPTION] Translation path decision:")
            logger.info(f"  - include_timecodes: {include_timecodes}")
            logger.info(f"  - segments provided: {len(segments) if segments else 0}")
            logger.info(f"  - will use timecode preservation: {include_timecodes and segments}")
            
            if include_timecodes and segments:
                logger.info(f"[TRANSCRIPTION] Using segment-by-segment translation to preserve timecodes")
                # For timecoded text, translate each segment separately to preserve timing
                translated_segments = []
                
                for segment in segments:
                    segment_text = segment.get("text", "").strip()
                    if segment_text:
                        # Create prompt for translating this segment
                        prompt = f"""Translate the following {source_name} text to {target_name}. 
                        
CRITICAL REQUIREMENTS:
- Translate ONLY the text content
- Preserve the original meaning and tone
- Do NOT add any explanations, notes, or formatting
- Return ONLY the translated text, nothing else
- Keep the same speaking style (formal/informal)

Text to translate: {segment_text}"""

                        try:
                            response = client.chat.completions.create(
                                model='gpt-4o-mini',
                                temperature=0.3,  # Low temperature for consistent translations
                                max_tokens=500,   # Limit tokens per segment
                                messages=[
                                    {"role": "system", "content": "You are a professional translator. Translate text accurately while preserving tone and meaning."},
                                    {"role": "user", "content": prompt}
                                ]
                            )
                            
                            translated_segment_text = response.choices[0].message.content.strip()
                            
                            # Create translated segment with original timing
                            translated_segment = {
                                "start": segment["start"],
                                "end": segment["end"],
                                "text": translated_segment_text
                            }
                            translated_segments.append(translated_segment)
                            
                        except Exception as segment_error:
                            logger.warning(f"Failed to translate segment, using original: {segment_error}")
                            # Keep original segment if translation fails
                            translated_segments.append(segment)
                
                # Format translated segments with timecodes
                if translated_segments:
                    return self._format_transcript_with_timecodes(translated_segments)
                else:
                    return f"[00:00:00] [Translation failed]"
                    
            else:
                logger.info(f"[TRANSCRIPTION] Using whole-text translation (no timecode preservation)")
                # For non-timecoded text, translate the entire text at once
                prompt = f"""Translate the following {source_name} text to {target_name}.

CRITICAL REQUIREMENTS:
- Translate ONLY the text content
- Preserve the original meaning, tone, and speaking style
- Do NOT add any explanations, notes, or formatting
- Return ONLY the translated text, nothing else
- Maintain the same level of formality/informality
- Preserve any natural speech patterns

Text to translate:
{text}"""

                response = client.chat.completions.create(
                    model='gpt-4o-mini',
                    temperature=0.3,  # Low temperature for consistent translations
                    max_tokens=4000,  # Higher limit for full text
                    messages=[
                        {"role": "system", "content": "You are a professional translator. Translate text accurately while preserving tone, meaning, and natural speech patterns."},
                        {"role": "user", "content": prompt}
                    ]
                )
                
                translated_text = response.choices[0].message.content.strip()
                logger.info(f"[TRANSCRIPTION] Translation completed: {len(translated_text)} characters")
                return translated_text
                
        except Exception as e:
            logger.error(f"Error in OpenAI translation: {e}")
            return None
    
    def _split_text_into_sentences(self, text):
        """
        Split text into sentences for better timecode distribution.
        
        Args:
            text (str): Text to split
            
        Returns:
            list: List of sentences
        """
        import re
        
        # Simple sentence splitting on common sentence endings
        # This handles most cases for transcript text
        sentences = re.split(r'[.!?]+\s+', text)
        
        # Clean up and filter out very short segments
        cleaned_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 10:  # Only include sentences with reasonable length
                cleaned_sentences.append(sentence)
        
        # If we have no good sentences, split on other punctuation
        if not cleaned_sentences:
            sentences = re.split(r'[,:;]+\s+', text)
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) > 10:
                    cleaned_sentences.append(sentence)
        
        # If still no good splits, create reasonable chunks by word count
        if not cleaned_sentences:
            words = text.split()
            chunk_size = max(10, len(words) // 5)  # Aim for 5 chunks minimum
            for i in range(0, len(words), chunk_size):
                chunk = ' '.join(words[i:i + chunk_size])
                if chunk.strip():
                    cleaned_sentences.append(chunk.strip())
        
        return cleaned_sentences if cleaned_sentences else [text]
    
    def _apply_corrective_filter(self, raw_transcript, language='en'):
        """
        Apply corrective filter to improve transcript accuracy using GPT.
        
        Args:
            raw_transcript (str): The raw transcript text to correct
            language (str): Language code for the transcript
            
        Returns:
            str: Corrected transcript text, or original if correction fails
        """
        try:
            # Check if corrective filtering is enabled
            if not self.config.get('enable_corrective_filter', False):
                return raw_transcript
                
            # Check if OpenAI API is available for correction
            if not OPENAI_AVAILABLE or not self.config.get('openai_api_key'):
                logger.warning("OpenAI API not available for corrective filtering, using raw transcript")
                return raw_transcript
            
            logger.info("[TRANSCRIPTION] Applying corrective filter")
            
            # Create system prompt for transcript correction
            system_prompt = """You are a helpful assistant that corrects transcription errors. Your task is to:

1. Fix spelling mistakes and typos in the transcribed text
2. Add proper punctuation (periods, commas, capitalization) where needed
3. Correct obvious word misrecognitions (e.g., "their" vs "there", "two" vs "to")
4. Fix common transcription errors (homophones, similar-sounding words)
5. Ensure proper capitalization of names, places, and proper nouns
6. Remove filler words like "um", "uh", "like" when excessive
7. Fix grammar issues while preserving the original meaning and speaker's intent

CRITICAL RULES:
- Preserve ALL timecodes exactly as they appear [HH:MM:SS]
- Do NOT add any segment markers, dividers, or formatting
- Do NOT truncate or shorten the text
- Return the COMPLETE corrected transcript
- Only make corrections that are clearly needed
- Preserve the original meaning and tone
- Don't add information that wasn't in the original
- Don't change technical terms unless clearly wrong
- Keep the same speaking style and natural flow
- If unsure about a correction, leave the original text

Return ONLY the corrected transcript text without any additional commentary, formatting, or segment markers."""

            # Call OpenAI API for correction using new interface
            from openai import OpenAI
            client = OpenAI(api_key=self.config.get('openai_api_key'))
            
            # Check if transcript is too long for a single API call
            # GPT-4o-mini has ~128k token limit, but let's be conservative
            # Roughly 4 chars per token, so ~50k chars should be safe
            max_chars = 50000
            
            if len(raw_transcript) > max_chars:
                logger.warning(f"Transcript too long ({len(raw_transcript)} chars) for corrective filter, skipping correction")
                return raw_transcript
            
            response = client.chat.completions.create(
                model=self.config.get('correction_model', 'gpt-4o-mini'),
                temperature=0.1,  # Low temperature for consistent corrections
                max_tokens=None,  # Let the model use as many tokens as needed
                messages=[
                    {
                        "role": "system", 
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": f"Please correct this transcript:\n\n{raw_transcript}"
                    }
                ]
            )
            
            corrected_text = response.choices[0].message.content.strip()
            
            # Basic validation to ensure the corrected text isn't truncated
            if len(corrected_text) < len(raw_transcript) * 0.8:
                logger.warning(f"Corrected text appears truncated (original: {len(raw_transcript)}, corrected: {len(corrected_text)}), using raw transcript")
                return raw_transcript
            
            logger.info(f"[TRANSCRIPTION] Corrective filter applied")
            
            return corrected_text
            
        except Exception as e:
            logger.error(f"Error applying corrective filter: {e}")
            logger.warning("Using raw transcript due to correction failure")
            return raw_transcript
    
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
        # Ensure the model/client is loaded
        if not self.load_model():
            logger.error(f"Failed to load {self.provider} model/client, cannot transcribe")
            return None
            
        # Check if the audio file exists
        audio_path = Path(audio_file)
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_file}")
            return None
            
        # Route to appropriate transcription method
        if self.provider == 'openai':
            # For OpenAI API, we have simpler processing
            try:
                result = self._transcribe_with_openai(str(audio_path), language, verbose)
                if not result:
                    return None
                
                # Apply corrective filter to improve transcript accuracy
                raw_text = result["text"]
                
                # Handle corrective filtering differently based on whether we have segments
                if include_timecodes and "segments" in result and result["segments"]:
                    # For timecoded transcripts, apply corrective filter to each segment
                    # to maintain timing while improving text quality
                    corrected_segments = []
                    for segment in result["segments"]:
                        segment_text = segment.get("text", "")
                        if segment_text.strip():
                            corrected_segment_text = self._apply_corrective_filter(segment_text, result["language"])
                            corrected_segment = segment.copy()
                            corrected_segment["text"] = corrected_segment_text
                            corrected_segments.append(corrected_segment)
                        else:
                            corrected_segments.append(segment)
                    
                    # Update segments with corrected text
                    result["segments"] = corrected_segments
                    
                    # Create corrected full text from segments
                    corrected_text = " ".join([seg.get("text", "") for seg in corrected_segments if seg.get("text", "").strip()])
                    result["text"] = corrected_text
                    
                    # Apply timecode formatting
                    result["text"] = self._format_transcript_with_timecodes(corrected_segments)
                    
                else:
                    # For non-timecoded transcripts, apply normal corrective filtering
                    corrected_text = self._apply_corrective_filter(raw_text, result["language"])
                    result["text"] = corrected_text
                
                # Store both versions for reference
                result["raw_text"] = raw_text
                
                # Apply timecodes if requested (for non-segment cases)
                if include_timecodes:
                    if not ("segments" in result and result["segments"]):
                        # No segments available from OpenAI API, create a simple timecode format
                        # Try to estimate duration from audio file if possible
                        try:
                            audio_duration = self._get_audio_duration(str(audio_path))
                            if audio_duration:
                                result["duration"] = audio_duration
                            else:
                                audio_duration = 0
                        except:
                            audio_duration = 0
                        
                        # Create simple single segment with the text
                        current_text = result.get("text", "")
                        if current_text.strip():
                            result["text"] = f"[00:00:00] {current_text}"
                        else:
                            result["text"] = "[00:00:00] [No transcription available]"
                
                # Handle translation if requested
                if translate_to:
                    # Convert target language code if needed
                    target_lang = translate_to
                    if '-' in target_lang:
                        target_lang = target_lang.split('-')[0].lower()
                    
                    # Check if target language is different from source
                    source_lang = result["language"]
                    if target_lang != source_lang:
                        logger.info(f"Translating from {source_lang} to {target_lang}")
                        
                        # For OpenAI API, we need to implement translation ourselves
                        # Since OpenAI transcription API doesn't do translation, we'll use ChatGPT
                        segments_data = result.get("segments", [])
                        logger.info(f"[TRANSCRIPTION] Translation parameters:")
                        logger.info(f"  - source_lang: {source_lang}")
                        logger.info(f"  - target_lang: {target_lang}")
                        logger.info(f"  - include_timecodes: {include_timecodes}")
                        logger.info(f"  - segments count: {len(segments_data)}")
                        logger.info(f"  - text preview: {result['text'][:200]}...")
                        
                        translated_text = self._translate_with_openai(result["text"], source_lang, target_lang, segments_data, include_timecodes)
                        
                        if translated_text:
                            # Update result with translation
                            result["original_text"] = result["text"]
                            result["original_language"] = source_lang
                            result["text"] = translated_text
                            result["translated_text"] = translated_text
                            result["target_language"] = {
                                "code": target_lang,
                                "name": whisper.tokenizer.LANGUAGES.get(target_lang, "Unknown") if target_lang in whisper.tokenizer.LANGUAGES else "Unknown"
                            }
                            logger.info(f"Translation completed successfully")
                        else:
                            logger.warning(f"Translation failed, using original text")
                    else:
                        logger.info(f"Target language {target_lang} is same as source, no translation needed")
                
                # Set up final result
                final_result = {
                    "text": result["text"],
                    "detected_language": {
                        "code": result["language"],
                        "name": whisper.tokenizer.LANGUAGES.get(result["language"], "Unknown") if result["language"] != "unknown" else "Unknown"
                    },
                    "segments": result.get("segments", []),
                    "duration": result.get("duration", 0)
                }
                
                # Add translation info if present
                if "original_text" in result:
                    final_result["original_text"] = result["original_text"]
                    final_result["original_language"] = result["original_language"] 
                    final_result["translated_text"] = result["translated_text"]
                    final_result["target_language"] = result["target_language"]
                
                # Save output if requested
                if output_file:
                    self._save_output(final_result, output_file, output_format)
                
                return final_result
                
            except Exception as e:
                logger.error(f"Error in OpenAI transcription: {e}")
                return None
        
        # Local Whisper processing continues below...
            
        try:
            provider_label = "OpenAI API" if self.provider == 'openai' else "Local Whisper"
            logger.info(f"[TRANSCRIPTION] Starting {provider_label} transcription")
            
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
                    logger.info(f"Detected language: {detected_language_code}")
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
            elif language:
                # Check if language has a hyphen and extract just the primary language code
                if '-' in language:
                    whisper_language = language.split('-')[0].lower()
                else:
                    whisper_language = language.lower()
            
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
            
            # Determine task based on parameters
            current_task = task
            if translate_to:  # For multi-step translation, first step is always 'transcribe'
                current_task = "transcribe"
            
            transcribe_options["task"] = current_task
            
            # Check if we should chunk the audio file
            audio_duration = self._get_audio_duration(str(audio_path))
            if audio_duration and audio_duration > 600:  # 10 minutes threshold for chunking
                logger.info(f"Audio duration {audio_duration:.1f}s exceeds threshold, using chunked transcription")
                result = self._transcribe_chunked(str(audio_path), transcribe_options, include_timecodes)
            else:
                # Perform single transcription for shorter files
                result = self.model.transcribe(str(audio_path), **transcribe_options)
            
            # Store the original transcript
            raw_transcript = result["text"]
            
            # Apply corrective filter to improve transcript accuracy
            corrected_transcript = self._apply_corrective_filter(raw_transcript, result.get("language", "unknown"))
            original_transcript = corrected_transcript
            
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
            final_result["raw_text"] = raw_transcript  # Store raw transcript before correction
            final_result["original_language"] = detected_language_code
            
            # Log some stats about the transcription
            duration = result.get("duration", 0)
            logger.info(f"[TRANSCRIPTION] {provider_label} transcription completed ({duration:.1f}s, {detected_language_code})")
            
            
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
                            if include_timecodes:
                                # Always use original segments for timing, but get translated text
                                if "segments" in result and result["segments"]:
                                    original_segments = result["segments"]
                                    
                                    # Create segments with original timing but translated text
                                    # Distribute the translated text across the original segments
                                    trans_text = translate_result["text"].strip()
                                    
                                    if trans_text:
                                        # Split translated text into words
                                        words = trans_text.split()
                                        total_words = len(words)
                                        total_segments = len(original_segments)
                                        
                                        if total_words > 0 and total_segments > 0:
                                            # Distribute words proportionally across segments
                                            words_per_segment = max(1, total_words // total_segments)
                                            
                                            combined_segments = []
                                            word_index = 0
                                            
                                            for i, orig_seg in enumerate(original_segments):
                                                if word_index < total_words:
                                                    # Calculate words for this segment
                                                    if i == total_segments - 1:
                                                        # Last segment gets all remaining words
                                                        segment_words = words[word_index:]
                                                    else:
                                                        # Calculate proportional words based on segment duration
                                                        segment_duration = orig_seg.get("end", 0) - orig_seg.get("start", 0)
                                                        total_duration = result.get("duration", 1)
                                                        duration_ratio = segment_duration / total_duration if total_duration > 0 else 1/total_segments
                                                        segment_word_count = max(1, int(total_words * duration_ratio))
                                                        
                                                        end_word_index = min(word_index + segment_word_count, total_words)
                                                        segment_words = words[word_index:end_word_index]
                                                    
                                                    segment_text = " ".join(segment_words)
                                                    
                                                    if segment_text.strip():
                                                        combined_seg = {
                                                            "start": orig_seg["start"],
                                                            "end": orig_seg["end"], 
                                                            "text": segment_text
                                                        }
                                                        combined_segments.append(combined_seg)
                                                    
                                                    word_index += len(segment_words)
                                            
                                            if combined_segments:
                                                translated_text = self._format_transcript_with_timecodes(combined_segments)
                                            else:
                                                # Fallback: single segment with full text
                                                translated_text = f"[00:00:00] {trans_text}"
                                        else:
                                            # No words or segments, use simple format
                                            translated_text = f"[00:00:00] {trans_text}"
                                    else:
                                        # No translated text
                                        translated_text = "[00:00:00] [Translation failed]"
                                else:
                                    # No original segments, use simple timestamp
                                    translated_text = f"[00:00:00] {translate_result['text']}"
                            
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
                    
                    # If we have translation result, also update segments info
                    if 'translate_result' in locals() and translate_result:
                        # Update duration from translation if available (use original if translation doesn't have it)
                        if "duration" in translate_result:
                            final_result["duration"] = translate_result["duration"]
                        # If we created combined segments, store them
                        if 'combined_segments' in locals() and combined_segments:
                            final_result["segments"] = combined_segments
                        # Store both original and translated text
                        if "text" in result:
                            final_result["original_text"] = result["text"]
                    
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
            
            # Skip segments with invalid text (like ###SEGMENT_X### markers)
            if text and not text.startswith("###SEGMENT_"):
                # Ensure start_time is a valid number
                try:
                    start_time = float(start_time) if start_time is not None else 0
                except (ValueError, TypeError):
                    start_time = 0
                
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