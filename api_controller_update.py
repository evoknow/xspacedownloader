#!/usr/bin/env python3
"""
Steps to update api_controller.py to integrate spaces download endpoint:

1. Add the following import at the top of api_controller.py:
```python
from api_controller_spaces_download import register_spaces_download_routes
```

2. Add the following code at the end of the file, just before the "Run the application" 
   section (right before the if __name__ == '__main__': block):
```python
# Register additional routes from external modules
register_spaces_download_routes(app, require_api_key, rate_limit, get_db_connection)
```

3. Ensure the space_download_scheduler table exists in your database schema.
   You can check and create it if needed by adding this code to your
   "if __name__ == '__main__':" block:
```python
# Create space_download_scheduler table if it doesn't exist
try:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if space_download_scheduler table exists
    cursor.execute("SHOW TABLES LIKE 'space_download_scheduler'")
    if not cursor.fetchone():
        print("Creating space_download_scheduler table...")
        
        # Create space_download_scheduler table
        cursor.execute("""
        CREATE TABLE space_download_scheduler (
            id INT AUTO_INCREMENT PRIMARY KEY,
            space_id VARCHAR(255) NOT NULL,
            user_id INT NOT NULL DEFAULT 0,
            status ENUM('pending', 'downloading', 'completed', 'failed', 'cancelled') NOT NULL DEFAULT 'pending',
            file_type VARCHAR(10) NOT NULL DEFAULT 'mp3',
            process_id INT NULL,
            progress_in_percent INT NOT NULL DEFAULT 0,
            progress_in_size FLOAT NOT NULL DEFAULT 0,
            error_message TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
            completed_at TIMESTAMP NULL,
            INDEX idx_space_id (space_id),
            INDEX idx_user_id (user_id),
            INDEX idx_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        
        conn.commit()
        print("space_download_scheduler table created successfully")
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f"Error checking/creating space_download_scheduler table: {e}")
```

These changes will integrate the new endpoint for scheduling space downloads
that can be accessed from the PWA frontend at /api/spaces/download/schedule