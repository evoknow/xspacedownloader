#!/usr/bin/env python3
"""
API Route for scheduling space downloads in XSpace Downloader
This module handles the route for scheduling space downloads through the API.
"""

from flask import request, jsonify, g
from functools import wraps
import logging
import json
import time
from datetime import datetime

# Configure logging
logging.basicConfig(
    filename='api_server.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('api_spaces_download')

def register_spaces_download_routes(app, require_api_key, rate_limit, get_db_connection):
    """Register the routes for scheduling space downloads."""
    
    @app.route('/api/spaces/download/schedule', methods=['POST'])
    @rate_limit
    def schedule_space_download():
        """Schedule a space for download without requiring API key."""
        data = request.json
        
        # Validate required fields
        if 'space_url' not in data:
            return jsonify({'success': False, 'error': 'Space URL is required'}), 400
        
        try:
            # Get database connection
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Extract space_id from URL
            space_url = data['space_url']
            
            # Import here to avoid circular imports
            from components.Space import Space
            space_component = Space(conn)
            
            # Extract space_id from URL (also check if provided directly in data)
            space_id = data.get('space_id') or space_component.extract_space_id(space_url)
            
            if not space_id:
                return jsonify({'success': False, 'error': 'Invalid Space URL'}), 400
                
            # Check if space already exists in the scheduler
            cursor.execute(
                "SELECT id, status FROM space_download_scheduler WHERE space_id = %s AND status != 'failed' ORDER BY id DESC LIMIT 1",
                (space_id,)
            )
            existing_job = cursor.fetchone()
            
            if existing_job:
                # If already has an active job, return it
                if existing_job['status'] in ['pending', 'downloading', 'in_progress']:
                    return jsonify({
                        'success': True, 
                        'message': 'Space already scheduled for download',
                        'job_id': existing_job['id']
                    })
            
            # Check if space exists in spaces table
            cursor.execute("SELECT id FROM spaces WHERE id = %s", (space_id,))
            space_record = cursor.fetchone()
            
            if not space_record:
                # Create space record if it doesn't exist
                # Default to public access since it's coming from web app
                user_id = 0  # Public/anonymous user
                
                cursor.execute(
                    "INSERT INTO spaces (id, url, title, user_id, created_at, status) VALUES (%s, %s, %s, %s, NOW(), 'active')",
                    (space_id, space_url, f"X Space {space_id}", user_id)
                )
            
            # Create download job entry
            cursor.execute(
                """
                INSERT INTO space_download_scheduler
                (space_id, user_id, status, file_type, created_at)
                VALUES (%s, %s, %s, %s, NOW())
                """,
                (space_id, 0, 'pending', 'mp3')  # Default to mp3 format and anonymous user (0)
            )
            
            # Get the job ID
            job_id = cursor.lastrowid
            
            # Commit the transaction
            conn.commit()
            
            # Log the job creation
            logger.info(f"Created download job {job_id} for space {space_id} via web app")
            
            # Return successful response
            return jsonify({
                'success': True,
                'message': 'Download scheduled successfully',
                'job_id': job_id,
                'space_id': space_id
            })
            
        except Exception as e:
            logger.error(f"Error scheduling download: {str(e)}", exc_info=True)
            
            # Try to rollback if possible
            try:
                if 'conn' in locals() and conn:
                    conn.rollback()
            except:
                pass
                
            return jsonify({'success': False, 'error': str(e)}), 500