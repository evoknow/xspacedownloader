-- Create space_clips table for storing audio clips
CREATE TABLE IF NOT EXISTS space_clips (
    id INT PRIMARY KEY AUTO_INCREMENT,
    space_id VARCHAR(255) NOT NULL,  -- Must match spaces.space_id type
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Create clips directory if needed (note: this is just documentation, actual directory creation happens in code)
-- Directory structure: downloads/clips/