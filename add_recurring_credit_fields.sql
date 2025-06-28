-- Add recurring credit fields to users table
ALTER TABLE users 
ADD COLUMN recurring_credits INT DEFAULT 0 COMMENT 'Monthly recurring credit amount for lifetime subscriptions',
ADD COLUMN last_credit_reset DATETIME NULL COMMENT 'Last time recurring credits were reset';

-- Create index on last_credit_reset for efficient cron job queries
CREATE INDEX idx_users_last_credit_reset ON users(last_credit_reset);