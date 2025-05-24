-- Create only the space_clips table (since you already have the count columns)

CREATE TABLE IF NOT EXISTS space_clips (
    id INT PRIMARY KEY AUTO_INCREMENT,
    space_id VARCHAR(255) NOT NULL,  -- Matches your spaces.space_id type
    clip_title VARCHAR(255) NOT NULL,
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    duration FLOAT GENERATED ALWAYS AS (end_time - start_time) STORED,
    filename VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    download_count INT DEFAULT 0,
    INDEX idx_space_id (space_id),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (space_id) REFERENCES spaces(space_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Verify it was created
DESCRIBE space_clips;