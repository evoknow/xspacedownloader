#!/usr/bin/env python3
"""Test script to verify language detection functionality."""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from components.SpeechToText import SpeechToText

def test_language_detection():
    print("Testing Language Detection Functionality...\n")
    
    stt = SpeechToText()
    
    # Test samples in different languages
    test_samples = {
        "English": "Hello, this is a test of the emergency broadcast system. We have been working on this project for a long time and we think it will be very helpful for everyone.",
        "Bengali": "আমি বাংলা ভাষায় কথা বলছি। এটি একটি পরীক্ষা। আমাদের দেশের ভাষা বাংলা এবং আমরা এই ভাষায় গর্বিত।",
        "Hindi": "मैं हिंदी में बात कर रहा हूं। यह एक परीक्षा है। हमारे देश की भाषा हिंदी है और हम इस भाषा पर गर्व करते हैं।",
        "Arabic": "مرحبا، هذا اختبار للنظام. نحن نعمل على هذا المشروع منذ وقت طويل ونعتقد أنه سيكون مفيدا جدا للجميع.",
        "Spanish": "Hola, esta es una prueba del sistema. Hemos estado trabajando en este proyecto durante mucho tiempo y creemos que será muy útil para todos.",
        "French": "Bonjour, ceci est un test du système. Nous travaillons sur ce projet depuis longtemps et nous pensons qu'il sera très utile pour tout le monde.",
        "German": "Hallo, das ist ein Test des Systems. Wir arbeiten schon lange an diesem Projekt und glauben, dass es für alle sehr hilfreich sein wird."
    }
    
    print("Testing language detection with sample texts:")
    print("=" * 60)
    
    for expected_lang, text in test_samples.items():
        detected = stt._detect_language_from_text(text)
        
        # Map our short codes to full names for better display
        lang_names = {
            'en': 'English',
            'bn': 'Bengali', 
            'hi': 'Hindi',
            'ar': 'Arabic',
            'ur': 'Urdu',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'unknown': 'Unknown'
        }
        
        detected_name = lang_names.get(detected, detected)
        status = "✓" if (
            (expected_lang == "English" and detected == "en") or
            (expected_lang == "Bengali" and detected == "bn") or
            (expected_lang == "Hindi" and detected == "hi") or
            (expected_lang == "Arabic" and detected in ["ar", "ur"]) or  # Arabic/Urdu can be confused
            (expected_lang == "Spanish" and detected == "es") or
            (expected_lang == "French" and detected == "fr") or
            (expected_lang == "German" and detected == "de")
        ) else "✗"
        
        print(f"{status} Expected: {expected_lang:10} | Detected: {detected_name:10} ({detected})")
        print(f"  Sample: {text[:80]}...")
        print()
    
    print("Testing edge cases:")
    print("-" * 40)
    
    edge_cases = {
        "Empty text": "",
        "Very short": "Hi",
        "Numbers only": "123 456 789",
        "Mixed scripts": "Hello নমস্কার मेरे दोस্त",
        "Punctuation": "!!! ??? ... ---"
    }
    
    for case_name, text in edge_cases.items():
        detected = stt._detect_language_from_text(text)
        detected_name = lang_names.get(detected, detected)
        print(f"{case_name:15}: {detected_name:10} ({detected})")
        if text:
            print(f"                 Text: '{text}'")
        print()
    
    print("✓ Language detection test completed!")

if __name__ == "__main__":
    test_language_detection()