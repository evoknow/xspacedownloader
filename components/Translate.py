#!/usr/bin/env python3
# components/Translate.py
"""Translation component for XSpace Downloader using AI providers."""

import os
import json
import logging
from typing import Dict, List, Optional, Union, Tuple
from .CostAwareAI import CostAwareAI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Translate:
    """Translation component that uses AI providers for translation."""
    
    def __init__(self, api_url=None, api_key=None, config_file="mainconfig.json"):
        """
        Initialize the Translate component.
        
        Args:
            api_url (str, optional): Not used - kept for compatibility
            api_key (str, optional): Not used - kept for compatibility
            config_file (str, optional): Path to the configuration file
        """
        self.config_file = config_file
        self.ai = None
        self.self_hosted = True  # Set to True to avoid API key warnings
        self.api_key = "configured"  # Fake value to avoid warnings
        self.api_url = "AI-powered translation"  # Descriptive value for web API
        
        try:
            self.ai = CostAwareAI()
            logger.info(f"Translation component initialized using CostAware AI provider: {self.ai.get_provider_name()}")
            self.api_key = "AI-configured"
        except Exception as e:
            logger.error(f"Failed to initialize CostAware AI component: {e}")
            self.ai = None
            self.api_key = None
            self.api_url = "AI component not available - check API keys"
        
        # Get available languages from AI provider
        if self.ai:
            self.available_languages = self.ai.get_supported_languages()
        else:
            # Fallback language list
            self.available_languages = [
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
                {"code": "ko", "name": "Korean"}
            ]
    
    def get_languages(self) -> List[Dict[str, str]]:
        """
        Get the list of available languages for translation.
        
        Returns:
            List[Dict[str, str]]: List of language dictionaries with code and name
        """
        return self.available_languages
    
    def translate(self, text: str, source_lang: str, target_lang: str, space_id: str = None) -> Tuple[bool, Union[str, Dict]]:
        """
        Translate text from source language to target language.
        
        Args:
            text (str): The text to translate
            source_lang (str): The source language code (e.g., 'en', 'es')
            target_lang (str): The target language code (e.g., 'en', 'es')
            space_id (str, optional): Space ID for cost tracking
            
        Returns:
            Tuple[bool, Union[str, Dict]]: A tuple containing:
                - Success flag (True if successful, False otherwise)
                - Either the translated text (if successful) or an error dictionary
        """
        if not self.ai:
            return False, {
                "error": "AI provider not available",
                "details": "Please configure an AI provider (OpenAI or Claude) in mainconfig.json"
            }
        
        if not text:
            return False, {"error": "No text provided for translation"}
            
        if source_lang == target_lang:
            return True, text
        
        # Complex languages that often have issues with GPT-3.5
        problematic_languages = ['bn', 'ar', 'hi', 'th', 'ko', 'ja']
        
        try:
            # Use cost tracking version if space_id is provided
            if space_id:
                success, result = self.ai.translate_with_cost_tracking(space_id, source_lang, target_lang, text)
            else:
                success, result = self.ai.translate(source_lang, target_lang, text)
            
            # If translation failed or is for a problematic language, try with Claude if available
            if (not success or target_lang.lower() in problematic_languages) and hasattr(self, '_try_claude_fallback'):
                logger.info(f"Attempting Claude fallback for {target_lang} translation")
                claude_success, claude_result = self._try_claude_fallback(source_lang, target_lang, text)
                if claude_success:
                    logger.info(f"Claude fallback successful for {target_lang}")
                    return True, claude_result
            
            return success, result
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return False, {"error": f"Translation error: {str(e)}"}
    
    def _try_claude_fallback(self, source_lang: str, target_lang: str, text: str) -> Tuple[bool, Union[str, Dict]]:
        """
        Try translation with Claude as fallback.
        
        Args:
            source_lang (str): Source language code
            target_lang (str): Target language code  
            text (str): Text to translate
            
        Returns:
            Tuple[bool, Union[str, Dict]]: Success flag and result
        """
        try:
            from .Claude import Claude
            import os
            
            # Check if Claude API key is available
            api_key = os.getenv('ANTHROPIC_API_KEY')
            if not api_key:
                logger.warning("Claude fallback not available - no API key")
                return False, {"error": "Claude API key not available"}
            
            # Create Claude instance
            claude = Claude(api_key)
            
            # Try translation with Claude
            return claude.translate(source_lang, target_lang, text)
            
        except Exception as e:
            logger.error(f"Claude fallback error: {e}")
            return False, {"error": f"Claude fallback error: {str(e)}"}
    
    def detect_language(self, text: str) -> Tuple[bool, Union[str, Dict]]:
        """
        Detect the language of the provided text.
        
        Args:
            text (str): The text to analyze
            
        Returns:
            Tuple[bool, Union[str, Dict]]: A tuple containing:
                - Success flag (True if successful, False otherwise)
                - Either the detected language code (if successful) or an error dictionary
        """
        if not text:
            return False, {"error": "No text provided for language detection"}
        
        # Simple language detection fallback
        try:
            # Count non-ASCII characters
            non_ascii_count = sum(1 for c in text if ord(c) > 127)
            non_ascii_ratio = non_ascii_count / len(text) if len(text) > 0 else 0
            
            # Check for specific scripts
            has_cyrillic = any(0x0400 <= ord(c) <= 0x04FF for c in text)
            has_arabic = any(0x0600 <= ord(c) <= 0x06FF for c in text)
            has_devanagari = any(0x0900 <= ord(c) <= 0x097F for c in text)
            has_bengali = any(0x0980 <= ord(c) <= 0x09FF for c in text)
            has_cjk = any((0x4E00 <= ord(c) <= 0x9FFF or  # CJK Unified
                          0x3040 <= ord(c) <= 0x30FF or   # Japanese
                          0xAC00 <= ord(c) <= 0xD7A3)     # Korean
                         for c in text)
            
            # Determine language based on script
            if has_cyrillic:
                detected_lang = "ru"
            elif has_arabic:
                detected_lang = "ar"
            elif has_devanagari:
                detected_lang = "hi"
            elif has_bengali:
                detected_lang = "bn"
            elif has_cjk:
                if any(0x3040 <= ord(c) <= 0x30FF for c in text):
                    detected_lang = "ja"
                elif any(0xAC00 <= ord(c) <= 0xD7A3 for c in text):
                    detected_lang = "ko"
                else:
                    detected_lang = "zh"
            else:
                detected_lang = "en"  # Default to English for Latin scripts

            logger.info(f"Language detected: {detected_lang}")
            return True, detected_lang
                
        except Exception as e:
            logger.error(f"Language detection error: {e}")
            return False, {"error": f"Language detection error: {str(e)}"}
    
    def summary(self, content: str, max_length: int = None, language: str = None, space_id: str = None) -> Tuple[bool, Union[str, Dict]]:
        """
        Generate a summary of the given content using AI.
        
        Args:
            content (str): Content to summarize
            max_length (int, optional): Maximum length of summary in words
            language (str, optional): Language for the summary output
            space_id (str, optional): Space ID for cost tracking
            
        Returns:
            Tuple[bool, Union[str, Dict]]: Success flag and summary or error dict
        """
        if not self.ai:
            return False, {
                "error": "AI provider not available",
                "details": "Please configure an AI provider (OpenAI or Claude) in mainconfig.json"
            }
        
        if not content:
            return False, {"error": "No content provided for summarization"}
        
        try:
            # Use cost tracking version if space_id is provided
            if space_id:
                return self.ai.summary_with_cost_tracking(space_id, content, max_length)
            else:
                # Pass language parameter if AI provider supports it
                # Check if the AI provider's summary method accepts language parameter
                import inspect
                sig = inspect.signature(self.ai.summary)
                params = sig.parameters
                
                if 'language' in params:
                    # AI provider supports language parameter
                    return self.ai.summary(content, max_length, language)
                else:
                    # Fallback to basic summary without language
                    return self.ai.summary(content, max_length)
        except Exception as e:
            logger.error(f"Summarization error: {e}")
            return False, {"error": f"Summarization error: {str(e)}"}


# Example usage
if __name__ == "__main__":
    # Initialize the translator
    translator = Translate()
    
    # Test translation
    print("Testing translation:")
    text = "Hello, how are you today?"
    success, result = translator.translate(text, "en", "es")
    
    if success:
        print(f"Original: {text}")
        print(f"Translation: {result}")
    else:
        print(f"Translation error: {result}")
    
    # Test summarization
    print("\nTesting summarization:")
    long_text = """
    Artificial intelligence (AI) is intelligence demonstrated by machines, in contrast to the natural intelligence displayed by humans and animals. Leading AI textbooks define the field as the study of intelligent agents: any device that perceives its environment and takes actions that maximize its chance of successfully achieving its goals. Colloquially, the term artificial intelligence is often used to describe machines that mimic cognitive functions that humans associate with the human mind, such as learning and problem solving.
    """
    success, result = translator.summary(long_text.strip(), max_length=50)
    
    if success:
        print(f"Summary: {result}")
    else:
        print(f"Summary error: {result}")
    
    # Test language detection
    print("\nTesting language detection:")
    test_texts = [
        "Hello world",
        "Hola mundo", 
        "こんにちは",
        "नमस्ते दुनिया",
        "বিশ্ব নমস্কার"
    ]
    
    for test_text in test_texts:
        success, lang = translator.detect_language(test_text)
        if success:
            print(f"Text: {test_text} => Language: {lang}")
        else:
            print(f"Error: {lang}")