#!/usr/bin/env python3
"""
Update database schema for tickets system.
"""

import json
import mysql.connector
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    try:
        # Load database configuration
        with open('db_config.json', 'r') as f:
            config = json.load(f)
        
        # Remove unsupported parameters
        db_config = config['mysql'].copy()
        db_config.pop('use_ssl', None)
        
        # Connect to database
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Check if tickets table exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = %s AND table_name = 'tickets'
        """, (db_config['database'],))
        
        if cursor.fetchone()[0] == 0:
            logger.info("Creating tickets table...")
            cursor.execute("""
                CREATE TABLE `tickets` (
                  `id` int NOT NULL AUTO_INCREMENT,
                  `user_id` int NOT NULL COMMENT 'Ticket creator',
                  `issue_title` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Issue title',
                  `issue_detail` json NOT NULL COMMENT 'Issue details including images/PDFs',
                  `priority` tinyint NOT NULL DEFAULT '0' COMMENT '0-normal, 1-medium, 2-high, 3-critical',
                  `opened_at` datetime NOT NULL COMMENT 'When ticket was opened',
                  `last_updated_by_owner` datetime DEFAULT NULL COMMENT 'Last update by ticket owner',
                  `responded_by_staff_id` int DEFAULT NULL COMMENT 'Staff user ID who responded',
                  `response_date` datetime DEFAULT NULL COMMENT 'When staff responded',
                  `response` json DEFAULT NULL COMMENT 'Array of timestamp:response pairs',
                  `last_updated_by_staff` datetime DEFAULT NULL COMMENT 'Last update by staff',
                  `status` tinyint NOT NULL DEFAULT '0' COMMENT '0-open, 1-responded, 2-closed, -1-deleted by owner, -9-deleted by staff, -6-archived',
                  PRIMARY KEY (`id`),
                  KEY `idx_user_id` (`user_id`),
                  KEY `idx_status` (`status`),
                  KEY `idx_priority` (`priority`),
                  KEY `idx_staff_id` (`responded_by_staff_id`),
                  KEY `idx_opened_at` (`opened_at`),
                  CONSTRAINT `tickets_user_fk` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
                  CONSTRAINT `tickets_staff_fk` FOREIGN KEY (`responded_by_staff_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Support ticket system'
            """)
            logger.info("Tickets table created successfully")
        else:
            logger.info("Tickets table already exists")
        
        # Check if is_staff column exists in users table
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.columns 
            WHERE table_schema = %s 
            AND table_name = 'users' 
            AND column_name = 'is_staff'
        """, (db_config['database'],))
        
        if cursor.fetchone()[0] == 0:
            logger.info("Adding is_staff column to users table...")
            cursor.execute("""
                ALTER TABLE `users` 
                ADD COLUMN `is_staff` tinyint(1) DEFAULT '0' 
                COMMENT 'Whether user is support staff' 
                AFTER `is_admin`
            """)
            logger.info("is_staff column added successfully")
        else:
            logger.info("is_staff column already exists")
        
        # Check if display_name column exists in users table
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.columns 
            WHERE table_schema = %s 
            AND table_name = 'users' 
            AND column_name = 'display_name'
        """, (db_config['database'],))
        
        if cursor.fetchone()[0] == 0:
            logger.info("Adding display_name column to users table...")
            cursor.execute("""
                ALTER TABLE `users` 
                ADD COLUMN `display_name` varchar(100) DEFAULT NULL 
                COMMENT 'Display name for user' 
                AFTER `email`
            """)
            logger.info("display_name column added successfully")
        else:
            logger.info("display_name column already exists")
        
        conn.commit()
        logger.info("Schema update completed successfully")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error updating schema: {e}")
        raise

if __name__ == "__main__":
    main()