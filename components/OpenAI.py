#!/usr/bin/env python3
# components/OpenAI.py
"""OpenAI provider for AI translation and summarization services."""

import requests
import json
import logging
from typing import Dict, List, Optional, Union, Tuple
from .AI import AIProvider

logger = logging.getLogger(__name__)

class OpenAI(AIProvider):
    """OpenAI implementation for AI services."""
    
    def __init__(self, api_key: str, endpoint: str = None, model: str = "gpt-4o"):
        """
        Initialize OpenAI provider.
        
        Args:
            api_key (str): OpenAI API key
            endpoint (str, optional): Custom endpoint (defaults to OpenAI's API)
            model (str): Model to use (default: gpt-4o - latest GPT-4 model with 128K context)
        """
        super().__init__(api_key, endpoint, model)
        
        self.endpoint = endpoint or "https://api.openai.com/v1/chat/completions"
        # Use GPT-4o as default - latest GPT-4 model with excellent performance and 128K context
        self.model = model or "gpt-4o"
        
        # Initialize session with headers
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        })
        
        logger.info(f"OpenAI provider initialized with model: {self.model}")
    
    def _make_request(self, messages: List[Dict], max_tokens: int = 1000, temperature: float = 0.3, frequency_penalty: float = 0.0, presence_penalty: float = 0.0) -> Tuple[bool, Union[str, Dict]]:
        """
        Make a request to OpenAI API.
        
        Args:
            messages (List[Dict]): List of message objects
            max_tokens (int): Maximum tokens to generate
            temperature (float): Sampling temperature
            
        Returns:
            Tuple[bool, Union[str, Dict]]: Success flag and response or error
        """
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "frequency_penalty": frequency_penalty,
                "presence_penalty": presence_penalty
            }
            
            # Calculate timeout based on expected response size
            # Base timeout of 120 seconds, plus additional time for larger responses
            timeout = max(120, 120 + (max_tokens / 100))  # Add 1 second per 100 tokens
            
            logger.info(f"Making request to OpenAI API with model {self.model}, timeout={timeout}s")
            logger.info(f"========== OPENAI API PAYLOAD ==========")
            logger.info(f"Model: {payload['model']}")
            logger.info(f"Max tokens: {payload['max_tokens']}")
            logger.info(f"Temperature: {payload['temperature']}")
            logger.info(f"Messages count: {len(payload['messages'])}")
            for i, msg in enumerate(payload['messages']):
                logger.info(f"Message {i+1} ({msg['role']}): {msg['content'][:200]}{'...' if len(msg['content']) > 200 else ''}")
            logger.info(f"=======================================")
            
            response = self.session.post(self.endpoint, json=payload, timeout=timeout)
            
            if response.status_code != 200:
                logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
                
                # Check for specific error types
                if response.status_code == 400 and 'max_tokens is too large' in response.text:
                    return False, {
                        "error": "Content too long for OpenAI model - using chunked translation",
                        "details": "The text is too long for a single API call, will be processed in chunks",
                        "should_chunk": True
                    }
                
                return False, {
                    "error": f"OpenAI API error: {response.status_code}",
                    "details": response.text
                }
            
            result = response.json()
            
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content'].strip()
                logger.info("Successfully received response from OpenAI")
                logger.info(f"========== OPENAI API RESPONSE ==========")
                logger.info(f"Response content: {content}")
                logger.info(f"Response length: {len(content)} characters")
                logger.info(f"========================================")
                return True, content
            else:
                logger.error(f"Unexpected OpenAI response format: {result}")
                return False, {
                    "error": "Unexpected response format",
                    "details": result
                }
                
        except requests.RequestException as e:
            logger.error(f"Request error: {e}")
            return False, {"error": f"Network error: {str(e)}"}
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return False, {"error": f"Invalid response format: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return False, {"error": f"Unexpected error: {str(e)}"}
    
    def translate(self, from_lang: str, to_lang: str, content: str) -> Tuple[bool, Union[str, Dict]]:
        """
        Translate content using OpenAI.
        
        Args:
            from_lang (str): Source language code or name
            to_lang (str): Target language code or name
            content (str): Content to translate
            
        Returns:
            Tuple[bool, Union[str, Dict]]: Success flag and translated text or error dict
        """
        if not content:
            return False, {"error": "No content provided for translation"}
        
        if from_lang == to_lang:
            return True, content
        
        # Check if content has timecodes that need to be preserved
        import re
        timecode_pattern = r'\[(\d{2}):(\d{2}):(\d{2})\]'
        has_timecodes = bool(re.search(timecode_pattern, content))
        
        logger.info(f"========== OPENAI TRANSLATION DEBUG ==========")
        logger.info(f"From: {from_lang} -> To: {to_lang}")
        logger.info(f"Content length: {len(content)} chars")
        logger.info(f"Content preview: {content[:300]}...")
        logger.info(f"Timecode detection: has_timecodes={has_timecodes}")
        
        if has_timecodes:
            logger.info("✅ USING TIMECODE-PRESERVING TRANSLATION")
            result = self._translate_with_timecodes(from_lang, to_lang, content)
            logger.info(f"========== TRANSLATION RESULT ==========")
            if result[0]:  # Success
                logger.info(f"Translation successful, length: {len(result[1]) if result[1] else 0}")
                logger.info(f"Result preview: {result[1][:300] if result[1] else 'None'}...")
            else:
                logger.error(f"Translation failed: {result[1]}")
            logger.info(f"======================================")
            return result
        else:
            logger.info("❌ USING STANDARD TRANSLATION (no timecodes detected)")
        
        # Map language codes to full names for better results
        lang_map = {
            'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
            'it': 'Italian', 'pt': 'Portuguese', 'ru': 'Russian', 'zh': 'Chinese',
            'ja': 'Japanese', 'ar': 'Arabic', 'bn': 'Bengali (বাংলা)', 'hi': 'Hindi',
            'ko': 'Korean', 'nl': 'Dutch', 'sv': 'Swedish', 'tr': 'Turkish'
        }
        
        # Languages that require special handling due to complex scripts or model limitations
        complex_languages = ['bn', 'ar', 'hi', 'zh', 'ja', 'ko']
        
        from_language = lang_map.get(from_lang.lower(), from_lang)
        to_language = lang_map.get(to_lang.lower(), to_lang)
        
        # Special handling for complex languages
        is_complex_target = to_lang.lower() in complex_languages
        
        if is_complex_target:
            # Enhanced prompt for complex languages
            if from_lang.lower() == 'auto':
                prompt = f"Translate the following ENTIRE text to {to_language}. You must translate ALL content - do not leave any part in the original language. Every single word and sentence must be translated to {to_language}. Do not mix languages:\n\n{content}"
            else:
                prompt = f"Translate the following ENTIRE text from {from_language} to {to_language}. You must translate ALL content - do not leave any part in {from_language}. Every single word and sentence must be translated to {to_language}. Do not mix languages:\n\n{content}"
            
            system_content = f"You are a professional translator specializing in {to_language}. Translate the ENTIRE text completely - every single word must be in {to_language}. Do NOT leave any part in the original language. Do NOT mix languages. Do NOT stop mid-sentence. Provide only the complete translation without any commentary."
        else:
            # Standard prompt for other languages
            if from_lang.lower() == 'auto':
                prompt = f"Translate the following text to {to_language}. If the source language is already {to_language}, just return the original text. Translate the ENTIRE text completely and avoid repetition:\n\n{content}"
            else:
                prompt = f"Translate the following text from {from_language} to {to_language}. Translate the ENTIRE text completely and avoid repetition:\n\n{content}"
            
            system_content = "You are a professional translator. Provide only the translated text without any additional commentary or explanation. Maintain the original formatting and structure. Translate the ENTIRE text completely - do not stop mid-sentence or repeat phrases. Ensure the translation is complete and coherent from start to finish."
        
        messages = [
            {
                "role": "system",
                "content": system_content
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        # Calculate appropriate max_tokens based on content length
        # Rough estimate: 1 token ≈ 0.75 words, allow 1.5x for translation expansion
        content_tokens = len(content.split()) * 1.33  # Convert words to estimated tokens
        
        # GPT-4o-mini has 128K context window, much more generous limits
        if "gpt-4" in self.model.lower():
            # GPT-4 models have much larger context windows
            max_tokens = max(4000, min(int(content_tokens * 1.5), 16000))  # Between 4K and 16K tokens
        else:
            # Fallback for GPT-3.5 or other models
            max_tokens = max(2000, min(int(content_tokens * 1.5), 4000))  # Between 2K and 4K tokens
        
        logger.info(f"Translation request - Content tokens estimate: {content_tokens}, Max tokens: {max_tokens}")
        
        # For very long content or complex languages, use chunking strategy
        # Use higher thresholds for GPT-4 models with larger context windows
        if "gpt-4" in self.model.lower():
            # GPT-4 can handle much larger content before chunking
            chunk_threshold = 50000  # 50K tokens for GPT-4 models
            complex_threshold = 30000  # 30K tokens for complex languages
        else:
            # Conservative thresholds for GPT-3.5
            chunk_threshold = 2500
            complex_threshold = 1500
        
        if content_tokens > chunk_threshold or (is_complex_target and content_tokens > complex_threshold):
            return self._translate_in_chunks(content, from_language, to_language, is_complex_target)
        
        # Use different parameters for complex languages
        if is_complex_target:
            success, result = self._make_request(messages, max_tokens=max_tokens, temperature=0.0, frequency_penalty=0.7, presence_penalty=0.5)
        else:
            success, result = self._make_request(messages, max_tokens=max_tokens, temperature=0.1, frequency_penalty=0.5, presence_penalty=0.3)
        
        # If we get a token limit error, automatically chunk the content
        if not success and isinstance(result, dict) and result.get('should_chunk'):
            logger.info("Auto-chunking due to token limit exceeded")
            return self._translate_in_chunks(content, from_language, to_language, is_complex_target)
        
        return success, result
    
    def _translate_in_chunks(self, content: str, from_language: str, to_language: str, is_complex: bool = False) -> Tuple[bool, Union[str, Dict]]:
        """
        Translate very long content by breaking it into smaller chunks.
        
        Args:
            content (str): Content to translate
            from_language (str): Source language name
            to_language (str): Target language name
            
        Returns:
            Tuple[bool, Union[str, Dict]]: Success flag and translated text or error dict
        """
        # Split content into sentences to avoid breaking mid-sentence
        sentences = content.replace('\n', ' ').split('. ')
        chunks = []
        current_chunk = ""
        
        # Group sentences into chunks - larger chunks for GPT-4 models
        if "gpt-4" in self.model.lower():
            chunk_size = 3000 if is_complex else 5000  # Much larger chunks for GPT-4
        else:
            chunk_size = 1000 if is_complex else 2000  # Conservative for other models
        for sentence in sentences:
            if len(current_chunk.split()) + len(sentence.split()) > chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                current_chunk += (". " if current_chunk else "") + sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        logger.info(f"Translating in {len(chunks)} chunks")
        
        translated_chunks = []
        for i, chunk in enumerate(chunks):
            logger.info(f"Translating chunk {i+1}/{len(chunks)}")
            
            if is_complex:
                prompt = f"Translate the following text from {from_language} to {to_language}. This is part {i+1} of {len(chunks)} of a longer text. You must translate ALL content - do not leave any part in {from_language}. Every single word must be in {to_language}:\n\n{chunk}"
                system_content = f"You are a professional translator specializing in {to_language}. Translate ALL text completely - every word must be in {to_language}. Do NOT mix languages. This is part of a longer translation."
                temp = 0.0
                freq_pen = 0.7
                pres_pen = 0.5
            else:
                prompt = f"Translate the following text from {from_language} to {to_language}. This is part {i+1} of {len(chunks)} of a longer text:\n\n{chunk}"
                system_content = "You are a professional translator. Provide only the translated text without any additional commentary or explanation. Maintain the original formatting and structure. This is part of a longer translation, so ensure continuity and coherence."
                temp = 0.1
                freq_pen = 0.5
                pres_pen = 0.3
            
            messages = [
                {
                    "role": "system",
                    "content": system_content
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
            
            # Use larger max_tokens for GPT-4 models in chunking
            chunk_max_tokens = 8000 if "gpt-4" in self.model.lower() else 3000
            success, result = self._make_request(messages, max_tokens=chunk_max_tokens, temperature=temp, frequency_penalty=freq_pen, presence_penalty=pres_pen)
            
            if not success:
                return False, result
            
            translated_chunks.append(result)
        
        # Join all translated chunks
        full_translation = " ".join(translated_chunks)
        logger.info(f"Chunked translation completed - Total length: {len(full_translation)}")
        
        # Validate translation for complex languages
        if is_complex:
            validation_result = self._validate_translation(full_translation, to_language)
            if not validation_result:
                logger.warning(f"Translation validation failed for {to_language} - attempting retry with stronger prompts")
                # Retry with even stronger prompts
                return self._retry_translation_with_strict_prompts(content, from_language, to_language)
        
        return True, full_translation
    
    def _translate_with_timecodes(self, from_lang: str, to_lang: str, content: str) -> Tuple[bool, Union[str, Dict]]:
        """
        Translate content while preserving timecodes in [HH:MM:SS] format.
        
        Args:
            from_lang (str): Source language code or name
            to_lang (str): Target language code or name
            content (str): Content with timecodes to translate
            
        Returns:
            Tuple[bool, Union[str, Dict]]: Success flag and translated text or error dict
        """
        import re
        
        logger.info(f"STARTING TIMECODE-PRESERVING TRANSLATION: {from_lang} -> {to_lang}")
        
        # Map language codes to full names for better results
        lang_map = {
            'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
            'it': 'Italian', 'pt': 'Portuguese', 'ru': 'Russian', 'zh': 'Chinese',
            'ja': 'Japanese', 'ar': 'Arabic', 'bn': 'Bengali (বাংলা)', 'hi': 'Hindi',
            'ko': 'Korean', 'nl': 'Dutch', 'sv': 'Swedish', 'tr': 'Turkish'
        }
        
        from_language = lang_map.get(from_lang.lower(), from_lang)
        to_language = lang_map.get(to_lang.lower(), to_lang)
        
        logger.info(f"Language mapping: {from_lang} -> {from_language}, {to_lang} -> {to_language}")
        
        # Split content into lines with timecodes
        lines = content.strip().split('\n')
        translated_lines = []
        
        logger.info(f"Processing {len(lines)} lines of content")
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Match timecode pattern [HH:MM:SS] followed by text
            timecode_match = re.match(r'^(\[\d{2}:\d{2}:\d{2}\])\s*(.*)$', line)
            
            if timecode_match:
                timecode = timecode_match.group(1)
                text_to_translate = timecode_match.group(2).strip()
                
                if text_to_translate:
                    # Translate just the text part, preserving the timecode
                    prompt = f"""Translate the following text from {from_language} to {to_language}.
                    
CRITICAL INSTRUCTIONS:
- Translate ONLY the text content
- Do NOT translate or modify the timecode
- Do NOT add any formatting, markers, or segment numbers
- Do NOT use ###SEGMENT_X### or any other markers
- Return ONLY the translated text, nothing else
- Preserve the original meaning and tone

Text to translate: {text_to_translate}"""

                    system_content = f"""You are a professional translator. Your task is to translate text while preserving timecodes.

CRITICAL RULES:
- Translate ONLY the text content to {to_language}
- Do NOT modify, translate, or remove timecodes [HH:MM:SS]
- Do NOT add segment markers like ###SEGMENT_X###
- Do NOT add any formatting or bullet points
- Return ONLY the translated text without any additional content
- Preserve the original tone and meaning"""

                    messages = [
                        {
                            "role": "system",
                            "content": system_content
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                    
                    # LOG THE EXACT REQUEST BEING SENT TO AI
                    logger.info(f"========== SENDING TO AI (Line with timecode {timecode}) ==========")
                    logger.info(f"System prompt: {system_content}")
                    logger.info(f"User prompt: {prompt}")
                    logger.info(f"Original text to translate: '{text_to_translate}'")
                    logger.info(f"Max tokens: 200, temperature: 0.1")
                    logger.info(f"====================================================================")
                    
                    success, translated_text = self._make_request(messages, max_tokens=200, temperature=0.1)
                    
                    # LOG THE AI RESPONSE
                    logger.info(f"========== AI RESPONSE (Line with timecode {timecode}) ==========")
                    if success:
                        logger.info(f"Translation successful: '{translated_text}'")
                    else:
                        logger.error(f"Translation failed: {translated_text}")
                    logger.info(f"=================================================================")
                    
                    if success:
                        # Clean up the translated text to remove any unwanted formatting
                        translated_text = translated_text.strip()
                        # Remove any segment markers that might have been added
                        translated_text = re.sub(r'###SEGMENT_\d+###\s*', '', translated_text)
                        translated_text = re.sub(r'\*+.*?\*+', '', translated_text)  # Remove markdown formatting
                        translated_text = translated_text.strip()
                        
                        # Combine timecode with translated text
                        translated_lines.append(f"{timecode} {translated_text}")
                    else:
                        logger.warning(f"Failed to translate line: {line}")
                        # Keep original line if translation fails
                        translated_lines.append(line)
                else:
                    # Empty text after timecode, keep timecode only
                    translated_lines.append(timecode)
            else:
                # Line without timecode, translate directly
                if line:
                    prompt = f"Translate this text from {from_language} to {to_language}: {line}"
                    system_content = f"Translate to {to_language} only. No additional formatting."
                    
                    messages = [
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": prompt}
                    ]
                    
                    success, translated_text = self._make_request(messages, max_tokens=200, temperature=0.1)
                    
                    if success:
                        translated_lines.append(translated_text.strip())
                    else:
                        translated_lines.append(line)
        
        # Join all translated lines
        final_translation = '\n'.join(translated_lines)
        
        logger.info(f"Timecode-preserving translation completed: {len(translated_lines)} lines")
        logger.info(f"Final translation preview: {final_translation[:300]}...")
        
        # Verify no segment markers were generated
        if '###SEGMENT_' in final_translation:
            logger.error("WARNING: Found ###SEGMENT markers in final translation!")
        else:
            logger.info("SUCCESS: No ###SEGMENT markers found in final translation")
        
        return True, final_translation
    
    def _retry_translation_with_strict_prompts(self, content: str, from_language: str, to_language: str) -> Tuple[bool, Union[str, Dict]]:
        """
        Retry translation with extremely strict prompts for problematic languages.
        
        Args:
            content (str): Content to translate
            from_language (str): Source language name  
            to_language (str): Target language name
            
        Returns:
            Tuple[bool, Union[str, Dict]]: Success flag and translated text or error dict
        """
        logger.info(f"Retrying translation with strict prompts for {to_language}")
        
        # Split into smaller chunks for better control
        sentences = content.replace('\n', ' ').split('. ')
        chunks = []
        current_chunk = ""
        
        # Use very small chunks for strict mode
        for sentence in sentences:
            if len(current_chunk.split()) + len(sentence.split()) > 300:  # Very small chunks
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                current_chunk += (". " if current_chunk else "") + sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        logger.info(f"Strict retry: translating in {len(chunks)} small chunks")
        
        translated_chunks = []
        for i, chunk in enumerate(chunks):
            logger.info(f"Strict retry chunk {i+1}/{len(chunks)}")
            
            # Extremely strict prompt
            prompt = f"""
CRITICAL INSTRUCTION: You MUST translate EVERY SINGLE WORD to {to_language}. 
DO NOT use ANY English words. DO NOT mix languages. DO NOT add formatting.
DO NOT add bullet points or asterisks. Just translate the text completely.

Translate this text to {to_language}:
{chunk}

Remember: EVERY word must be in {to_language}. NO English allowed.
"""
            
            system_content = f"""You are a {to_language} translation expert. Your ONLY job is to translate text to {to_language}.

CRITICAL RULES:
1. EVERY word must be in {to_language}
2. NO English words allowed AT ALL
3. NO mixing of languages
4. NO formatting like *word* or bullet points
5. NO explanations or commentary
6. Just provide the pure {to_language} translation

If you use ANY English words, you have FAILED."""
            
            messages = [
                {
                    "role": "system",
                    "content": system_content
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ]
            
            success, result = self._make_request(messages, max_tokens=1500, temperature=0.0, frequency_penalty=0.8, presence_penalty=0.6)
            
            if not success:
                return False, result
            
            # Validate each chunk
            english_count = sum(1 for phrase in ['Hello', 'I\'m', 'You', 'the', 'and', 'or', 'but', 'said', '*'] if phrase.lower() in result.lower())
            if english_count > 0:
                logger.warning(f"Chunk {i+1} still contains English words, retrying once more")
                # One more try with even stricter prompt
                stricter_prompt = f"Only translate to {to_language}. No English: {chunk}"
                stricter_messages = [
                    {"role": "system", "content": f"Translate ONLY to {to_language}. Use NO English words."},
                    {"role": "user", "content": stricter_prompt}
                ]
                success, result = self._make_request(stricter_messages, max_tokens=1000, temperature=0.0, frequency_penalty=0.9, presence_penalty=0.7)
                if not success:
                    return False, result
            
            translated_chunks.append(result)
        
        # Join all translated chunks
        full_translation = " ".join(translated_chunks)
        logger.info(f"Strict retry completed - Total length: {len(full_translation)}")
        
        return True, full_translation
    
    def _validate_translation(self, translation: str, target_lang: str) -> bool:
        """
        Validate that the translation is complete and in the target language.
        
        Args:
            translation (str): The translated text
            target_lang (str): Target language code
            
        Returns:
            bool: True if translation appears valid
        """
        # Check for common signs of incomplete translation
        english_phrases = [
            'Hello and welcome', 'I\'m', 'You know', 'Yeah', 'Oh', 'And I\'m',
            'said that', 'going to', 'click a link', 'email from', 'supposed to be',
            'technical difficulties', 'Please request', 'behind this party',
            '*JSON output*', '*HTML output*', '*Role playing*', '*Prompt engineering*',
            'the mic and I will', 'joining us shortly'
        ]
        
        # Count English phrases in the translation
        english_count = sum(1 for phrase in english_phrases if phrase.lower() in translation.lower())
        
        # Check for length ratio - translation should be roughly similar length
        original_length = len(translation)
        if target_lang == 'Bengali (বাংলা)' and original_length < 10000:  # Bengali should be substantial
            logger.warning(f"Translation too short for Bengali: {original_length} chars")
            return False
        
        # If more than 1 English phrase found for complex languages, likely incomplete
        if english_count > 1:
            logger.warning(f"Found {english_count} English phrases in {target_lang} translation")
            return False
            
        return True
    
    def summary(self, content: str, max_length: int = None, language: str = None) -> Tuple[bool, Union[str, Dict]]:
        """
        Generate a summary using OpenAI.
        
        Args:
            content (str): Content to summarize
            max_length (int, optional): Maximum length of summary in words
            language (str, optional): Language for the summary output
            
        Returns:
            Tuple[bool, Union[str, Dict]]: Success flag and summary or error dict
        """
        if not content:
            return False, {"error": "No content provided for summarization"}
        
        # Map language codes to full names
        lang_map = {
            'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
            'it': 'Italian', 'pt': 'Portuguese', 'ru': 'Russian', 'zh': 'Chinese',
            'ja': 'Japanese', 'ar': 'Arabic', 'bn': 'Bengali', 'hi': 'Hindi',
            'ko': 'Korean', 'nl': 'Dutch', 'sv': 'Swedish', 'tr': 'Turkish'
        }
        
        # Language parameter is now ignored - AI will use the language of the input text
        # Keeping the parameter for backward compatibility
        
        # Determine max_tokens based on max_length
        if max_length:
            max_tokens = min(max_length * 2, 1000)  # Rough estimate: 1 token ≈ 0.5 words
            length_instruction = f"in approximately {max_length} words"
        else:
            max_tokens = 500
            length_instruction = "concisely"
        
        prompt = f"""Summarize the following content {length_instruction}. Focus on the key points and main ideas:

{content}"""
        
        messages = [
            {
                "role": "system",
                "content": "You are a professional content summarizer. Provide clear, concise summaries that capture the essential information and main points. Use bullet points or paragraphs as appropriate. Maintain the same language as the input content."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        return self._make_request(messages, max_tokens=max_tokens, temperature=0.3)
    
    def get_supported_languages(self) -> List[Dict[str, str]]:
        """
        Get list of supported languages.
        
        Returns:
            List[Dict[str, str]]: List of language dictionaries
        """
        return [
            {"code": "en", "name": "English"},
            {"code": "es", "name": "Spanish"},
            {"code": "fr", "name": "French"},
            {"code": "de", "name": "German"},
            {"code": "it", "name": "Italian"},
            {"code": "pt", "name": "Portuguese"},
            {"code": "ru", "name": "Russian"},
            {"code": "zh", "name": "Chinese"},
            {"code": "ja", "name": "Japanese"},
            {"code": "ar", "name": "Arabic"},
            {"code": "bn", "name": "Bengali/Bangla"},
            {"code": "hi", "name": "Hindi"},
            {"code": "ko", "name": "Korean"},
            {"code": "nl", "name": "Dutch"},
            {"code": "sv", "name": "Swedish"},
            {"code": "tr", "name": "Turkish"},
            {"code": "vi", "name": "Vietnamese"},
            {"code": "pl", "name": "Polish"},
            {"code": "da", "name": "Danish"},
            {"code": "fi", "name": "Finnish"},
            {"code": "no", "name": "Norwegian"},
            {"code": "th", "name": "Thai"},
            {"code": "id", "name": "Indonesian"},
            {"code": "ms", "name": "Malay"},
            {"code": "tl", "name": "Filipino"},
            {"code": "uk", "name": "Ukrainian"},
            {"code": "cs", "name": "Czech"},
            {"code": "sk", "name": "Slovak"},
            {"code": "hu", "name": "Hungarian"},
            {"code": "ro", "name": "Romanian"},
            {"code": "bg", "name": "Bulgarian"},
            {"code": "hr", "name": "Croatian"},
            {"code": "sr", "name": "Serbian"},
            {"code": "sl", "name": "Slovenian"},
            {"code": "et", "name": "Estonian"},
            {"code": "lv", "name": "Latvian"},
            {"code": "lt", "name": "Lithuanian"}
        ]

# Example usage
if __name__ == "__main__":
    import os
    
    # You would normally get this from your config
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Please set OPENAI_API_KEY environment variable")
        exit(1)
    
    openai_provider = OpenAI(api_key)
    
    # Test translation
    print("Testing translation:")
    success, result = openai_provider.translate("en", "es", "Hello, how are you today?")
    if success:
        print(f"Translation: {result}")
    else:
        print(f"Error: {result}")
    
    # Test summarization
    print("\nTesting summarization:")
    long_text = """
    Artificial intelligence (AI) is intelligence demonstrated by machines, in contrast to the natural intelligence displayed by humans and animals. Leading AI textbooks define the field as the study of intelligent agents: any device that perceives its environment and takes actions that maximize its chance of successfully achieving its goals. Colloquially, the term artificial intelligence is often used to describe machines that mimic cognitive functions that humans associate with the human mind, such as learning and problem solving.
    """
    success, result = openai_provider.summary(long_text.strip(), max_length=50)
    if success:
        print(f"Summary: {result}")
    else:
        print(f"Error: {result}")