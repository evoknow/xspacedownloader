#!/usr/bin/env python3
# app.py - Flask app for XSpace Downloader

import re
import os
import sys
import json
import logging
import datetime
import subprocess
from pathlib import Path
from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, session, send_file, Response

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
# Import SpeechToText component if available
try:
    from components.SpeechToText import SpeechToText
    SPEECH_TO_TEXT_AVAILABLE = True
except ImportError:
    SPEECH_TO_TEXT_AVAILABLE = False
    logger = logging.getLogger('webapp')
    logger.warning("SpeechToText component not available - transcription features will be limited")
    
# Import Translate component if available
try:
    from components.Translate import Translate
    TRANSLATE_AVAILABLE = True
except ImportError:
    TRANSLATE_AVAILABLE = False
    logger = logging.getLogger('webapp')
    logger.warning("Translate component not available - translation features will be limited")

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
    
    try:
        # Create a new Space component if it doesn't exist
        if not space_component:
            space_component = Space()
            if hasattr(space_component, 'connection'):
                db_connection = space_component.connection
            logger.info("Created new Space component instance")
            return space_component
            
        # Check if connection is valid and ping it to test
        if db_connection and hasattr(db_connection, 'is_connected'):
            try:
                # Try to ping the connection with a timeout
                db_connection.ping(reconnect=True, attempts=1, delay=0.5)
                if db_connection.is_connected():
                    # Connection is good
                    return space_component
            except Exception as ping_err:
                logger.warning(f"Database ping failed: {ping_err}")
                
                # Explicitly close the connection to avoid memory leaks or corruption
                try:
                    if db_connection and hasattr(db_connection, 'close'):
                        db_connection.close()
                        db_connection = None
                except Exception:
                    pass
                        
                # Will try to reconnect below
        
        # Create fresh connection if previous checks failed - clean up old one first
        if space_component:
            try:
                if hasattr(space_component, 'connection') and space_component.connection:
                    if hasattr(space_component.connection, 'close'):
                        space_component.connection.close()
            except Exception:
                # Ignore any errors during cleanup
                pass
                
        # Create a new instance
        space_component = Space()
        if hasattr(space_component, 'connection'):
            db_connection = space_component.connection
            logger.info("Recreated Space component with fresh connection")
    except Exception as e:
        logger.error(f"Error in get_space_component: {e}", exc_info=True)
        
        # Cleanup existing resources
        try:
            if db_connection and hasattr(db_connection, 'close'):
                db_connection.close()
        except Exception:
            pass
            
        # Reset global variables
        space_component = None
        db_connection = None
        
        # Create a new instance as a final fallback
        try:
            space_component = Space()
            if hasattr(space_component, 'connection'):
                db_connection = space_component.connection
        except Exception as new_err:
            logger.error(f"Failed to create new Space component: {new_err}", exc_info=True)
    
    return space_component

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

@app.route('/', methods=['GET'])
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

@app.route('/api/check_url', methods=['POST'])
def check_url():
    """API endpoint to check if a URL is valid."""
    url = request.json.get('url', '')
    valid = is_valid_space_url(url)
    return jsonify({'valid': valid})

def is_valid_space_url(url):
    """Check if a given URL appears to be a valid X space URL."""
    # This pattern matches URLs like https://x.com/i/spaces/1dRJZEpyjlNGB
    pattern = r'https?://(?:www\.)?(?:twitter|x)\.com/\w+/(?:spaces|status)/\w+'
    return bool(re.match(pattern, url))

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
        space_details = space.get_space(space_id, include_transcript=True)
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
        
        # If file exists, always ensure status is 'completed' for UI logic
        if file_path:
            # Update the in-memory space_details to show completed
            space_details['status'] = 'completed'
            
            # Also ensure the database is updated
            try:
                cursor = space.connection.cursor()
                update_space_query = """
                UPDATE spaces
                SET status = 'completed', format = %s, downloaded_at = NOW()
                WHERE space_id = %s AND status != 'completed'
                """
                cursor.execute(update_space_query, (str(file_size), space_id))
                space.connection.commit()
                cursor.close()
                logger.info(f"Updated space {space_id} status to completed")
            except Exception as update_err:
                logger.error(f"Error updating space status: {update_err}")
        
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
        
        # Ensure we always have the right content type for the audio player
        if file_extension:
            # Map file extensions to MIME types
            mime_types = {
                'mp3': 'audio/mpeg',
                'm4a': 'audio/mp4',
                'wav': 'audio/wav',
                'ogg': 'audio/ogg',
                'flac': 'audio/flac'
            }
            content_type = mime_types.get(file_extension, f'audio/{file_extension}')
        else:
            # Default to MP3 if no extension is found
            content_type = 'audio/mpeg'
            
        return render_template('space.html', 
                               space=space_details, 
                               file_path=file_path, 
                               file_size=file_size, 
                               file_extension=file_extension,
                               content_type=content_type,
                               job=job)
        
    except Exception as e:
        logger.error(f"Error displaying space page: {e}", exc_info=True)
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('index'))

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

@app.route('/api/space_status/<space_id>', methods=['GET'])
def api_space_status(space_id):
    """API endpoint to get space download status."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Check if the physical file exists
        download_dir = app.config['DOWNLOAD_DIR']
        file_exists = False
        file_size = 0
        
        for ext in ['mp3', 'm4a', 'wav']:
            path = os.path.join(download_dir, f"{space_id}.{ext}")
            if os.path.exists(path) and os.path.getsize(path) > 1024*1024:  # > 1MB
                file_exists = True
                file_size = os.path.getsize(path)
                break
        
        # Get space details
        space_details = space.get_space(space_id)
        status = space_details['status'] if space_details else 'unknown'
        
        # Get the latest job for this space
        try:
            cursor = space.connection.cursor(dictionary=True)
            query = """
            SELECT * FROM space_download_scheduler
            WHERE space_id = %s 
            ORDER BY id DESC LIMIT 1
            """
            cursor.execute(query, (space_id,))
            job = cursor.fetchone()
            cursor.close()
        except Exception as e:
            logger.error(f"Error fetching job for space status API: {e}")
            job = None
            
        result = {
            'space_id': space_id,
            'file_exists': file_exists,
            'status': status,
            'file_size': file_size if file_exists else 0
        }
        
        # Add job details if job exists
        if job:
            result.update({
                'job_id': job['id'],
                'job_status': job['status'],
                'progress_in_percent': job['progress_in_percent'],
                'progress_in_size': job['progress_in_size'],
                'error_message': job['error_message'] if 'error_message' in job else None,
                'start_time': job['start_time'].isoformat() if job['start_time'] else None,
                'end_time': job['end_time'].isoformat() if job['end_time'] else None
            })
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in space status API: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/transcript_job/<job_id>', methods=['GET'])
def api_get_transcript_job(job_id):
    """API endpoint to get transcript job status."""
    try:
        from pathlib import Path
        import json
        
        # Check if job exists
        job_file = Path(f'./transcript_jobs/{job_id}.json')
        if not job_file.exists():
            return jsonify({'error': 'Job not found'}), 404
        
        # Read job data
        with open(job_file, 'r') as f:
            job_data = json.load(f)
        
        # Get space details
        space = get_space_component()
        
        # If job is completed, include transcript ID
        if job_data['status'] == 'completed' and 'result' in job_data and job_data['result']:
            # Try to get transcript details
            transcript_id = job_data['result'].get('transcript_id')
            if transcript_id:
                transcript = space.get_transcript(transcript_id)
                if transcript:
                    job_data['transcript'] = {
                        'id': transcript_id,
                        'language': transcript['language'],
                        'created_at': transcript['created_at'],
                        'text_sample': transcript['transcript'][:500] + "..." if len(transcript['transcript']) > 500 else transcript['transcript']
                    }
        
        return jsonify(job_data)
        
    except Exception as e:
        logger.error(f"Error getting transcript job status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
        
@app.route('/download/<space_id>', methods=['GET'])
@app.route('/spaces/<space_id>/download', methods=['GET'])
def download_space(space_id):
    """Download a space audio file."""
    try:
        # Get attachment flag
        attachment = request.args.get('attachment', '0') == '1'
        
        # Get Space component
        space = get_space_component()
        
        # First check if the physical file exists
        download_dir = app.config['DOWNLOAD_DIR']
        file_path = None
        file_size = 0
        content_type = 'audio/mpeg'  # Default
        
        for ext in ['mp3', 'm4a', 'wav']:
            path = os.path.join(download_dir, f"{space_id}.{ext}")
            if os.path.exists(path) and os.path.getsize(path) > 1024*1024:  # > 1MB
                file_path = path
                file_size = os.path.getsize(path)
                # Map file extensions to MIME types
                mime_types = {
                    'mp3': 'audio/mpeg',
                    'm4a': 'audio/mp4',
                    'wav': 'audio/wav',
                    'ogg': 'audio/ogg',
                    'flac': 'audio/flac'
                }
                content_type = mime_types.get(ext, f'audio/{ext}')
                break
        
        if not file_path:
            flash('Space file not found', 'error')
            return redirect(url_for('space_page', space_id=space_id))
        
        # Get space details to use for filename
        space_details = space.get_space(space_id)
        
        # Count the download
        try:
            cursor = space.connection.cursor()
            update_query = "UPDATE spaces SET download_cnt = download_cnt + 1 WHERE space_id = %s"
            cursor.execute(update_query, (space_id,))
            space.connection.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"Error updating download count: {e}")
        
        # Set filename
        filename = f"{space_id}"
        if space_details and space_details.get('title'):
            # Clean the title to make it safe for filenames
            clean_title = re.sub(r'[^\w\s-]', '', space_details['title']).strip()
            clean_title = re.sub(r'[-\s]+', '-', clean_title)
            if clean_title:
                filename = f"{clean_title}_{space_id}"
        
        # Set extension based on content type
        if content_type == 'audio/mpeg':
            ext = 'mp3'
        elif content_type == 'audio/mp4':
            ext = 'm4a'
        elif content_type == 'audio/wav':
            ext = 'wav'
        elif content_type == 'audio/ogg':
            ext = 'ogg'
        elif content_type == 'audio/flac':
            ext = 'flac'
        else:
            ext = os.path.splitext(file_path)[1][1:]  # Extract from path as fallback
        
        filename = f"{filename}.{ext}"
        
        # Return the file
        if attachment:
            return send_file(file_path, as_attachment=True, download_name=filename, mimetype=content_type)
        else:
            return send_file(file_path, mimetype=content_type, conditional=True)
            
    except Exception as e:
        logger.error(f"Error downloading space: {e}", exc_info=True)
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('space_page', space_id=space_id))
        
@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors."""
    # Check if this is an API request
    if request.path.startswith('/api/') or request.is_json:
        return jsonify({'error': 'Resource not found'}), 404
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors."""
    logger.error(f"Server error: {e}", exc_info=True)
    # Check if this is an API request
    if request.path.startswith('/api/') or request.is_json:
        return jsonify({'error': 'Internal server error'}), 500
    return render_template('500.html'), 500

@app.after_request
def after_request(response):
    """Cleanup after each request to avoid memory leaks."""
    # Clean up resources that might cause memory corruption
    try:
        from gc import collect
        collect()
    except Exception:
        pass
    return response

# Global translate component instance
translate_component = None

def get_translate_component():
    """Get a Translate component instance."""
    global translate_component
    
    if not TRANSLATE_AVAILABLE:
        return None
        
    try:
        # Create a new Translate component if it doesn't exist
        if not translate_component:
            translate_component = Translate()
            logger.info("Created new Translate component instance")
        
        return translate_component
    except Exception as e:
        logger.error(f"Error in get_translate_component: {e}", exc_info=True)
        # Create a new instance as a final fallback
        try:
            translate_component = Translate()
        except Exception as new_err:
            logger.error(f"Failed to create new Translate component: {new_err}", exc_info=True)
    
    return translate_component

@app.route('/api/translate/languages', methods=['GET'])
def api_translate_languages():
    """API endpoint to get available translation languages."""
    if not TRANSLATE_AVAILABLE:
        return jsonify({'error': 'Translation service is not available'}), 503
        
    try:
        # Get Translate component
        translator = get_translate_component()
        if not translator:
            return jsonify({'error': 'Could not initialize translation service'}), 500
            
        # Get available languages
        languages = translator.get_languages()
        
        # Return languages
        return jsonify({
            'languages': languages
        })
        
    except Exception as e:
        logger.error(f"Error getting translation languages: {e}", exc_info=True)
        return jsonify({'error': 'An unexpected error occurred'}), 500

@app.route('/api/translate', methods=['POST'])
def api_translate():
    """API endpoint to translate text."""
    if not TRANSLATE_AVAILABLE:
        return jsonify({'error': 'Translation service is not available'}), 503
        
    try:
        # Validate request
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400
            
        # Get request data
        data = request.json
        text = data.get('text')
        source_lang = data.get('source_lang', 'auto')
        target_lang = data.get('target_lang')
        
        # Validate required fields
        if not text:
            return jsonify({'error': 'Missing text parameter'}), 400
            
        if not target_lang:
            return jsonify({'error': 'Missing target_lang parameter'}), 400
            
        # Get Translate component
        translator = get_translate_component()
        if not translator:
            return jsonify({'error': 'Could not initialize translation service'}), 500
            
        # Auto-detect source language if set to 'auto'
        if source_lang == 'auto':
            success, result = translator.detect_language(text)
            if not success:
                return jsonify({'error': 'Language detection failed', 'details': result}), 400
            source_lang = result
            
        # Perform translation
        success, result = translator.translate(text, source_lang, target_lang)
        
        if not success:
            return jsonify({'error': 'Translation failed', 'details': result}), 400
            
        # Return translated text
        return jsonify({
            'translated_text': result,
            'source_lang': source_lang,
            'target_lang': target_lang
        })
        
    except Exception as e:
        logger.error(f"Error translating text: {e}", exc_info=True)
        return jsonify({'error': 'An unexpected error occurred'}), 500

@app.route('/api/detect-language', methods=['POST'])
def api_detect_language():
    """API endpoint to detect language of text."""
    if not TRANSLATE_AVAILABLE:
        return jsonify({'error': 'Translation service is not available'}), 503
        
    try:
        # Validate request
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400
            
        # Get request data
        data = request.json
        text = data.get('text')
        
        # Validate required fields
        if not text:
            return jsonify({'error': 'Missing text parameter'}), 400
            
        # Get Translate component
        translator = get_translate_component()
        if not translator:
            return jsonify({'error': 'Could not initialize translation service'}), 500
            
        # Detect language
        success, result = translator.detect_language(text)
        
        if not success:
            return jsonify({'error': 'Language detection failed', 'details': result}), 400
            
        # Return detected language
        return jsonify({
            'detected_language': result
        })
        
    except Exception as e:
        logger.error(f"Error detecting language: {e}", exc_info=True)
        return jsonify({'error': 'An unexpected error occurred'}), 500

@app.route('/api/transcript/<transcript_id>', methods=['GET'])
def api_get_transcript(transcript_id):
    """API endpoint to get transcript content."""
    try:
        # Get a fresh Space component to avoid connection issues
        try:
            # Explicitly close any existing connection
            global space_component, db_connection
            if db_connection and hasattr(db_connection, 'close'):
                try:
                    db_connection.close()
                except Exception:
                    pass
            space_component = None
            db_connection = None
            
            # Get a fresh instance
            space = Space()
            
            # Store in global variables
            space_component = space
            if hasattr(space, 'connection'):
                db_connection = space.connection
        except Exception as conn_err:
            logger.error(f"Error creating fresh connection: {conn_err}", exc_info=True)
            # Fall back to standard get_space_component
            space = get_space_component()
        
        # Validate transcript_id is a valid integer
        try:
            transcript_id = int(transcript_id)
        except ValueError:
            return jsonify({'error': 'Invalid transcript ID format'}), 400
        
        # Get transcript from database
        try:
            transcript = space.get_transcript(transcript_id)
        except Exception as db_err:
            logger.error(f"Database error getting transcript: {db_err}", exc_info=True)
            return jsonify({'error': 'Database error retrieving transcript'}), 500
            
        if not transcript:
            return jsonify({'error': 'Transcript not found'}), 404
            
        # Safely extract transcript fields with default values
        safe_transcript = {
            'transcript_id': transcript_id,
            'language': 'unknown',
            'transcript': '',
            'created_at': None
        }
        
        # Only update with values that exist in the transcript
        if isinstance(transcript, dict):
            if 'language' in transcript and transcript['language']:
                safe_transcript['language'] = str(transcript['language'])
                
            if 'transcript' in transcript and transcript['transcript']:
                safe_transcript['transcript'] = str(transcript['transcript'])
                
            if 'created_at' in transcript and transcript['created_at']:
                try:
                    # Convert to string if it's a datetime
                    if hasattr(transcript['created_at'], 'isoformat'):
                        safe_transcript['created_at'] = transcript['created_at'].isoformat()
                    else:
                        safe_transcript['created_at'] = str(transcript['created_at'])
                except Exception:
                    # Leave as default if conversion fails
                    pass
                    
        # Return transcript data
        return jsonify(safe_transcript)
        
    except Exception as e:
        logger.error(f"Error getting transcript: {e}", exc_info=True)
        return jsonify({'error': 'An unexpected error occurred'}), 500

# Route for transcribing a space
@app.route('/api/transcribe/<space_id>', methods=['POST'])
@app.route('/spaces/<space_id>/transcribe', methods=['POST'])
def transcribe_space(space_id):
    """Submit a space for transcription."""
    try:
        # Check if SpeechToText component is available
        if not SPEECH_TO_TEXT_AVAILABLE:
            if request.is_json:
                return jsonify({'error': 'Speech-to-text functionality is not available'}), 400
            flash('Speech-to-text functionality is not available', 'error')
            return redirect(url_for('space_page', space_id=space_id))
        
        # Get language parameter based on request type
        if request.is_json:
            # API request with JSON body
            language = request.json.get('language', 'en')
            model = request.json.get('model', 'base')
            detect_language = request.json.get('detect_language', False)
            translate_to = request.json.get('translate_to')
            overwrite = request.json.get('overwrite', True)
        else:
            # Form submission
            language = request.form.get('language', 'en')
            model = request.form.get('model', 'base')
            detect_language = request.form.get('detect_language', 'false') == 'true'
            translate_to = request.form.get('translate_to')
            overwrite = request.form.get('overwrite', 'true') == 'true'
        
        # Get Space component
        space = get_space_component()
        
        # First check if the physical file exists
        download_dir = app.config['DOWNLOAD_DIR']
        file_path = None
        
        for ext in ['mp3', 'm4a', 'wav']:
            path = os.path.join(download_dir, f"{space_id}.{ext}")
            if os.path.exists(path) and os.path.getsize(path) > 1024*1024:  # > 1MB
                file_path = path
                break
        
        if not file_path:
            if request.is_json:
                return jsonify({'error': 'Space audio file not found'}), 404
            flash('Space audio file not found', 'error')
            return redirect(url_for('space_page', space_id=space_id))
            
        # Create transcription job with additional parameters
        options = {
            'model': model,
            'detect_language': detect_language,
            'translate_to': translate_to if translate_to else None,
            'overwrite': overwrite
        }
        
        # Create a background job file
        import uuid
        import json
        from pathlib import Path
        import datetime
        
        # Create transcript_jobs directory if it doesn't exist
        os.makedirs('./transcript_jobs', exist_ok=True)
        
        # Generate a unique job ID
        job_id = str(uuid.uuid4())
        
        # Create job data
        job_data = {
            'id': job_id,
            'space_id': space_id,
            'file_path': file_path,
            'language': language,
            'options': options,
            'status': 'pending',
            'progress': 0,
            'created_at': datetime.datetime.now().isoformat(),
            'updated_at': datetime.datetime.now().isoformat()
        }
        
        # Save job data to file
        job_file = Path(f'./transcript_jobs/{job_id}.json')
        with open(job_file, 'w') as f:
            json.dump(job_data, f)
            
        # API response or redirect based on request type
        if request.is_json:
            return jsonify({
                'job_id': job_id,
                'status': 'pending',
                'message': 'Transcription job scheduled'
            })
        
        # Redirect back to space page with success message
        flash('Transcription job scheduled. You will receive a notification when it is complete.', 'success')
        return redirect(url_for('space_page', space_id=space_id))
        
    except Exception as e:
        logger.error(f"Error transcribing space: {e}", exc_info=True)
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('space_page', space_id=space_id))

if __name__ == '__main__':
    # Get host and port from environment or use defaults
    host = os.environ.get('HOST', '0.0.0.0')  # Listen on all interfaces
    port = int(os.environ.get('PORT', 8080))
    
    # Create transcript jobs directory if it doesn't exist
    os.makedirs('./transcript_jobs', exist_ok=True)
    
    # Print startup message
    print(f"Starting XSpace Downloader Web App on {host}:{port}")
    print(f"Access the web interface at: http://127.0.0.1:{port} or http://localhost:{port}")
    
    # Run the app
    app.run(host=host, port=port, debug=app.config['DEBUG'])