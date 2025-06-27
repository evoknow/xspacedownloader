-- Create TTS jobs table
CREATE TABLE IF NOT EXISTS tts_jobs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    space_id VARCHAR(255) NOT NULL,
    user_id INT NOT NULL,
    source_text TEXT NOT NULL,
    target_language VARCHAR(10) NOT NULL,
    status ENUM('pending', 'in_progress', 'completed', 'failed') DEFAULT 'pending',
    progress INT DEFAULT 0,
    priority INT DEFAULT 1,
    job_data JSON,
    output_file VARCHAR(500),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    failed_at TIMESTAMP NULL,
    INDEX idx_status (status),
    INDEX idx_user_id (user_id),
    INDEX idx_space_id (space_id),
    INDEX idx_priority_created (priority DESC, created_at ASC),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);