#!/usr/bin/env python3
"""
Super simple text translator using requests directly
"""

import requests
import json
import sys
import urllib.parse
import random
import time

def translate_text(text, target_lang, source_lang=None):
    """
    Translate text using a free translation API.
    No API key required.
    """
    # Use MyMemory API
    base_url = "https://api.mymemory.translated.net/get"
    
    # Create a language pair string
    if source_lang:
        lang_pair = f"{source_lang}|{target_lang}"
    else:
        lang_pair = f"auto|{target_lang}"
    
    # Add a random email to avoid rate limiting
    # Generate a random email for demo purposes
    random_email = f"user{random.randint(1000, 9999)}@example.com"
    
    # Parameters
    params = {
        'q': text,
        'langpair': lang_pair,
        'de': random_email
    }
    
    try:
        # Make the request
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        
        # Parse the response
        data = response.json()
        
        if 'responseData' in data and 'translatedText' in data['responseData']:
            return {
                'success': True,
                'text': data['responseData']['translatedText'],
                'source_lang': source_lang or 'auto',
                'target_lang': target_lang
            }
        else:
            error_msg = data.get('responseDetails', 'Unknown error')
            return {
                'success': False,
                'error': error_msg
            }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def get_supported_languages():
    """
    Return a list of supported languages.
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
        {"code": "hi", "name": "Hindi"},
        {"code": "bn", "name": "Bengali"},
        {"code": "ko", "name": "Korean"},
        {"code": "nl", "name": "Dutch"},
        {"code": "tr", "name": "Turkish"},
        {"code": "pl", "name": "Polish"},
        {"code": "sv", "name": "Swedish"},
        {"code": "fi", "name": "Finnish"},
        {"code": "da", "name": "Danish"},
        {"code": "no", "name": "Norwegian"}
    ]

def detect_language(text):
    """
    Simple language detection based on character sets.
    """
    # This is a very simplistic detection - only useful for major scripts
    # For real applications, use a proper language detection library
    
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
        return "ru"  # Russian (simplified)
    elif has_arabic:
        return "ar"  # Arabic
    elif has_devanagari:
        return "hi"  # Hindi
    elif has_bengali:
        return "bn"  # Bengali
    elif has_cjk:
        # Very crude - in reality we'd need more sophisticated detection
        if any(0x3040 <= ord(c) <= 0x30FF for c in text):
            return "ja"  # Japanese
        elif any(0xAC00 <= ord(c) <= 0xD7A3 for c in text):
            return "ko"  # Korean
        else:
            return "zh"  # Chinese
    
    # For Latin scripts, this is very inaccurate but provides a fallback
    return "en"  # Default to English for Latin script

def main():
    # Show usage if no arguments
    if len(sys.argv) < 3:
        languages = get_supported_languages()
        print("Simple Text Translator")
        print("---------------------")
        print("Usage: python simple_language_translate.py 'text' target_lang [source_lang]")
        print("Example: python simple_language_translate.py 'Hello world' es")
        print("\nSupported languages:")
        for lang in languages:
            print(f"  {lang['code']} - {lang['name']}")
        return
    
    # Get command line arguments
    text = sys.argv[1]
    target_lang = sys.argv[2]
    source_lang = sys.argv[3] if len(sys.argv) > 3 else None
    
    # If source language not provided, try to detect it
    if not source_lang:
        source_lang = detect_language(text)
        print(f"Detected language: {source_lang}")
    
    # Translate the text
    print(f"Translating from {source_lang} to {target_lang}...")
    result = translate_text(text, target_lang, source_lang)
    
    # Print the result
    if result['success']:
        print(f"\nOriginal ({source_lang}): {text}")
        print(f"Translation ({target_lang}): {result['text']}")
    else:
        print(f"Error: {result['error']}")

# Simple component class that follows the interface
class SimpleTranslate:
    def __init__(self):
        self.available_languages = get_supported_languages()
    
    def get_languages(self):
        return self.available_languages
    
    def translate(self, text, source_lang, target_lang):
        if not text:
            return False, {"error": "No text provided for translation"}
            
        if source_lang == target_lang:
            return True, text  # No translation needed
        
        result = translate_text(text, target_lang, source_lang)
        
        if result['success']:
            return True, result['text']
        else:
            return False, {"error": result['error']}
    
    def detect_language(self, text):
        if not text:
            return False, {"error": "No text provided for language detection"}
        
        lang = detect_language(text)
        return True, lang

if __name__ == "__main__":
    main()