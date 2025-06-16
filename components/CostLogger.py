#!/usr/bin/env python3
"""
Cost Logger Component for AI Operations

Handles cost tracking, credit deduction, and transaction logging for AI operations.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from flask import session
from .DatabaseManager import DatabaseManager

class CostLogger:
    """Handles AI cost tracking and credit deduction."""
    
    def __init__(self):
        """Initialize the CostLogger component."""
        self.db = DatabaseManager()
        self._setup_cost_logging()
    
    def _setup_cost_logging(self):
        """Setup cost.log file logging."""
        # Create logs directory if it doesn't exist
        logs_dir = Path('logs')
        logs_dir.mkdir(exist_ok=True)
        
        # Setup cost logger
        self.cost_logger = logging.getLogger('cost_operations')
        self.cost_logger.setLevel(logging.INFO)
        
        # Remove existing handlers to avoid duplicates
        for handler in self.cost_logger.handlers[:]:
            self.cost_logger.removeHandler(handler)
        
        # Create file handler for cost.log
        cost_log_file = logs_dir / 'cost.log'
        file_handler = logging.FileHandler(cost_log_file)
        file_handler.setLevel(logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        self.cost_logger.addHandler(file_handler)
        self.cost_logger.propagate = False
    
    def get_user_info(self) -> Tuple[Optional[int], Optional[str]]:
        """
        Get current user ID and cookie ID.
        
        Returns:
            tuple: (user_id, cookie_id)
        """
        user_id = session.get('user_id')
        cookie_id = session.get('visitor_id')
        
        if not cookie_id:
            # Generate cookie ID if not exists
            import uuid
            cookie_id = str(uuid.uuid4())
            session['visitor_id'] = cookie_id
            session.permanent = True
        
        return user_id, cookie_id
    
    def get_ai_model_costs(self, vendor: str, model: str) -> Optional[Dict[str, float]]:
        """
        Get AI model costs from database.
        
        Args:
            vendor (str): AI vendor (e.g., 'openai', 'anthropic')
            model (str): Model name
            
        Returns:
            dict: Model costs or None if not found
        """
        try:
            connection = self.db.pool.get_connection()
            
            try:
                cursor = connection.cursor(dictionary=True)
                
                cursor.execute("""
                    SELECT input_token_cost_per_million_tokens, output_token_cost_per_million_tokens
                    FROM ai_api_cost 
                    WHERE vendor = %s AND model = %s
                """, (vendor, model))
                
                result = cursor.fetchone()
                cursor.close()
                
                if result:
                    return {
                        'input_cost_per_million': float(result['input_token_cost_per_million_tokens']),
                        'output_cost_per_million': float(result['output_token_cost_per_million_tokens'])
                    }
                    
                return None
                
            finally:
                connection.close()
                
        except Exception as e:
            self.cost_logger.error(f"Error getting AI model costs: {e}")
            return None
    
    def calculate_cost(self, vendor: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate total cost for AI operation.
        
        Args:
            vendor (str): AI vendor
            model (str): Model name
            input_tokens (int): Number of input tokens
            output_tokens (int): Number of output tokens
            
        Returns:
            float: Total cost in credits
        """
        costs = self.get_ai_model_costs(vendor, model)
        if not costs:
            # Default fallback costs if not in database
            self.cost_logger.warning(f"No costs found for {vendor}/{model}, using defaults")
            costs = {
                'input_cost_per_million': 0.00015,  # Default $0.00015 per 1M input tokens
                'output_cost_per_million': 0.0006   # Default $0.0006 per 1M output tokens
            }
        
        input_cost = (input_tokens / 1000000) * costs['input_cost_per_million']
        output_cost = (output_tokens / 1000000) * costs['output_cost_per_million']
        total_cost = input_cost + output_cost
        
        return round(total_cost, 6)
    
    def get_user_balance(self, user_id: int) -> float:
        """
        Get user's current credit balance.
        
        Args:
            user_id (int): User ID
            
        Returns:
            float: Current balance
        """
        try:
            connection = self.db.pool.get_connection()
            
            try:
                cursor = connection.cursor(dictionary=True)
                
                cursor.execute("SELECT credits FROM users WHERE id = %s", (user_id,))
                result = cursor.fetchone()
                cursor.close()
                
                if result:
                    return float(result['credits'])
                    
                return 0.0
                
            finally:
                connection.close()
                
        except Exception as e:
            self.cost_logger.error(f"Error getting user balance: {e}")
            return 0.0
    
    def deduct_credits(self, user_id: int, amount: float) -> bool:
        """
        Deduct credits from user balance.
        
        Args:
            user_id (int): User ID
            amount (float): Amount to deduct
            
        Returns:
            bool: True if successful
        """
        try:
            connection = self.db.pool.get_connection()
            
            try:
                cursor = connection.cursor()
                
                cursor.execute("""
                    UPDATE users 
                    SET credits = credits - %s 
                    WHERE id = %s AND credits >= %s
                """, (amount, user_id, amount))
                
                success = cursor.rowcount > 0
                connection.commit()
                cursor.close()
                
                return success
                
            finally:
                connection.close()
                
        except Exception as e:
            self.cost_logger.error(f"Error deducting credits: {e}")
            return False
    
    def record_transaction(self, user_id: Optional[int], cookie_id: str, space_id: str, 
                          action: str, ai_model: str, input_tokens: int, output_tokens: int, 
                          cost: float, balance_before: Optional[float], balance_after: Optional[float]) -> bool:
        """
        Record transaction in database.
        
        Args:
            user_id: User ID (None for visitors)
            cookie_id: Cookie ID
            space_id: Space ID
            action: Action type (summary, transcript, translation)
            ai_model: AI model used
            input_tokens: Input tokens used
            output_tokens: Output tokens used
            cost: Total cost
            balance_before: Balance before transaction
            balance_after: Balance after transaction
            
        Returns:
            bool: True if successful
        """
        try:
            connection = self.db.pool.get_connection()
            
            try:
                cursor = connection.cursor()
                
                cursor.execute("""
                    INSERT INTO transactions 
                    (user_id, cookie_id, space_id, action, ai_model, input_tokens, 
                     output_tokens, cost, balance_before, balance_after)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, cookie_id, space_id, action, ai_model, input_tokens, 
                      output_tokens, cost, balance_before, balance_after))
                
                connection.commit()
                cursor.close()
                
                return True
                
            finally:
                connection.close()
                
        except Exception as e:
            self.cost_logger.error(f"Error recording transaction: {e}")
            return False
    
    def track_ai_operation(self, space_id: str, action: str, vendor: str, model: str, 
                          input_tokens: int, output_tokens: int) -> Tuple[bool, str, float]:
        """
        Track AI operation cost and deduct from user balance.
        
        Args:
            space_id: Space ID
            action: Action type (summary, transcript, translation)
            vendor: AI vendor
            model: AI model
            input_tokens: Input tokens used
            output_tokens: Output tokens used
            
        Returns:
            tuple: (success, message, cost)
        """
        user_id, cookie_id = self.get_user_info()
        cost = self.calculate_cost(vendor, model, input_tokens, output_tokens)
        
        # Get user balance if logged in
        balance_before = None
        balance_after = None
        
        if user_id:
            balance_before = self.get_user_balance(user_id)
            
            # Check if user has sufficient credits
            if balance_before < cost:
                message = f"Insufficient credits. Required: {cost:.6f}, Available: {balance_before:.2f}"
                self.cost_logger.warning(f"User {user_id} - {message}")
                return False, message, cost
            
            # Deduct credits
            if self.deduct_credits(user_id, cost):
                balance_after = balance_before - cost
                self.cost_logger.info(f"User {user_id} - Deducted {cost:.6f} credits. Balance: {balance_before:.2f} -> {balance_after:.2f}")
            else:
                message = "Failed to deduct credits from user balance"
                self.cost_logger.error(f"User {user_id} - {message}")
                return False, message, cost
        else:
            # Visitor - block AI operations
            message = "AI operations require user login"
            self.cost_logger.warning(f"Visitor {cookie_id} - {message}")
            return False, message, cost
        
        # Record transaction
        self.record_transaction(
            user_id, cookie_id, space_id, action, f"{vendor}/{model}",
            input_tokens, output_tokens, cost, balance_before, balance_after
        )
        
        # Log to cost.log
        user_identifier = f"user_id:{user_id}" if user_id else f"cookie_id:{cookie_id}"
        action_details = action
        if action == "translation":
            action_details = f"{action} ({vendor}/{model})"
        
        self.cost_logger.info(
            f"{user_identifier} | space_id:{space_id} | action:{action_details} | "
            f"model:{vendor}/{model} | input_tokens:{input_tokens} | output_tokens:{output_tokens} | "
            f"cost:{cost:.6f} | balance_before:{balance_before} | balance_after:{balance_after}"
        )
        
        return True, "Cost tracked successfully", cost
    
    def get_compute_cost_per_second(self) -> float:
        """
        Get compute cost per second from app settings.
        
        Returns:
            float: Cost per second
        """
        try:
            connection = self.db.pool.get_connection()
            
            try:
                cursor = connection.cursor(dictionary=True)
                
                cursor.execute("""
                    SELECT setting_value FROM app_settings 
                    WHERE setting_name = 'compute_cost_per_second'
                """)
                result = cursor.fetchone()
                cursor.close()
                
                if result:
                    return float(result['setting_value'])
                    
                # Default fallback
                return 0.001
                
            finally:
                connection.close()
                
        except Exception as e:
            self.cost_logger.error(f"Error getting compute cost per second: {e}")
            return 0.001
    
    def record_compute_transaction(self, user_id: Optional[int], cookie_id: str, space_id: str, 
                                  action: str, compute_time_seconds: float, cost_per_second: float,
                                  total_cost: float, balance_before: Optional[float], 
                                  balance_after: Optional[float]) -> bool:
        """
        Record compute transaction in database.
        
        Args:
            user_id: User ID (None for visitors)
            cookie_id: Cookie ID
            space_id: Space ID
            action: Action type (mp3, mp4)
            compute_time_seconds: Compute time in seconds
            cost_per_second: Cost per second rate
            total_cost: Total compute cost
            balance_before: Balance before transaction
            balance_after: Balance after transaction
            
        Returns:
            bool: True if successful
        """
        try:
            connection = self.db.pool.get_connection()
            
            try:
                cursor = connection.cursor()
                
                cursor.execute("""
                    INSERT INTO computes 
                    (user_id, cookie_id, space_id, action, compute_time_seconds, 
                     cost_per_second, total_cost, balance_before, balance_after)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, cookie_id, space_id, action, compute_time_seconds,
                      cost_per_second, total_cost, balance_before, balance_after))
                
                connection.commit()
                cursor.close()
                
                return True
                
            finally:
                connection.close()
                
        except Exception as e:
            self.cost_logger.error(f"Error recording compute transaction: {e}")
            return False
    
    def track_compute_operation(self, space_id: str, action: str, compute_time_seconds: float) -> Tuple[bool, str, float]:
        """
        Track compute operation cost and deduct from user balance.
        
        Args:
            space_id: Space ID
            action: Action type (mp3, mp4)
            compute_time_seconds: Compute time in seconds
            
        Returns:
            tuple: (success, message, cost)
        """
        user_id, cookie_id = self.get_user_info()
        cost_per_second = self.get_compute_cost_per_second()
        total_cost = round(compute_time_seconds * cost_per_second, 6)
        
        # Get user balance if logged in
        balance_before = None
        balance_after = None
        
        if user_id:
            balance_before = self.get_user_balance(user_id)
            
            # Check if user has sufficient credits
            if balance_before < total_cost:
                message = f"Insufficient credits. Required: {total_cost:.6f}, Available: {balance_before:.2f}"
                self.cost_logger.warning(f"User {user_id} - {message}")
                return False, message, total_cost
            
            # Deduct credits
            if self.deduct_credits(user_id, total_cost):
                balance_after = balance_before - total_cost
                self.cost_logger.info(f"User {user_id} - Deducted {total_cost:.6f} credits for {action}. Balance: {balance_before:.2f} -> {balance_after:.2f}")
            else:
                message = "Failed to deduct credits from user balance"
                self.cost_logger.error(f"User {user_id} - {message}")
                return False, message, total_cost
        else:
            # Visitor - block compute operations  
            message = "Compute operations require user login"
            self.cost_logger.warning(f"Visitor {cookie_id} - {message}")
            return False, message, total_cost
        
        # Record compute transaction
        self.record_compute_transaction(
            user_id, cookie_id, space_id, action, compute_time_seconds,
            cost_per_second, total_cost, balance_before, balance_after
        )
        
        # Log to cost.log
        user_identifier = f"user_id:{user_id}" if user_id else f"cookie_id:{cookie_id}"
        
        self.cost_logger.info(
            f"{user_identifier} | space_id:{space_id} | action:{action} | "
            f"compute_time:{compute_time_seconds:.2f}s | cost_per_second:{cost_per_second:.6f} | "
            f"total_cost:{total_cost:.6f} | balance_before:{balance_before} | balance_after:{balance_after}"
        )
        
        return True, "Compute cost tracked successfully", total_cost