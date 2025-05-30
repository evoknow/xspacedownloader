#!/usr/bin/env python3
"""
Test script to verify tag generation logging is working properly.
This will generate tags and show what's being logged to tag.log
"""

import sys
import os

# Add the project directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from components.Space import Space

# Sample transcript text for testing
test_transcript = """
Hello and welcome to our discussion about artificial intelligence and machine learning.
Today we'll be talking about how Python is used in data science and web development.
We'll cover topics like neural networks, deep learning, and natural language processing.
Our guest today is an expert in cybersecurity and blockchain technology.
We'll discuss Bitcoin, cryptocurrency, and the future of Web3.
This is really exciting because technology is changing so rapidly.
Machine learning is revolutionizing how we approach problem solving.
Python has become the go-to language for AI development.
Let's dive into some specific examples of machine learning applications.
We'll look at computer vision, speech recognition, and predictive analytics.
"""

def test_tag_generation():
    """Test tag generation with logging."""
    print("Testing tag generation with logging to tag.log...")
    print("-" * 60)
    
    # Create Space instance
    space = Space()
    
    # Generate tags (this will log to tag.log)
    tags = space.generate_tags_from_transcript(test_transcript, max_tags=5)
    
    print(f"Generated tags: {tags}")
    print("-" * 60)
    print("Check tag.log for detailed logging of:")
    print("1. The full prompt sent to AI")
    print("2. The AI response")
    print("3. Final tags generated")
    print("4. Fallback keyword extraction (if AI fails)")
    
    # Also show the last few lines of tag.log if it exists
    if os.path.exists('tag.log'):
        print("\nLast 50 lines of tag.log:")
        print("-" * 60)
        with open('tag.log', 'r') as f:
            lines = f.readlines()
            for line in lines[-50:]:
                print(line.rstrip())

if __name__ == "__main__":
    test_tag_generation()