#!/usr/bin/env python3
"""
Script to show the exact prompt being used for AI tag generation.
"""

def show_tag_generation_prompt():
    """Display the prompt that will be sent to AI for tag generation."""
    
    sample_transcript = """
    Hello everyone, welcome to today's discussion about cybersecurity and online safety. 
    I'm Anna, and I'll be talking about various aspects of email security, particularly 
    focusing on Mac security and spam protection. We'll cover the latest trends in 
    cybersecurity, how to protect yourself from phishing attacks, and some best practices 
    for maintaining good cyber hygiene. Let's dive into the topic of email security first.
    
    One of the biggest challenges we face today is the increasing sophistication of 
    cyber attacks. Email remains one of the primary vectors for these attacks, so 
    understanding how to secure your email is crucial. Whether you're using Gmail, 
    Outlook, or Apple Mail on your Mac, there are specific steps you can take.
    
    For Mac users, there are some unique considerations when it comes to security...
    """
    
    prompt = f"""Extract the top 10 topic words from the following transcript. Focus only on the most relevant nouns and concepts discussed. Do not include hashtags, filler words, or speaker names. The result should be a concise list of 10 topic keywords representing the main themes.

Return ONLY a JSON array of keywords, nothing else. Example: ["artificial intelligence", "python", "web development"]

Transcript:
{sample_transcript[:3000]}..."""

    print("=== AI TAG GENERATION PROMPT ===")
    print()
    print("System Message:")
    print("You are a helpful assistant that extracts topic tags from transcripts.")
    print()
    print("User Message:")
    print(prompt)
    print()
    print("=== EXPECTED OUTPUT ===")
    print('["cybersecurity", "email security", "Mac security", "spam protection", "phishing attacks", "cyber hygiene", "online safety"]')
    print()
    print("This prompt will:")
    print("1. Extract exactly 10 topic words")
    print("2. Focus on nouns and concepts only") 
    print("3. Exclude filler words and speaker names")
    print("4. Return a clean JSON array")
    print("5. Represent the main themes discussed")

if __name__ == "__main__":
    show_tag_generation_prompt()