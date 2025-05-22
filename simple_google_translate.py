#!/usr/bin/env python3
"""
Super simple translator using googletrans
"""

from googletrans import Translator
import sys

def main():
    # Process arguments
    if len(sys.argv) < 3:
        print("Usage: python simple_google_translate.py 'Text to translate' target_language [source_language]")
        print("Example: python simple_google_translate.py 'Hello world' es")
        print("Example with source: python simple_google_translate.py 'Hola mundo' en es")
        sys.exit(1)
        
    text = sys.argv[1]
    target_lang = sys.argv[2]
    source_lang = sys.argv[3] if len(sys.argv) > 3 else None
    
    # Initialize translator
    translator = Translator()
    
    # Detect language if not provided
    if not source_lang:
        try:
            detection = translator.detect(text)
            source_lang = detection.lang
            confidence = detection.confidence
            print(f"Detected language: {source_lang} (confidence: {confidence:.2f})")
        except Exception as e:
            print(f"Error detecting language: {e}")
            source_lang = 'en'
            print("Using English as default source language")
    
    # Translate
    try:
        if source_lang:
            result = translator.translate(text, dest=target_lang, src=source_lang)
        else:
            result = translator.translate(text, dest=target_lang)
            
        print(f"\nOriginal ({result.src}): {text}")
        print(f"Translation ({result.dest}): {result.text}")
        
    except Exception as e:
        print(f"Translation error: {e}")

if __name__ == "__main__":
    main()