#!/usr/bin/env python3
"""
Test script for the AI component system.
This demonstrates how to use OpenAI and Claude for translation and summarization.
API keys are read from environment variables.
"""

import os
import sys
import json
from components.AI import AI

def main():
    # Check for OpenAI API key
    openai_key = os.getenv('OPENAI_API_KEY')
    claude_key = os.getenv('ANTHROPIC_API_KEY')
    
    if not openai_key and not claude_key:
        print("Error: No AI API keys found in environment variables.")
        print("Please set either OPENAI_API_KEY or ANTHROPIC_API_KEY")
        print("")
        print("Examples:")
        print("  export OPENAI_API_KEY='sk-your-openai-api-key'")
        print("  export ANTHROPIC_API_KEY='your-anthropic-api-key'")
        return
    
    # Determine which provider to use based on available keys
    if openai_key:
        provider = 'openai'
        print("Using OpenAI API key from environment")
    elif claude_key:
        provider = 'claude'
        print("Using Anthropic Claude API key from environment")
    else:
        print("No API keys available")
        return
    
    # Create a temporary config for testing (API keys read from environment)
    test_config = {
        "ai": {
            "provider": provider,
            "openai": {
                "endpoint": "https://api.openai.com/v1/chat/completions",
                "model": "gpt-3.5-turbo"
            },
            "claude": {
                "endpoint": "https://api.anthropic.com/v1/messages",
                "model": "claude-3-sonnet-20240229"
            }
        }
    }
    
    # Write temporary config file
    with open('test_ai_config.json', 'w') as f:
        json.dump(test_config, f, indent=2)
    
    try:
        # Initialize AI component
        ai = AI('test_ai_config.json')
        print(f"AI component initialized with provider: {ai.get_provider_name()}")
        
        # Test translation
        print("\n=== Testing Translation ===")
        test_translations = [
            ("Hello, how are you today?", "en", "es"),
            ("The weather is beautiful today.", "en", "fr"),
            ("I love programming in Python.", "en", "bn"),
        ]
        
        for text, from_lang, to_lang in test_translations:
            print(f"\nTranslating: '{text}' from {from_lang} to {to_lang}")
            success, result = ai.translate(from_lang, to_lang, text)
            
            if success:
                print(f"Translation: {result}")
            else:
                print(f"Error: {result.get('error', result)}")
        
        # Test summarization
        print("\n=== Testing Summarization ===")
        long_texts = [
            {
                "text": """
                Artificial intelligence (AI) is intelligence demonstrated by machines, in contrast to the natural intelligence displayed by humans and animals. Leading AI textbooks define the field as the study of intelligent agents: any device that perceives its environment and takes actions that maximize its chance of successfully achieving its goals. Colloquially, the term artificial intelligence is often used to describe machines that mimic cognitive functions that humans associate with the human mind, such as learning and problem solving.
                
                The term artificial intelligence was coined in 1956, but AI has become more popular today thanks to increased data volumes, advanced algorithms, and improvements in computing power and storage. Early AI research in the 1950s explored topics like problem solving and symbolic methods. In the 1960s, the US Department of Defense took interest in this type of work and began training computers to mimic basic human reasoning.
                """,
                "max_length": 100
            },
            {
                "text": """
                Machine learning is a method of data analysis that automates analytical model building. It is a branch of artificial intelligence based on the idea that systems can learn from data, identify patterns and make decisions with minimal human intervention. Machine learning algorithms build a model based on training data in order to make predictions or decisions without being explicitly programmed to do so.
                """,
                "max_length": 50
            }
        ]
        
        for i, item in enumerate(long_texts, 1):
            text = item["text"].strip()
            max_length = item.get("max_length")
            
            print(f"\nSummarizing text {i} (max {max_length} words):")
            print(f"Original length: {len(text)} characters")
            
            success, result = ai.summary(text, max_length)
            
            if success:
                print(f"Summary: {result}")
                print(f"Summary length: {len(result)} characters")
            else:
                print(f"Error: {result.get('error', result)}")
        
        # Show supported languages
        print("\n=== Supported Languages ===")
        languages = ai.get_supported_languages()
        print(f"Total languages supported: {len(languages)}")
        print("Sample languages:")
        for lang in languages[:10]:
            print(f"  {lang['name']} ({lang['code']})")
        print("  ...")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Clean up
        if os.path.exists('test_ai_config.json'):
            os.remove('test_ai_config.json')

if __name__ == "__main__":
    main()