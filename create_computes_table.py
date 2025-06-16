#!/usr/bin/env python3
"""
Create computes table for tracking MP3/MP4 compute costs.
"""

import logging
import sys
from components.DatabaseManager import DatabaseManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_computes_table():
    """Create the computes table for tracking compute costs."""
    try:
        db = DatabaseManager()
        
        with db.get_connection() as connection:
            cursor = connection.cursor()
            
            # Create computes table
            create_table_sql = """
                CREATE TABLE IF NOT EXISTS `computes` (
                  `id` int NOT NULL AUTO_INCREMENT,
                  `user_id` int DEFAULT NULL COMMENT 'User ID if logged in',
                  `cookie_id` varchar(255) DEFAULT NULL COMMENT 'Cookie ID for visitors',
                  `space_id` varchar(100) NOT NULL COMMENT 'Space ID for the operation',
                  `action` varchar(50) NOT NULL COMMENT 'Compute action: mp3, mp4',
                  `compute_time_seconds` decimal(10,2) NOT NULL COMMENT 'Compute time in seconds',
                  `cost_per_second` decimal(10,6) NOT NULL COMMENT 'Cost per second rate used',
                  `total_cost` decimal(10,6) NOT NULL COMMENT 'Total compute cost',
                  `balance_before` decimal(10,2) DEFAULT NULL COMMENT 'User balance before transaction',
                  `balance_after` decimal(10,2) DEFAULT NULL COMMENT 'User balance after transaction',
                  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (`id`),
                  KEY `idx_user_id` (`user_id`),
                  KEY `idx_cookie_id` (`cookie_id`),
                  KEY `idx_space_id` (`space_id`),
                  KEY `idx_action` (`action`),
                  KEY `idx_created_at` (`created_at`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Compute cost transactions for MP3/MP4 generation'
            """
            
            cursor.execute(create_table_sql)
            connection.commit()
            cursor.close()
            
            logger.info("Successfully created computes table")
            return True
            
    except Exception as e:
        logger.error(f"Error creating computes table: {e}")
        return False

def main():
    """Main function."""
    logger.info("=" * 60)
    logger.info("Creating computes table for compute cost tracking")
    logger.info("=" * 60)
    
    success = create_computes_table()
    if success:
        logger.info("Database table creation completed successfully")
        sys.exit(0)
    else:
        logger.error("Database table creation failed")
        sys.exit(1)

if __name__ == "__main__":
    main()