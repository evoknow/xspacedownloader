#!/usr/bin/env python3
"""
OpenAI Pricing Update Script
Fetches current OpenAI pricing and updates the ai_api_cost table.

This script should be run via cron job to keep pricing up to date.
"""

import requests
import json
import logging
import sys
import os
from datetime import datetime
from components.DatabaseManager import DatabaseManager

# Setup logging
def setup_logging():
    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    log_file = os.path.join(logs_dir, 'openai_pricing_update.log')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

setup_logging()
logger = logging.getLogger(__name__)

def process_models_section(cursor, models_data, section_name):
    """
    Process a section of models and update the database.
    
    Args:
        cursor: Database cursor
        models_data: Dictionary of models with pricing data
        section_name: Name of the section for logging
        
    Returns:
        int: Number of models successfully processed
    """
    processed_count = 0
    
    for model_name, model_data in models_data.items():
        try:
            # Extract pricing information
            input_cost = model_data.get('input', 0)
            output_cost = model_data.get('output', 0)
            
            # Skip if both costs are missing or zero
            if input_cost == 0 and output_cost == 0:
                logger.warning(f"Skipping {model_name} in {section_name}: no pricing data available")
                continue
            
            # Convert to cost per million tokens (pricing data is usually per 1K tokens)
            # Check if the pricing is already per million or per thousand
            if input_cost > 0 and input_cost < 1:  # Likely per thousand tokens
                input_cost_per_million = input_cost * 1000
            else:  # Already per million or very expensive per thousand, or zero
                input_cost_per_million = input_cost
                
            if output_cost > 0 and output_cost < 1:  # Likely per thousand tokens
                output_cost_per_million = output_cost * 1000
            else:  # Already per million or very expensive per thousand, or zero
                output_cost_per_million = output_cost
            
            # Use REPLACE INTO to insert or update
            query = """
                REPLACE INTO ai_api_cost (
                    vendor,
                    model,
                    input_token_cost_per_million_tokens,
                    output_token_cost_per_million_tokens,
                    updated_at
                ) VALUES (%s, %s, %s, %s, NOW())
            """
            
            cursor.execute(query, (
                'openai',
                model_name,
                input_cost_per_million,
                output_cost_per_million
            ))
            
            processed_count += 1
            logger.debug(f"Updated {model_name} from {section_name}: input=${input_cost_per_million:.4f}, output=${output_cost_per_million:.4f} per million tokens")
            
        except Exception as e:
            logger.error(f"Error processing model {model_name} in {section_name}: {e}")
            continue
    
    logger.info(f"Processed {processed_count} models from {section_name}")
    return processed_count

def fetch_openai_pricing():
    """
    Fetch OpenAI pricing from the GitHub repository.
    
    Returns:
        dict: Parsed pricing data or None if failed
    """
    url = "https://raw.githubusercontent.com/outl1ne/openai-pricing/refs/heads/main/pricing.json"
    
    try:
        logger.info(f"Fetching OpenAI pricing from: {url}")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        pricing_data = response.json()
        logger.info(f"Successfully fetched pricing data with {len(pricing_data)} entries")
        
        return pricing_data
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching pricing data: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing pricing JSON: {e}")
        return None

def update_pricing_database(pricing_data):
    """
    Update the ai_api_cost table with new pricing data.
    
    Args:
        pricing_data (dict): Pricing data from OpenAI API
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Initialize database connection using context manager
        db = DatabaseManager()
        
        updated_count = 0
        
        logger.info("Starting database update...")
        
        with db.get_connection() as connection:
            cursor = connection.cursor()
            
            # Process regular models
            models_data = pricing_data.get('models', {})
            if models_data:
                logger.info(f"Processing {len(models_data)} regular models...")
                updated_count += process_models_section(cursor, models_data, 'regular models')
            
            # Process transcription/speech models
            transcription_data = pricing_data.get('transcription_speech', {})
            if transcription_data:
                # Process text_tokens models
                text_tokens = transcription_data.get('text_tokens', {})
                if text_tokens:
                    logger.info(f"Processing {len(text_tokens)} transcription text_tokens models...")
                    updated_count += process_models_section(cursor, text_tokens, 'transcription text_tokens')
                
                # Process audio_tokens models  
                audio_tokens = transcription_data.get('audio_tokens', {})
                if audio_tokens:
                    logger.info(f"Processing {len(audio_tokens)} transcription audio_tokens models...")
                    updated_count += process_models_section(cursor, audio_tokens, 'transcription audio_tokens')
            
            # Process embedding models
            embedding_data = pricing_data.get('embedding', {})
            if embedding_data:
                logger.info(f"Processing {len(embedding_data)} embedding models...")
                updated_count += process_models_section(cursor, embedding_data, 'embedding models')
            
            # Process image models
            image_data = pricing_data.get('image', {})
            if image_data:
                logger.info(f"Processing {len(image_data)} image models...")
                updated_count += process_models_section(cursor, image_data, 'image models')
            
            # Process audio models
            audio_data = pricing_data.get('audio', {})
            if audio_data:
                logger.info(f"Processing {len(audio_data)} audio models...")
                updated_count += process_models_section(cursor, audio_data, 'audio models')
            
            if updated_count == 0:
                logger.error("No models found in pricing data")
                return False
            
            # Commit all changes
            connection.commit()
            cursor.close()
        
        logger.info(f"Database update completed: {updated_count} models updated total")
        return True
        
    except Exception as e:
        logger.error(f"Database error: {e}")
        return False

def main():
    """Main function to run the pricing update."""
    logger.info("=" * 50)
    logger.info("Starting OpenAI pricing update")
    logger.info("=" * 50)
    
    # Fetch pricing data
    pricing_data = fetch_openai_pricing()
    if not pricing_data:
        logger.error("Failed to fetch pricing data. Exiting.")
        sys.exit(1)
    
    # Update database
    success = update_pricing_database(pricing_data)
    if not success:
        logger.error("Failed to update database. Exiting.")
        sys.exit(1)
    
    logger.info("OpenAI pricing update completed successfully")
    logger.info("=" * 50)

if __name__ == "__main__":
    main()