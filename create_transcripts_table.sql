-- SQL to create space_transcripts table
-- This table stores transcriptions for space audio files

CREATE TABLE IF NOT EXISTS `space_transcripts` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `space_id` varchar(255) NOT NULL COMMENT 'Space ID that matches spaces.space_id',
  `language` varchar(10) NOT NULL DEFAULT 'en-US' COMMENT 'Language code for transcript (e.g. en-US, bn-BD)',
  `transcript` TEXT COMMENT 'Full text transcript of the space audio',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `space_id_language` (`space_id`, `language`),
  CONSTRAINT `space_transcripts_space_id_fk` FOREIGN KEY (`space_id`) 
    REFERENCES `spaces` (`space_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;