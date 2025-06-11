-- Fix transcript column size to handle larger transcripts
-- The current TEXT type has a limit of 65,535 bytes (~65KB)
-- MEDIUMTEXT can store up to 16,777,215 bytes (~16MB)
-- LONGTEXT can store up to 4,294,967,295 bytes (~4GB)

-- Change transcript column to MEDIUMTEXT (16MB should be more than enough for most transcripts)
ALTER TABLE `space_transcripts` 
MODIFY COLUMN `transcript` MEDIUMTEXT COLLATE utf8mb4_unicode_ci 
COMMENT 'Full text transcript of the space audio (up to 16MB)';

-- Also update summary column to MEDIUMTEXT for consistency
ALTER TABLE `space_transcripts` 
MODIFY COLUMN `summary` MEDIUMTEXT COLLATE utf8mb4_unicode_ci 
COMMENT 'AI-generated summary of the transcript';

-- Add index on language for better query performance
ALTER TABLE `space_transcripts` 
ADD INDEX `idx_language` (`language`);

-- Show the updated table structure
SHOW CREATE TABLE `space_transcripts`;