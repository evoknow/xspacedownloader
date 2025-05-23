#!/usr/bin/env python3
# components/Claude.py
"""Claude (Anthropic) provider for AI translation and summarization services."""

import requests
import json
import logging
from typing import Dict, List, Optional, Union, Tuple
from .AI import AIProvider

logger = logging.getLogger(__name__)

class Claude(AIProvider):
    """Claude (Anthropic) implementation for AI services."""
    
    def __init__(self, api_key: str, endpoint: str = None, model: str = "claude-3-sonnet-20240229"):
        """
        Initialize Claude provider.
        
        Args:
            api_key (str): Anthropic API key
            endpoint (str, optional): Custom endpoint (defaults to Anthropic's API)
            model (str): Model to use (default: claude-3-sonnet-20240229)
        """
        super().__init__(api_key, endpoint, model)
        
        self.endpoint = endpoint or "https://api.anthropic.com/v1/messages"
        self.model = model or "claude-3-sonnet-20240229"
        
        # Initialize session with headers
        self.session = requests.Session()
        self.session.headers.update({
            'x-api-key': self.api_key,
            'Content-Type': 'application/json',
            'anthropic-version': '2023-06-01'
        })
        
        logger.info(f"Claude provider initialized with model: {self.model}")
    
    def _make_request(self, system_prompt: str, user_prompt: str, max_tokens: int = 1000, temperature: float = 0.1) -> Tuple[bool, Union[str, Dict]]:
        """
        Make a request to Claude API.
        
        Args:
            system_prompt (str): System prompt
            user_prompt (str): User prompt
            max_tokens (int): Maximum tokens to generate
            
        Returns:
            Tuple[bool, Union[str, Dict]]: Success flag and response or error
        """
        try:
            payload = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ]
            }
            
            logger.info(f"Making request to Claude API with model {self.model}")
            response = self.session.post(self.endpoint, json=payload, timeout=60)
            
            if response.status_code != 200:
                logger.error(f"Claude API error: {response.status_code} - {response.text}")
                return False, {
                    "error": f"Claude API error: {response.status_code}",
                    "details": response.text
                }
            
            result = response.json()
            
            if 'content' in result and len(result['content']) > 0:
                content = result['content'][0]['text'].strip()
                logger.info("Successfully received response from Claude")
                return True, content
            else:
                logger.error(f"Unexpected Claude response format: {result}")
                return False, {
                    "error": "Unexpected response format",
                    "details": result
                }
                
        except requests.RequestException as e:
            logger.error(f"Request error: {e}")
            return False, {"error": f"Network error: {str(e)}"}
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return False, {"error": f"Invalid response format: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return False, {"error": f"Unexpected error: {str(e)}"}
    
    def translate(self, from_lang: str, to_lang: str, content: str) -> Tuple[bool, Union[str, Dict]]:
        """
        Translate content using Claude.
        
        Args:
            from_lang (str): Source language code or name
            to_lang (str): Target language code or name
            content (str): Content to translate
            
        Returns:
            Tuple[bool, Union[str, Dict]]: Success flag and translated text or error dict
        """
        if not content:
            return False, {"error": "No content provided for translation"}
        
        if from_lang == to_lang:
            return True, content
        
        # Map language codes to full names for better results
        lang_map = {
            'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
            'it': 'Italian', 'pt': 'Portuguese', 'ru': 'Russian', 'zh': 'Chinese',
            'ja': 'Japanese', 'ar': 'Arabic', 'bn': 'Bengali', 'hi': 'Hindi',
            'ko': 'Korean', 'nl': 'Dutch', 'sv': 'Swedish', 'tr': 'Turkish'
        }
        
        from_language = lang_map.get(from_lang.lower(), from_lang)
        to_language = lang_map.get(to_lang.lower(), to_lang)
        
        system_prompt = "You are a professional translator. Provide only the translated text without any additional commentary, explanation, or formatting. Maintain the original structure and meaning as closely as possible. Translate the ENTIRE text completely - do not stop mid-sentence or repeat phrases. Ensure the translation is complete and coherent from start to finish."
        
        # Handle auto-detection
        if from_lang.lower() == 'auto':
            user_prompt = f"Translate the following text to {to_language}. If the source language is already {to_language}, just return the original text. Translate the ENTIRE text completely and avoid repetition:\n\n{content}"
        else:
            user_prompt = f"Translate the following text from {from_language} to {to_language}. Translate the ENTIRE text completely and avoid repetition:\n\n{content}"
        
        # Calculate appropriate max_tokens based on content length
        # Rough estimate: 1 token ≈ 0.75 words, allow 1.5x for translation expansion
        content_tokens = len(content.split()) * 1.33  # Convert words to estimated tokens
        max_tokens = max(4000, min(int(content_tokens * 1.5), 32000))  # Between 4K and 32K tokens (Claude supports more)
        
        logger.info(f"Claude translation request - Content tokens estimate: {content_tokens}, Max tokens: {max_tokens}")
        
        return self._make_request(system_prompt, user_prompt, max_tokens=max_tokens, temperature=0.1)
    
    def summary(self, content: str, max_length: int = None, language: str = None) -> Tuple[bool, Union[str, Dict]]:
        """
        Generate a summary using Claude.
        
        Args:
            content (str): Content to summarize
            max_length (int, optional): Maximum length of summary in words
            language (str, optional): Language for the summary output
            
        Returns:
            Tuple[bool, Union[str, Dict]]: Success flag and summary or error dict
        """
        if not content:
            return False, {"error": "No content provided for summarization"}
        
        # Determine max_tokens based on max_length
        if max_length:
            max_tokens = min(max_length * 2, 1000)  # Rough estimate: 1 token ≈ 0.5 words
            length_instruction = f"in approximately {max_length} words"
        else:
            max_tokens = 500
            length_instruction = "concisely"
        
        # Map language codes to full names
        lang_map = {
            'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
            'it': 'Italian', 'pt': 'Portuguese', 'ru': 'Russian', 'zh': 'Chinese',
            'ja': 'Japanese', 'ar': 'Arabic', 'bn': 'Bengali', 'hi': 'Hindi',
            'ko': 'Korean', 'nl': 'Dutch', 'sv': 'Swedish', 'tr': 'Turkish'
        }
        
        # Determine output language
        output_language = lang_map.get(language.lower() if language else 'en', language or 'English')
        
        system_prompt = f"You are a professional content summarizer. Provide clear, concise summaries that capture the essential information and main points. Focus on accuracy and clarity. Always provide the summary in {output_language}."
        
        user_prompt = f"""Summarize the following content {length_instruction} in {output_language}. Focus on the key points and main ideas:

{content}"""
        
        return self._make_request(system_prompt, user_prompt, max_tokens=max_tokens)
    
    def get_supported_languages(self) -> List[Dict[str, str]]:
        """
        Get list of supported languages.
        
        Returns:
            List[Dict[str, str]]: List of language dictionaries
        """
        return [
            {"code": "en", "name": "English"},
            {"code": "es", "name": "Spanish"},
            {"code": "fr", "name": "French"},
            {"code": "de", "name": "German"},
            {"code": "it", "name": "Italian"},
            {"code": "pt", "name": "Portuguese"},
            {"code": "ru", "name": "Russian"},
            {"code": "zh", "name": "Chinese"},
            {"code": "ja", "name": "Japanese"},
            {"code": "ar", "name": "Arabic"},
            {"code": "bn", "name": "Bengali/Bangla"},
            {"code": "hi", "name": "Hindi"},
            {"code": "ko", "name": "Korean"},
            {"code": "nl", "name": "Dutch"},
            {"code": "sv", "name": "Swedish"},
            {"code": "tr", "name": "Turkish"},
            {"code": "vi", "name": "Vietnamese"},
            {"code": "pl", "name": "Polish"},
            {"code": "da", "name": "Danish"},
            {"code": "fi", "name": "Finnish"},
            {"code": "no", "name": "Norwegian"},
            {"code": "th", "name": "Thai"},
            {"code": "id", "name": "Indonesian"},
            {"code": "ms", "name": "Malay"},
            {"code": "tl", "name": "Filipino"},
            {"code": "uk", "name": "Ukrainian"},
            {"code": "cs", "name": "Czech"},
            {"code": "sk", "name": "Slovak"},
            {"code": "hu", "name": "Hungarian"},
            {"code": "ro", "name": "Romanian"},
            {"code": "bg", "name": "Bulgarian"},
            {"code": "hr", "name": "Croatian"},
            {"code": "sr", "name": "Serbian"},
            {"code": "sl", "name": "Slovenian"},
            {"code": "et", "name": "Estonian"},
            {"code": "lv", "name": "Latvian"},
            {"code": "lt", "name": "Lithuanian"}
        ]

# Example usage
if __name__ == "__main__":
    import os
    
    # You would normally get this from your config
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Please set ANTHROPIC_API_KEY environment variable")
        exit(1)
    
    claude_provider = Claude(api_key)
    
    # Test translation
    print("Testing translation:")
    success, result = claude_provider.translate("en", "es", "Hello, how are you today?")
    if success:
        print(f"Translation: {result}")
    else:
        print(f"Error: {result}")
    
    # Test summarization
    print("\nTesting summarization:")
    long_text = """
    Artificial intelligence (AI) is intelligence demonstrated by machines, in contrast to the natural intelligence displayed by humans and animals. Leading AI textbooks define the field as the study of intelligent agents: any device that perceives its environment and takes actions that maximize its chance of successfully achieving its goals. Colloquially, the term artificial intelligence is often used to describe machines that mimic cognitive functions that humans associate with the human mind, such as learning and problem solving.
    """
    success, result = claude_provider.summary(long_text.strip(), max_length=50)
    if success:
        print(f"Summary: {result}")
    else:
        print(f"Error: {result}")