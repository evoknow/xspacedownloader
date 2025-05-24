-- Add play_count and download_count columns to spaces table
ALTER TABLE spaces 
ADD COLUMN play_count INT DEFAULT 0 AFTER status,
ADD COLUMN download_count INT DEFAULT 0 AFTER play_count;

-- Add indexes for better performance
ALTER TABLE spaces
ADD INDEX idx_popularity ((play_count * 1.5 + download_count)) DESC;

-- Update existing records to have 0 counts
UPDATE spaces SET play_count = 0, download_count = 0 WHERE play_count IS NULL OR download_count IS NULL;