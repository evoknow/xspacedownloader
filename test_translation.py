#!/usr/bin/env python3
"""
Test script for the Translation component.
This script demonstrates how to use the Translate component with different configurations.
"""

import sys
import json
from components.Translate import Translate

def main():
    """Main function to test translation functionality."""
    # Parse command line arguments
    api_key = None
    if len(sys.argv) > 1:
        api_key = sys.argv[1]
        print(f"Using provided API key: {api_key[:4]}..." if api_key and len(api_key) > 4 else "Using provided API key")
    
    # Initialize translation component
    if api_key:
        translator = Translate(api_key=api_key)
    else:
        translator = Translate()
    
    # Display configuration
    print("\n=== Translation Configuration ===")
    print(f"API URL: {translator.api_url}")
    print(f"API Key configured: {'Yes' if translator.api_key else 'No'}")
    print(f"Self-hosted mode: {'Yes' if translator.self_hosted else 'No'}")
    
    # Get available languages
    print("\n=== Available Languages ===")
    languages = translator.get_languages()
    if languages:
        for lang in languages:
            print(f"- {lang.get('name', 'Unknown')} ({lang.get('code', 'unknown')})")
    else:
        print("No languages available. Check your configuration.")
    
    # Test translation
    test_texts = [
        ("Hello, how are you today?", "en", "es"),
        ("The quick brown fox jumps over the lazy dog.", "en", "fr"),
        ("Bonjour, comment allez-vous aujourd'hui?", "fr", "en"),
    ]
    
    print("\n=== Translation Tests ===")
    for text, source, target in test_texts:
        print(f"\nTranslating from {source} to {target}:")
        print(f"Original: '{text}'")
        
        success, result = translator.translate(text, source, target)
        
        if success:
            print(f"Translation: '{result}'")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
            if 'details' in result:
                print(f"Details: {json.dumps(result.get('details'), indent=2)}")
    
    # Test language detection
    test_detection_texts = [
        "Hello, this is English text.",
        "Hola, este es un texto en español.",
        "Bonjour, c'est un texte en français.",
        "こんにちは、これは日本語のテキストです。",
    ]
    
    print("\n=== Language Detection Tests ===")
    for text in test_detection_texts:
        print(f"\nDetecting language for: '{text[:40]}...' if len(text) > 40 else text")
        
        success, result = translator.detect_language(text)
        
        if success:
            print(f"Detected language: {result}")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
            if 'details' in result:
                print(f"Details: {json.dumps(result.get('details'), indent=2)}")
    
    print("\n=== Usage Instructions ===")
    print("1. To use LibreTranslate's hosted service:")
    print("   - Get an API key from https://portal.libretranslate.com/")
    print("   - Add the API key to mainconfig.json in the 'translate' section")
    print("   - Or run this script with the API key as an argument: ./test_translation.py YOUR_API_KEY")
    print()
    print("2. To use a self-hosted LibreTranslate instance:")
    print("   - Set 'self_hosted' to true in mainconfig.json")
    print("   - Configure 'self_hosted_url' to point to your local instance")
    print()
    print("Note: Without a valid API key or self-hosted instance, translation will fail with authorization errors.")

if __name__ == "__main__":
    main()