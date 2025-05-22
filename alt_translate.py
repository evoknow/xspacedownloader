#!/usr/bin/env python3
"""
Simple translator component using translate package
"""

from translate import Translator
from langdetect import detect, LangDetectException
import json
import logging
from typing import Dict, List, Optional, Union, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimpleTranslate:
    """Simple translation component using translate package."""
    
    def __init__(self):
        """Initialize the translator component."""
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
        logger.info("Simple translator initialized")
        
    def get_languages(self) -> List[Dict[str, str]]:
        """Get list of available languages."""
        return self.available_languages
    
    def translate(self, text: str, source_lang: str, target_lang: str) -> Tuple[bool, Union[str, Dict]]:
        """Translate text from source language to target language."""
        if not text:
            return False, {"error": "No text provided for translation"}
            
        if source_lang == target_lang:
            return True, text  # No translation needed
        
        try:
            # If source language is 'auto', detect it
            if source_lang == 'auto':
                try:
                    source_lang = detect(text)
                    logger.info(f"Detected language: {source_lang}")
                except LangDetectException:
                    source_lang = 'en'
                    logger.warning("Could not detect language, using English as default")
            
            # Create translator and translate text
            translator = Translator(to_lang=target_lang, from_lang=source_lang)
            result = translator.translate(text)
            
            logger.info(f"Successfully translated text from {source_lang} to {target_lang}")
            return True, result
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return False, {"error": f"Translation error: {str(e)}"}
            
    def detect_language(self, text: str) -> Tuple[bool, Union[str, Dict]]:
        """Detect the language of the provided text."""
        if not text:
            return False, {"error": "No text provided for language detection"}
            
        try:
            lang = detect(text)
            logger.info(f"Detected language: {lang}")
            return True, lang
        except LangDetectException as e:
            logger.error(f"Language detection error: {e}")
            return False, {"error": f"Language detection error: {str(e)}"}

# Example usage
if __name__ == "__main__":
    translator = SimpleTranslate()
    
    # Test translation
    text = "Hello, how are you?"
    success, result = translator.translate(text, "en", "es")
    
    if success:
        print(f"Translation: {result}")
    else:
        print(f"Error: {result}")
