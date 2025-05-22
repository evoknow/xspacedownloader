#!/usr/bin/env python3
"""
Simple tool to use libretranslatepy directly without a server
"""

import argparse
from libretranslatepy import LibreTranslate

def main():
    parser = argparse.ArgumentParser(description='Translate text using libretranslatepy')
    parser.add_argument('--text', type=str, help='Text to translate', required=True)
    parser.add_argument('--source', type=str, help='Source language', default='auto')
    parser.add_argument('--target', type=str, help='Target language', required=True)
    
    args = parser.parse_args()
    
    # Initialize LibreTranslate
    lt = LibreTranslate()
    
    # If source is auto, try to detect language
    if args.source == 'auto':
        detection = lt.detect(args.text)
        if detection and len(detection) > 0:
            source_lang = detection[0]['language']
            confidence = detection[0]['confidence']
            print(f"Detected language: {source_lang} (confidence: {confidence:.2f})")
        else:
            source_lang = 'en'
            print("Could not detect language, using English as default")
    else:
        source_lang = args.source
        
    # Get available languages
    languages = lt.languages()
    lang_list = []
    for lang in languages:
        lang_list.append(f"{lang['name']} ({lang['code']})")
    print(f"Available languages: {', '.join(lang_list)}")
    
    # Translate
    print(f"\nTranslating from {source_lang} to {args.target}...")
    print(f"Original: {args.text}")
    
    try:
        result = lt.translate(args.text, source_lang, args.target)
        print(f"Translation: {result}")
    except Exception as e:
        print(f"Error: {e}")
        
if __name__ == "__main__":
    main()