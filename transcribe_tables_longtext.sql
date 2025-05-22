-- SQL to modify space_transcripts table to use LONGTEXT
-- This allows for storing transcripts longer than 65535 bytes

ALTER TABLE `space_transcripts` 
MODIFY COLUMN `transcript` LONGTEXT COMMENT 'Full text transcript of the space audio';