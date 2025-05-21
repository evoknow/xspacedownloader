#!/usr/bin/env python3
# components/Translate.py
"""Translation component for XSpace Downloader using LibreTranslate."""

import os
import json
import logging
import requests
from typing import Dict, List, Optional, Union, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('translate_component.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class Translate:
    """Class for handling translation of text between languages."""
    
    def __init__(self, api_url=None, api_key=None, config_file="mainconfig.json"):
        """
        Initialize the Translate component.
        
        Args:
            api_url (str, optional): URL of the LibreTranslate API server
            api_key (str, optional): API key for LibreTranslate if required
            config_file (str, optional): Path to the configuration file
        """
        self.api_url = api_url
        self.api_key = api_key
        
        # If no API URL provided, try to load from config
        if not self.api_url or not self.api_key:
            self._load_config(config_file)
            
        # Default API URL if not provided in config
        if not self.api_url:
            self.api_url = "https://libretranslate.com/translate"
            logger.warning(f"No API URL provided, using default: {self.api_url}")
            
        # Initialize session
        self.session = requests.Session()
        
        # Try to get available languages
        self.available_languages = self._get_available_languages()
        if not self.available_languages:
            logger.warning("Could not fetch available languages from API")
            # Default language list if API call fails
            self.available_languages = [
                {"code": "en", "name": "English"},
                {"code": "es", "name": "Spanish"},
                {"code": "fr", "name": "French"},
                {"code": "de", "name": "German"},
                {"code": "it", "name": "Italian"},
                {"code": "pt", "name": "Portuguese"},
                {"code": "ru", "name": "Russian"},
                {"code": "zh", "name": "Chinese"},
                {"code": "ja", "name": "Japanese"},
                {"code": "ar", "name": "Arabic"}
            ]
    
    def _load_config(self, config_file: str) -> None:
        """
        Load configuration from file.
        
        Args:
            config_file (str): Path to the configuration file
        """
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    
                translate_config = config.get('translate', {})
                self.api_url = translate_config.get('api_url', self.api_url)
                self.api_key = translate_config.get('api_key', self.api_key)
                
                if self.api_url and self.api_key:
                    logger.info(f"Loaded translation configuration from {config_file}")
            else:
                logger.warning(f"Configuration file {config_file} not found")
        except Exception as e:
            logger.error(f"Error loading translation configuration: {e}")
            
    def _get_available_languages(self) -> List[Dict[str, str]]:
        """
        Get list of available languages from LibreTranslate API.
        
        Returns:
            List[Dict[str, str]]: List of language dictionaries with code and name
        """
        try:
            # Get the base API URL (without /translate endpoint)
            base_url = self.api_url
            if base_url.endswith('/translate'):
                base_url = base_url[:-10]
                
            languages_url = f"{base_url}/languages"
            
            # Make API request
            params = {}
            if self.api_key:
                params['api_key'] = self.api_key
                
            response = self.session.get(languages_url, params=params, timeout=5)
            response.raise_for_status()
            
            languages = response.json()
            logger.info(f"Retrieved {len(languages)} available languages from API")
            return languages
        except Exception as e:
            logger.error(f"Error fetching available languages: {e}")
            return []
            
    def get_languages(self) -> List[Dict[str, str]]:
        """
        Get the list of available languages for translation.
        
        Returns:
            List[Dict[str, str]]: List of language dictionaries with code and name
        """
        return self.available_languages
        
    def translate(self, text: str, source_lang: str, target_lang: str) -> Tuple[bool, Union[str, Dict]]:
        """
        Translate text from source language to target language.
        
        Args:
            text (str): The text to translate
            source_lang (str): The source language code (e.g., 'en', 'es')
            target_lang (str): The target language code (e.g., 'en', 'es')
            
        Returns:
            Tuple[bool, Union[str, Dict]]: A tuple containing:
                - Success flag (True if successful, False otherwise)
                - Either the translated text (if successful) or an error dictionary
        """
        if not text:
            return False, {"error": "No text provided for translation"}
            
        if source_lang == target_lang:
            return True, text  # No translation needed
            
        try:
            # Prepare request payload
            payload = {
                'q': text,
                'source': source_lang,
                'target': target_lang,
                'format': 'text'
            }
            
            # Add API key if available
            if self.api_key:
                payload['api_key'] = self.api_key
                
            # Make API request
            response = self.session.post(self.api_url, json=payload, timeout=30)
            
            # Check response status
            if response.status_code != 200:
                logger.error(f"Translation API error: {response.status_code} - {response.text}")
                return False, {
                    "error": f"API error: {response.status_code}",
                    "details": response.text
                }
                
            # Parse response
            result = response.json()
            
            # Handle different API response formats
            translated_text = result.get('translatedText', None)
            if translated_text is None:
                translated_text = result.get('text', None)
                
            if translated_text is None:
                logger.error(f"Unexpected API response format: {result}")
                return False, {
                    "error": "Unexpected API response format",
                    "details": result
                }
                
            logger.info(f"Successfully translated text from {source_lang} to {target_lang}")
            return True, translated_text
            
        except requests.RequestException as e:
            logger.error(f"Request error in translation: {e}")
            return False, {"error": f"Network error: {str(e)}"}
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in translation: {e}")
            return False, {"error": f"Invalid response format: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error in translation: {e}")
            return False, {"error": f"Unexpected error: {str(e)}"}
            
    def detect_language(self, text: str) -> Tuple[bool, Union[str, Dict]]:
        """
        Detect the language of the provided text.
        
        Args:
            text (str): The text to analyze
            
        Returns:
            Tuple[bool, Union[str, Dict]]: A tuple containing:
                - Success flag (True if successful, False otherwise)
                - Either the detected language code (if successful) or an error dictionary
        """
        if not text:
            return False, {"error": "No text provided for language detection"}
            
        try:
            # Get the base API URL (without /translate endpoint)
            base_url = self.api_url
            if base_url.endswith('/translate'):
                base_url = base_url[:-10]
                
            detect_url = f"{base_url}/detect"
            
            # Prepare request payload
            payload = {'q': text}
            
            # Add API key if available
            if self.api_key:
                payload['api_key'] = self.api_key
                
            # Make API request
            response = self.session.post(detect_url, json=payload, timeout=10)
            
            # Check response status
            if response.status_code != 200:
                logger.error(f"Language detection API error: {response.status_code} - {response.text}")
                return False, {
                    "error": f"API error: {response.status_code}",
                    "details": response.text
                }
                
            # Parse response
            result = response.json()
            
            # LibreTranslate returns a list of possible languages with confidence scores
            # We'll take the one with the highest confidence
            if isinstance(result, list) and len(result) > 0:
                # Sort by confidence (descending)
                result.sort(key=lambda x: x.get('confidence', 0), reverse=True)
                detected_lang = result[0].get('language')
                confidence = result[0].get('confidence', 0)
                
                logger.info(f"Detected language: {detected_lang} with confidence {confidence}")
                return True, detected_lang
            else:
                logger.error(f"Unexpected API response format for language detection: {result}")
                return False, {
                    "error": "Unexpected API response format",
                    "details": result
                }
                
        except requests.RequestException as e:
            logger.error(f"Request error in language detection: {e}")
            return False, {"error": f"Network error: {str(e)}"}
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in language detection: {e}")
            return False, {"error": f"Invalid response format: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error in language detection: {e}")
            return False, {"error": f"Unexpected error: {str(e)}"}


# Example usage if run directly
if __name__ == "__main__":
    # Initialize Translate component
    translator = Translate()
    
    # Get available languages
    languages = translator.get_languages()
    print(f"Available languages: {languages}")
    
    # Example translation
    text = "Hello, how are you today?"
    result = translator.translate(text, "en", "es")
    
    if result[0]:
        print(f"Translation: {result[1]}")
    else:
        print(f"Translation error: {result[1]}")
        
    # Example language detection
    detect_result = translator.detect_language(text)
    
    if detect_result[0]:
        print(f"Detected language: {detect_result[1]}")
    else:
        print(f"Detection error: {detect_result[1]}")