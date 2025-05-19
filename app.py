#!/usr/bin/env python3
# app.py - Flask app for XSpace Downloader

import re
import os
import sys
import json
import logging
import datetime
from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, session, send_file

# Import our space record fixer
try:
    from fix_direct_spaces import ensure_space_record
except ImportError:
    # Define a fallback function if import fails
    def ensure_space_record(space_id, file_path=None):
        logger.error("fix_direct_spaces module not available - space records may not be created properly")
        return False

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
    # Get a list of completed downloads to display
    try:
        space = get_space_component()
        completed_spaces = space.list_download_jobs(status='completed', limit=5)
        return render_template('index.html', completed_spaces=completed_spaces)
    except Exception as e:
        logger.error(f"Error loading completed spaces: {e}", exc_info=True)
        return render_template('index.html')

@app.route('/submit', methods=['POST', 'GET'])
def submit_space():
    """Handle submission of a space URL."""
    # Handle GET request with space_url parameter
    if request.method == 'GET' and request.args.get('space_url'):
        space_url = request.args.get('space_url', '').strip()
    else:
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
        
        # Step 1: First check if the physical file exists
        download_dir = app.config['DOWNLOAD_DIR']
        file_exists = False
        file_path = None
        file_size = 0
        file_extension = None
        
        for ext in ['mp3', 'm4a', 'wav']:
            path = os.path.join(download_dir, f"{space_id}.{ext}")
            if os.path.exists(path) and os.path.getsize(path) > 1024*1024:  # > 1MB
                file_exists = True
                file_path = path
                file_size = os.path.getsize(path)
                file_extension = ext
                break
        
        # Step 2: If file exists, make sure the database record exists
        if file_exists:
            logger.info(f"Found physical file for space {space_id} - checking database record")
            
            # Use the specialized function to ensure space record exists
            result = ensure_space_record(space_id, file_path)
            
            if result:
                logger.info(f"Successfully ensured space record for {space_id} with file {file_path}")
            else:
                logger.warning(f"Could not ensure space record for {space_id} - may not appear in searches")
                
            # Also update any pending download jobs to completed
            try:
                cursor = space.connection.cursor(dictionary=True)
                
                # Find all pending/in-progress jobs for this space
                job_query = """
                SELECT id FROM space_download_scheduler
                WHERE space_id = %s AND status IN ('pending', 'in_progress')
                """
                cursor.execute(job_query, (space_id,))
                jobs = cursor.fetchall()
                
                # Mark all as completed
                if jobs:
                    logger.info(f"Marking {len(jobs)} pending jobs as completed for space {space_id}")
                    for job in jobs:
                        update_job_query = """
                        UPDATE space_download_scheduler
                        SET status = 'completed', progress_in_percent = 100,
                            progress_in_size = %s, end_time = NOW(), updated_at = NOW()
                        WHERE id = %s
                        """
                        cursor.execute(update_job_query, (file_size, job['id']))
                    
                    space.connection.commit()
                
                cursor.close()
            except Exception as job_err:
                logger.error(f"Error updating pending jobs: {job_err}")
            
            # Take user directly to the space page
            flash(f'This space has already been downloaded and is available for listening.', 'info')
            return redirect(url_for('space_page', space_id=space_id))
        
        # If no file exists, continue with normal processing to check for pending downloads
            
        # If file doesn't exist, check if there's an active download job
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
                    # Double-check if file actually exists (redundant but safe)
                    if file_exists:
                        flash(f'This space has already been downloaded and is available for listening.', 'info')
                        return redirect(url_for('space_page', space_id=space_id))
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
        
@app.route('/api/space_status/<space_id>', methods=['GET'])
def api_space_status(space_id):
    """API endpoint to get space status for AJAX updates."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get space details
        space_details = space.get_space(space_id)
        if not space_details:
            # Don't return 404 - create a minimal response that indicates an issue
            # but allows the frontend to continue processing
            return jsonify({
                'space_id': space_id,
                'status': 'unknown',
                'file_exists': False,
                'error': 'Space not found in database'
            })
        
        # Check if the physical file exists
        download_dir = app.config['DOWNLOAD_DIR']
        file_path = None
        file_size = 0
        
        for ext in ['mp3', 'm4a', 'wav']:
            path = os.path.join(download_dir, f"{space_id}.{ext}")
            if os.path.exists(path) and os.path.getsize(path) > 1024*1024:  # > 1MB
                file_path = path
                file_size = os.path.getsize(path)
                break
        
        # Get the latest job for this space (any status to include errors)
        job = None
        try:
            cursor = space.connection.cursor(dictionary=True)
            
            # First check for active jobs
            active_query = """
            SELECT * FROM space_download_scheduler
            WHERE space_id = %s AND status IN ('pending', 'in_progress', 'downloading')
            ORDER BY id DESC LIMIT 1
            """
            cursor.execute(active_query, (space_id,))
            job = cursor.fetchone()
            
            # If no active jobs, check for the most recent failed job
            if not job:
                failed_query = """
                SELECT * FROM space_download_scheduler
                WHERE space_id = %s AND status = 'failed'
                ORDER BY id DESC LIMIT 1
                """
                cursor.execute(failed_query, (space_id,))
                job = cursor.fetchone()
                
            cursor.close()
        except Exception as job_err:
            logger.error(f"Error getting job: {job_err}")
        
        # Return status data
        response = {
            'space_id': space_id,
            'status': space_details.get('status', 'unknown'),
            'file_exists': file_path is not None,
            'file_size': file_size if file_path else 0
        }
        
        # Add job data if available
        if job:
            job_status = job.get('status')
            progress_percent = job.get('progress_in_percent', 0)
            progress_size = job.get('progress_in_size', 0)
            
            response.update({
                'job_id': job.get('id'),
                'job_status': job_status,
                'progress_in_percent': progress_percent,
                'progress_in_size': progress_size
            })
            
            # Include error message for failed jobs
            if job_status == 'failed' and job.get('error_message'):
                response['error_message'] = job.get('error_message')
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error in API space status: {e}", exc_info=True)
        return jsonify({
            'space_id': space_id,
            'status': 'error',
            'error': f"Error retrieving space status: {str(e)}"
        })

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

@app.route('/spaces/<space_id>')
def space_page(space_id):
    """Display a space page with audio player and download options."""
    try:
        # Get Space component
        space = get_space_component()
        
        # First check if the physical file exists
        download_dir = app.config['DOWNLOAD_DIR']
        file_path = None
        file_size = 0
        file_extension = None
        
        for ext in ['mp3', 'm4a', 'wav']:
            path = os.path.join(download_dir, f"{space_id}.{ext}")
            if os.path.exists(path) and os.path.getsize(path) > 1024*1024:  # > 1MB
                file_path = path
                file_size = os.path.getsize(path)
                file_extension = ext
                break
        
        # Create a safe record to display to the user
        display_details = None
        
        # First priority: Use the database record if it exists
        space_details = space.get_space(space_id)
        if space_details:
            display_details = space_details
            
            # If we have a record but no file, mark it as missing
            if not file_path:
                display_details['_file_missing'] = True
                logger.warning(f"Space {space_id} has database record but file is missing")
                
                # Try to update the status in the database, but don't stop on error
                try:
                    cursor = space.connection.cursor()
                    query = "UPDATE spaces SET status = 'file_missing' WHERE space_id = %s"
                    cursor.execute(query, (space_id,))
                    space.connection.commit()
                    cursor.close()
                except Exception as db_err:
                    logger.error(f"Error updating space status to file_missing: {db_err}")
        
        # Second priority: If the file exists but no record, create a minimal object
        elif file_path:
            # Try to create a record in the database
            ensure_space_record(space_id, file_path)
            
            # Either way, create a minimal object for display
            display_details = {
                'space_id': space_id,
                'space_url': f"https://x.com/i/spaces/{space_id}",
                'title': f"Space {space_id}",
                'status': 'completed',
                'download_cnt': 0
            }
            logger.info(f"Created minimal object for display because file exists: {space_id}")
        
        # If neither record nor file exists, return error
        if not display_details:
            flash('Space not found', 'error')
            return redirect(url_for('index'))
            
        # Use the display details for rendering
        space_details = display_details
        
        # Get the latest job for this space (for status and other details)
        cursor = space.connection.cursor(dictionary=True)
        query = """
        SELECT * FROM space_download_scheduler
        WHERE space_id = %s 
        ORDER BY id DESC LIMIT 1
        """
        cursor.execute(query, (space_id,))
        job = cursor.fetchone()
        cursor.close()
        
        return render_template('space.html', 
                               space=space_details, 
                               file_path=file_path, 
                               file_size=file_size, 
                               file_extension=file_extension,
                               job=job)
        
    except Exception as e:
        logger.error(f"Error displaying space page: {e}", exc_info=True)
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/spaces')
def all_spaces():
    """Display all downloaded spaces."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get all completed downloads
        completed_spaces = space.list_download_jobs(status='completed')
        
        # Check which files actually exist
        download_dir = app.config['DOWNLOAD_DIR']
        for job in completed_spaces:
            file_exists = False
            for ext in ['mp3', 'm4a', 'wav']:
                file_path = os.path.join(download_dir, f"{job['space_id']}.{ext}")
                if os.path.exists(file_path) and os.path.getsize(file_path) > 1024*1024:  # > 1MB
                    file_exists = True
                    job['file_exists'] = True
                    job['file_size'] = os.path.getsize(file_path)
                    job['file_extension'] = ext
                    break
            
            if not file_exists:
                job['file_exists'] = False
        
        return render_template('all_spaces.html', spaces=completed_spaces)
        
    except Exception as e:
        logger.error(f"Error listing all spaces: {e}", exc_info=True)
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/download/<space_id>')
def download_space(space_id):
    """Serve the space audio file for download or streaming."""
    try:
        # Check if the file exists
        download_dir = app.config['DOWNLOAD_DIR']
        file_path = None
        
        for ext in ['mp3', 'm4a', 'wav']:
            path = os.path.join(download_dir, f"{space_id}.{ext}")
            if os.path.exists(path) and os.path.getsize(path) > 1024*1024:  # > 1MB
                file_path = path
                break
        
        if not file_path:
            flash('File not found', 'error')
            return redirect(url_for('space_page', space_id=space_id))
        
        # Check if this is a direct download or for streaming
        as_attachment = request.args.get('attachment', '0') == '1'
        
        return send_file(
            file_path,
            as_attachment=as_attachment,
            download_name=f"space_{space_id}.{file_path.split('.')[-1]}"
        )
        
    except Exception as e:
        logger.error(f"Error downloading space file: {e}", exc_info=True)
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('space_page', space_id=space_id))

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