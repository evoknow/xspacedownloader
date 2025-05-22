#!/usr/bin/env python3
# components/AI.py
"""Abstract AI component for translation and summarization services."""

import os
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AIProvider(ABC):
    """Abstract base class for AI providers."""
    
    def __init__(self, api_key: str, endpoint: str = None, model: str = None):
        """
        Initialize the AI provider.
        
        Args:
            api_key (str): API key for the AI service
            endpoint (str, optional): Custom endpoint URL
            model (str, optional): Model name to use
        """
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model
        self.provider_name = self.__class__.__name__
        
        if not api_key:
            raise ValueError(f"API key is required for {self.provider_name}")
            
        logger.info(f"Initialized {self.provider_name} provider")
    
    @abstractmethod
    def translate(self, from_lang: str, to_lang: str, content: str) -> Tuple[bool, Union[str, Dict]]:
        """
        Translate content from one language to another.
        
        Args:
            from_lang (str): Source language code (e.g., 'en', 'es', 'auto')
            to_lang (str): Target language code (e.g., 'en', 'es')
            content (str): Content to translate
            
        Returns:
            Tuple[bool, Union[str, Dict]]: Success flag and translated text or error dict
        """
        pass
    
    @abstractmethod
    def summary(self, content: str, max_length: int = None) -> Tuple[bool, Union[str, Dict]]:
        """
        Generate a summary of the given content.
        
        Args:
            content (str): Content to summarize
            max_length (int, optional): Maximum length of summary
            
        Returns:
            Tuple[bool, Union[str, Dict]]: Success flag and summary text or error dict
        """
        pass
    
    @abstractmethod
    def get_supported_languages(self) -> List[Dict[str, str]]:
        """
        Get list of supported languages.
        
        Returns:
            List[Dict[str, str]]: List of language dictionaries with code and name
        """
        pass

class AI:
    """Main AI component that manages different AI providers."""
    
    def __init__(self, config_file: str = "mainconfig.json"):
        """
        Initialize the AI component.
        
        Args:
            config_file (str): Path to configuration file
        """
        self.config_file = config_file
        self.provider = None
        self.config = self._load_config()
        
        # Initialize the selected provider
        self._initialize_provider()
    
    def _load_config(self) -> Dict:
        """Load configuration from file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    
                ai_config = config.get('ai', {})
                if not ai_config:
                    logger.warning(f"No AI configuration found in {self.config_file}")
                    return {}
                    
                logger.info(f"Loaded AI configuration from {self.config_file}")
                return ai_config
            else:
                logger.warning(f"Configuration file {self.config_file} not found")
                return {}
        except Exception as e:
            logger.error(f"Error loading AI configuration: {e}")
            return {}
    
    def _initialize_provider(self):
        """Initialize the selected AI provider."""
        if not self.config:
            logger.error("No AI configuration available")
            return
            
        provider_name = self.config.get('provider', '').lower()
        
        if provider_name == 'openai':
            from .OpenAI import OpenAI
            openai_config = self.config.get('openai', {})
            # Get API key from environment variable
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                logger.error("OPENAI_API_KEY environment variable not set")
                raise ValueError("OPENAI_API_KEY environment variable not set")
            
            self.provider = OpenAI(
                api_key=api_key,
                endpoint=openai_config.get('endpoint'),
                model=openai_config.get('model', 'gpt-3.5-turbo')
            )
        elif provider_name == 'claude':
            from .Claude import Claude
            claude_config = self.config.get('claude', {})
            # Get API key from environment variable
            api_key = os.getenv('ANTHROPIC_API_KEY')
            if not api_key:
                logger.error("ANTHROPIC_API_KEY environment variable not set")
                raise ValueError("ANTHROPIC_API_KEY environment variable not set")
            
            self.provider = Claude(
                api_key=api_key,
                endpoint=claude_config.get('endpoint'),
                model=claude_config.get('model', 'claude-3-sonnet-20240229')
            )
        else:
            logger.error(f"Unsupported AI provider: {provider_name}")
            raise ValueError(f"Unsupported AI provider: {provider_name}")
    
    def translate(self, from_lang: str, to_lang: str, content: str) -> Tuple[bool, Union[str, Dict]]:
        """
        Translate content using the configured AI provider.
        
        Args:
            from_lang (str): Source language code
            to_lang (str): Target language code
            content (str): Content to translate
            
        Returns:
            Tuple[bool, Union[str, Dict]]: Success flag and result
        """
        if not self.provider:
            return False, {"error": "No AI provider initialized"}
            
        return self.provider.translate(from_lang, to_lang, content)
    
    def summary(self, content: str, max_length: int = None) -> Tuple[bool, Union[str, Dict]]:
        """
        Generate summary using the configured AI provider.
        
        Args:
            content (str): Content to summarize
            max_length (int, optional): Maximum length of summary
            
        Returns:
            Tuple[bool, Union[str, Dict]]: Success flag and result
        """
        if not self.provider:
            return False, {"error": "No AI provider initialized"}
            
        return self.provider.summary(content, max_length)
    
    def get_supported_languages(self) -> List[Dict[str, str]]:
        """Get supported languages from the provider."""
        if not self.provider:
            return []
            
        return self.provider.get_supported_languages()
    
    def get_provider_name(self) -> str:
        """Get the name of the current provider."""
        return self.provider.provider_name if self.provider else "None"

# Example usage
if __name__ == "__main__":
    # This would normally load from config file
    ai = AI()
    
    if ai.provider:
        # Test translation
        print("Testing translation:")
        success, result = ai.translate("en", "es", "Hello, how are you today?")
        if success:
            print(f"Translation: {result}")
        else:
            print(f"Translation error: {result}")
        
        # Test summarization
        print("\nTesting summarization:")
        long_text = """
        Artificial intelligence (AI) is intelligence demonstrated by machines, in contrast to the natural intelligence displayed by humans and animals. Leading AI textbooks define the field as the study of intelligent agents: any device that perceives its environment and takes actions that maximize its chance of successfully achieving its goals. Colloquially, the term artificial intelligence is often used to describe machines that mimic cognitive functions that humans associate with the human mind, such as learning and problem solving.
        """
        success, result = ai.summary(long_text.strip())
        if success:
            print(f"Summary: {result}")
        else:
            print(f"Summary error: {result}")
    else:
        print("No AI provider available. Check your configuration.")