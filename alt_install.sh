#!/bin/bash
# Alternative installer for translation using translate package

echo "Installing alternative translate package..."

pip install translate
pip install langdetect

# Create test script
cat > test_translate.py << 'EOL'
#!/usr/bin/env python3
"""
Simple test script for translate package
"""
from translate import Translator
import argparse
from langdetect import detect

def main():
    parser = argparse.ArgumentParser(description='Translate text using translate package')
    parser.add_argument('--text', type=str, help='Text to translate', required=True)
    parser.add_argument('--source', type=str, help='Source language', default='auto')
    parser.add_argument('--target', type=str, help='Target language', required=True)
    
    args = parser.parse_args()
    
    # If source is auto, detect language
    if args.source == 'auto':
        try:
            source_lang = detect(args.text)
            print(f"Detected language: {source_lang}")
        except:
            source_lang = 'en'
            print("Could not detect language, using English as default")
    else:
        source_lang = args.source
    
    # Translate text
    translator = Translator(to_lang=args.target, from_lang=source_lang)
    result = translator.translate(args.text)
    
    print(f"\nTranslating from {source_lang} to {args.target}...")
    print(f"Original: {args.text}")
    print(f"Translation: {result}")

if __name__ == "__main__":
    main()
EOL

chmod +x test_translate.py

# Update the Translate component
cat > alt_translate.py << 'EOL'
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
EOL

# Update configuration
sed -i.bak3 's/"api_url": ".*"/"api_url": "direct"/g' mainconfig.json

echo ""
echo "Alternative translation package installed!"
echo ""
echo "To test translation, run:"
echo ""
echo "python test_translate.py --text \"Hello, world!\" --target es"
echo ""
echo "Update your code to use SimpleTranslate from alt_translate.py"