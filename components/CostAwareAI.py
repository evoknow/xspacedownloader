#!/usr/bin/env python3
"""
Cost-Aware AI Component

Wrapper around AI components that tracks costs and deducts credits from user balance.
"""

import logging
from typing import Dict, Optional, Tuple, Union
from .AI import AI
from .CostLogger import CostLogger

logger = logging.getLogger(__name__)

class CostAwareAI:
    """AI wrapper that tracks costs and manages user credits."""
    
    def __init__(self):
        """Initialize the cost-aware AI component."""
        self.ai = AI()
        self.cost_logger = CostLogger()
        self.provider_name = self.ai.get_provider_name() if hasattr(self.ai, 'get_provider_name') else 'unknown'
        
    def get_provider_name(self) -> str:
        """Get the AI provider name."""
        return self.provider_name
    
    def _extract_content_and_usage(self, ai_result: Union[str, Dict]) -> Tuple[str, Dict]:
        """
        Extract content and usage information from AI result.
        
        Args:
            ai_result: Result from AI provider (string or dict with usage info)
            
        Returns:
            tuple: (content, usage_info)
        """
        if isinstance(ai_result, dict):
            content = ai_result.get('content', '')
            usage = ai_result.get('usage', {})
        else:
            content = str(ai_result)
            usage = {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}
        
        return content, usage
    
    def translate_with_cost_tracking(self, space_id: str, from_lang: str, to_lang: str, 
                                   content: str) -> Tuple[bool, Union[str, Dict]]:
        """
        Translate content with cost tracking and credit deduction.
        
        Args:
            space_id: Space ID for cost tracking
            from_lang: Source language
            to_lang: Target language
            content: Content to translate
            
        Returns:
            tuple: (success, result_or_error)
        """
        try:
            # Call AI translation
            success, result = self.ai.translate(from_lang, to_lang, content)
            
            if not success:
                return False, result
            
            # Extract content and usage information
            translated_content, usage = self._extract_content_and_usage(result)
            
            # Track cost if we have usage information
            if usage.get('input_tokens', 0) > 0 or usage.get('output_tokens', 0) > 0:
                cost_success, cost_message, cost = self.cost_logger.track_ai_operation(
                    space_id=space_id,
                    action=f"translation ({from_lang} -> {to_lang})",
                    vendor=self.provider_name.lower().replace('ai', ''),  # e.g., 'openai' -> 'openai'
                    model=getattr(self.ai.provider, 'model', 'unknown') if hasattr(self.ai, 'provider') else 'unknown',
                    input_tokens=usage.get('input_tokens', 0),
                    output_tokens=usage.get('output_tokens', 0)
                )
                
                if not cost_success:
                    logger.warning(f"Translation successful but cost tracking failed: {cost_message}")
                    return False, {'error': cost_message}
            
            return True, translated_content
            
        except Exception as e:
            logger.error(f"Error in translate_with_cost_tracking: {e}")
            return False, {'error': f"Translation failed: {str(e)}"}
    
    def summary_with_cost_tracking(self, space_id: str, content: str, 
                                 max_length: Optional[int] = None) -> Tuple[bool, Union[str, Dict]]:
        """
        Generate summary with cost tracking and credit deduction.
        
        Args:
            space_id: Space ID for cost tracking
            content: Content to summarize
            max_length: Maximum length of summary
            
        Returns:
            tuple: (success, result_or_error)
        """
        try:
            # Call AI summary
            success, result = self.ai.summary(content, max_length)
            
            if not success:
                return False, result
            
            # Extract content and usage information
            summary_content, usage = self._extract_content_and_usage(result)
            
            # Track cost if we have usage information
            if usage.get('input_tokens', 0) > 0 or usage.get('output_tokens', 0) > 0:
                cost_success, cost_message, cost = self.cost_logger.track_ai_operation(
                    space_id=space_id,
                    action="summary",
                    vendor=self.provider_name.lower().replace('ai', ''),
                    model=getattr(self.ai.provider, 'model', 'unknown') if hasattr(self.ai, 'provider') else 'unknown',
                    input_tokens=usage.get('input_tokens', 0),
                    output_tokens=usage.get('output_tokens', 0)
                )
                
                if not cost_success:
                    logger.warning(f"Summary successful but cost tracking failed: {cost_message}")
                    return False, {'error': cost_message}
            
            return True, summary_content
            
        except Exception as e:
            logger.error(f"Error in summary_with_cost_tracking: {e}")
            return False, {'error': f"Summary failed: {str(e)}"}
    
    def generate_text_with_cost_tracking(self, space_id: str, prompt: str, 
                                       max_tokens: int = 150) -> Dict:
        """
        Generate text with cost tracking and credit deduction.
        
        Args:
            space_id: Space ID for cost tracking
            prompt: Text prompt
            max_tokens: Maximum tokens to generate
            
        Returns:
            dict: Result with 'success' and 'text' or 'error' keys
        """
        try:
            # Call AI text generation
            result = self.ai.generate_text(prompt, max_tokens)
            
            if not result.get('success'):
                return result
            
            # Extract content and usage information
            generated_text = result.get('text', '')
            
            # For text generation, we need to estimate token usage since the AI.py wrapper
            # might not return detailed usage info. This is a fallback approach.
            estimated_input_tokens = len(prompt.split()) * 1.33  # Rough estimate
            estimated_output_tokens = len(generated_text.split()) * 1.33
            
            # Try to get actual usage if available
            usage = result.get('usage', {
                'input_tokens': int(estimated_input_tokens),
                'output_tokens': int(estimated_output_tokens),
                'total_tokens': int(estimated_input_tokens + estimated_output_tokens)
            })
            
            # Track cost
            cost_success, cost_message, cost = self.cost_logger.track_ai_operation(
                space_id=space_id,
                action="text_generation",
                vendor=self.provider_name.lower().replace('ai', ''),
                model=getattr(self.ai.provider, 'model', 'unknown') if hasattr(self.ai, 'provider') else 'unknown',
                input_tokens=usage.get('input_tokens', 0),
                output_tokens=usage.get('output_tokens', 0)
            )
            
            if not cost_success:
                logger.warning(f"Text generation successful but cost tracking failed: {cost_message}")
                return {'success': False, 'error': cost_message}
            
            return {'success': True, 'text': generated_text}
            
        except Exception as e:
            logger.error(f"Error in generate_text_with_cost_tracking: {e}")
            return {'success': False, 'error': f"Text generation failed: {str(e)}"}
    
    # Backward compatibility methods (without cost tracking)
    def translate(self, from_lang: str, to_lang: str, content: str) -> Tuple[bool, Union[str, Dict]]:
        """Backward compatibility translate method without cost tracking."""
        success, result = self.ai.translate(from_lang, to_lang, content)
        if success and isinstance(result, dict):
            return True, result.get('content', result)
        return success, result
    
    def summary(self, content: str, max_length: Optional[int] = None) -> Tuple[bool, Union[str, Dict]]:
        """Backward compatibility summary method without cost tracking."""
        success, result = self.ai.summary(content, max_length)
        if success and isinstance(result, dict):
            return True, result.get('content', result)
        return success, result
    
    def generate_text(self, prompt: str, max_tokens: int = 150) -> Dict:
        """Backward compatibility generate_text method without cost tracking."""
        return self.ai.generate_text(prompt, max_tokens)