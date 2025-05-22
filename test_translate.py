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
