-- Add priority column to space_download_scheduler table
-- This column is used for queue priority management in the admin interface

-- Check if column exists before adding it
SET @dbname = DATABASE();
SET @tablename = 'space_download_scheduler';
SET @columnname = 'priority';
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      (TABLE_SCHEMA = @dbname)
      AND (TABLE_NAME = @tablename)
      AND (COLUMN_NAME = @columnname)
  ) > 0,
  "SELECT 'Column priority already exists in space_download_scheduler table';",
  "ALTER TABLE space_download_scheduler ADD COLUMN priority INT NOT NULL DEFAULT 3 COMMENT '1=highest, 2=high, 3=normal, 4=low, 5=lowest';"
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;

-- Add index on priority and status for efficient queue queries
-- First check if index exists
SET @indexname = 'idx_priority_status';
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE
      (TABLE_SCHEMA = @dbname)
      AND (TABLE_NAME = @tablename)
      AND (INDEX_NAME = @indexname)
  ) > 0,
  "SELECT 'Index idx_priority_status already exists';",
  "CREATE INDEX idx_priority_status ON space_download_scheduler(priority, status);"
));
PREPARE createIndexIfNotExists FROM @preparedStatement;
EXECUTE createIndexIfNotExists;
DEALLOCATE PREPARE createIndexIfNotExists;

-- Show the updated table structure
DESCRIBE space_download_scheduler;

-- Show some statistics about current jobs by priority
SELECT 
    priority,
    CASE priority
        WHEN 1 THEN 'Highest'
        WHEN 2 THEN 'High'
        WHEN 3 THEN 'Normal'
        WHEN 4 THEN 'Low'
        WHEN 5 THEN 'Lowest'
        ELSE 'Unknown'
    END as priority_label,
    COUNT(*) as job_count,
    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_count,
    SUM(CASE WHEN status = 'downloading' THEN 1 ELSE 0 END) as downloading_count,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_count,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_count
FROM space_download_scheduler
GROUP BY priority
ORDER BY priority;