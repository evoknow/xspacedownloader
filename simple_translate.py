#!/usr/bin/env python3
"""
Simple script to demonstrate the Python libretranslatepy library.
This shows how to use LibreTranslate API without setting up a local server.
"""

import sys
from libretranslatepy import LibreTranslateAPI

def main():
    # Initialize LibreTranslate API
    # If you have an API key, you can specify it here
    api_key = None
    if len(sys.argv) > 1:
        api_key = sys.argv[1]
        print(f"Using provided API key: {api_key[:4]}..." if api_key and len(api_key) > 4 else "Using provided API key")
    
    # Connect to the public LibreTranslate API
    lt = LibreTranslateAPI("https://libretranslate.com/", api_key=api_key)
    
    # Test translation
    try:
        # Get available languages
        languages = lt.languages()
        print(f"Available languages: {', '.join([lang['name'] for lang in languages])}")
        
        # Simple translation example
        text = "Hello, world!"
        source_lang = "en"
        target_lang = "es"
        
        print(f"\nTranslating from {source_lang} to {target_lang}:")
        print(f"Original: {text}")
        
        result = lt.translate(text, source_lang, target_lang)
        print(f"Translation: {result}")
        
        # Detect language example
        detect_text = "Bonjour, comment allez-vous?"
        print(f"\nDetecting language for: '{detect_text}'")
        detected = lt.detect(detect_text)
        detected_lang = detected[0]['language']
        confidence = detected[0]['confidence']
        print(f"Detected language: {detected_lang} (confidence: {confidence:.2f})")
        
    except Exception as e:
        print(f"Error: {e}")
        print("\nIf you're seeing API errors, you might need an API key.")
        print("Get an API key from: https://portal.libretranslate.com/")
        print("Then run: python simple_translate.py YOUR_API_KEY")

if __name__ == "__main__":
    main()