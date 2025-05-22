-- create_api_keys_table.sql
-- Creates API keys table for external API access

CREATE TABLE IF NOT EXISTS `api_keys` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL COMMENT 'User ID that owns this API key',
    `key` VARCHAR(255) NOT NULL COMMENT 'The API key string',
    `name` VARCHAR(255) NOT NULL COMMENT 'Descriptive name for this API key',
    `permissions` JSON NULL COMMENT 'List of permissions granted to this key',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When the key was created',
    `last_used_at` TIMESTAMP NULL COMMENT 'When the key was last used',
    `expires_at` TIMESTAMP NULL COMMENT 'When the key expires (NULL = no expiration)',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether the key is active',
    UNIQUE KEY `key` (`key`),
    INDEX `idx_user_id` (`user_id`),
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='API keys for external application access';

-- Insert a default set of permissions (these can be used as reference)
INSERT INTO `api_keys` (`user_id`, `key`, `name`, `permissions`, `created_at`, `expires_at`, `is_active`)
SELECT 
    (SELECT `id` FROM `users` WHERE `email` = 'admin@xspacedownload.com' LIMIT 1), -- assuming admin user exists with this email
    'DEV_API_KEY_DO_NOT_USE_IN_PRODUCTION', -- this should be replaced in production
    'Default Admin API Key',
    JSON_ARRAY(
        'view_users', 'manage_users',
        'view_spaces', 'create_spaces', 'edit_spaces', 'delete_spaces', 'view_all_spaces', 'edit_all_spaces', 'delete_all_spaces',
        'download_spaces', 'download_all_spaces', 'view_downloads', 'manage_downloads', 'view_all_downloads', 'manage_all_downloads',
        'view_tags', 'manage_tags',
        'manage_api_keys',
        'view_stats'
    ),
    NOW(),
    DATE_ADD(NOW(), INTERVAL 1 YEAR),
    1
WHERE EXISTS (SELECT 1 FROM `users` WHERE `email` = 'admin@xspacedownload.com') AND NOT EXISTS (SELECT 1 FROM `api_keys` WHERE `name` = 'Default Admin API Key');

-- Create a read-only API key
INSERT INTO `api_keys` (`user_id`, `key`, `name`, `permissions`, `created_at`, `expires_at`, `is_active`)
SELECT 
    (SELECT `id` FROM `users` WHERE `email` = 'admin@xspacedownload.com' LIMIT 1), -- assuming admin user exists
    'DEV_READONLY_API_KEY', -- this should be replaced in production
    'Default Read-Only API Key',
    JSON_ARRAY(
        'view_spaces',
        'view_downloads',
        'view_tags',
        'view_stats'
    ),
    NOW(),
    DATE_ADD(NOW(), INTERVAL 1 YEAR),
    1
WHERE EXISTS (SELECT 1 FROM `users` WHERE `email` = 'admin@xspacedownload.com') AND NOT EXISTS (SELECT 1 FROM `api_keys` WHERE `name` = 'Default Read-Only API Key');