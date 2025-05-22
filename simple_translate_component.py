#!/usr/bin/env python3
"""
Simple Translate component that uses googletrans
This can be imported directly into your application
"""

import logging
from typing import Dict, List, Optional, Union, Tuple
from googletrans import Translator, LANGUAGES

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimpleTranslate:
    """Simple translation component using googletrans package."""
    
    def __init__(self):
        """Initialize the translator component."""
        self.translator = Translator()
        self.available_languages = [
            {"code": code, "name": name.capitalize()} 
            for code, name in LANGUAGES.items()
        ]
        logger.info(f"Simple translator initialized with {len(self.available_languages)} languages")
        
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
            # If source language is 'auto', don't specify it
            if source_lang == 'auto':
                result = self.translator.translate(text, dest=target_lang)
                source_lang = result.src  # Get the detected language
            else:
                result = self.translator.translate(text, src=source_lang, dest=target_lang)
            
            logger.info(f"Successfully translated text from {source_lang} to {target_lang}")
            return True, result.text
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return False, {"error": f"Translation error: {str(e)}"}
            
    def detect_language(self, text: str) -> Tuple[bool, Union[str, Dict]]:
        """Detect the language of the provided text."""
        if not text:
            return False, {"error": "No text provided for language detection"}
            
        try:
            detection = self.translator.detect(text)
            logger.info(f"Detected language: {detection.lang} (confidence: {detection.confidence:.2f})")
            return True, detection.lang
        except Exception as e:
            logger.error(f"Language detection error: {e}")
            return False, {"error": f"Language detection error: {str(e)}"}

# Example usage
if __name__ == "__main__":
    translator = SimpleTranslate()
    
    # Print available languages
    print("Available languages:")
    for lang in translator.get_languages()[:10]:  # Show first 10 languages
        print(f"  {lang['name']} ({lang['code']})")
    print(f"  ... and {len(translator.get_languages()) - 10} more")
    
    # Test translation
    print("\nTranslation test:")
    text = "Hello, how are you today?"
    success, result = translator.translate(text, "en", "es")
    
    if success:
        print(f"Original: {text}")
        print(f"Translation: {result}")
    else:
        print(f"Error: {result}")
        
    # Test language detection
    print("\nLanguage detection test:")
    texts = [
        "Hello world",
        "Hola mundo",
        "Bonjour le monde",
        "Hallo Welt",
        "こんにちは世界",
        "مرحبا بالعالم",
        "हैलो वर्ल्ड"
    ]
    
    for sample in texts:
        success, lang = translator.detect_language(sample)
        if success:
            print(f"Text: {sample} => Language: {lang}")
        else:
            print(f"Error detecting language for '{sample}': {lang}")