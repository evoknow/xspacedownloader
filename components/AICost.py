#!/usr/bin/env python3
"""
Unified AI Cost Tracking Component

Handles all AI-related cost calculations and transaction recording for:
- Transcription (OpenAI Whisper API)
- Translation (OpenAI/Claude)
- Summarization (OpenAI/Claude)
- Language Detection (OpenAI/Claude)
- Text Generation (OpenAI/Claude)
- Tag Generation (OpenAI/Claude)

Cost Calculation Formula:
cost = (input_tokens / 1,000,000) * input_cost_per_million + (output_tokens / 1,000,000) * output_cost_per_million
Total cost is rounded to nearest integer (minimum 1 credit)
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import mysql.connector
from .DatabaseManager import DatabaseManager

# Optional Flask import (for session management)
try:
    from flask import session
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    session = None

class AICost:
    """Unified AI cost tracking and credit management."""
    
    # Default costs per million tokens if not found in database
    DEFAULT_COSTS = {
        'openai': {
            'gpt-4o-mini': {'input': 0.15, 'output': 0.60},  # $0.15/$0.60 per 1M tokens
            'gpt-4o-mini-transcribe': {'input': 0.15, 'output': 0.60},
            'gpt-4o': {'input': 5.00, 'output': 15.00},  # $5/$15 per 1M tokens
            'gpt-3.5-turbo': {'input': 0.50, 'output': 1.50},  # $0.50/$1.50 per 1M tokens
            'whisper-1': {'input': 0.006, 'output': 0.0}  # $0.006 per minute (no output cost)
        },
        'anthropic': {
            'claude-3-haiku-20240307': {'input': 0.25, 'output': 1.25},  # $0.25/$1.25 per 1M tokens
            'claude-3-sonnet-20240229': {'input': 3.00, 'output': 15.00},  # $3/$15 per 1M tokens
            'claude-3-opus-20240229': {'input': 15.00, 'output': 75.00}  # $15/$75 per 1M tokens
        }
    }
    
    def __init__(self):
        """Initialize the AICost component."""
        self.db = DatabaseManager()
        self._setup_cost_logging()
        
    def _setup_cost_logging(self):
        """Setup cost.log file logging."""
        logs_dir = Path('logs')
        logs_dir.mkdir(exist_ok=True)
        
        self.cost_logger = logging.getLogger('ai_cost_operations')
        self.cost_logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplicates
        for handler in self.cost_logger.handlers[:]:
            self.cost_logger.removeHandler(handler)
        
        # Create file handler for cost.log
        cost_log_file = logs_dir / 'cost.log'
        file_handler = logging.FileHandler(cost_log_file)
        file_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        self.cost_logger.addHandler(file_handler)
        self.cost_logger.propagate = False
    
    def get_user_info(self) -> Tuple[Optional[int], Optional[str]]:
        """Get current user ID and cookie ID from session."""
        user_id = session.get('user_id') if session else None
        cookie_id = session.get('visitor_id') if session else None
        
        if session and not cookie_id:
            import uuid
            cookie_id = str(uuid.uuid4())
            session['visitor_id'] = cookie_id
            session.permanent = True
        
        return user_id, cookie_id
    
    def get_model_costs(self, vendor: str, model: str) -> Dict[str, float]:
        """
        Get AI model costs from database or defaults.
        
        Returns:
            dict: {'input_cost_per_million': float, 'output_cost_per_million': float}
        """
        try:
            with self.db.get_connection() as connection:
                cursor = connection.cursor(dictionary=True)
                
                cursor.execute("""
                    SELECT input_token_cost_per_million_tokens, output_token_cost_per_million_tokens
                    FROM ai_api_cost 
                    WHERE vendor = %s AND model = %s
                """, (vendor, model))
                
                result = cursor.fetchone()
                
                if result:
                    return {
                        'input_cost_per_million': float(result['input_token_cost_per_million_tokens']),
                        'output_cost_per_million': float(result['output_token_cost_per_million_tokens'])
                    }
                
                # Fall back to defaults
                vendor_defaults = self.DEFAULT_COSTS.get(vendor.lower(), {})
                model_defaults = vendor_defaults.get(model, {'input': 0.15, 'output': 0.60})
                
                self.cost_logger.warning(f"No costs found for {vendor}/{model}, using defaults")
                return {
                    'input_cost_per_million': model_defaults['input'],
                    'output_cost_per_million': model_defaults['output']
                }
            
        except Exception as e:
            self.cost_logger.error(f"Error getting model costs: {e}")
            # Return safe defaults
            return {'input_cost_per_million': 0.15, 'output_cost_per_million': 0.60}
    
    def calculate_cost(self, vendor: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate total cost for AI operation.
        
        Formula:
        cost = (input_tokens / 1,000,000) * input_cost_per_million + (output_tokens / 1,000,000) * output_cost_per_million
        
        Returns:
            float: Total cost in credits (minimum 1)
        """
        costs = self.get_model_costs(vendor, model)
        
        input_cost = (input_tokens / 1_000_000) * costs['input_cost_per_million']
        output_cost = (output_tokens / 1_000_000) * costs['output_cost_per_million']
        total_cost = input_cost + output_cost
        
        # Round to nearest integer, minimum 1 credit
        return max(1.0, round(total_cost))
    
    def track_cost(self, 
                   space_id: str,
                   action: str,
                   vendor: str,
                   model: str,
                   input_tokens: int,
                   output_tokens: int,
                   user_id: Optional[int] = None,
                   cookie_id: Optional[str] = None,
                   deduct_credits: bool = True,
                   source_language: Optional[str] = None,
                   target_language: Optional[str] = None) -> Tuple[bool, str, float]:
        """
        Track AI operation cost and optionally deduct credits.
        
        Args:
            space_id: Space ID
            action: Action type (transcription, translation, summary, etc.)
            vendor: AI vendor (openai, anthropic)
            model: Model name
            input_tokens: Input tokens used
            output_tokens: Output tokens generated
            user_id: User ID (optional, will get from session if not provided)
            cookie_id: Cookie ID (optional, will get from session if not provided)
            deduct_credits: Whether to deduct credits from user balance
            
        Returns:
            tuple: (success, message, cost)
        """
        # Get user info
        if user_id is None or cookie_id is None:
            session_user_id, session_cookie_id = self.get_user_info()
            user_id = user_id or session_user_id
            cookie_id = cookie_id or session_cookie_id
        
        # Calculate cost
        cost = self.calculate_cost(vendor, model, input_tokens, output_tokens)
        
        balance_before = None
        balance_after = None
        
        try:
            with self.db.get_connection() as connection:
                cursor = connection.cursor()
                
                # Check user balance and deduct if requested
                if user_id and deduct_credits:
                    # Get current balance
                    cursor.execute("SELECT credits FROM users WHERE id = %s", (user_id,))
                    result = cursor.fetchone()
                    
                    if not result:
                        return False, "User not found", cost
                    
                    balance_before = float(result[0])
                    
                    if balance_before < cost:
                        message = f"Insufficient credits. Required: {cost:.2f}, Available: {balance_before:.2f}"
                        self.cost_logger.warning(f"User {user_id} - {message}")
                        return False, message, cost
                    
                    # Deduct credits (ensure credits never go below 0)
                    cursor.execute("""
                        UPDATE users 
                        SET credits = GREATEST(0, credits - %s)
                        WHERE id = %s AND credits >= %s
                    """, (cost, user_id, cost))
                    
                    if cursor.rowcount == 0:
                        return False, "Failed to deduct credits", cost
                    
                    balance_after = balance_before - cost
                elif user_id and not deduct_credits:
                    # Just get the balance for logging
                    cursor.execute("SELECT credits FROM users WHERE id = %s", (user_id,))
                    result = cursor.fetchone()
                    balance_before = float(result[0]) if result else 0.0
                    balance_after = balance_before  # No deduction
                elif not user_id:
                    return False, "AI operations require user login", cost
                
                # Record transaction
                cursor.execute("""
                    INSERT INTO transactions 
                    (user_id, cookie_id, space_id, action, ai_model, input_tokens, 
                     output_tokens, cost, balance_before, balance_after, source_language, target_language)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, cookie_id, space_id, action, f"{vendor}/{model}", 
                      input_tokens, output_tokens, cost, balance_before, balance_after, 
                      source_language, target_language))
                
                # Update space_cost table based on action type
                cost_column = self._get_cost_column_for_action(action)
                if cost_column:
                    cursor.execute(f"""
                        INSERT INTO space_cost (space_id, {cost_column}) 
                        VALUES (%s, %s) 
                        ON DUPLICATE KEY UPDATE 
                        {cost_column} = {cost_column} + %s
                    """, (space_id, cost, cost))
                
                connection.commit()
                
                # Log to cost.log
                user_identifier = f"user_id:{user_id}" if user_id else f"cookie_id:{cookie_id}"
                self.cost_logger.info(
                    f"{user_identifier} | space_id:{space_id} | action:{action} | "
                    f"model:{vendor}/{model} | input_tokens:{input_tokens} | output_tokens:{output_tokens} | "
                    f"cost:{cost:.2f} | balance_before:{balance_before} | balance_after:{balance_after} | "
                    f"deducted:{deduct_credits}"
                )
                
                return True, "Cost tracked successfully", cost
            
        except Exception as e:
            self.cost_logger.error(f"Error tracking AI cost: {e}")
            return False, f"Error tracking cost: {str(e)}", cost
    
    def _get_cost_column_for_action(self, action: str) -> Optional[str]:
        """Map action type to space_cost table column."""
        mapping = {
            'transcription': 'transcription_cost',
            'translation': 'translation_cost',
            'summary': 'summary_cost',
            'language_detection': 'transcription_cost',  # Group with transcription
            'tag_generation': 'transcription_cost',  # Group with transcription
            'text_generation': 'summary_cost'  # Group with summary
        }
        
        # Handle complex action names like "translation (en -> es)"
        base_action = action.split(' ')[0].lower()
        return mapping.get(base_action)
    
    def estimate_tokens(self, text: str, is_input: bool = True) -> int:
        """
        Estimate token count from text.
        
        Rough approximation:
        - English: ~1.3 tokens per word
        - Other languages: ~1.5 tokens per word
        - Input typically has more tokens due to system prompts
        """
        word_count = len(text.split())
        multiplier = 1.3
        
        if is_input:
            # Add ~20% for system prompts and formatting
            return int(word_count * multiplier * 1.2)
        else:
            return int(word_count * multiplier)
    
    def estimate_transcription_tokens(self, audio_duration_seconds: float, transcript_length: int) -> Tuple[int, int]:
        """
        Estimate tokens for transcription.
        
        Args:
            audio_duration_seconds: Duration of audio in seconds
            transcript_length: Length of transcript text
            
        Returns:
            tuple: (input_tokens, output_tokens)
        """
        # Rough estimates based on Whisper API patterns
        # Input: ~10 tokens per second of audio
        # Output: Based on transcript word count
        input_tokens = int(audio_duration_seconds * 10)
        output_tokens = self.estimate_tokens(transcript_length * ' ', is_input=False)  # Rough char to word conversion
        
        return input_tokens, output_tokens
    
    def get_user_balance(self, user_id: int) -> float:
        """
        Get user credit balance.
        
        Args:
            user_id: User ID
            
        Returns:
            float: User credit balance
        """
        try:
            with self.db.get_connection() as connection:
                cursor = connection.cursor()
                
                cursor.execute("SELECT credits FROM users WHERE id = %s", (user_id,))
                result = cursor.fetchone()
                
                if result:
                    return float(result[0])
                else:
                    return 0.0
                    
        except Exception as e:
            self.cost_logger.error(f"Error getting user balance: {e}")
            return 0.0