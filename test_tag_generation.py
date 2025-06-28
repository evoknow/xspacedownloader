#!/usr/bin/env python3
"""Test script for improved tag generation from transcripts."""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from components.Space import Space

# Sample transcript text for testing
test_transcript = """
Hello everyone, welcome to today's discussion about artificial intelligence and machine learning. 
I'm here with Elon Musk from Tesla and SpaceX, and we're going to talk about the future of AI 
in autonomous vehicles and space exploration.

So Elon, what do you think about the recent developments in neural networks and deep learning? 
I think it's really fascinating how OpenAI has been pushing the boundaries with GPT models.

Well, I think the progress in Bangladesh and other developing countries in adopting AI technology 
is quite remarkable. Cities like Dhaka are becoming tech hubs. The blockchain technology is also 
being integrated with AI systems for better security and transparency.

We should also discuss quantum computing and how it might revolutionize cryptography and 
cybersecurity. The zero-day exploits are becoming more sophisticated, and we need better 
defense mechanisms.

Let's talk about climate finance and how AI can help in predicting weather patterns and 
optimizing renewable energy systems. Solar panels and wind turbines can be managed more 
efficiently with machine learning algorithms.

I was just in Silicon Valley last week, and the innovation there is incredible. Companies like 
Google, Apple, and Microsoft are all investing heavily in AI research. The competition is fierce.

What about data privacy concerns? With all this AI processing personal data, we need strong 
regulations like GDPR to protect users. The ethical implications are significant.

Nuclear submarines are also using AI for navigation and threat detection. The military 
applications are advancing rapidly, though we need to be careful about autonomous weapons.

In conclusion, AI is transforming every industry from healthcare to finance to transportation. 
The future is both exciting and challenging. Thank you for joining us today.
"""

def test_tag_generation():
    """Test the improved tag generation method."""
    space = Space()
    
    print("Testing improved tag generation...")
    print("="*80)
    print(f"Transcript length: {len(test_transcript)} characters")
    print("="*80)
    
    # Test with different max_tags values
    for max_tags in [5, 10]:
        print(f"\nGenerating {max_tags} tags...")
        tags = space.generate_tags_from_transcript(test_transcript, max_tags=max_tags)
        
        print(f"Generated tags: {tags}")
        print(f"Number of tags: {len(tags)}")
        print("-"*40)
    
    print("\n✅ Tag generation test completed!")
    print("Check logs/tag.log for detailed generation process")

if __name__ == "__main__":
    test_tag_generation()