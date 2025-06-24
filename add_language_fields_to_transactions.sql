-- Add language fields to transactions table for better translation tracking
ALTER TABLE transactions 
ADD COLUMN source_language varchar(10) DEFAULT NULL COMMENT 'Source language for translation',
ADD COLUMN target_language varchar(10) DEFAULT NULL COMMENT 'Target language for translation';