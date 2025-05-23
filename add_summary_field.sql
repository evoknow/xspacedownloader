-- Add summary field to space_transcripts table
ALTER TABLE space_transcripts ADD COLUMN summary TEXT NULL AFTER transcript;