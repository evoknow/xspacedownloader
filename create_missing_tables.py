#!/usr/bin/env python3
"""
Create Missing Tables Script
Creates any missing tables from the schema for XSpace Downloader.
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

# SQL statements for creating missing tables
# Most tables already exist, so we only need these two:
CREATE_TABLES = {
    'app_settings': """
        CREATE TABLE IF NOT EXISTS `app_settings` (
          `id` int NOT NULL AUTO_INCREMENT,
          `setting_name` varchar(100) NOT NULL COMMENT 'Name of the setting',
          `setting_value` text COMMENT 'Value of the setting',
          `setting_type` varchar(50) DEFAULT 'string' COMMENT 'Type of setting (string, boolean, integer, json)',
          `description` text COMMENT 'Description of the setting',
          `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
          `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (`id`),
          UNIQUE KEY `setting_name` (`setting_name`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Application settings'
    """,
    
    'system_messages': """
        CREATE TABLE IF NOT EXISTS `system_messages` (
          `id` int NOT NULL AUTO_INCREMENT,
          `message` text NOT NULL COMMENT 'The system message content',
          `start_date` datetime NOT NULL COMMENT 'When the message should start displaying',
          `end_date` datetime NOT NULL COMMENT 'When the message should stop displaying',
          `status` int NOT NULL DEFAULT '0' COMMENT 'Status: 0 = pending, 1 = displayed, -1 = deleted',
          `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
          `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (`id`),
          KEY `idx_status` (`status`),
          KEY `idx_dates` (`start_date`,`end_date`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='System-wide messages for users'
    """
}

# Default data to insert
DEFAULT_DATA = {
    'app_settings': [
        ("INSERT IGNORE INTO app_settings (setting_name, setting_value, setting_type, description) VALUES (%s, %s, %s, %s)",
         [
            ('transcription_enabled', 'true', 'boolean', 'Enable/disable transcription service'),
            ('video_generation_enabled', 'true', 'boolean', 'Enable/disable video generation service'),
            ('compute_cost_per_second', '0.001', 'decimal', 'Cost per second for compute operations in USD')
         ])
    ]
}

def create_missing_tables():
    """Create any missing tables from the schema."""
    try:
        db = DatabaseManager()
        
        logger.info("Checking and creating missing tables...")
        
        with db.get_connection() as connection:
            cursor = connection.cursor()
            
            created_tables = []
            for table_name, create_sql in CREATE_TABLES.items():
                try:
                    # Check if table exists
                    cursor.execute(f"""
                        SELECT COUNT(*) as count 
                        FROM information_schema.tables 
                        WHERE table_schema = DATABASE() 
                        AND table_name = '{table_name}'
                    """)
                    exists = cursor.fetchone()[0] > 0
                    
                    if not exists:
                        logger.info(f"Creating table: {table_name}")
                        cursor.execute(create_sql)
                        created_tables.append(table_name)
                    else:
                        logger.info(f"Table already exists: {table_name}")
                        
                except Exception as e:
                    logger.error(f"Error creating table {table_name}: {e}")
            
            # Commit table creations
            connection.commit()
            
            # Insert default data
            logger.info("Inserting default data...")
            for table_name, inserts in DEFAULT_DATA.items():
                if table_name in created_tables or True:  # Always try to insert defaults
                    for query, data_list in inserts:
                        for data in data_list:
                            try:
                                cursor.execute(query, data)
                            except Exception as e:
                                logger.debug(f"Could not insert default data for {table_name}: {e}")
            
            # Commit default data
            connection.commit()
            cursor.close()
            
            if created_tables:
                logger.info(f"Successfully created tables: {', '.join(created_tables)}")
            else:
                logger.info("All tables already exist")
        
        # Check credits column in separate connection
        with db.get_connection() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM information_schema.columns 
                    WHERE table_schema = DATABASE() 
                    AND table_name = 'users' 
                    AND column_name = 'credits'
                """)
                credits_exists = cursor.fetchone()[0] > 0
                
                if not credits_exists:
                    logger.info("Adding credits column to users table...")
                    cursor.execute("""
                        ALTER TABLE users 
                        ADD COLUMN credits DECIMAL(10,2) NOT NULL DEFAULT 5.00 
                        COMMENT 'User credits in USD'
                    """)
                    connection.commit()
                    logger.info("Credits column added successfully")
                else:
                    logger.info("Credits column already exists in users table")
                    
            except Exception as e:
                logger.error(f"Error checking/adding credits column: {e}")
            finally:
                cursor.close()
            
        return True
        
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        return False

def main():
    """Main function."""
    logger.info("=" * 60)
    logger.info("Creating missing database tables for XSpace Downloader")
    logger.info("=" * 60)
    
    success = create_missing_tables()
    if success:
        logger.info("Database setup completed successfully")
        sys.exit(0)
    else:
        logger.error("Database setup failed")
        sys.exit(1)

if __name__ == "__main__":
    main()