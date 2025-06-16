#!/usr/bin/env python3
"""
Cost Tracking Component
Handles AI and compute cost tracking for XSpace Downloader.
"""

import logging
import json
from typing import Dict, Optional, Tuple
from datetime import datetime
from .DatabaseManager import DatabaseManager

logger = logging.getLogger(__name__)

class CostTracker:
    """Handles cost tracking for AI operations and compute resources."""
    
    def __init__(self, config_file="mainconfig.json"):
        """
        Initialize the CostTracker.
        
        Args:
            config_file (str): Path to the configuration file
        """
        self.config_file = config_file
        self.db = DatabaseManager()
        self.compute_cost_per_second = self._get_compute_cost_per_second()
    
    def _get_compute_cost_per_second(self) -> float:
        """
        Get compute cost per second from configuration.
        
        Returns:
            float: Cost per second for compute operations
        """
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                return float(config.get('compute_cost_per_second', 0.001))  # Default $0.001/second
        except Exception as e:
            logger.warning(f"Could not load compute cost from config: {e}, using default")
            return 0.001  # Default fallback
    
    def get_ai_cost(self, vendor: str, model: str) -> Optional[Dict]:
        """
        Get AI cost information for a specific vendor and model.
        
        Args:
            vendor (str): AI vendor (e.g., 'openai', 'claude')
            model (str): Model name
            
        Returns:
            dict: Cost information or None if not found
        """
        try:
            cursor = self.db.connection.cursor(dictionary=True)
            query = """
                SELECT input_token_cost_per_million_tokens, output_token_cost_per_million_tokens
                FROM ai_api_cost
                WHERE vendor = %s AND model = %s
            """
            cursor.execute(query, (vendor, model))
            result = cursor.fetchone()
            cursor.close()
            return result
        except Exception as e:
            logger.error(f"Error getting AI cost for {vendor}/{model}: {e}")
            return None
    
    def calculate_ai_cost(self, vendor: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate the cost of an AI operation.
        
        Args:
            vendor (str): AI vendor
            model (str): Model name
            input_tokens (int): Number of input tokens
            output_tokens (int): Number of output tokens
            
        Returns:
            float: Total cost in USD
        """
        cost_info = self.get_ai_cost(vendor, model)
        if not cost_info:
            logger.warning(f"No cost info found for {vendor}/{model}, using fallback rates")
            # Fallback rates (approximate)
            if 'gpt-4' in model.lower():
                input_cost = 30.0  # $30 per million tokens
                output_cost = 60.0  # $60 per million tokens
            elif 'gpt-3.5' in model.lower():
                input_cost = 1.5  # $1.50 per million tokens
                output_cost = 2.0  # $2.00 per million tokens
            elif 'claude' in model.lower():
                input_cost = 15.0  # $15 per million tokens (approximate)
                output_cost = 75.0  # $75 per million tokens (approximate)
            else:
                input_cost = 10.0  # Generic fallback
                output_cost = 30.0
        else:
            input_cost = cost_info['input_token_cost_per_million_tokens']
            output_cost = cost_info['output_token_cost_per_million_tokens']
        
        # Calculate total cost
        input_cost_usd = (input_tokens / 1_000_000) * input_cost
        output_cost_usd = (output_tokens / 1_000_000) * output_cost
        total_cost = input_cost_usd + output_cost_usd
        
        logger.debug(f"AI cost calculation: {input_tokens} input + {output_tokens} output tokens = ${total_cost:.6f}")
        
        return total_cost
    
    def calculate_compute_cost(self, duration_seconds: float) -> float:
        """
        Calculate compute cost based on duration.
        
        Args:
            duration_seconds (float): Duration in seconds
            
        Returns:
            float: Cost in USD
        """
        cost = duration_seconds * self.compute_cost_per_second
        logger.debug(f"Compute cost calculation: {duration_seconds}s × ${self.compute_cost_per_second}/s = ${cost:.6f}")
        return cost
    
    def record_space_cost(self, space_id: str, user_id: int, cost_type: str, amount: float, 
                         description: str = None, ai_vendor: str = None, ai_model: str = None,
                         input_tokens: int = None, output_tokens: int = None) -> bool:
        """
        Record a cost entry for a space.
        
        Args:
            space_id (str): Space ID
            user_id (int): User ID who incurred the cost
            cost_type (str): Type of cost ('transcription', 'translation', 'compute', 'video_generation')
            amount (float): Cost amount in USD
            description (str, optional): Description of the operation
            ai_vendor (str, optional): AI vendor used
            ai_model (str, optional): AI model used
            input_tokens (int, optional): Number of input tokens
            output_tokens (int, optional): Number of output tokens
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cursor = self.db.connection.cursor()
            
            query = """
                INSERT INTO space_cost (
                    space_id, user_id, cost_type, amount, description,
                    ai_vendor, ai_model, input_tokens, output_tokens,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """
            
            cursor.execute(query, (
                space_id, user_id, cost_type, amount, description,
                ai_vendor, ai_model, input_tokens, output_tokens
            ))
            
            self.db.connection.commit()
            cursor.close()
            
            logger.info(f"Recorded cost: ${amount:.6f} for {cost_type} on space {space_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error recording space cost: {e}")
            return False
    
    def deduct_user_credits(self, user_id: int, amount: float, description: str = None) -> Tuple[bool, float]:
        """
        Deduct credits from a user's account.
        
        Args:
            user_id (int): User ID
            amount (float): Amount to deduct in USD
            description (str, optional): Description of the deduction
            
        Returns:
            tuple: (success, remaining_balance)
        """
        try:
            cursor = self.db.connection.cursor(dictionary=True)
            
            # Get current balance
            cursor.execute("SELECT credits FROM users WHERE id = %s", (user_id,))
            result = cursor.fetchone()
            
            if not result:
                logger.error(f"User {user_id} not found")
                cursor.close()
                return False, 0.0
            
            current_balance = float(result['credits'])
            
            # Check if user has sufficient credits
            if current_balance < amount:
                logger.warning(f"Insufficient credits for user {user_id}: ${current_balance:.2f} < ${amount:.2f}")
                cursor.close()
                return False, current_balance
            
            # Deduct credits
            new_balance = current_balance - amount
            cursor.execute(
                "UPDATE users SET credits = %s, updated_at = NOW() WHERE id = %s",
                (new_balance, user_id)
            )
            
            self.db.connection.commit()
            cursor.close()
            
            logger.info(f"Deducted ${amount:.6f} from user {user_id}. New balance: ${new_balance:.2f}")
            return True, new_balance
            
        except Exception as e:
            logger.error(f"Error deducting user credits: {e}")
            return False, 0.0
    
    def check_user_credits(self, user_id: int) -> float:
        """
        Check a user's current credit balance.
        
        Args:
            user_id (int): User ID
            
        Returns:
            float: Current credit balance
        """
        try:
            cursor = self.db.connection.cursor(dictionary=True)
            cursor.execute("SELECT credits FROM users WHERE id = %s", (user_id,))
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                return float(result['credits'])
            else:
                logger.warning(f"User {user_id} not found")
                return 0.0
                
        except Exception as e:
            logger.error(f"Error checking user credits: {e}")
            return 0.0
    
    def track_transcription_cost(self, space_id: str, user_id: int, vendor: str, model: str,
                               input_tokens: int, output_tokens: int) -> Tuple[bool, float]:
        """
        Track cost for transcription operation.
        
        Args:
            space_id (str): Space ID
            user_id (int): User ID
            vendor (str): AI vendor
            model (str): AI model
            input_tokens (int): Input tokens used
            output_tokens (int): Output tokens used
            
        Returns:
            tuple: (success, cost_amount)
        """
        cost = self.calculate_ai_cost(vendor, model, input_tokens, output_tokens)
        
        # Record the cost
        success = self.record_space_cost(
            space_id=space_id,
            user_id=user_id,
            cost_type='transcription',
            amount=cost,
            description=f"Transcription using {vendor}/{model}",
            ai_vendor=vendor,
            ai_model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )
        
        if success:
            # Deduct from user credits
            deduction_success, remaining_balance = self.deduct_user_credits(user_id, cost)
            return deduction_success, cost
        
        return False, cost
    
    def track_translation_cost(self, space_id: str, user_id: int, vendor: str, model: str,
                             input_tokens: int, output_tokens: int) -> Tuple[bool, float]:
        """
        Track cost for translation operation.
        
        Args:
            space_id (str): Space ID
            user_id (int): User ID
            vendor (str): AI vendor
            model (str): AI model
            input_tokens (int): Input tokens used
            output_tokens (int): Output tokens used
            
        Returns:
            tuple: (success, cost_amount)
        """
        cost = self.calculate_ai_cost(vendor, model, input_tokens, output_tokens)
        
        # Record the cost
        success = self.record_space_cost(
            space_id=space_id,
            user_id=user_id,
            cost_type='translation',
            amount=cost,
            description=f"Translation using {vendor}/{model}",
            ai_vendor=vendor,
            ai_model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )
        
        if success:
            # Deduct from user credits
            deduction_success, remaining_balance = self.deduct_user_credits(user_id, cost)
            return deduction_success, cost
        
        return False, cost
    
    def track_compute_cost(self, space_id: str, user_id: int, operation: str, 
                          duration_seconds: float) -> Tuple[bool, float]:
        """
        Track cost for compute operation (MP3/MP4 generation).
        
        Args:
            space_id (str): Space ID
            user_id (int): User ID
            operation (str): Type of operation ('mp3_generation', 'mp4_generation')
            duration_seconds (float): Duration of the operation
            
        Returns:
            tuple: (success, cost_amount)
        """
        cost = self.calculate_compute_cost(duration_seconds)
        
        # Record the cost
        success = self.record_space_cost(
            space_id=space_id,
            user_id=user_id,
            cost_type='compute',
            amount=cost,
            description=f"{operation} ({duration_seconds:.2f}s)"
        )
        
        if success:
            # Deduct from user credits
            deduction_success, remaining_balance = self.deduct_user_credits(user_id, cost)
            return deduction_success, cost
        
        return False, cost