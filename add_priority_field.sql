-- Add priority field to space_download_scheduler table
-- Priority values: 1 = highest, 2 = high, 3 = normal (default), 4 = low, 5 = lowest

ALTER TABLE `space_download_scheduler` 
ADD COLUMN `priority` tinyint NOT NULL DEFAULT 3 COMMENT 'Job priority: 1=highest, 2=high, 3=normal, 4=low, 5=lowest'
AFTER `status`;

-- Add index for priority to improve query performance
ALTER TABLE `space_download_scheduler` 
ADD KEY `idx_priority_status` (`priority`, `status`);

-- Update the existing schema comment
ALTER TABLE `space_download_scheduler` 
COMMENT='Table to track Space audio download progress with priority support';