#!/usr/bin/env python3
# app.py - Flask app for XSpace Downloader

import re
import os
import sys
import json
import logging
import datetime
from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, session

# Add parent directory to path for importing components
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Try to import Flask and related packages
try:
    from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, session
    from flask_cors import CORS
except ImportError:
    print("Error: Required packages not found. Installing...")
    import subprocess
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "flask==2.0.3", "werkzeug==2.0.3", "flask-cors==3.0.10"])
        from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, session
        from flask_cors import CORS
    except Exception as e:
        print(f"Failed to install required packages: {e}")
        sys.exit(1)

# Import application components
from components.Space import Space

# Configure logging
logging.basicConfig(
    filename='webapp.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('webapp')

# Create Flask application
app = Flask(__name__)
CORS(app)

# Secret key for sessions and flashing messages
app.secret_key = os.environ.get('SECRET_KEY', 'xspacedownloaderdevkey')

# Default configuration
app.config.update(
    DOWNLOAD_DIR=os.environ.get('DOWNLOAD_DIR', './downloads'),
    MAX_CONCURRENT_DOWNLOADS=int(os.environ.get('MAX_CONCURRENT_DOWNLOADS', 5)),
    DEBUG=os.environ.get('DEBUG', 'false').lower() == 'true'
)

# Create download directory if it doesn't exist
os.makedirs(app.config['DOWNLOAD_DIR'], exist_ok=True)

# Maintain a database connection
db_connection = None
space_component = None

def get_space_component():
    """Get a Space component instance with an active DB connection."""
    global space_component, db_connection
    
    # Create a new Space component if it doesn't exist or the connection is lost
    if not space_component or not db_connection or not hasattr(db_connection, 'is_connected') or not db_connection.is_connected():
        space_component = Space()
        if hasattr(space_component, 'connection'):
            db_connection = space_component.connection
    
    return space_component

def is_valid_space_url(url):
    """Check if a given URL appears to be a valid X space URL."""
    # This pattern matches URLs like https://x.com/i/spaces/1dRJZEpyjlNGB
    pattern = r'https?://(?:www\.)?(?:twitter|x)\.com/\w+/(?:spaces|status)/\w+'
    return bool(re.match(pattern, url))

@app.route('/')
def index():
    """Home page with form to submit a space URL."""
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit_space():
    """Handle submission of a space URL."""
    space_url = request.form.get('space_url', '').strip()
    
    # Basic validation
    if not space_url:
        flash('Please enter a space URL', 'error')
        return redirect(url_for('index'))
    
    if not is_valid_space_url(space_url):
        flash('Invalid space URL format. Please enter a valid X space URL', 'error')
        return redirect(url_for('index'))
    
    try:
        # Get Space component
        space = get_space_component()
        
        # Extract space_id from URL
        space_id = space.extract_space_id(space_url)
        if not space_id:
            flash('Could not extract space ID from URL', 'error')
            return redirect(url_for('index'))
        
        # Check if this space already exists in the download scheduler
        # Check for ANY job (including completed ones)
        try:
            # Direct SQL query to find all jobs for this space_id (including completed ones)
            cursor = space.connection.cursor(dictionary=True)
            query = """
            SELECT id, status FROM space_download_scheduler
            WHERE space_id = %s 
            ORDER BY id DESC LIMIT 1
            """
            cursor.execute(query, (space_id,))
            existing_job = cursor.fetchone()
            cursor.close()
            
            if existing_job:
                if existing_job['status'] in ['pending', 'in_progress']:
                    flash(f'This space is already scheduled for download. Current status: {existing_job["status"]}', 'info')
                    return redirect(url_for('status', job_id=existing_job['id']))
                elif existing_job['status'] == 'completed':
                    # Check if the file actually exists
                    download_dir = app.config['DOWNLOAD_DIR']
                    file_exists = False
                    for ext in ['mp3', 'm4a', 'wav']:
                        file_path = os.path.join(download_dir, f"{space_id}.{ext}")
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 1024*1024:  # > 1MB
                            file_exists = True
                            break
                    
                    if file_exists:
                        flash(f'This space has already been downloaded and is available in the downloads directory.', 'info')
                        return redirect(url_for('status', job_id=existing_job['id']))
                    # If file doesn't exist but job is marked completed, we'll create a new job
        except Exception as check_err:
            logger.error(f"Error checking for existing jobs: {check_err}", exc_info=True)
            # Continue with normal flow if check fails
        
        # Create a new download job
        job_id = space.create_download_job(space_id)
        if not job_id:
            flash('Failed to schedule the download', 'error')
            return redirect(url_for('index'))
        
        # Redirect to status page
        return redirect(url_for('status', job_id=job_id))
        
    except Exception as e:
        logger.error(f"Error submitting space: {e}", exc_info=True)
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/status/<int:job_id>')
def status(job_id):
    """Show the status of a download job."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get job details
        job = space.get_download_job(job_id=job_id)
        if not job:
            flash('Download job not found', 'error')
            return redirect(url_for('index'))
        
        # Get space details
        space_id = job.get('space_id')
        space_details = space.get_space(space_id) if space_id else None
        
        return render_template('status.html', job=job, space=space_details)
        
    except Exception as e:
        logger.error(f"Error checking status: {e}", exc_info=True)
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/api/status/<int:job_id>', methods=['GET'])
def api_status(job_id):
    """API endpoint to get job status for AJAX updates."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get job details
        job = space.get_download_job(job_id=job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        # Return job data
        return jsonify({
            'status': job.get('status', 'unknown'),
            'progress_in_percent': job.get('progress_in_percent', 0),
            'progress_in_size': job.get('progress_in_size', 0),
            'error_message': job.get('error_message', '')
        })
        
    except Exception as e:
        logger.error(f"Error in API status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/queue', methods=['GET'])
def api_queue():
    """API endpoint to get download queue status."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get active downloads
        in_progress = space.list_download_jobs(status='in_progress')
        
        # Get pending downloads
        pending = space.list_download_jobs(status='pending')
        
        # Return queue data
        return jsonify({
            'active': len(in_progress),
            'pending': len(pending),
            'max_concurrent': app.config['MAX_CONCURRENT_DOWNLOADS']
        })
        
    except Exception as e:
        logger.error(f"Error in API queue: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors."""
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors."""
    logger.error(f"Server error: {e}", exc_info=True)
    return render_template('500.html'), 500

if __name__ == '__main__':
    # Get host and port from environment or use defaults
    host = os.environ.get('HOST', '0.0.0.0')  # Listen on all interfaces
    port = int(os.environ.get('PORT', 5000))
    
    # Print startup message
    print(f"Starting XSpace Downloader Web App on {host}:{port}")
    print(f"Access the web interface at: http://127.0.0.1:{port} or http://localhost:{port}")
    
    # Run the app
    app.run(host=host, port=port, debug=app.config['DEBUG'])