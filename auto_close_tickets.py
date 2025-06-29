#!/usr/bin/env python3
"""
Auto-close tickets that haven't been updated in 48 hours after staff response.
This script should be run periodically (e.g., hourly via cron).
"""

import json
import logging
from components.Ticket import Ticket

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Main function to auto-close tickets."""
    try:
        # Load database configuration
        with open('db_config.json', 'r') as f:
            config = json.load(f)
        db_config = config['mysql']
        
        # Create Ticket instance
        ticket = Ticket(db_config)
        
        # Auto-close tickets
        ticket.auto_close_tickets()
        
        logger.info("Auto-close tickets process completed successfully")
        
        ticket.close()
        
    except Exception as e:
        logger.error(f"Error in auto-close tickets process: {e}")
        raise

if __name__ == "__main__":
    main()