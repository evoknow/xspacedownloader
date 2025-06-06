#!/usr/bin/env python3
# app.py - Flask app for XSpace Downloader

import re
import os
import sys
import json
import logging
import datetime
import subprocess
import secrets
import string
import requests
from pathlib import Path
from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, session, send_file, Response, send_from_directory
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Load environment variables from .env file if it exists
try:
    from load_env import load_env
    load_env()
    print("Environment variables loaded from .env file")
except ImportError:
    print("load_env module not found - using system environment variables only")

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

# Configure logging using centralized logger
try:
    from components.Logger import setup_app_logging
    logger = setup_app_logging('app')
except ImportError:
    # Fallback to basic logging if Logger component not available
    logging.basicConfig(
        filename='webapp.log',
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger('webapp')

# Application version
__version__ = "1.1.1"

# Create Flask application
app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)

# Secret key for sessions and flashing messages
app.secret_key = os.environ.get('SECRET_KEY', 'xspacedownloaderdevkey')

# Load rate limit configuration
rate_limit_config = {}
try:
    with open('mainconfig.json', 'r') as f:
        main_config = json.load(f)
        rate_limit_config = main_config.get('rate_limits', {})
except Exception as e:
    logger.warning(f"Could not load rate limit config: {e}")

# Set up rate limits based on configuration
rate_limits_enabled = rate_limit_config.get('enabled', True)
daily_limit = rate_limit_config.get('daily_limit', 200)
hourly_limit = rate_limit_config.get('hourly_limit', 50)

# Initialize rate limiter
if rate_limits_enabled:
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=[f"{daily_limit} per day", f"{hourly_limit} per hour"],
        storage_uri="memory://"
    )
else:
    # Disable rate limiting by setting very high limits
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["1000000 per day"],
        storage_uri="memory://"
    )

# Default configuration
app.config.update(
    DOWNLOAD_DIR=os.environ.get('DOWNLOAD_DIR', './downloads'),
    MAX_CONCURRENT_DOWNLOADS=int(os.environ.get('MAX_CONCURRENT_DOWNLOADS', 5)),
    DEBUG=os.environ.get('DEBUG', 'false').lower() == 'true'
)

# Create download directory if it doesn't exist
os.makedirs(app.config['DOWNLOAD_DIR'], exist_ok=True)

# Template filter for relative time
@app.template_filter('relative_time')
def relative_time_filter(dt):
    """Convert datetime to relative time string."""
    if not dt:
        return ''
    
    # Handle string datetime
    if isinstance(dt, str):
        try:
            # Try parsing common datetime formats
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']:
                try:
                    dt = datetime.datetime.strptime(dt, fmt)
                    break
                except ValueError:
                    continue
            else:
                return dt  # Return original if no format matches
        except Exception:
            return dt
    
    # Calculate time difference
    now = datetime.datetime.now()
    diff = now - dt
    
    # Convert to relative time
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "just now"
    elif seconds < 3600:  # Less than 1 hour
        minutes = int(seconds / 60)
        return f"{minutes} min ago"
    elif seconds < 86400:  # Less than 1 day
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        if minutes > 0:
            return f"{hours} hour{'s' if hours > 1 else ''} {minutes} min ago"
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    else:  # Days
        days = int(seconds / 86400)
        hours = int((seconds % 86400) / 3600)
        minutes = int((seconds % 3600) / 60)
        
        result = f"{days} day{'s' if days > 1 else ''}"
        if hours > 0:
            result += f" {hours} hour{'s' if hours > 1 else ''}"
        if minutes > 0 and days < 7:  # Only show minutes for less than a week
            result += f" {minutes} min"
        return result + " ago"

# Global variables for space component and database connection
space_component = None
db_connection = None

# Database connection is now created per request to avoid memory corruption

def get_space_component():
    """Get a Space component instance with a fresh DB connection."""
    try:
        # Always create a new Space component to avoid threading issues
        # This prevents memory corruption from shared database connections
        space_component = Space()
        return space_component
        
    except Exception as e:
        logger.error(f"Error getting Space component: {e}")
        return None

def index():
    """Home page with form to submit a space URL."""
    # Check if setup is needed (no admin exists)
    try:
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as admin_count FROM users WHERE is_admin = 1")
        result = cursor.fetchone()
        cursor.close()
        
        if result['admin_count'] == 0:
            # No admin exists, redirect to setup
            return redirect(url_for('setup'))
    except Exception as e:
        logger.error(f"Error checking admin existence: {e}", exc_info=True)
        # Continue to normal index if check fails
    
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
                    return redirect(url_for('view_queue'))
                elif existing_job['status'] == 'completed':
                    # Double-check if file actually exists (redundant but safe)
                    if file_exists:
                        flash(f'This space has already been downloaded and is available for listening.', 'info')
                        return redirect(url_for('space_page', space_id=space_id))
                    # If file doesn't exist but job is marked completed, we'll create a new job
        except Exception as check_err:
            logger.error(f"Error checking for existing jobs: {check_err}", exc_info=True)
            # Continue with normal flow if check fails
        
        # Create a new download job with user_id if logged in
        user_id = session.get('user_id', 0)
        cookie_id = session.get('cookie_id') if not user_id else None
        job_id = space.create_download_job(space_id, user_id=user_id, cookie_id=cookie_id)
        if not job_id:
            flash('Failed to schedule the download', 'error')
            return redirect(url_for('index'))
        
        # Redirect to queue page
        flash('Your download has been queued successfully!', 'success')
        return redirect(url_for('view_queue'))
        
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
        
        # Get all completed spaces directly from spaces table - only latest entry per space_id
        cursor = space.connection.cursor(dictionary=True)
        query = """
            SELECT s.* FROM spaces s
            INNER JOIN (
                SELECT space_id, MAX(id) as max_id 
                FROM spaces 
                WHERE status = 'completed'
                GROUP BY space_id
            ) latest ON s.id = latest.max_id
            WHERE s.status = 'completed'
            ORDER BY s.downloaded_at DESC, 
                     (COALESCE(s.playback_cnt, 0) * 1.5 + COALESCE(s.download_cnt, 0)) DESC
        """
        cursor.execute(query)
        completed_spaces = cursor.fetchall()
        cursor.close()
        
        # Initialize metadata for each space
        for space_row in completed_spaces:
            space_row['metadata'] = {}
        
        # Check which files actually exist and add metadata
        download_dir = app.config['DOWNLOAD_DIR']
        for space_row in completed_spaces:
            file_exists = False
            for ext in ['mp3', 'm4a', 'wav']:
                file_path = os.path.join(download_dir, f"{space_row['space_id']}.{ext}")
                if os.path.exists(file_path) and os.path.getsize(file_path) > 1024*1024:  # > 1MB
                    file_exists = True
                    space_row['file_exists'] = True
                    space_row['file_size'] = os.path.getsize(file_path)
                    space_row['file_extension'] = ext
                    break
            
            if not file_exists:
                space_row['file_exists'] = False
            
            # Add transcript/translation/summary metadata
            try:
                space_details = space.get_space(space_row['space_id'], include_transcript=True)
                if space_details:
                    space_row['has_transcript'] = bool(space_details.get('transcripts'))
                    space_row['transcript_count'] = len(space_details.get('transcripts', []))
                    transcripts = space_details.get('transcripts', [])
                    space_row['has_translation'] = len(transcripts) > 1 if transcripts else False
                    space_row['has_summary'] = any(t.get('summary') for t in transcripts)
                    # Don't override title if it already exists
                    if not space_row.get('title'):
                        space_row['title'] = space_details.get('title', '')
                    
                    # Get review data
                    review_result = space.get_reviews(space_row['space_id'])
                    if review_result['success']:
                        space_row['average_rating'] = review_result['average_rating']
                        space_row['total_reviews'] = review_result['total_reviews']
                    else:
                        space_row['average_rating'] = 0
                        space_row['total_reviews'] = 0
                    
                    # Update metadata if we have more details
                    if space_details.get('metadata'):
                        space_row['metadata'].update(space_details['metadata'])
                else:
                    space_row['average_rating'] = 0
                    space_row['total_reviews'] = 0
            except Exception as e:
                logger.warning(f"Error getting metadata for space {space_row.get('space_id')}: {e}")
                space_row['has_transcript'] = False
                space_row['has_translation'] = False
                space_row['has_summary'] = False
                space_row['transcript_count'] = 0
                if not space_row.get('title'):
                    space_row['title'] = ''
                space_row['average_rating'] = 0
                space_row['total_reviews'] = 0
                # Keep existing metadata structure
        
        # Get tags for each space
        from components.Tag import Tag
        tag_component = Tag(space.connection)
        
        for space_row in completed_spaces:
            tags = tag_component.get_space_tags(space_row['space_id'])
            space_row['tags'] = tags
            # Create a comma-separated string for searching
            space_row['tags_string'] = ', '.join([tag.get('name', '') for tag in tags])
        
        # Get popular tags (top 20)
        popular_tags = tag_component.get_popular_tags(limit=20)
        
        return render_template('all_spaces.html', spaces=completed_spaces, popular_tags=popular_tags)
        
    except Exception as e:
        logger.error(f"Error listing all spaces: {e}", exc_info=True)
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/queue')
def view_queue():
    """Display all spaces currently in the download queue."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get all jobs that are pending or in progress
        pending_jobs = space.list_download_jobs(status='pending')
        in_progress_jobs = space.list_download_jobs(status='in_progress')
        downloading_jobs = space.list_download_jobs(status='downloading')
        
        # Combine all active jobs
        queue_jobs = []
        
        # Add status labels for clarity
        for job in pending_jobs:
            job['status_label'] = 'Pending'
            job['status_class'] = 'secondary'
            queue_jobs.append(job)
            
        for job in in_progress_jobs:
            job['status_label'] = 'In Progress'
            job['status_class'] = 'info'
            queue_jobs.append(job)
            
        for job in downloading_jobs:
            job['status_label'] = 'Downloading'
            job['status_class'] = 'primary'
            # Try to get progress information
            if hasattr(job, 'progress'):
                job['progress_percent'] = job.progress
            elif hasattr(job, 'download_cnt'):
                job['progress_percent'] = job.download_cnt
            else:
                job['progress_percent'] = 0
            
            # Calculate ETA for downloads
            if job.get('progress_percent', 0) > 0 and job.get('created_at'):
                try:
                    # Calculate elapsed time
                    created_at = datetime.fromisoformat(str(job['created_at']))
                    elapsed = (datetime.now() - created_at).total_seconds()
                    
                    # Calculate remaining time based on progress
                    progress = job['progress_percent']
                    if progress > 0 and progress < 100:
                        total_estimated_seconds = (elapsed / progress) * 100
                        remaining_seconds = total_estimated_seconds - elapsed
                        
                        # Convert to human-readable format
                        if remaining_seconds > 0:
                            if remaining_seconds > 3600:  # More than 1 hour
                                hours = int(remaining_seconds // 3600)
                                minutes = int((remaining_seconds % 3600) // 60)
                                job['eta'] = f"{hours}h {minutes}m"
                            elif remaining_seconds > 60:  # More than 1 minute
                                minutes = int(remaining_seconds // 60)
                                seconds = int(remaining_seconds % 60)
                                job['eta'] = f"{minutes}m {seconds}s"
                            else:
                                job['eta'] = f"{int(remaining_seconds)}s"
                    elif progress >= 100:
                        job['eta'] = "Completing..."
                except Exception as e:
                    logger.debug(f"Error calculating download ETA: {e}")
            
            queue_jobs.append(job)
        
        # Sort by created_at (oldest first, so they appear in queue order)
        queue_jobs.sort(key=lambda x: x.get('created_at', ''))
        
        # Get transcription jobs
        transcript_jobs = []
        transcript_jobs_dir = Path('transcript_jobs')
        if transcript_jobs_dir.exists():
            for job_file in transcript_jobs_dir.glob('*.json'):
                try:
                    with open(job_file, 'r') as f:
                        job_data = json.load(f)
                        # Only include pending, in_progress, or processing transcription jobs
                        if job_data.get('status') in ['pending', 'in_progress', 'processing']:
                            # Get space details for title
                            space_details = space.get_space(job_data.get('space_id'))
                            if space_details:
                                job_data['title'] = space_details.get('title', f"Space {job_data.get('space_id')}")
                            else:
                                job_data['title'] = f"Space {job_data.get('space_id')}"
                            
                            if job_data.get('status') == 'pending':
                                job_data['status_label'] = 'Pending Transcription'
                                job_data['status_class'] = 'warning'
                            elif job_data.get('status') == 'processing':
                                job_data['status_label'] = 'Processing'
                                job_data['status_class'] = 'info'
                                job_data['progress_percent'] = job_data.get('progress', 0)
                            else:
                                job_data['status_label'] = 'Transcribing'
                                job_data['status_class'] = 'success'
                                job_data['progress_percent'] = job_data.get('progress', 0)
                            
                            # Check if this is a translation job
                            if job_data.get('translate_to') or (job_data.get('options', {}).get('translate_to')):
                                target_lang = job_data.get('translate_to') or job_data.get('options', {}).get('translate_to')
                                job_data['is_translation'] = True
                                job_data['target_language'] = target_lang
                                if job_data.get('status') == 'pending':
                                    job_data['status_label'] = 'Pending Translation'
                                elif job_data.get('status') == 'processing':
                                    job_data['status_label'] = f'Translating to {target_lang}'
                            
                            # Calculate ETA for transcription/translation jobs
                            if job_data.get('status') == 'processing' and job_data.get('progress', 0) > 0:
                                result = job_data.get('result', {})
                                if result.get('processing_elapsed_seconds') and result.get('estimated_audio_minutes'):
                                    elapsed_seconds = result['processing_elapsed_seconds']
                                    progress = job_data.get('progress', 0)
                                    
                                    # Calculate remaining time based on current progress
                                    if progress > 0:
                                        total_estimated_seconds = (elapsed_seconds / progress) * 100
                                        remaining_seconds = total_estimated_seconds - elapsed_seconds
                                        
                                        # Convert to human-readable format
                                        if remaining_seconds > 0:
                                            minutes = int(remaining_seconds // 60)
                                            seconds = int(remaining_seconds % 60)
                                            if minutes > 0:
                                                job_data['eta'] = f"{minutes}m {seconds}s"
                                            else:
                                                job_data['eta'] = f"{seconds}s"
                                        else:
                                            job_data['eta'] = "Almost done"
                            
                            transcript_jobs.append(job_data)
                except Exception as e:
                    logger.error(f"Error reading transcript job file {job_file}: {e}")
        
        # Sort transcript jobs by created_at
        transcript_jobs.sort(key=lambda x: x.get('created_at', ''))
        
        # Separate transcription and translation jobs
        transcription_only_jobs = [job for job in transcript_jobs if not job.get('is_translation')]
        translation_jobs = [job for job in transcript_jobs if job.get('is_translation')]
        
        return render_template('queue.html', 
                             queue_jobs=queue_jobs, 
                             transcript_jobs=transcript_jobs,
                             transcription_only_jobs=transcription_only_jobs,
                             translation_jobs=translation_jobs)
        
    except Exception as e:
        logger.error(f"Error viewing queue: {e}", exc_info=True)
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/favicon.ico')
def favicon():
    """Serve favicon to avoid 404 errors."""
    return send_from_directory('static', 'favicon.svg', mimetype='image/svg+xml')

@app.route('/', methods=['GET'])
def index():
    """Home page with form to submit a space URL."""
    # Get a list of completed downloads to display
    try:
        space = get_space_component()
        completed_spaces = space.list_download_jobs(status='completed', limit=5)
        
        # Enhance each space with additional metadata
        for job in completed_spaces:
            try:
                # Get space details including transcripts
                space_details = space.get_space(job['space_id'], include_transcript=True)
                if space_details:
                    # Check for transcripts
                    job['has_transcript'] = bool(space_details.get('transcripts'))
                    job['transcript_count'] = len(space_details.get('transcripts', []))
                    
                    # Check for translations (transcripts in languages other than original)
                    transcripts = space_details.get('transcripts', [])
                    job['has_translation'] = len(transcripts) > 1 if transcripts else False
                    
                    # Check for summaries
                    job['has_summary'] = any(t.get('summary') for t in transcripts)
                    
                    # Add title if available
                    job['title'] = space_details.get('title', '')
            except Exception as e:
                logger.warning(f"Error enhancing space {job.get('space_id')}: {e}")
                job['has_transcript'] = False
                job['has_translation'] = False
                job['has_summary'] = False
                job['transcript_count'] = 0
                job['title'] = ''
        
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

@app.route('/api/track_play/<space_id>', methods=['POST'])
@limiter.limit("60 per minute")
def track_play(space_id):
    """API endpoint to track when a space is played."""
    try:
        from datetime import datetime, timedelta
        
        # Get user identification
        user_id = session.get('user_id', 0)
        cookie_id = request.cookies.get('xspace_user_id', '')
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent', '')
        
        # Get play duration if provided
        data = request.get_json() or {}
        duration_seconds = data.get('duration', 0)
        
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        # Get tracking configuration
        config_query = "SELECT config_key, config_value FROM system_config WHERE config_key IN (%s, %s, %s)"
        cursor.execute(config_query, ('play_tracking_enabled', 'play_cooldown_minutes', 'play_minimum_duration_seconds'))
        config = {row['config_key']: row['config_value'] for row in cursor.fetchall()}
        
        # Check if tracking is enabled
        if config.get('play_tracking_enabled', 'true') == 'false':
            cursor.close()
            return jsonify({'success': True, 'counted': False, 'reason': 'tracking_disabled'})
        
        # Get cooldown period from config
        cooldown_minutes = int(config.get('play_cooldown_minutes', '30'))
        min_duration = int(config.get('play_minimum_duration_seconds', '30'))
        
        # Check minimum duration if configured
        if min_duration > 0 and duration_seconds < min_duration:
            cursor.close()
            return jsonify({'success': True, 'counted': False, 'reason': 'min_duration_not_met'})
        
        # Check if eligible for counting (configurable cooldown)
        cooldown_time = datetime.now() - timedelta(minutes=cooldown_minutes)
        
        check_query = """
            SELECT MAX(played_at) as last_played 
            FROM space_play_history 
            WHERE space_id = %s 
            AND played_at > %s
            AND (
                (user_id IS NOT NULL AND user_id = %s) OR
                (cookie_id IS NOT NULL AND cookie_id != '' AND cookie_id = %s) OR
                (ip_address = %s)
            )
        """
        cursor.execute(check_query, (space_id, cooldown_time, user_id if user_id > 0 else None, 
                                   cookie_id if cookie_id else None, ip_address))
        result = cursor.fetchone()
        
        should_count = True
        reason = None
        
        if result and result['last_played']:
            # User has played this space within the cooldown period
            should_count = False
            reason = 'cooldown'
        
        # Record the play event regardless
        insert_query = """
            INSERT INTO space_play_history 
            (space_id, user_id, cookie_id, ip_address, user_agent, duration_seconds)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (
            space_id,
            user_id if user_id > 0 else None,
            cookie_id if cookie_id else None,
            ip_address,
            user_agent[:500] if user_agent else None,  # Limit user agent length
            duration_seconds
        ))
        
        # Only increment count if eligible
        if should_count:
            update_query = "UPDATE spaces SET playback_cnt = playback_cnt + 1 WHERE space_id = %s"
            cursor.execute(update_query, (space_id,))
        
        space.connection.commit()
        cursor.close()
        
        return jsonify({
            'success': True, 
            'counted': should_count,
            'reason': reason
        })
        
    except Exception as e:
        logger.error(f"Error tracking play: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/track_download/<space_id>', methods=['POST'])
@limiter.limit("60 per minute")
def track_download(space_id):
    """API endpoint to track when a space is downloaded."""
    try:
        from datetime import datetime, date, timedelta
        
        # Get user identification
        user_id = session.get('user_id', 0)
        cookie_id = request.cookies.get('xspace_user_id', '')
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent', '')
        
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        # Get tracking configuration
        config_query = "SELECT config_key, config_value FROM system_config WHERE config_key IN (%s, %s, %s)"
        cursor.execute(config_query, ('download_tracking_enabled', 'download_daily_limit', 'download_hourly_ip_limit'))
        config = {row['config_key']: row['config_value'] for row in cursor.fetchall()}
        
        # Check if tracking is enabled
        if config.get('download_tracking_enabled', 'true') == 'false':
            cursor.close()
            return jsonify({'success': True, 'counted': False, 'reason': 'tracking_disabled'})
        
        # Get limits from config
        daily_limit = int(config.get('download_daily_limit', '1'))
        hourly_ip_limit = int(config.get('download_hourly_ip_limit', '10'))
        
        # Check if eligible for counting (configurable daily limit per user)
        today = date.today()
        
        check_query = """
            SELECT COUNT(*) as download_count 
            FROM space_download_history 
            WHERE space_id = %s 
            AND DATE(downloaded_at) = %s
            AND (
                (user_id IS NOT NULL AND user_id = %s) OR
                (cookie_id IS NOT NULL AND cookie_id != '' AND cookie_id = %s) OR
                (ip_address = %s)
            )
        """
        cursor.execute(check_query, (space_id, today, user_id if user_id > 0 else None, 
                                   cookie_id if cookie_id else None, ip_address))
        result = cursor.fetchone()
        
        should_count = True
        reason = None
        
        if result and result['download_count'] >= daily_limit:
            # User has reached the daily download limit for this space
            should_count = False
            reason = 'daily_limit'
        
        # Also check IP rate limit (configurable downloads per hour across all spaces)
        if should_count:
            hour_ago = datetime.now() - timedelta(hours=1)
            ip_check_query = """
                SELECT COUNT(*) as hour_downloads
                FROM space_download_history
                WHERE ip_address = %s AND downloaded_at > %s
            """
            cursor.execute(ip_check_query, (ip_address, hour_ago))
            ip_result = cursor.fetchone()
            
            if ip_result and ip_result['hour_downloads'] >= hourly_ip_limit:
                should_count = False
                reason = 'rate_limit'
        
        # Record the download event regardless
        insert_query = """
            INSERT INTO space_download_history 
            (space_id, user_id, cookie_id, ip_address, user_agent)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (
            space_id,
            user_id if user_id > 0 else None,
            cookie_id if cookie_id else None,
            ip_address,
            user_agent[:500] if user_agent else None  # Limit user agent length
        ))
        
        # Only increment count if eligible
        if should_count:
            update_query = "UPDATE spaces SET download_cnt = download_cnt + 1 WHERE space_id = %s"
            cursor.execute(update_query, (space_id,))
        
        space.connection.commit()
        cursor.close()
        
        return jsonify({
            'success': True,
            'counted': should_count,
            'reason': reason
        })
        
    except Exception as e:
        logger.error(f"Error tracking download: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/spaces/<space_id>/clips', methods=['GET'])
def get_space_clips(space_id):
    """Get all clips for a space."""
    try:
        space = get_space_component()
        clips = space.list_clips(space_id)
        return jsonify({'success': True, 'clips': clips})
    except Exception as e:
        logger.error(f"Error getting clips: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/spaces/<space_id>/clips', methods=['POST'])
def create_space_clip(space_id):
    """Create a new clip from a space."""
    try:
        import subprocess
        
        # Get request data
        data = request.json
        clip_title = data.get('title', '').strip()
        start_time = float(data.get('start_time', 0))
        end_time = float(data.get('end_time', 0))
        
        # Validate inputs
        if not clip_title:
            return jsonify({'success': False, 'error': 'Clip title is required'}), 400
        
        if start_time >= end_time:
            return jsonify({'success': False, 'error': 'End time must be after start time'}), 400
        
        duration = end_time - start_time
        if duration <= 0:
            return jsonify({'success': False, 'error': 'Invalid clip duration'}), 400
            
        if duration > 300:  # 5 minutes max
            return jsonify({'success': False, 'error': 'Clip duration cannot exceed 5 minutes'}), 400
        
        # Get space component
        space = get_space_component()
        
        # Find the source file
        download_dir = app.config['DOWNLOAD_DIR']
        source_file = None
        for ext in ['mp3', 'm4a', 'wav']:
            path = os.path.join(download_dir, f"{space_id}.{ext}")
            if os.path.exists(path):
                source_file = path
                break
                
        if not source_file:
            return jsonify({'success': False, 'error': 'Source audio file not found'}), 404
        
        # Create clips directory if it doesn't exist
        clips_dir = os.path.join(download_dir, 'clips')
        os.makedirs(clips_dir, exist_ok=True)
        
        # Generate clip filename
        import time
        timestamp = int(time.time())
        safe_title = re.sub(r'[^\w\s-]', '', clip_title).strip().replace(' ', '_')[:50]
        clip_filename = f"{space_id}_{safe_title}_{timestamp}.mp3"
        clip_path = os.path.join(clips_dir, clip_filename)
        
        # Use ffmpeg to create the clip
        try:
            cmd = [
                'ffmpeg',
                '-i', source_file,
                '-ss', str(start_time),
                '-t', str(duration),
                '-acodec', 'libmp3lame',
                '-ab', '192k',
                '-y',  # Overwrite output file
                clip_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr}")
                return jsonify({'success': False, 'error': 'Failed to create clip'}), 500
                
        except FileNotFoundError:
            return jsonify({'success': False, 'error': 'FFmpeg not installed'}), 500
        except Exception as e:
            logger.error(f"Error running ffmpeg: {e}")
            return jsonify({'success': False, 'error': 'Failed to create clip'}), 500
        
        # Save clip to database
        clip_id = space.create_clip(
            space_id=space_id,
            clip_title=clip_title,
            start_time=start_time,
            end_time=end_time,
            filename=clip_filename,
            created_by=request.remote_addr
        )
        
        if not clip_id:
            # Clean up file if database save failed
            try:
                os.remove(clip_path)
            except:
                pass
            return jsonify({'success': False, 'error': 'Failed to save clip'}), 500
        
        return jsonify({
            'success': True,
            'clip_id': clip_id,
            'filename': clip_filename
        })
        
    except Exception as e:
        logger.error(f"Error creating clip: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/clips/<int:clip_id>/download', methods=['GET'])
def download_clip(clip_id):
    """Download a clip."""
    try:
        space = get_space_component()
        clip = space.get_clip(clip_id)
        
        if not clip:
            return jsonify({'success': False, 'error': 'Clip not found'}), 404
        
        # Build file path
        download_dir = app.config['DOWNLOAD_DIR']
        clip_path = os.path.join(download_dir, 'clips', clip['filename'])
        
        if not os.path.exists(clip_path):
            return jsonify({'success': False, 'error': 'Clip file not found'}), 404
        
        # Increment download count
        space.increment_clip_download_count(clip_id)
        
        # Return file
        return send_file(
            clip_path,
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name=f"{clip['clip_title']}.mp3"
        )
        
    except Exception as e:
        logger.error(f"Error downloading clip: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/clips/<int:clip_id>', methods=['DELETE'])
def delete_clip(clip_id):
    """Delete a clip."""
    try:
        space = get_space_component()
        
        # Delete from database (returns clip info)
        result = space.delete_clip(clip_id)
        
        if not result['success']:
            return jsonify(result), 404
        
        # Delete the physical file
        if result.get('filename'):
            download_dir = app.config['DOWNLOAD_DIR']
            clip_path = os.path.join(download_dir, 'clips', result['filename'])
            
            try:
                if os.path.exists(clip_path):
                    os.remove(clip_path)
                    logger.info(f"Deleted clip file: {clip_path}")
            except Exception as e:
                logger.error(f"Error deleting clip file: {e}")
                # Continue even if file deletion fails
        
        return jsonify({
            'success': True,
            'message': 'Clip deleted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error deleting clip: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/spaces/<space_id>/trim', methods=['POST'])
def trim_audio(space_id):
    """Trim an audio file using FFmpeg."""
    try:
        # Get request data
        data = request.get_json()
        start_time = data.get('start_time', 0)
        end_time = data.get('end_time')  # None means end of file
        cookie_id = data.get('cookie_id')
        user_id = session.get('user_id', 0)
        
        # Check permissions - user must own the space
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        query = "SELECT user_id, cookie_id FROM spaces WHERE space_id = %s"
        cursor.execute(query, (space_id,))
        space_record = cursor.fetchone()
        cursor.close()
        
        if not space_record:
            return jsonify({'error': 'Space not found'}), 404
        
        # Check ownership
        can_edit = False
        if user_id > 0:
            # Logged in user - must match user_id
            can_edit = (space_record['user_id'] == user_id)
        else:
            # Not logged in - must match cookie_id
            can_edit = (space_record['cookie_id'] == cookie_id and space_record['user_id'] == 0)
        
        if not can_edit:
            return jsonify({'error': 'You do not have permission to trim this space'}), 403
        
        # Validate input
        if start_time < 0:
            return jsonify({'success': False, 'error': 'Start time cannot be negative'}), 400
        
        if end_time is not None and end_time <= start_time:
            return jsonify({'success': False, 'error': 'End time must be after start time'}), 400
        
        # Find the audio file
        download_dir = app.config['DOWNLOAD_DIR']
        file_path = None
        
        for ext in ['mp3', 'm4a', 'wav']:
            path = os.path.join(download_dir, f"{space_id}.{ext}")
            if os.path.exists(path):
                file_path = path
                break
        
        if not file_path:
            return jsonify({'success': False, 'error': 'Audio file not found'}), 404
        
        # Create a temporary file for the trimmed audio with proper extension
        file_ext = os.path.splitext(file_path)[1]
        temp_file = file_path.replace(file_ext, f'_tmp{file_ext}')
        
        # Build FFmpeg command
        cmd = ['ffmpeg', '-y', '-i', file_path]
        
        # Add start time
        if start_time > 0:
            cmd.extend(['-ss', str(start_time)])
        
        # Add duration if end time is specified
        if end_time is not None:
            duration = end_time - start_time
            cmd.extend(['-t', str(duration)])
        
        # Copy codec to avoid re-encoding (faster)
        cmd.extend(['-c', 'copy', temp_file])
        
        logger.info(f"Trimming audio with command: {' '.join(cmd)}")
        
        # Execute FFmpeg command
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"FFmpeg output: {result.stdout}")
            
            # Replace original file with trimmed version
            if os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
                os.replace(temp_file, file_path)
                logger.info(f"Successfully trimmed audio file: {file_path}")
                
                # Get new file size for response
                new_size = os.path.getsize(file_path)
                
                return jsonify({
                    'success': True,
                    'message': 'Audio trimmed successfully',
                    'new_size': new_size
                })
            else:
                return jsonify({'success': False, 'error': 'Failed to create trimmed file'}), 500
                
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr}")
            # Clean up temp file if it exists
            if os.path.exists(temp_file):
                os.remove(temp_file)
            return jsonify({'success': False, 'error': f'FFmpeg error: {e.stderr}'}), 500
            
    except Exception as e:
        logger.error(f"Error trimming audio: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

def is_valid_space_url(url):
    """Check if a given URL appears to be a valid X space URL."""
    # This pattern matches URLs like https://x.com/i/spaces/1dRJZEpyjlNGB
    pattern = r'https?://(?:www\.)?(?:twitter|x)\.com/\w+/(?:spaces|status)/\w+'
    return bool(re.match(pattern, url))

def is_private_ip(ip):
    """Check if IP is private/localhost"""
    import ipaddress
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local
    except:
        return False

def get_country_code_from_geoip2(ip):
    """Get country code using local GeoIP2 database"""
    try:
        import geoip2.database
        
        # Look for database files
        db_paths = [
            os.path.join(os.path.dirname(__file__), 'data', 'GeoLite2-Country.mmdb'),
            os.path.join(os.path.dirname(__file__), 'data', 'GeoLite2-Country-Test.mmdb'),
            '/usr/share/GeoIP/GeoLite2-Country.mmdb',  # Common system location
        ]
        
        db_path = None
        for path in db_paths:
            if os.path.exists(path):
                db_path = path
                break
        
        if not db_path:
            logger.info("No GeoIP2 database found")
            return None
            
        with geoip2.database.Reader(db_path) as reader:
            response = reader.country(ip)
            country_code = response.country.iso_code
            logger.info(f"Got country code {country_code} from GeoIP2 database")
            return country_code
            
    except geoip2.errors.AddressNotFoundError:
        logger.info(f"IP {ip} not found in GeoIP2 database")
        return None
    except Exception as e:
        logger.debug(f"GeoIP2 lookup failed: {e}")
        return None

def get_country_code(ip):
    """Get country code from IP address using GeoIP2 database or online APIs"""
    try:
        # Check if it's a private/localhost IP
        if is_private_ip(ip):
            logger.info(f"IP {ip} is private/localhost, cannot geolocate")
            # For testing purposes, try to get the public IP
            try:
                public_ip_response = requests.get('https://api.ipify.org?format=json', timeout=5)
                if public_ip_response.status_code == 200:
                    public_ip = public_ip_response.json().get('ip')
                    logger.info(f"Using public IP {public_ip} instead of private IP {ip} for geolocation")
                    ip = public_ip
                else:
                    return None
            except:
                logger.warning("Could not get public IP for geolocation")
                return None
        
        # First try GeoIP2 database (fastest, no rate limits)
        country = get_country_code_from_geoip2(ip)
        if country:
            return country
        
        # Fall back to online APIs
        # First try ipapi.co
        url = f"https://ipapi.co/{ip}/country/"
        logger.info(f"Trying ipapi.co for IP {ip}")
        response = requests.get(url, timeout=5)
        logger.info(f"ipapi.co response status: {response.status_code}, text: {repr(response.text)}")
        
        if response.status_code == 200:
            country = response.text.strip()
            # Validate it's a 2-letter country code
            if len(country) == 2 and country.isalpha():
                logger.info(f"Got country code {country} from ipapi.co")
                return country.upper()
            else:
                logger.warning(f"Invalid country code from ipapi.co: {repr(country)}")
        elif response.status_code == 429:
            # Rate limited, try alternative API
            logger.info("ipapi.co rate limited, trying ip-api.com")
            alt_url = f"http://ip-api.com/json/{ip}?fields=status,countryCode"
            alt_response = requests.get(alt_url, timeout=5)
            logger.info(f"ip-api.com response status: {alt_response.status_code}")
            
            if alt_response.status_code == 200:
                data = alt_response.json()
                logger.info(f"ip-api.com response data: {data}")
                if data.get('status') == 'success':
                    country = data.get('countryCode', '').strip()
                    if len(country) == 2 and country.isalpha():
                        logger.info(f"Got country code {country} from ip-api.com")
                        return country.upper()
                    else:
                        logger.warning(f"Invalid country code from ip-api.com: {repr(country)}")
                else:
                    logger.warning(f"ip-api.com returned failure status for IP {ip}")
        else:
            logger.warning(f"Unexpected response from ipapi.co: {response.status_code}")
        
        return None
    except Exception as e:
        logger.error(f"Failed to get country code for IP {ip}: {e}", exc_info=True)
        return None

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
            
        # Get clips for this space
        clips = []
        try:
            clips = space.list_clips(space_id)
        except Exception as e:
            logger.error(f"Error getting clips: {e}")
            
        # Check if user can edit this space
        can_edit_space = False
        user_id = session.get('user_id', 0)
        cookie_id = request.cookies.get('xspace_user_id', '')
        is_admin = session.get('is_admin', False)
        
        if space_details:
            space_user_id = space_details.get('user_id', 0)
            space_cookie_id = space_details.get('cookie_id', '')
            
            if is_admin:
                # Admin can always edit
                can_edit_space = True
            elif user_id > 0:
                # Logged in user - must match user_id
                can_edit_space = (space_user_id == user_id)
            else:
                # Not logged in - must match cookie_id
                can_edit_space = (space_cookie_id == cookie_id and space_user_id == 0)
        
        # Check if space is favorited
        is_favorite = space.is_favorite(space_id, user_id, cookie_id)
        
        # Get tags for this space
        tags = space.get_space_tags(space_id)
        
        # Add tag_slug for template compatibility (tags table only has 'name')
        for tag in tags:
            if 'name' in tag and 'tag_slug' not in tag:
                # Create slug from name
                tag['tag_slug'] = tag['name'].lower().replace(' ', '-').replace('_', '-')
        
        # Check for pending transcription job
        has_pending_transcript_job = False
        transcript_jobs_dir = Path('./transcript_jobs')
        if transcript_jobs_dir.exists():
            for job_file in transcript_jobs_dir.glob('*.json'):
                try:
                    with open(job_file, 'r') as f:
                        job_data = json.load(f)
                        if (job_data.get('space_id') == space_id and 
                            job_data.get('status') in ['pending', 'in_progress']):
                            has_pending_transcript_job = True
                            break
                except Exception as e:
                    logger.error(f"Error reading transcript job file {job_file}: {e}")
        
        # Get reviews for this space
        reviews = None
        try:
            review_result = space.get_reviews(space_id)
            if review_result['success']:
                reviews = {
                    'average_rating': review_result['average_rating'],
                    'total_reviews': review_result['total_reviews']
                }
        except Exception as e:
            logger.error(f"Error getting reviews for space {space_id}: {e}")
        
        # Get tracking configuration for frontend
        tracking_config = {}
        try:
            cursor = space.connection.cursor(dictionary=True)
            config_query = "SELECT config_key, config_value FROM system_config WHERE config_key = %s"
            cursor.execute(config_query, ('play_minimum_duration_seconds',))
            config_row = cursor.fetchone()
            if config_row:
                tracking_config['min_play_duration'] = int(config_row['config_value'])
            else:
                tracking_config['min_play_duration'] = 30  # Default fallback
            cursor.close()
        except Exception as e:
            logger.error(f"Error getting tracking config: {e}")
            tracking_config['min_play_duration'] = 30  # Default fallback
            
        return render_template('space.html', 
                               space=space_details, 
                               file_path=file_path, 
                               file_size=file_size, 
                               file_extension=file_extension,
                               content_type=content_type,
                               job=job,
                               clips=clips,
                               can_edit_space=can_edit_space,
                               is_admin=is_admin,
                               is_favorite=is_favorite,
                               tags=tags,
                               reviews=reviews,
                               tracking_config=tracking_config,
                               has_pending_transcript_job=has_pending_transcript_job)
        
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

@app.route('/api/queue_status', methods=['GET'])
def api_queue_status():
    """API endpoint to get detailed queue status for real-time updates."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get all jobs that are pending or in progress
        pending_jobs = space.list_download_jobs(status='pending')
        in_progress_jobs = space.list_download_jobs(status='in_progress')
        downloading_jobs = space.list_download_jobs(status='downloading')
        
        # Combine and format all active jobs
        queue_jobs = []
        
        # Process pending jobs
        for job in pending_jobs:
            queue_jobs.append({
                'id': job.get('id'),
                'space_id': job.get('space_id'),
                'title': job.get('title', ''),
                'status': 'pending',
                'status_label': 'Pending',
                'status_class': 'secondary',
                'created_at': str(job.get('created_at', '')),
                'space_url': job.get('space_url', ''),
                'progress_percent': 0,
                'progress_in_size': 0
            })
            
        # Process in_progress jobs
        for job in in_progress_jobs:
            queue_jobs.append({
                'id': job.get('id'),
                'space_id': job.get('space_id'),
                'title': job.get('title', ''),
                'status': 'in_progress',
                'status_label': 'In Progress',
                'status_class': 'info',
                'created_at': str(job.get('created_at', '')),
                'space_url': job.get('space_url', ''),
                'progress_percent': job.get('progress_in_percent', 0),
                'progress_in_size': job.get('progress_in_size', 0)
            })
            
        # Process downloading jobs
        for job in downloading_jobs:
            # Get progress from the correct field
            progress = job.get('progress_in_percent', 0)
            if progress == 0:
                # Fallback to other progress fields
                if hasattr(job, 'progress'):
                    progress = job.progress
                elif hasattr(job, 'download_cnt'):
                    progress = job.download_cnt
                elif isinstance(job, dict):
                    progress = job.get('progress', job.get('download_cnt', 0))
                
            job_data = {
                'id': job.get('id'),
                'space_id': job.get('space_id'),
                'title': job.get('title', ''),
                'status': 'downloading',
                'status_label': 'Downloading',
                'status_class': 'primary',
                'created_at': str(job.get('created_at', '')),
                'space_url': job.get('space_url', ''),
                'progress_percent': progress,
                'progress_in_size': job.get('progress_in_size', 0)
            }
            
            # Calculate ETA for downloads
            if progress > 0 and progress < 100:
                try:
                    created_at = datetime.fromisoformat(job_data['created_at'])
                    elapsed = (datetime.now() - created_at).total_seconds()
                    total_estimated_seconds = (elapsed / progress) * 100
                    remaining_seconds = total_estimated_seconds - elapsed
                    
                    if remaining_seconds > 0:
                        if remaining_seconds > 3600:
                            hours = int(remaining_seconds // 3600)
                            minutes = int((remaining_seconds % 3600) // 60)
                            job_data['eta'] = f"{hours}h {minutes}m"
                        elif remaining_seconds > 60:
                            minutes = int(remaining_seconds // 60)
                            seconds = int(remaining_seconds % 60)
                            job_data['eta'] = f"{minutes}m {seconds}s"
                        else:
                            job_data['eta'] = f"{int(remaining_seconds)}s"
                except Exception:
                    pass
            
            queue_jobs.append(job_data)
        
        # Sort by created_at (oldest first)
        queue_jobs.sort(key=lambda x: x.get('created_at', ''))
        
        # Get transcription jobs
        transcript_jobs = []
        transcript_jobs_dir = Path('transcript_jobs')
        if transcript_jobs_dir.exists():
            for job_file in transcript_jobs_dir.glob('*.json'):
                try:
                    with open(job_file, 'r') as f:
                        job_data = json.load(f)
                        # Only include pending or in_progress transcription jobs
                        if job_data.get('status') in ['pending', 'in_progress']:
                            # Get space details for title
                            space_details = space.get_space(job_data.get('space_id'))
                            if space_details:
                                title = space_details.get('title', f"Space {job_data.get('space_id')}")
                            else:
                                title = f"Space {job_data.get('space_id')}"
                            
                            transcript_jobs.append({
                                'id': job_data.get('id'),
                                'space_id': job_data.get('space_id'),
                                'title': title,
                                'status': job_data.get('status'),
                                'status_label': 'Pending Transcription' if job_data.get('status') == 'pending' else 'Transcribing',
                                'status_class': 'warning' if job_data.get('status') == 'pending' else 'success',
                                'created_at': job_data.get('created_at', ''),
                                'progress_percent': job_data.get('progress', 0),
                                'type': 'transcription'
                            })
                except Exception as e:
                    logger.error(f"Error reading transcript job file {job_file}: {e}")
        
        # Sort transcript jobs by created_at
        transcript_jobs.sort(key=lambda x: x.get('created_at', ''))
        
        return jsonify({
            'jobs': queue_jobs,
            'transcript_jobs': transcript_jobs,
            'total': len(queue_jobs) + len(transcript_jobs)
        })
        
    except Exception as e:
        logger.error(f"Error in API queue status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/status/<int:job_id>', methods=['GET'])
def api_job_status(job_id):
    """API endpoint to get download job status by job ID."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get job details
        job = space.get_download_job(job_id=job_id)
        
        if not job:
            return jsonify({'error': 'Resource not found'}), 404
        
        # Check if the physical file exists
        download_dir = app.config['DOWNLOAD_DIR']
        file_exists = False
        file_size = 0
        file_path = None
        
        space_id = job.get('space_id')
        if space_id:
            for ext in ['mp3', 'm4a', 'wav']:
                path = os.path.join(download_dir, f"{space_id}.{ext}")
                if os.path.exists(path) and os.path.getsize(path) > 1024*1024:  # > 1MB
                    file_exists = True
                    file_size = os.path.getsize(path)
                    file_path = path
                    break
        
        # Build response
        response = {
            'job_id': job_id,
            'space_id': job.get('space_id'),
            'status': job.get('status', 'unknown'),
            'progress_in_percent': job.get('progress_in_percent', 0),
            'progress_in_size': job.get('progress_in_size', 0),
            'file_type': job.get('file_type', 'mp3'),
            'created_at': job.get('created_at'),
            'start_time': job.get('start_time'),
            'end_time': job.get('end_time'),
            'error_message': job.get('error_message'),
            'file_exists': file_exists,
            'file_size': file_size,
            'file_path': file_path
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error in API job status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/space/<space_id>/title', methods=['PUT'])
def update_space_title(space_id):
    """API endpoint to update space title."""
    try:
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        title = data.get('title', '').strip()
        cookie_id = data.get('cookie_id')
        user_id = session.get('user_id', 0)
        
        # Get Space component
        space = get_space_component()
        
        # Check permissions - user must own the space
        cursor = space.connection.cursor(dictionary=True)
        query = "SELECT user_id, cookie_id FROM spaces WHERE space_id = %s"
        cursor.execute(query, (space_id,))
        space_record = cursor.fetchone()
        cursor.close()
        
        if not space_record:
            return jsonify({'error': 'Space not found'}), 404
        
        # Check ownership
        can_edit = False
        if user_id > 0:
            # Logged in user - must match user_id
            can_edit = (space_record['user_id'] == user_id)
        else:
            # Not logged in - must match cookie_id
            can_edit = (space_record['cookie_id'] == cookie_id and space_record['user_id'] == 0)
        
        if not can_edit:
            return jsonify({'error': 'You do not have permission to edit this space'}), 403
        
        # Update title in database
        success = space.update_title(space_id, title)
        
        if success:
            return jsonify({
                'success': True,
                'space_id': space_id,
                'title': title
            })
        else:
            return jsonify({'error': 'Failed to update title'}), 500
            
    except Exception as e:
        logger.error(f"Error updating space title: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/space/<space_id>/metadata', methods=['POST'])
def fetch_space_metadata(space_id):
    """API endpoint to fetch and save space metadata."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Fetch and save metadata
        result = space.fetch_and_save_metadata(space_id)
        
        if result['success']:
            return jsonify({
                'success': True,
                'space_id': space_id,
                'metadata': result['metadata']
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Failed to fetch metadata')
            }), 500
            
    except Exception as e:
        logger.error(f"Error fetching space metadata: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/space/<space_id>/metadata', methods=['GET'])
def get_space_metadata(space_id):
    """API endpoint to get existing space metadata."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get metadata from database
        metadata = space.get_metadata(space_id)
        
        if metadata:
            return jsonify({
                'success': True,
                'space_id': space_id,
                'metadata': metadata
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No metadata found for this space'
            }), 404
            
    except Exception as e:
        logger.error(f"Error getting space metadata: {e}", exc_info=True)
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

@app.route('/api/spaces/<space_id>/notes', methods=['GET'])
def get_space_notes(space_id):
    """Get notes for a specific space."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get cookie ID from query parameter
        cookie_id = request.args.get('cookie_id')
        user_id = session.get('user_id', 0)  # Default to 0 for non-logged-in users
        
        # Get ALL notes for this space, marking which ones belong to current user
        cursor = space.connection.cursor(dictionary=True)
        query = """
            SELECT id, space_id, notes, user_id, cookie_id, created_at, updated_at
            FROM space_notes
            WHERE space_id = %s
            ORDER BY updated_at DESC
        """
        cursor.execute(query, (space_id,))
        notes = cursor.fetchall()
        cursor.close()
        
        # Mark which notes can be edited by the current user
        for note in notes:
            # User can edit if:
            # 1. They are logged in and it's their note (user_id matches)
            # 2. They are not logged in but have the cookie_id (anonymous note)
            if user_id > 0:
                note['can_edit'] = (note['user_id'] == user_id)
            else:
                note['can_edit'] = (note['cookie_id'] == cookie_id and note['user_id'] == 0)
            
            # Convert datetime objects to strings
            if note['created_at']:
                note['created_at'] = note['created_at'].isoformat()
            if note['updated_at']:
                note['updated_at'] = note['updated_at'].isoformat()
            
            # Add author info
            if note['user_id'] > 0:
                # Get user email for display
                cursor = space.connection.cursor(dictionary=True)
                cursor.execute("SELECT email FROM users WHERE id = %s", (note['user_id'],))
                user = cursor.fetchone()
                cursor.close()
                note['author'] = user['email'].split('@')[0] if user else 'User'
            else:
                note['author'] = 'Anonymous'
        
        return jsonify({'notes': notes})
        
    except Exception as e:
        logger.error(f"Error getting notes: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/spaces/<space_id>/notes', methods=['POST'])
def create_space_note(space_id):
    """Create a new note for a space."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get note data
        data = request.get_json()
        notes_content = data.get('notes', '').strip()
        cookie_id = data.get('cookie_id')
        user_id = session.get('user_id', 0)
        
        if not notes_content:
            return jsonify({'error': 'Note content is required'}), 400
        
        # Insert note
        cursor = space.connection.cursor()
        query = """
            INSERT INTO space_notes (space_id, notes, user_id, cookie_id)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(query, (space_id, notes_content, user_id, cookie_id if user_id == 0 else None))
        space.connection.commit()
        
        note_id = cursor.lastrowid
        cursor.close()
        
        return jsonify({
            'success': True,
            'note_id': note_id,
            'message': 'Note created successfully'
        })
        
    except Exception as e:
        logger.error(f"Error creating note: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/spaces/<space_id>/notes/<int:note_id>', methods=['PUT'])
def update_space_note(space_id, note_id):
    """Update an existing note."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get note data
        data = request.get_json()
        notes_content = data.get('notes', '').strip()
        cookie_id = data.get('cookie_id')
        user_id = session.get('user_id', 0)
        
        if not notes_content:
            return jsonify({'error': 'Note content is required'}), 400
        
        # Update note with ownership check
        cursor = space.connection.cursor()
        if user_id > 0:
            query = """
                UPDATE space_notes 
                SET notes = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND space_id = %s AND user_id = %s
            """
            cursor.execute(query, (notes_content, note_id, space_id, user_id))
        else:
            query = """
                UPDATE space_notes 
                SET notes = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND space_id = %s AND cookie_id = %s AND user_id = 0
            """
            cursor.execute(query, (notes_content, note_id, space_id, cookie_id))
        
        affected_rows = cursor.rowcount
        space.connection.commit()
        cursor.close()
        
        if affected_rows > 0:
            return jsonify({
                'success': True,
                'message': 'Note updated successfully'
            })
        else:
            return jsonify({'error': 'Note not found or unauthorized'}), 404
        
    except Exception as e:
        logger.error(f"Error updating note: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/spaces/<space_id>/notes/<int:note_id>', methods=['DELETE'])
def delete_space_note(space_id, note_id):
    """Delete a note."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get identification
        cookie_id = request.args.get('cookie_id')
        user_id = session.get('user_id', 0)
        
        # Delete note with ownership check
        cursor = space.connection.cursor()
        if user_id > 0:
            query = """
                DELETE FROM space_notes 
                WHERE id = %s AND space_id = %s AND user_id = %s
            """
            cursor.execute(query, (note_id, space_id, user_id))
        else:
            query = """
                DELETE FROM space_notes 
                WHERE id = %s AND space_id = %s AND cookie_id = %s AND user_id = 0
            """
            cursor.execute(query, (note_id, space_id, cookie_id))
        
        affected_rows = cursor.rowcount
        space.connection.commit()
        cursor.close()
        
        if affected_rows > 0:
            return jsonify({
                'success': True,
                'message': 'Note deleted successfully'
            })
        else:
            return jsonify({'error': 'Note not found or unauthorized'}), 404
        
    except Exception as e:
        logger.error(f"Error deleting note: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/spaces/<space_id>/reviews', methods=['GET'])
def get_space_reviews(space_id):
    """Get reviews for a specific space."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get reviews
        result = space.get_reviews(space_id)
        
        if result['success']:
            # Get current user info to mark editable reviews
            user_id = session.get('user_id', 0)
            cookie_id = request.args.get('cookie_id', '')
            
            # Check if user owns this space
            cursor = space.connection.cursor(dictionary=True)
            cursor.execute("SELECT user_id, cookie_id FROM spaces WHERE space_id = %s", (space_id,))
            space_record = cursor.fetchone()
            cursor.close()
            
            is_space_owner = False
            if space_record:
                if user_id > 0:
                    is_space_owner = (space_record['user_id'] == user_id)
                else:
                    is_space_owner = (space_record['cookie_id'] == cookie_id and space_record['user_id'] == 0)
            
            # Mark which reviews can be edited/deleted
            for review in result['reviews']:
                # User can edit/delete their own review
                can_edit = False
                if user_id > 0:
                    can_edit = (review['user_id'] == user_id)
                else:
                    can_edit = (review['cookie_id'] == cookie_id and review['user_id'] == 0)
                
                review['can_edit'] = can_edit
                review['can_delete'] = can_edit or is_space_owner
            
            return jsonify({
                'success': True,
                'average_rating': result['average_rating'],
                'total_reviews': result['total_reviews'],
                'reviews': result['reviews'],
                'is_space_owner': is_space_owner
            })
        else:
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"Error getting reviews: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/spaces/<space_id>/reviews', methods=['POST'])
def create_space_review(space_id):
    """Create a new review for a space."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get review data
        data = request.get_json()
        rating = data.get('rating')
        review_text = data.get('review', '').strip()
        cookie_id = data.get('cookie_id', '')
        user_id = session.get('user_id', 0)
        
        # Validate input
        if not rating:
            return jsonify({'error': 'Rating is required'}), 400
        
        try:
            rating = int(rating)
        except:
            return jsonify({'error': 'Invalid rating value'}), 400
            
        if not 1 <= rating <= 5:
            return jsonify({'error': 'Rating must be between 1 and 5'}), 400
        
        # Add review
        result = space.add_review(space_id, user_id, cookie_id, rating, review_text)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"Error creating review: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/spaces/<space_id>/reviews/<int:review_id>', methods=['PUT'])
def update_space_review(space_id, review_id):
    """Update an existing review."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get review data
        data = request.get_json()
        rating = data.get('rating')
        review_text = data.get('review', '').strip()
        cookie_id = data.get('cookie_id', '')
        user_id = session.get('user_id', 0)
        
        # Validate input
        if not rating:
            return jsonify({'error': 'Rating is required'}), 400
        
        try:
            rating = int(rating)
        except:
            return jsonify({'error': 'Invalid rating value'}), 400
            
        if not 1 <= rating <= 5:
            return jsonify({'error': 'Rating must be between 1 and 5'}), 400
        
        # Update review
        result = space.update_review(review_id, user_id, cookie_id, rating, review_text)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 404
            
    except Exception as e:
        logger.error(f"Error updating review: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/spaces/<space_id>/reviews/<int:review_id>', methods=['DELETE'])
def delete_space_review(space_id, review_id):
    """Delete a review."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get user info
        cookie_id = request.args.get('cookie_id', '')
        user_id = session.get('user_id', 0)
        
        # Delete review (space_id is passed for owner check)
        result = space.delete_review(review_id, user_id, cookie_id, space_id)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 404
            
    except Exception as e:
        logger.error(f"Error deleting review: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/spaces/<space_id>/favorite', methods=['POST'])
def toggle_favorite(space_id):
    """Toggle favorite status for a space."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get user info
        user_id = session.get('user_id', 0)
        cookie_id = request.json.get('cookie_id', '') if request.is_json else request.args.get('cookie_id', '')
        
        # Check if already favorited
        is_fav = space.is_favorite(space_id, user_id, cookie_id)
        
        if is_fav:
            # Remove from favorites
            result = space.remove_favorite(space_id, user_id, cookie_id)
            action = 'removed'
        else:
            # Add to favorites
            result = space.add_favorite(space_id, user_id, cookie_id)
            action = 'added'
        
        if result['success']:
            return jsonify({
                'success': True,
                'action': action,
                'is_favorite': not is_fav
            })
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"Error toggling favorite: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/spaces/<space_id>/favorite', methods=['GET'])
def check_favorite(space_id):
    """Check if a space is favorited."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get user info
        user_id = session.get('user_id', 0)
        cookie_id = request.args.get('cookie_id', '')
        
        # Check favorite status
        is_fav = space.is_favorite(space_id, user_id, cookie_id)
        
        return jsonify({
            'success': True,
            'is_favorite': is_fav
        })
        
    except Exception as e:
        logger.error(f"Error checking favorite: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/favorites')
def favorites():
    """Display user's favorite spaces."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get user info
        user_id = session.get('user_id', 0)
        cookie_id = request.cookies.get('xspace_user_id', '')
        
        # Get favorites
        favorites = space.get_user_favorites(user_id, cookie_id)
        
        # Check which files exist and add metadata
        download_dir = app.config['DOWNLOAD_DIR']
        for fav in favorites:
            # Check file existence
            file_exists = False
            for ext in ['mp3', 'm4a', 'wav']:
                file_path = os.path.join(download_dir, f"{fav['space_id']}.{ext}")
                if os.path.exists(file_path) and os.path.getsize(file_path) > 1024*1024:  # > 1MB
                    file_exists = True
                    fav['file_exists'] = True
                    fav['file_size'] = os.path.getsize(file_path)
                    fav['file_extension'] = ext
                    break
            
            if not file_exists:
                fav['file_exists'] = False
            
            # Get review data
            try:
                review_result = space.get_reviews(fav['space_id'])
                if review_result['success']:
                    fav['average_rating'] = review_result['average_rating']
                    fav['total_reviews'] = review_result['total_reviews']
                else:
                    fav['average_rating'] = 0
                    fav['total_reviews'] = 0
            except:
                fav['average_rating'] = 0
                fav['total_reviews'] = 0
            
            # Get metadata (host and speakers) and summary
            try:
                space_details = space.get_space(fav['space_id'])
                if space_details:
                    if space_details.get('metadata'):
                        fav['metadata'] = space_details['metadata']
                    else:
                        fav['metadata'] = None
                    
                    # Get summary from transcript if available
                    if space_details.get('transcript') and space_details['transcript'].get('summary'):
                        fav['summary'] = space_details['transcript']['summary']
                    else:
                        fav['summary'] = None
                else:
                    fav['metadata'] = None
                    fav['summary'] = None
            except:
                fav['metadata'] = None
                fav['summary'] = None
        
        return render_template('favorites.html', favorites=favorites)
        
    except Exception as e:
        logger.error(f"Error loading favorites: {e}", exc_info=True)
        flash('An error occurred while loading favorites', 'error')
        return redirect(url_for('index'))

@app.route('/spaces/tag/<tag_slug>')
def spaces_by_tag(tag_slug):
    """Display all spaces with a specific tag."""
    try:
        # Get Space component
        space = get_space_component()
        
        # Get tag and spaces
        result = space.get_spaces_by_tag(tag_slug)
        
        if not result['success']:
            flash(f"Tag not found: {tag_slug}", 'error')
            return redirect(url_for('all_spaces'))
        
        tag = result['tag']
        spaces = result['spaces']
        
        # Check which files exist and add metadata
        download_dir = app.config['DOWNLOAD_DIR']
        for space_item in spaces:
            # Check file existence
            file_exists = False
            for ext in ['mp3', 'm4a', 'wav']:
                file_path = os.path.join(download_dir, f"{space_item['space_id']}.{ext}")
                if os.path.exists(file_path) and os.path.getsize(file_path) > 1024*1024:  # > 1MB
                    file_exists = True
                    space_item['file_exists'] = True
                    space_item['file_size'] = os.path.getsize(file_path)
                    space_item['file_extension'] = ext
                    break
            
            if not file_exists:
                space_item['file_exists'] = False
            
            # Get metadata and reviews
            try:
                space_details = space.get_space(space_item['space_id'])
                if space_details:
                    space_item['metadata'] = space_details.get('metadata', {})
                    
                    # Get review data
                    review_result = space.get_reviews(space_item['space_id'])
                    if review_result['success']:
                        space_item['average_rating'] = review_result['average_rating']
                        space_item['total_reviews'] = review_result['total_reviews']
                    else:
                        space_item['average_rating'] = 0
                        space_item['total_reviews'] = 0
                else:
                    space_item['metadata'] = {}
                    space_item['average_rating'] = 0
                    space_item['total_reviews'] = 0
            except:
                space_item['metadata'] = {}
                space_item['average_rating'] = 0
                space_item['total_reviews'] = 0
        
        return render_template('tag_spaces.html', tag=tag, spaces=spaces)
        
    except Exception as e:
        logger.error(f"Error loading spaces by tag: {e}", exc_info=True)
        flash('An error occurred while loading spaces', 'error')
        return redirect(url_for('all_spaces'))

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
        
        # Check for specific format if requested
        format_requested = request.args.get('format', '').lower()
        
        # Define priority order for file formats
        if format_requested == 'mp4':
            search_extensions = ['mp4']
        elif format_requested == 'audio':
            search_extensions = ['mp3', 'm4a', 'wav']
        else:
            # Default: prefer audio, but include video if no audio found
            search_extensions = ['mp3', 'm4a', 'wav', 'mp4']
        
        for ext in search_extensions:
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
                    'flac': 'audio/flac',
                    'mp4': 'video/mp4'
                }
                content_type = mime_types.get(ext, f'audio/{ext}')
                break
        
        if not file_path:
            flash('Space file not found', 'error')
            return redirect(url_for('space_page', space_id=space_id))
        
        # Get space details to use for filename
        space_details = space.get_space(space_id)
        
        # Increment download count
        try:
            space.increment_download_count(space_id)
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
        elif content_type == 'video/mp4':
            ext = 'mp4'
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

@app.route('/api/spaces/<space_id>/available-formats', methods=['GET'])
def get_available_formats(space_id):
    """Get available download formats for a space."""
    try:
        download_dir = app.config['DOWNLOAD_DIR']
        available_formats = []
        
        # Check for different file formats
        formats_to_check = {
            'mp3': {'type': 'audio', 'name': 'MP3 Audio', 'icon': 'bi-music-note'},
            'm4a': {'type': 'audio', 'name': 'M4A Audio', 'icon': 'bi-music-note'},
            'wav': {'type': 'audio', 'name': 'WAV Audio', 'icon': 'bi-music-note'},
            'mp4': {'type': 'video', 'name': 'MP4 Video', 'icon': 'bi-camera-video'}
        }
        
        for ext, format_info in formats_to_check.items():
            file_path = os.path.join(download_dir, f"{space_id}.{ext}")
            if os.path.exists(file_path) and os.path.getsize(file_path) > 1024*1024:  # > 1MB
                file_size = os.path.getsize(file_path)
                available_formats.append({
                    'format': ext,
                    'type': format_info['type'],
                    'name': format_info['name'],
                    'icon': format_info['icon'],
                    'size': file_size,
                    'size_formatted': format_file_size(file_size)
                })
        
        return jsonify({
            'success': True,
            'formats': available_formats
        })
        
    except Exception as e:
        logger.error(f"Error getting available formats for space {space_id}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def format_file_size(size_bytes):
    """Format file size in human readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024*1024:
        return f"{size_bytes/1024:.1f} KB"
    elif size_bytes < 1024*1024*1024:
        return f"{size_bytes/(1024*1024):.1f} MB"
    else:
        return f"{size_bytes/(1024*1024*1024):.1f} GB"

@app.route('/share/<space_id>.jpg')
@app.route('/share/<space_id>.large.jpg')
def share_image(space_id):
    """Generate dynamic share image for a space."""
    try:
        # Determine image size based on route
        is_large = request.path.endswith('.large.jpg')
        width = 1200 if is_large else 300
        height = 630 if is_large else 157
        
        # Get space details
        space = get_space_component()
        space_details = space.get_space(space_id)
        
        if not space_details:
            # Return a default image or 404
            return "Space not found", 404
        
        # Get space title and metadata
        title = space_details.get('title', f'Space {space_id}')
        metadata = space_details.get('metadata', {})
        host_handle = metadata.get('host_handle', '') if metadata else ''
        
        # Create image with white background
        img = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(img)
        
        # Try to use a system font, fallback to default if not available
        try:
            # Try different font sizes for different image sizes
            font_size = 48 if is_large else 20
            title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
            handle_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", int(font_size * 0.7))
        except:
            # Use default font if system font not found
            title_font = ImageFont.load_default()
            handle_font = ImageFont.load_default()
        
        # Define layout parameters
        padding = 40 if is_large else 20
        avatar_size = 120 if is_large else 60
        avatar_x = padding
        avatar_y = (height - avatar_size) // 2
        
        # Try to fetch host profile picture
        avatar_img = None
        if host_handle:
            try:
                # Remove @ if present
                username = host_handle[1:] if host_handle.startswith('@') else host_handle
                avatar_url = f"https://unavatar.io/twitter/{username}"
                
                # Download avatar with timeout
                response = requests.get(avatar_url, timeout=5)
                if response.status_code == 200:
                    avatar_img = Image.open(BytesIO(response.content))
                    # Resize to avatar size
                    avatar_img = avatar_img.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
                    
                    # Create circular mask
                    mask = Image.new('L', (avatar_size, avatar_size), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.ellipse([0, 0, avatar_size, avatar_size], fill=255)
                    
                    # Apply circular mask
                    output = Image.new('RGBA', (avatar_size, avatar_size), (0, 0, 0, 0))
                    output.paste(avatar_img, (0, 0))
                    output.putalpha(mask)
                    
                    # Paste onto main image
                    img.paste(output, (avatar_x, avatar_y), output)
                    
                    # Add purple border around avatar
                    border_color = '#511fb2'
                    border_width = 3 if is_large else 2
                    draw.ellipse(
                        [avatar_x - border_width, avatar_y - border_width, 
                         avatar_x + avatar_size + border_width, avatar_y + avatar_size + border_width],
                        outline=border_color,
                        width=border_width
                    )
            except Exception as e:
                logger.warning(f"Failed to fetch avatar for {host_handle}: {e}")
                avatar_img = None
        
        # Fallback to letter avatar if image fetch failed
        if not avatar_img:
            # Draw avatar placeholder (circle)
            avatar_color = '#511fb2'  # Purple color matching the site theme
            draw.ellipse(
                [avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size],
                fill=avatar_color,
                outline=avatar_color
            )
            
            # If we have a host handle, add the first letter in the avatar
            if host_handle:
                # Get first letter of handle (remove @ if present)
                first_letter = host_handle[1] if host_handle.startswith('@') else host_handle[0]
                # Calculate text position to center it in the circle
                letter_font_size = 60 if is_large else 30
                try:
                    letter_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", letter_font_size)
                except:
                    letter_font = title_font
                
                # Get text bounding box for centering
                letter_bbox = draw.textbbox((0, 0), first_letter.upper(), font=letter_font)
                letter_width = letter_bbox[2] - letter_bbox[0]
                letter_height = letter_bbox[3] - letter_bbox[1]
                letter_x = avatar_x + (avatar_size - letter_width) // 2
                letter_y = avatar_y + (avatar_size - letter_height) // 2
                
                draw.text((letter_x, letter_y), first_letter.upper(), fill='white', font=letter_font)
        
        # Calculate text area
        text_x = avatar_x + avatar_size + padding
        text_width = width - text_x - padding
        
        # Draw host handle if available
        text_y = avatar_y
        if host_handle:
            draw.text((text_x, text_y), host_handle, fill='#666666', font=handle_font)
            text_y += int(font_size * 0.8)
        
        # Wrap and draw title
        # Simple word wrapping
        words = title.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=title_font)
            if bbox[2] - bbox[0] <= text_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    lines.append(word)
                    current_line = []
        
        if current_line:
            lines.append(' '.join(current_line))
        
        # Draw title lines
        for line in lines[:3]:  # Limit to 3 lines
            draw.text((text_x, text_y), line, fill='#333333', font=title_font)
            text_y += int(font_size * 1.2)
        
        # Add site branding at bottom
        brand_text = "XSpace Downloader"
        brand_font_size = 24 if is_large else 12
        try:
            brand_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", brand_font_size)
        except:
            brand_font = handle_font
        
        brand_bbox = draw.textbbox((0, 0), brand_text, font=brand_font)
        brand_width = brand_bbox[2] - brand_bbox[0]
        brand_x = width - brand_width - padding
        brand_y = height - padding - brand_font_size
        draw.text((brand_x, brand_y), brand_text, fill='#999999', font=brand_font)
        
        # Convert to bytes
        img_bytes = BytesIO()
        img.save(img_bytes, format='JPEG', quality=85)
        img_bytes.seek(0)
        
        # Return image with proper headers
        response = send_file(
            img_bytes,
            mimetype='image/jpeg',
            as_attachment=False,
            download_name=f'{space_id}{"_large" if is_large else ""}.jpg'
        )
        
        # Add cache headers (cache for 1 hour)
        response.headers['Cache-Control'] = 'public, max-age=3600'
        
        return response
        
    except Exception as e:
        logger.error(f"Error generating share image: {e}", exc_info=True)
        # Return a 1x1 transparent pixel as fallback
        img = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return send_file(img_bytes, mimetype='image/png')
        
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

@app.route('/api/translate/info', methods=['GET'])
def api_translate_info():
    """API endpoint to check translation service availability."""
    if not TRANSLATE_AVAILABLE:
        return jsonify({
            'available': False,
            'error': 'Translation service is not available. Please configure an AI provider (OpenAI or Claude) in mainconfig.json'
        }), 503
        
    # Get Translate component
    translator = get_translate_component()
    if not translator:
        return jsonify({
            'available': False,
            'error': 'Could not initialize translation service. Please check your AI provider configuration.'
        }), 503
    
    # Check if AI component is available
    ai_available = hasattr(translator, 'ai') and translator.ai is not None
    
    # Return service info
    return jsonify({
        'available': ai_available,
        'self_hosted': translator.self_hosted,
        'api_key_configured': ai_available,
        'api_url': translator.api_url,
        'provider': translator.ai.get_provider_name() if ai_available else "None",
        'error': None if ai_available else "AI component not initialized - check API keys"
    })

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
        space_id = data.get('space_id')  # Optional: for database storage
        include_timecodes = data.get('include_timecodes', False)
        
        # Debug logging
        logger.info(f"========== TRANSLATION REQUEST ==========")
        logger.info(f"Text length: {len(text) if text else 0}")
        logger.info(f"Source: {source_lang}")
        logger.info(f"Target: {target_lang}")
        logger.info(f"Space ID: {space_id}")
        logger.info(f"Include timecodes: {include_timecodes}")
        if text:
            logger.info(f"First 300 chars: {text[:300]}...")
            logger.info(f"Last 300 chars: ...{text[-300:]}")
        logger.info(f"=========================================")
        
        # Validate required fields
        if not text:
            return jsonify({'error': 'Missing text parameter'}), 400
            
        if not target_lang:
            return jsonify({'error': 'Missing target_lang parameter'}), 400
            
        # Get Translate component
        translator = get_translate_component()
        if not translator:
            return jsonify({'error': 'Could not initialize translation service'}), 500
        
        # Check database for existing translation if space_id is provided
        if space_id:
            try:
                space = get_space_component()
                
                # Format target language consistently
                if target_lang and len(target_lang) == 2:
                    target_lang_formatted = f"{target_lang}-{target_lang.upper()}"
                else:
                    target_lang_formatted = target_lang
                
                # Check for existing translation
                cursor = space.connection.cursor(dictionary=True)
                
                # First try exact match
                query = "SELECT * FROM space_transcripts WHERE space_id = %s AND language = %s"
                cursor.execute(query, (space_id, target_lang_formatted))
                existing_translation = cursor.fetchone()
                
                # If no exact match, try language family match
                if not existing_translation and '-' in target_lang_formatted:
                    base_language = target_lang_formatted.split('-')[0]
                    query = "SELECT * FROM space_transcripts WHERE space_id = %s AND language LIKE %s"
                    cursor.execute(query, (space_id, f"{base_language}-%"))
                    existing_translation = cursor.fetchone()
                    
                cursor.close()
                
                if existing_translation:
                    logger.info(f"Found existing translation for space {space_id} in {existing_translation['language']}")
                    return jsonify({
                        'success': True,
                        'translated_text': existing_translation['transcript'],
                        'source_lang': source_lang,
                        'target_lang': existing_translation['language'],
                        'from_database': True
                    })
                    
            except Exception as db_err:
                logger.warning(f"Error checking existing translation: {db_err}")
                # Continue with AI translation if database check fails
            
        # Auto-detect source language if set to 'auto'
        if source_lang == 'auto':
            success, result = translator.detect_language(text)
            if not success:
                return jsonify({'error': 'Language detection failed', 'details': result}), 400
            source_lang = result
            
        # Perform translation
        logger.info(f"Starting AI translation from {source_lang} to {target_lang}")
        logger.info(f"Include timecodes parameter: {include_timecodes}")
        success, result = translator.translate(text, source_lang, target_lang)
        
        if not success:
            error_msg = 'Translation failed'
            status_code = 400
            
            # Check for specific error types to provide better guidance
            if isinstance(result, dict) and 'error' in result:
                if 'AI provider not available' in result.get('error', ''):
                    error_msg = 'AI translation service requires API key configuration'
                    # Add setup instructions for AI providers
                    result['setup_instructions'] = {
                        'option1': 'Set OPENAI_API_KEY environment variable with your OpenAI API key from https://platform.openai.com/api-keys',
                        'option2': 'Set ANTHROPIC_API_KEY environment variable with your Claude API key from https://console.anthropic.com/',
                        'option3': 'Configure the AI provider in mainconfig.json'
                    }
                elif 'API key required' in result.get('error', ''):
                    error_msg = 'Translation requires AI provider configuration'
                    # Add setup instructions to the response
                    result['setup_instructions'] = {
                        'option1': 'Configure OpenAI API key in mainconfig.json',
                        'option2': 'Configure Claude API key in mainconfig.json'
                    }
                elif '400' in result.get('error', '') or '403' in result.get('error', ''):
                    error_msg = 'Authentication error with AI service'
                    result['suggestion'] = 'Please check your API key configuration in mainconfig.json'
            
            return jsonify({'error': error_msg, 'details': result}), status_code
            
        # Log successful translation result
        logger.info(f"AI translation successful - Result length: {len(result) if result else 0}")
        if result:
            logger.info(f"Translation first 200 chars: {result[:200]}...")
            logger.info(f"Translation last 200 chars: ...{result[-200:]}")
            
        # Store successful translation in database if space_id is provided
        if space_id:
            try:
                space = get_space_component()
                cursor = space.connection.cursor()
                
                # Format target language consistently
                if target_lang and len(target_lang) == 2:
                    target_lang_formatted = f"{target_lang}-{target_lang.upper()}"
                else:
                    target_lang_formatted = target_lang
                
                # Insert or update translation in database
                insert_query = """
                INSERT INTO space_transcripts (space_id, language, transcript, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
                ON DUPLICATE KEY UPDATE
                transcript = VALUES(transcript),
                updated_at = NOW()
                """
                cursor.execute(insert_query, (space_id, target_lang_formatted, result))
                space.connection.commit()
                cursor.close()
                
                logger.info(f"Stored translation for space {space_id} in {target_lang_formatted}")
                
            except Exception as db_err:
                logger.warning(f"Error storing translation in database: {db_err}")
                # Continue even if database storage fails
        
        # Return translated text
        return jsonify({
            'success': True,
            'translated_text': result,
            'source_lang': source_lang,
            'target_lang': target_lang,
            'from_database': False
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

@app.route('/api/summary', methods=['POST'])
def api_summary():
    """API endpoint to generate summary of text."""
    if not TRANSLATE_AVAILABLE:
        return jsonify({'error': 'AI service is not available'}), 503
        
    try:
        # Validate request
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400
            
        # Get request data
        data = request.json
        text = data.get('text')
        max_length = data.get('max_length')  # Optional parameter
        language = data.get('language')  # Optional language parameter (now ignored)
        
        # Validate required fields
        if not text:
            return jsonify({'error': 'Missing text parameter'}), 400
            
        # Get Translate component (which now includes AI functionality)
        translator = get_translate_component()
        if not translator:
            return jsonify({'error': 'Could not initialize AI service'}), 500
            
        # Generate summary with language parameter
        success, result = translator.summary(text, max_length, language)
        
        if not success:
            return jsonify({'error': 'Summary generation failed', 'details': result}), 400
            
        # Return summary
        response_data = {
            'success': True,
            'summary': result,
            'original_length': len(text),
            'summary_length': len(result),
            'max_length': max_length,
            'language': 'auto'  # AI detects language from input
        }
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error generating summary: {e}", exc_info=True)
        return jsonify({'error': 'An unexpected error occurred'}), 500

@app.route('/api/transcript/<transcript_id>/summary', methods=['POST'])
def api_transcript_summary(transcript_id):
    """API endpoint to generate or retrieve summary for a specific transcript."""
    if not TRANSLATE_AVAILABLE:
        return jsonify({'error': 'AI service is not available'}), 503
        
    try:
        # Validate transcript_id is a valid integer
        try:
            transcript_id = int(transcript_id)
        except ValueError:
            return jsonify({'error': 'Invalid transcript ID format'}), 400
        
        # Get request data
        data = request.json if request.is_json else {}
        max_length = data.get('max_length', 200)  # Default to 200 words
        force_regenerate = data.get('force_regenerate', False)
        
        # Get Space component
        space = get_space_component()
        
        # STEP 1: Check database for existing summary
        logger.info(f"Checking database for existing summary for transcript {transcript_id}")
        try:
            cursor = space.connection.cursor(dictionary=True)
            query = "SELECT * FROM space_transcripts WHERE id = %s"
            cursor.execute(query, (transcript_id,))
            transcript_record = cursor.fetchone()
            cursor.close()
            
            if not transcript_record:
                return jsonify({'error': 'Transcript not found'}), 404
            
            # Check if summary already exists and force_regenerate is False
            if transcript_record.get('summary') and not force_regenerate:
                logger.info(f"Found existing summary for transcript {transcript_id}")
                return jsonify({
                    'success': True,
                    'summary': transcript_record['summary'],
                    'from_database': True,
                    'transcript_id': transcript_id,
                    'space_id': transcript_record['space_id'],
                    'language': transcript_record['language'],
                    'original_length': len(transcript_record.get('transcript', '')),
                    'summary_length': len(transcript_record['summary'])
                })
                
        except Exception as db_err:
            logger.warning(f"Error checking existing summary: {db_err}")
            return jsonify({'error': 'Database error'}), 500
        
        # STEP 2: Generate new summary using AI
        transcript_text = transcript_record.get('transcript', '')
        if not transcript_text:
            return jsonify({'error': 'No transcript text found'}), 400
        
        logger.info(f"Generating new summary for transcript {transcript_id} (length: {len(transcript_text)})")
        
        # Get Translate component (which includes AI functionality)
        translator = get_translate_component()
        if not translator:
            return jsonify({'error': 'Could not initialize AI service'}), 500
            
        # Generate summary
        success, result = translator.summary(transcript_text, max_length)
        
        if not success:
            return jsonify({'error': 'Summary generation failed', 'details': result}), 400
        
        # STEP 3: Store summary in database
        try:
            cursor = space.connection.cursor()
            update_query = "UPDATE space_transcripts SET summary = %s, updated_at = NOW() WHERE id = %s"
            cursor.execute(update_query, (result, transcript_id))
            space.connection.commit()
            cursor.close()
            logger.info(f"Stored summary for transcript {transcript_id}")
        except Exception as db_err:
            logger.warning(f"Error storing summary in database: {db_err}")
            # Continue even if database storage fails
            
        # Return summary
        return jsonify({
            'success': True,
            'summary': result,
            'from_database': False,
            'transcript_id': transcript_id,
            'space_id': transcript_record['space_id'],
            'language': transcript_record['language'],
            'original_length': len(transcript_text),
            'summary_length': len(result),
            'max_length': max_length
        })
        
    except Exception as e:
        logger.error(f"Error generating transcript summary: {e}", exc_info=True)
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

@app.route('/api/transcripts/<space_id>', methods=['GET'])
def api_get_transcripts_for_space(space_id):
    """API endpoint to get all transcripts for a space, optionally filtered by language."""
    try:
        # Get optional language parameter
        language = request.args.get('language')
        
        # Get Space component
        space = get_space_component()
        
        # Get transcripts for the space
        if language:
            # Get specific language transcript
            cursor = space.connection.cursor(dictionary=True)
            query = "SELECT * FROM space_transcripts WHERE space_id = %s AND language = %s"
            cursor.execute(query, (space_id, language))
            transcripts = cursor.fetchall()
            cursor.close()
        else:
            # Get all transcripts for the space
            transcripts = space.get_transcripts_for_space(space_id)
        
        # Convert datetime objects to strings for JSON serialization
        safe_transcripts = []
        for transcript in transcripts:
            safe_transcript = {}
            for key, value in transcript.items():
                if hasattr(value, 'isoformat'):
                    safe_transcript[key] = value.isoformat()
                else:
                    safe_transcript[key] = value
            safe_transcripts.append(safe_transcript)
        
        return jsonify({
            'space_id': space_id,
            'transcripts': safe_transcripts,
            'count': len(safe_transcripts)
        })
        
    except Exception as e:
        logger.error(f"Error getting transcripts for space {space_id}: {e}", exc_info=True)
        return jsonify({'error': 'An unexpected error occurred'}), 500

@app.route('/api/top_stats/<stat_type>')
def api_top_stats(stat_type):
    """Get top 10 spaces by plays, downloads, or top hosts."""
    try:
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        if stat_type == 'plays':
            # Get top 10 spaces by play count
            query = """
                SELECT 
                    s.space_id,
                    COALESCE(s.title, s.space_id) as title,
                    COALESCE(sm.host_handle, sm.host, 'Unknown') as host_name,
                    NULL as host_pic,
                    s.playback_cnt as play_count,
                    s.download_cnt as download_count,
                    s.created_at
                FROM spaces s
                LEFT JOIN space_metadata sm ON s.space_id = sm.space_id
                WHERE s.playback_cnt > 0
                ORDER BY s.playback_cnt DESC
                LIMIT 10
            """
            cursor.execute(query)
            results = cursor.fetchall()
            
        elif stat_type == 'downloads':
            # Get top 10 spaces by download count
            query = """
                SELECT 
                    s.space_id,
                    COALESCE(s.title, s.space_id) as title,
                    COALESCE(sm.host_handle, sm.host, 'Unknown') as host_name,
                    NULL as host_pic,
                    s.playback_cnt as play_count,
                    s.download_cnt as download_count,
                    s.created_at
                FROM spaces s
                LEFT JOIN space_metadata sm ON s.space_id = sm.space_id
                WHERE s.download_cnt > 0
                ORDER BY s.download_cnt DESC
                LIMIT 10
            """
            cursor.execute(query)
            results = cursor.fetchall()
            
        elif stat_type == 'hosts':
            # Get top 10 hosts by number of spaces
            query = """
                SELECT 
                    COALESCE(sm.host_handle, sm.host, 'Unknown') as host_name,
                    NULL as host_pic,
                    COUNT(DISTINCT s.id) as space_count,
                    SUM(s.playback_cnt) as total_plays,
                    SUM(s.download_cnt) as total_downloads,
                    MAX(s.created_at) as latest_space
                FROM spaces s
                LEFT JOIN space_metadata sm ON s.space_id = sm.space_id
                WHERE s.title IS NOT NULL AND (sm.host_handle IS NOT NULL OR sm.host IS NOT NULL)
                GROUP BY sm.host_handle, sm.host
                ORDER BY space_count DESC
                LIMIT 10
            """
            cursor.execute(query)
            results = cursor.fetchall()
            
        elif stat_type == 'users':
            # Get top 10 users by activity
            query = """
                SELECT 
                    u.id as user_id,
                    u.email,
                    u.login_count,
                    COUNT(DISTINCT s.id) as submission_count,
                    SUM(s.playback_cnt) as total_plays,
                    SUM(s.download_cnt) as total_downloads
                FROM users u
                LEFT JOIN spaces s ON u.id = s.user_id
                WHERE u.status = 1
                GROUP BY u.id, u.email, u.login_count
                ORDER BY (u.login_count + COUNT(DISTINCT s.id) + COALESCE(SUM(s.playback_cnt), 0) + COALESCE(SUM(s.download_cnt), 0)) DESC
                LIMIT 10
            """
            cursor.execute(query)
            results = cursor.fetchall()
            
            # Add MD5 hash for Gravatar
            import hashlib
            for result in results:
                if result.get('email'):
                    email_hash = hashlib.md5(result['email'].lower().strip().encode()).hexdigest()
                    result['email_hash'] = email_hash
                    # Don't send actual email to frontend for privacy
                    result.pop('email', None)
            
        elif stat_type == 'reviews':
            # Get top 10 spaces by average rating with minimum review count
            query = """
                SELECT 
                    s.space_id,
                    COALESCE(s.title, s.space_id) as title,
                    COALESCE(sm.host_handle, sm.host, 'Unknown') as host_name,
                    NULL as host_pic,
                    ROUND(AVG(r.rating), 1) as average_rating,
                    COUNT(r.id) as review_count,
                    s.playback_cnt as play_count,
                    s.download_cnt as download_count,
                    s.created_at
                FROM spaces s
                LEFT JOIN space_metadata sm ON s.space_id = sm.space_id
                INNER JOIN space_reviews r ON s.space_id = r.space_id
                GROUP BY s.space_id, s.title, sm.host_handle, sm.host, s.playback_cnt, s.download_cnt, s.created_at
                HAVING COUNT(r.id) >= 2
                ORDER BY average_rating DESC, review_count DESC
                LIMIT 10
            """
            cursor.execute(query)
            results = cursor.fetchall()
            
        else:
            return jsonify({'error': 'Invalid stat type'}), 400
        
        cursor.close()
        
        # Convert datetime objects to strings
        for result in results:
            for key, value in result.items():
                if hasattr(value, 'isoformat'):
                    result[key] = value.isoformat()
        
        return jsonify({
            'type': stat_type,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Error getting top stats: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# Helper function to generate secure tokens
def generate_secure_token(length=6):
    """Generate a secure random token like YouTube video IDs."""
    # Use URL-safe characters: letters (upper and lower) and digits
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# Route for sending login link
@app.route('/auth/send-login-link', methods=['POST'])
def send_login_link():
    """Send a magic login link to the user's email."""
    try:
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Email address is required', 'error')
            return redirect(url_for('index'))
        
        # Basic email validation
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            flash('Please enter a valid email address', 'error')
            return redirect(url_for('index'))
        
        # Get database connection
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        # Check if user exists, create if not
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        
        if not user:
            # Create new user with email only (no password needed)
            cursor.execute(
                "INSERT INTO users (email, password, status, is_admin, country) VALUES (%s, %s, %s, %s, %s)",
                (email, '', 1, 0, None)  # Empty password, status = 1 (active), is_admin = 0 (not admin), country = NULL
            )
            space.connection.commit()
            user_id = cursor.lastrowid
        else:
            user_id = user['id']
        
        # Generate login token
        token = generate_secure_token(6)
        expires_at = datetime.datetime.now() + datetime.timedelta(hours=24)
        
        # Store token in database
        cursor.execute(
            "INSERT INTO login_tokens (user_id, token, email, expires_at) VALUES (%s, %s, %s, %s)",
            (user_id, token, email, expires_at)
        )
        space.connection.commit()
        cursor.close()
        
        # Create login URL
        base_url = request.url_root.rstrip('/')
        login_url = f"{base_url}/auth/verify/{token}"
        
        # Send email using Email component
        try:
            from components.Email import Email
            email_component = Email()
            
            subject = "Your XSpace Downloader Login Link"
            body = f"""
Hello!

You requested a login link for XSpace Downloader. Click the link below to log in:

{login_url}

This link will expire in 24 hours.

If you didn't request this link, you can safely ignore this email.

Best regards,
XSpace Downloader Team
"""
            
            email_component.send(email, subject=subject, body=body, content_type='text/plain')
            flash('Login link sent! Check your email inbox.', 'success')
            
        except Exception as email_error:
            logger.error(f"Error sending login email: {email_error}")
            flash('Error sending email. Please try again later.', 'error')
            
        return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f"Error in send_login_link: {e}", exc_info=True)
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('index'))

# Route for verifying login token
@app.route('/auth/verify/<token>')
def verify_login_token(token):
    """Verify the login token and log the user in."""
    try:
        # Get database connection
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        # First check if token exists at all
        cursor.execute("""
            SELECT lt.*, u.email, u.id as user_id
            FROM login_tokens lt
            JOIN users u ON lt.user_id = u.id
            WHERE lt.token = %s
        """, (token,))
        
        token_data = cursor.fetchone()
        
        if not token_data:
            flash('This login link is invalid. Please request a new one.', 'error')
            return redirect(url_for('index'))
        
        # Check if token is already used
        if token_data['used']:
            flash('This login link has already been used. Please request a new one.', 'warning')
            return redirect(url_for('index'))
        
        # Check if token is expired
        cursor.execute("""
            SELECT expires_at > NOW() as is_valid
            FROM login_tokens
            WHERE token = %s
        """, (token,))
        
        validity = cursor.fetchone()
        if not validity['is_valid']:
            flash('This login link has expired. Please request a new one.', 'warning')
            return redirect(url_for('index'))
        
        # Mark token as used
        cursor.execute(
            "UPDATE login_tokens SET used = TRUE WHERE id = %s",
            (token_data['id'],)
        )
        
        # Get cookie_id from session if exists
        cookie_id = session.get('cookie_id')
        
        if cookie_id:
            # Migrate cookie-based data to user account
            # Update spaces
            cursor.execute("""
                UPDATE spaces 
                SET user_id = %s 
                WHERE cookie_id = %s AND user_id = 0
            """, (token_data['user_id'], cookie_id))
            
            # Update space_notes
            cursor.execute("""
                UPDATE space_notes 
                SET user_id = %s, cookie_id = NULL 
                WHERE cookie_id = %s AND user_id = 0
            """, (token_data['user_id'], cookie_id))
            
            # Update download_jobs
            cursor.execute("""
                UPDATE download_jobs 
                SET user_id = %s 
                WHERE cookie_id = %s AND user_id = 0
            """, (token_data['user_id'], cookie_id))
            
            logger.info(f"Migrated cookie data {cookie_id} to user {token_data['user_id']}")
        
        space.connection.commit()
        
        # Update last login time and increment login count
        cursor.execute(
            "UPDATE users SET last_logged_in = NOW(), login_count = COALESCE(login_count, 0) + 1 WHERE id = %s",
            (token_data['user_id'],)
        )
        
        # Check if user needs country set (first login)
        cursor.execute(
            "SELECT country FROM users WHERE id = %s",
            (token_data['user_id'],)
        )
        user_country_row = cursor.fetchone()
        logger.info(f"User country check - user_id: {token_data['user_id']}, country_row: {user_country_row}")
        
        if user_country_row:
            country_value = user_country_row.get('country')
            logger.info(f"Country value from DB: {repr(country_value)}")
            
            if country_value is None or country_value == '':
                # Get IP address from request
                user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
                logger.info(f"User IP address: {user_ip}, X-Forwarded-For: {request.headers.get('X-Forwarded-For')}, remote_addr: {request.remote_addr}")
                
                if user_ip:
                    # Handle comma-separated IPs from proxy headers
                    user_ip = user_ip.split(',')[0].strip()
                    logger.info(f"Using IP for geolocation: {user_ip}")
                    
                    # Get country code from IP
                    country_code = get_country_code(user_ip)
                    logger.info(f"Geolocation result: {country_code}")
                    
                    if country_code:
                        # Update user's country
                        cursor.execute(
                            "UPDATE users SET country = %s WHERE id = %s",
                            (country_code, token_data['user_id'])
                        )
                        logger.info(f"Set country {country_code} for user {token_data['user_id']} from IP {user_ip}")
                    else:
                        logger.warning(f"Could not determine country for IP {user_ip}")
                else:
                    logger.warning("No IP address available for geolocation")
            else:
                logger.info(f"User already has country set: {country_value}")
        else:
            logger.error(f"Could not fetch user record for user_id {token_data['user_id']}")
        
        space.connection.commit()
        
        # Check if user is admin
        cursor.execute("SELECT is_admin FROM users WHERE id = %s", (token_data['user_id'],))
        admin_check = cursor.fetchone()
        is_admin = admin_check.get('is_admin', 0) if admin_check else 0
        
        cursor.close()
        
        # Set session variables
        session['user_id'] = token_data['user_id']
        session['user_email'] = token_data['email']
        session['is_admin'] = bool(is_admin)
        session.permanent = True  # Make session persistent
        
        flash(f'Welcome! You are now logged in as {token_data["email"]}', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f"Error verifying login token: {e}", exc_info=True)
        flash('An error occurred during login. Please try again.', 'error')
        return redirect(url_for('index'))

# Route for logout
@app.route('/auth/logout')
def logout():
    """Log the user out."""
    session.pop('user_id', None)
    session.pop('user_email', None)
    session.pop('is_admin', None)
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('index'))

# Route for setup wizard
@app.route('/setup', methods=['GET', 'POST'])
def setup():
    """Setup wizard for initial admin configuration."""
    try:
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        # Check if any admin exists
        cursor.execute("SELECT COUNT(*) as admin_count FROM users WHERE is_admin = 1")
        result = cursor.fetchone()
        admin_exists = result['admin_count'] > 0
        
        # If admin exists, require admin login
        if admin_exists:
            user_id = session.get('user_id')
            if not user_id:
                flash('Please log in as admin to access setup.', 'warning')
                return redirect(url_for('index'))
            
            # Check if current user is admin
            cursor.execute("SELECT is_admin FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user or not user['is_admin']:
                flash('Admin access required for setup.', 'error')
                return redirect(url_for('index'))
        
        if request.method == 'POST':
            step = request.form.get('step', '1')
            
            if step == '1' and not admin_exists:
                # Create admin user
                admin_email = request.form.get('admin_email', '').strip()
                if not admin_email or '@' not in admin_email:
                    flash('Please enter a valid email address.', 'error')
                    return render_template('setup.html', step=1, admin_exists=admin_exists)
                
                # Check if user already exists
                cursor.execute("SELECT id FROM users WHERE email = %s", (admin_email,))
                existing_user = cursor.fetchone()
                
                if existing_user:
                    # Update existing user to admin
                    cursor.execute(
                        "UPDATE users SET is_admin = 1 WHERE id = %s",
                        (existing_user['id'],)
                    )
                    user_id = existing_user['id']
                else:
                    # Create new admin user
                    cursor.execute(
                        "INSERT INTO users (email, password, status, is_admin) VALUES (%s, %s, %s, %s)",
                        (admin_email, '', 1, 1)  # Empty password, active status, is_admin=1
                    )
                    user_id = cursor.lastrowid
                
                space.connection.commit()
                
                # Log in the admin
                session['user_id'] = user_id
                session['user_email'] = admin_email
                session['is_admin'] = True
                session.permanent = True
                
                flash('Admin account created successfully!', 'success')
                
                # Load existing config for next step
                config_data = {}
                try:
                    with open('db_config.json', 'r') as f:
                        db_config = json.load(f)
                        if 'mysql' in db_config:
                            config_data['db_host'] = db_config['mysql'].get('host', 'localhost')
                            config_data['db_port'] = db_config['mysql'].get('port', 3306)
                            config_data['db_name'] = db_config['mysql'].get('database', '')
                            config_data['db_user'] = db_config['mysql'].get('user', '')
                            config_data['db_password'] = db_config['mysql'].get('password', '')
                except:
                    pass
                
                return render_template('setup.html', step=2, admin_exists=True, config=config_data)
            
            elif step == '2':
                # Save database configuration
                db_host = request.form.get('db_host', '').strip()
                db_port = request.form.get('db_port', '3306').strip()
                db_name = request.form.get('db_name', '').strip()
                db_user = request.form.get('db_user', '').strip()
                db_password = request.form.get('db_password', '').strip()
                
                # Update db_config.json
                db_config = {
                    "type": "mysql",
                    "mysql": {
                        "host": db_host,
                        "port": int(db_port),
                        "database": db_name,
                        "user": db_user,
                        "password": db_password
                    }
                }
                
                with open('db_config.json', 'w') as f:
                    json.dump(db_config, f, indent=4)
                
                flash('Database configuration saved!', 'success')
                
                # Load existing config for next step
                config_data = {}
                
                # Load email config from database
                try:
                    cursor = space.connection.cursor(dictionary=True)
                    cursor.execute("SELECT * FROM email_config WHERE status = 1 ORDER BY id DESC LIMIT 1")
                    email_config = cursor.fetchone()
                    cursor.close()
                    
                    if email_config:
                        config_data['email_provider'] = email_config['provider']
                        config_data['email_api_key'] = email_config['api_key'] or ''
                        config_data['email_from_email'] = email_config['from_email'] or ''
                        config_data['email_from_name'] = email_config['from_name'] or ''
                        
                        # For mailgun, we need the domain
                        if email_config['provider'] == 'mailgun' and email_config['from_email']:
                            parts = email_config['from_email'].split('@')
                            if len(parts) == 2:
                                config_data['mailgun_domain'] = parts[1]
                except:
                    pass
                
                # Load .env for AI keys
                try:
                    if os.path.exists('.env'):
                        with open('.env', 'r') as f:
                            for line in f:
                                line = line.strip()
                                if line and not line.startswith('#') and '=' in line:
                                    key, value = line.split('=', 1)
                                    value = value.strip().strip('"').strip("'")
                                    if key in ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY']:
                                        config_data[key] = value
                except:
                    pass
                
                return render_template('setup.html', step=3, admin_exists=True, config=config_data)
            
            elif step == '3':
                # Save API configurations
                mail_provider = request.form.get('mail_provider', '').strip()
                mail_api_key = request.form.get('mail_api_key', '').strip()
                mail_from = request.form.get('mail_from', '').strip()
                mail_from_name = request.form.get('mail_from_name', 'XSpace Downloader').strip()
                mailgun_domain = request.form.get('mailgun_domain', '').strip()
                openai_api_key = request.form.get('openai_api_key', '').strip()
                anthropic_api_key = request.form.get('anthropic_api_key', '').strip()
                
                # Save email config to database
                if mail_provider and mail_api_key:
                    try:
                        cursor = space.connection.cursor()
                        
                        # First disable all existing email configs
                        cursor.execute("UPDATE email_config SET status = 0")
                        
                        # Check if this provider already exists
                        cursor.execute("SELECT id FROM email_config WHERE provider = %s", (mail_provider,))
                        existing = cursor.fetchone()
                        
                        if existing:
                            # Update existing record
                            cursor.execute("""
                                UPDATE email_config 
                                SET api_key = %s, from_email = %s, from_name = %s, 
                                    status = 1, updated_at = NOW()
                                WHERE id = %s
                            """, (mail_api_key, mail_from, mail_from_name, existing[0]))
                        else:
                            # Insert new record
                            cursor.execute("""
                                INSERT INTO email_config 
                                (provider, api_key, from_email, from_name, status)
                                VALUES (%s, %s, %s, %s, 1)
                            """, (mail_provider, mail_api_key, mail_from, mail_from_name))
                        
                        space.connection.commit()
                        cursor.close()
                        logger.info(f"Saved email config for provider: {mail_provider}")
                    except Exception as e:
                        logger.error(f"Error saving email config: {e}")
                        if cursor:
                            cursor.close()
                
                # Save AI API keys to .env file
                env_vars = {}
                
                # Read existing .env if it exists
                if os.path.exists('.env'):
                    with open('.env', 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#') and '=' in line:
                                key, value = line.split('=', 1)
                                env_vars[key] = value
                
                # Update AI keys
                if openai_api_key:
                    env_vars['OPENAI_API_KEY'] = openai_api_key
                
                if anthropic_api_key:
                    env_vars['ANTHROPIC_API_KEY'] = anthropic_api_key
                
                # Write updated .env file
                with open('.env', 'w') as f:
                    f.write("# XSpace Downloader Configuration\n")
                    f.write("# Generated by setup wizard\n\n")
                    
                    # Database section (commented, as it's in db_config.json)
                    f.write("# Database configuration is stored in db_config.json\n")
                    f.write("# Email configuration is stored in database email_config table\n\n")
                    
                    f.write("# AI API Keys\n")
                    for key in ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY']:
                        if key in env_vars:
                            f.write(f"{key}={env_vars[key]}\n")
                    
                    # Other existing variables (excluding old email configs)
                    f.write("\n# Other Configuration\n")
                    for key, value in env_vars.items():
                        if key not in ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY',
                                      'SENDGRID_API_KEY', 'SENDGRID_FROM_EMAIL', 
                                      'MAILGUN_API_KEY', 'MAILGUN_DOMAIN', 'MAILGUN_FROM_EMAIL']:
                            f.write(f"{key}={value}\n")
                
                flash('Configuration saved successfully! Setup complete.', 'success')
                return redirect(url_for('index'))
        
        # GET request - show appropriate step
        # Always load existing configuration for display
        config_data = {}
        
        # Load database config
        try:
            with open('db_config.json', 'r') as f:
                db_config = json.load(f)
                logger.debug(f"Loaded db_config: {db_config}")
                if 'mysql' in db_config:
                    config_data['db_host'] = db_config['mysql'].get('host', 'localhost')
                    config_data['db_port'] = db_config['mysql'].get('port', 3306)
                    config_data['db_name'] = db_config['mysql'].get('database', '')
                    config_data['db_user'] = db_config['mysql'].get('user', '')
                    config_data['db_password'] = db_config['mysql'].get('password', '')
                    logger.debug(f"Database config loaded: host={config_data.get('db_host')}, db={config_data.get('db_name')}")
        except Exception as e:
            logger.debug(f"Could not load db_config.json: {e}")
        
        # Load email config from database
        try:
            cursor = space.connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM email_config WHERE status = 1 ORDER BY id DESC LIMIT 1")
            email_config = cursor.fetchone()
            cursor.close()
            
            if email_config:
                config_data['email_provider'] = email_config['provider']
                config_data['email_api_key'] = email_config['api_key'] or ''
                config_data['email_from_email'] = email_config['from_email'] or ''
                config_data['email_from_name'] = email_config['from_name'] or ''
                
                # For mailgun, we need the domain from the from_email
                if email_config['provider'] == 'mailgun' and email_config['from_email']:
                    # Extract domain from email like noreply@mg.example.com
                    parts = email_config['from_email'].split('@')
                    if len(parts) == 2:
                        config_data['mailgun_domain'] = parts[1]
                
                logger.debug(f"Loaded email config from database: provider={email_config['provider']}")
        except Exception as e:
            logger.debug(f"Could not load email config from database: {e}")
        
        # Load .env values for AI keys only
        try:
            if os.path.exists('.env'):
                with open('.env', 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            # Remove quotes if present
                            value = value.strip().strip('"').strip("'")
                            if key in ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY']:
                                config_data[key] = value
                logger.debug(f"Loaded .env config: {list(config_data.keys())}")
        except Exception as e:
            logger.debug(f"Could not load .env file: {e}")
        
        if not admin_exists:
            return render_template('setup.html', step=1, admin_exists=False, config=config_data)
        else:
            # Determine which step to show based on URL parameter
            requested_step = request.args.get('step', '2')
            return render_template('setup.html', step=int(requested_step), admin_exists=True, config=config_data)
        
    except Exception as e:
        logger.error(f"Error in setup wizard: {e}", exc_info=True)
        flash('An error occurred during setup. Please try again.', 'error')
        return redirect(url_for('index'))
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()

# Route for testing database connection
@app.route('/setup/test-db', methods=['POST'])
def test_database_connection():
    """Test database connection with provided credentials."""
    try:
        data = request.get_json()
        
        # Validate input
        required_fields = ['host', 'port', 'database', 'user', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'Missing {field}'}), 400
        
        # Try to connect
        import mysql.connector
        try:
            connection = mysql.connector.connect(
                host=data['host'],
                port=int(data['port']),
                database=data['database'],
                user=data['user'],
                password=data['password'],
                connection_timeout=5
            )
            
            # Test with a simple query
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            connection.close()
            
            return jsonify({'success': True, 'message': 'Connection successful'})
            
        except mysql.connector.Error as e:
            error_msg = str(e)
            # Simplify error messages for common issues
            if 'Access denied' in error_msg:
                error_msg = 'Access denied - check username and password'
            elif 'Unknown database' in error_msg:
                error_msg = f"Database '{data['database']}' does not exist"
            elif "Can't connect" in error_msg:
                error_msg = f"Cannot connect to server at {data['host']}:{data['port']}"
            
            return jsonify({'success': False, 'error': error_msg})
            
    except Exception as e:
        logger.error(f"Error testing database connection: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Invalid request'}), 400

# Route for testing email configuration
@app.route('/setup/test-email', methods=['POST'])
def test_email_config():
    """Test email configuration by sending a test email."""
    try:
        data = request.get_json()
        
        # Validate input
        required_fields = ['provider', 'api_key', 'from_email', 'test_email']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'Missing {field}'}), 400
        
        provider = data['provider']
        api_key = data['api_key']
        from_email = data['from_email']
        from_name = data.get('from_name', 'XSpace Downloader')
        test_email = data['test_email']
        
        # Send test email based on provider
        try:
            if provider == 'sendgrid':
                import sendgrid
                from sendgrid.helpers.mail import Mail
                
                sg = sendgrid.SendGridAPIClient(api_key=api_key)
                message = Mail(
                    from_email=(from_email, from_name),
                    to_emails=test_email,
                    subject='Test Email from XSpace Downloader Setup',
                    html_content='<h3>Test Email Successful!</h3><p>Your SendGrid email configuration is working correctly.</p><p>You can now send emails from XSpace Downloader.</p>'
                )
                response = sg.send(message)
                
                if response.status_code in [200, 201, 202]:
                    return jsonify({'success': True, 'message': 'Test email sent successfully'})
                else:
                    return jsonify({'success': False, 'error': f'SendGrid returned status {response.status_code}'})
                    
            elif provider == 'mailgun':
                import requests
                
                mailgun_domain = data.get('mailgun_domain', '')
                if not mailgun_domain:
                    # Extract domain from from_email
                    parts = from_email.split('@')
                    if len(parts) == 2:
                        mailgun_domain = parts[1]
                
                response = requests.post(
                    f"https://api.mailgun.net/v3/{mailgun_domain}/messages",
                    auth=("api", api_key),
                    data={
                        "from": f"{from_name} <{from_email}>",
                        "to": test_email,
                        "subject": "Test Email from XSpace Downloader Setup",
                        "html": "<h3>Test Email Successful!</h3><p>Your Mailgun email configuration is working correctly.</p><p>You can now send emails from XSpace Downloader.</p>"
                    }
                )
                
                if response.status_code == 200:
                    return jsonify({'success': True, 'message': 'Test email sent successfully'})
                else:
                    error_data = response.json() if response.text else {}
                    return jsonify({'success': False, 'error': error_data.get('message', f'Mailgun returned status {response.status_code}')})
                    
            else:
                return jsonify({'success': False, 'error': f'Unsupported provider: {provider}'})
                
        except Exception as e:
            error_msg = str(e)
            # Simplify error messages
            if 'unauthorized' in error_msg.lower() or '401' in error_msg:
                error_msg = 'Invalid API key'
            elif 'not found' in error_msg.lower() or '404' in error_msg:
                error_msg = 'Invalid configuration (check domain/settings)'
            
            return jsonify({'success': False, 'error': error_msg})
            
    except Exception as e:
        logger.error(f"Error testing email config: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Invalid request'}), 400

# Route for testing OpenAI API
@app.route('/setup/test-openai', methods=['POST'])
def test_openai_api():
    """Test OpenAI API key."""
    try:
        data = request.get_json()
        api_key = data.get('api_key', '').strip()
        
        if not api_key:
            return jsonify({'success': False, 'error': 'API key is required'}), 400
        
        try:
            import openai
            
            # Try both old and new API styles
            try:
                # New style (openai >= 1.0)
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                response = client.models.list()
                model_count = len(list(response.data))
                return jsonify({
                    'success': True, 
                    'message': f'API key is valid! Found {model_count} available models.'
                })
            except:
                # Old style (openai < 1.0)
                openai.api_key = api_key
                response = openai.Model.list()
                model_count = len(response.data) if hasattr(response, 'data') else 0
                return jsonify({
                    'success': True, 
                    'message': f'API key is valid! Found {model_count} available models.'
                })
            
        except Exception as e:
            error_msg = str(e)
            if 'invalid' in error_msg.lower() or 'incorrect' in error_msg.lower() or 'authentication' in error_msg.lower():
                return jsonify({'success': False, 'error': 'Invalid API key'})
            elif 'rate' in error_msg.lower():
                return jsonify({'success': False, 'error': 'Rate limit reached (but key is valid)'})
            return jsonify({'success': False, 'error': f'API error: {error_msg}'})
            
    except Exception as e:
        logger.error(f"Error testing OpenAI API: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Invalid request'}), 400

# Route for testing Anthropic API
@app.route('/setup/test-anthropic', methods=['POST'])
def test_anthropic_api():
    """Test Anthropic API key."""
    try:
        data = request.get_json()
        api_key = data.get('api_key', '').strip()
        
        if not api_key:
            return jsonify({'success': False, 'error': 'API key is required'}), 400
        
        try:
            import anthropic
            
            # Try both old and new API styles
            try:
                # New style (anthropic >= 0.7)
                client = anthropic.Anthropic(api_key=api_key)
                
                # Try a simple API call to test the key
                response = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=1,
                    messages=[{"role": "user", "content": "Hi"}]
                )
                
                return jsonify({
                    'success': True, 
                    'message': 'API key is valid! Claude is ready to use.'
                })
            except:
                # Old style
                client = anthropic.Client(api_key=api_key)
                response = client.completions.create(
                    model="claude-instant-1.2",
                    prompt=f"{anthropic.HUMAN_PROMPT} Hi{anthropic.AI_PROMPT}",
                    max_tokens_to_sample=1
                )
                
                return jsonify({
                    'success': True, 
                    'message': 'API key is valid! Claude is ready to use.'
                })
            
        except Exception as e:
            error_msg = str(e)
            if 'invalid' in error_msg.lower() or 'unauthorized' in error_msg.lower() or 'authentication' in error_msg.lower():
                return jsonify({'success': False, 'error': 'Invalid API key'})
            elif 'rate' in error_msg.lower():
                return jsonify({'success': False, 'error': 'Rate limit reached (but key is valid)'})
            elif 'not found' in error_msg.lower():
                return jsonify({'success': False, 'error': 'API key format is incorrect'})
            return jsonify({'success': False, 'error': f'API error: {error_msg}'})
            
    except Exception as e:
        logger.error(f"Error testing Anthropic API: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Invalid request'}), 400

# Admin dashboard route
@app.route('/admin')
def admin_dashboard():
    """Admin dashboard for managing users, spaces, and viewing stats."""
    try:
        # Check if user is logged in and is admin
        if not session.get('user_id') or not session.get('is_admin'):
            flash('Admin access required.', 'error')
            return redirect(url_for('index'))
        
        # Get database connection
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        # Get basic stats
        # Total users
        cursor.execute("SELECT COUNT(*) as total FROM users")
        total_users = cursor.fetchone()['total']
        
        # Total spaces
        cursor.execute("SELECT COUNT(*) as total FROM spaces")
        total_spaces = cursor.fetchone()['total']
        
        # Total downloads
        cursor.execute("SELECT SUM(download_cnt) as total FROM spaces")
        total_downloads = cursor.fetchone()['total'] or 0
        
        # Total plays
        cursor.execute("SELECT SUM(playback_cnt) as total FROM spaces")
        total_plays = cursor.fetchone()['total'] or 0
        
        cursor.close()
        
        # Check if running on localhost for development tools
        is_localhost = request.host.startswith('localhost') or request.host.startswith('127.0.0.1')
        
        return render_template('admin.html',
                             total_users=total_users,
                             total_spaces=total_spaces,
                             total_downloads=total_downloads,
                             total_plays=total_plays,
                             rate_limits=rate_limit_config,
                             is_localhost=is_localhost)
        
    except Exception as e:
        logger.error(f"Error in admin dashboard: {e}", exc_info=True)
        flash('An error occurred loading the admin dashboard.', 'error')
        return redirect(url_for('index'))

# Admin API routes for AJAX operations
@app.route('/admin/api/users')
def admin_get_users():
    """Get paginated list of users for admin."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '')
        
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        # Build query
        query = """
            SELECT id, email, status, is_admin, country, login_count, 
                   last_logged_in, created_at,
                   (SELECT COUNT(*) FROM spaces WHERE user_id = users.id) as space_count
            FROM users
        """
        
        if search:
            query += " WHERE email LIKE %s"
            search_param = f"%{search}%"
        
        # Get total count
        count_query = "SELECT COUNT(*) as total FROM users"
        if search:
            count_query += " WHERE email LIKE %s"
            cursor.execute(count_query, (search_param,) if search else ())
        else:
            cursor.execute(count_query)
        
        total = cursor.fetchone()['total']
        
        # Get paginated results
        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        offset = (page - 1) * per_page
        
        if search:
            cursor.execute(query, (search_param, per_page, offset))
        else:
            cursor.execute(query, (per_page, offset))
        
        users = cursor.fetchall()
        cursor.close()
        
        # Convert datetime objects to strings
        for user in users:
            for field in ['created_at', 'last_logged_in']:
                if user.get(field):
                    user[field] = user[field].isoformat()
        
        return jsonify({
            'users': users,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page
        })
        
    except Exception as e:
        logger.error(f"Error getting users: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/users/<int:user_id>', methods=['PUT'])
def admin_update_user(user_id):
    """Update user details."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        # Check if we're trying to remove admin flag or suspend
        if ('is_admin' in data and not data['is_admin']) or ('status' in data and data['status'] != 1):
            # Check if this is the last admin
            cursor.execute("SELECT COUNT(*) as admin_count FROM users WHERE is_admin = 1 AND id != %s", (user_id,))
            admin_count = cursor.fetchone()['admin_count']
            
            if admin_count == 0:
                # This is the last admin
                cursor.execute("SELECT is_admin FROM users WHERE id = %s", (user_id,))
                user = cursor.fetchone()
                if user and user['is_admin']:
                    cursor.close()
                    return jsonify({'error': 'Cannot remove admin privileges or suspend the last admin user'}), 400
        
        # Build update query
        updates = []
        params = []
        
        if 'status' in data:
            updates.append("status = %s")
            params.append(data['status'])
        
        if 'is_admin' in data:
            updates.append("is_admin = %s")
            params.append(1 if data['is_admin'] else 0)
        
        if updates:
            query = f"UPDATE users SET {', '.join(updates)} WHERE id = %s"
            params.append(user_id)
            cursor.execute(query, params)
            space.connection.commit()
        
        cursor.close()
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error updating user: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/users/<int:user_id>', methods=['DELETE'])
def admin_delete_user(user_id):
    """Delete a user."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        # Prevent deleting self
        if user_id == session.get('user_id'):
            return jsonify({'error': 'Cannot delete your own account'}), 400
        
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        # Check if this is an admin user
        cursor.execute("SELECT is_admin FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if user and user['is_admin']:
            # Check if this is the last admin
            cursor.execute("SELECT COUNT(*) as admin_count FROM users WHERE is_admin = 1 AND id != %s", (user_id,))
            admin_count = cursor.fetchone()['admin_count']
            
            if admin_count == 0:
                cursor.close()
                return jsonify({'error': 'Cannot delete the last admin user'}), 400
        
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        space.connection.commit()
        cursor.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error deleting user: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/spaces')
def admin_get_spaces():
    """Get paginated list of spaces for admin."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '')
        
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        # Build query - get only the latest entry per space_id to avoid duplicates
        query = """
            SELECT s.*, s.title, sm.host_handle, sm.host,
                   u.email as user_email
            FROM spaces s
            INNER JOIN (
                SELECT space_id, MAX(id) as max_id 
                FROM spaces 
                GROUP BY space_id
            ) latest ON s.id = latest.max_id
            LEFT JOIN space_metadata sm ON s.space_id = sm.space_id
            LEFT JOIN users u ON s.user_id = u.id
        """
        
        if search:
            query += " WHERE s.space_id LIKE %s OR s.title LIKE %s OR sm.host_handle LIKE %s"
            search_param = f"%{search}%"
        
        # Get total count
        count_query = "SELECT COUNT(*) as total FROM spaces s LEFT JOIN space_metadata sm ON s.space_id = sm.space_id"
        if search:
            count_query += " WHERE s.space_id LIKE %s OR s.title LIKE %s OR sm.host_handle LIKE %s"
            cursor.execute(count_query, (search_param, search_param, search_param))
        else:
            cursor.execute(count_query)
        
        total = cursor.fetchone()['total']
        
        # Get paginated results
        query += " ORDER BY s.created_at DESC LIMIT %s OFFSET %s"
        offset = (page - 1) * per_page
        
        if search:
            cursor.execute(query, (search_param, search_param, search_param, per_page, offset))
        else:
            cursor.execute(query, (per_page, offset))
        
        spaces = cursor.fetchall()
        cursor.close()
        
        # Convert datetime objects to strings
        for space in spaces:
            for field in ['created_at', 'downloaded_at', 'updated_at']:
                if space.get(field):
                    space[field] = space[field].isoformat()
        
        return jsonify({
            'spaces': spaces,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page
        })
        
    except Exception as e:
        logger.error(f"Error getting spaces: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/spaces/<space_id>', methods=['DELETE'])
def admin_delete_space(space_id):
    """Delete a space."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        space = get_space_component()
        
        # Delete the space (will cascade to related tables)
        result = space.delete_space(space_id)
        
        if result:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Space not found'}), 404
        
    except Exception as e:
        logger.error(f"Error deleting space: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/spaces/<space_id>/tags', methods=['POST'])
def add_tag_to_space(space_id):
    """Add a tag to a space. Only space owner or admin can add tags."""
    try:
        # Check if user can edit this space
        space = get_space_component()
        
        # Get space details for permission checking
        cursor = space.connection.cursor(dictionary=True)
        cursor.execute("SELECT user_id, cookie_id FROM spaces WHERE space_id = %s", (space_id,))
        space_details = cursor.fetchone()
        cursor.close()
        
        if not space_details:
            return jsonify({'error': 'Space not found'}), 404
        
        # Check permissions: space owner OR admin
        user_id = session.get('user_id', 0)
        cookie_id = request.cookies.get('xspace_user_id', '')
        is_admin = session.get('is_admin', False)
        
        can_edit = False
        
        if is_admin:
            can_edit = True
        elif user_id > 0:
            # Logged in user - must match user_id
            can_edit = (space_details['user_id'] == user_id)
        else:
            # Not logged in - must match cookie_id
            can_edit = (space_details['cookie_id'] == cookie_id and space_details['user_id'] == 0)
        
        if not can_edit:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Get tag name from request
        data = request.get_json() or {}
        tag_name = data.get('tag_name', '').strip()
        
        if not tag_name:
            return jsonify({'error': 'Tag name is required'}), 400
        
        # Add tag using Tag component
        from components.Tag import Tag
        tag_component = Tag(space.connection)
        
        # Create or get tag ID
        tag_id = tag_component.create_tag(tag_name)
        if not tag_id:
            return jsonify({'error': 'Failed to create tag'}), 500
        
        # Add tag to space
        added_count = tag_component.add_tags_to_space(space_id, [tag_name], user_id or 0)
        
        if added_count > 0:
            # Create slug for response
            tag_slug = tag_name.lower().replace(' ', '-').replace('_', '-')
            
            return jsonify({
                'success': True,
                'message': 'Tag added successfully',
                'tag': {
                    'id': tag_id,
                    'name': tag_name,
                    'tag_name': tag_name,
                    'tag_slug': tag_slug
                }
            })
        else:
            return jsonify({'error': 'Tag may already exist on this space'}), 400
        
    except Exception as e:
        logger.error(f"Error adding tag to space {space_id}: {e}", exc_info=True)
        return jsonify({'error': 'Failed to add tag'}), 500

@app.route('/api/spaces/<space_id>/tags/<int:tag_id>', methods=['DELETE'])
def remove_tag_from_space(space_id, tag_id):
    """Remove a tag from a space. Only space owner or admin can remove tags."""
    try:
        # Check if user can edit this space
        space = get_space_component()
        
        # Get space details for permission checking
        cursor = space.connection.cursor(dictionary=True)
        cursor.execute("SELECT user_id, cookie_id FROM spaces WHERE space_id = %s", (space_id,))
        space_details = cursor.fetchone()
        cursor.close()
        
        if not space_details:
            return jsonify({'error': 'Space not found'}), 404
        
        # Check permissions: space owner OR admin
        user_id = session.get('user_id', 0)
        cookie_id = request.cookies.get('xspace_user_id', '')
        is_admin = session.get('is_admin', False)
        
        can_edit = False
        
        if is_admin:
            can_edit = True
        elif user_id > 0:
            # Logged in user - must match user_id
            can_edit = (space_details['user_id'] == user_id)
        else:
            # Not logged in - must match cookie_id
            can_edit = (space_details['cookie_id'] == cookie_id and space_details['user_id'] == 0)
        
        if not can_edit:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Remove tag using Tag component
        from components.Tag import Tag
        tag_component = Tag(space.connection)
        
        # Since we've already verified permissions (space owner or admin),
        # we can force remove the tag regardless of who originally added it
        success = tag_component.remove_tag_from_space(space_id, tag_id, user_id or 0, force_remove=True)
        
        if success:
            logger.info(f"Successfully removed tag {tag_id} from space {space_id} by user {user_id} (admin: {is_admin})")
            return jsonify({
                'success': True,
                'message': 'Tag removed successfully'
            })
        else:
            logger.warning(f"Failed to remove tag {tag_id} from space {space_id} - tag may not exist or DB error")
            return jsonify({'error': 'Tag not found or could not be removed'}), 400
        
    except Exception as e:
        logger.error(f"Error removing tag {tag_id} from space {space_id}: {e}", exc_info=True)
        return jsonify({'error': 'Failed to remove tag'}), 500

@app.route('/api/spaces/<space_id>/generate-video', methods=['POST'])
def generate_video(space_id):
    """Generate MP4 video for a space with audio visualization."""
    try:
        # Check if user can edit this space or is admin
        space = get_space_component()
        
        # Get space details for permission checking
        cursor = space.connection.cursor(dictionary=True)
        cursor.execute("SELECT user_id, cookie_id FROM spaces WHERE space_id = %s", (space_id,))
        space_details = cursor.fetchone()
        cursor.close()
        
        if not space_details:
            return jsonify({'error': 'Space not found'}), 404
        
        # Check permissions: space owner OR admin
        user_id = session.get('user_id', 0)
        cookie_id = request.cookies.get('xspace_user_id', '')
        is_admin = session.get('is_admin', False)
        
        can_edit = False
        
        if is_admin:
            can_edit = True
        elif user_id > 0:
            # Logged in user - must match user_id
            can_edit = (space_details['user_id'] == user_id)
        else:
            # Not logged in - must match cookie_id
            can_edit = (space_details['cookie_id'] == cookie_id and space_details['user_id'] == 0)
        
        if not can_edit:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Check if audio file exists
        download_dir = app.config['DOWNLOAD_DIR']
        audio_path = None
        
        for ext in ['mp3', 'm4a', 'wav']:
            path = os.path.join(download_dir, f"{space_id}.{ext}")
            if os.path.exists(path) and os.path.getsize(path) > 1024*1024:  # > 1MB
                audio_path = path
                break
        
        if not audio_path:
            return jsonify({'error': 'Audio file not found for this space'}), 404
        
        # Get space details with metadata
        space_data = space.get_space(space_id)
        if not space_data:
            return jsonify({'error': 'Space data not found'}), 404
        
        # Generate video using background task
        from components.VideoGenerator import VideoGenerator
        video_generator = VideoGenerator()
        
        # Create video generation job
        job_id = video_generator.create_video_job(
            space_id=space_id,
            audio_path=audio_path,
            space_data=space_data,
            user_id=user_id or 0
        )
        
        if job_id:
            return jsonify({
                'success': True,
                'job_id': job_id,
                'message': 'Video generation started'
            })
        else:
            return jsonify({'error': 'Failed to start video generation'}), 500
        
    except Exception as e:
        logger.error(f"Error generating video for space {space_id}: {e}", exc_info=True)
        return jsonify({'error': 'Failed to generate video'}), 500

@app.route('/api/spaces/<space_id>/video-status/<job_id>', methods=['GET'])
def get_video_status(space_id, job_id):
    """Get video generation status."""
    try:
        from components.VideoGenerator import VideoGenerator
        video_generator = VideoGenerator()
        
        status = video_generator.get_job_status(job_id)
        if status:
            return jsonify(status)
        else:
            return jsonify({'error': 'Job not found'}), 404
            
    except Exception as e:
        logger.error(f"Error getting video status for job {job_id}: {e}", exc_info=True)
        return jsonify({'error': 'Failed to get video status'}), 500

@app.route('/api/spaces/<space_id>/download-video/<job_id>')
def download_video(space_id, job_id):
    """Download generated video file."""
    try:
        from components.VideoGenerator import VideoGenerator
        video_generator = VideoGenerator()
        
        video_path = video_generator.get_video_path(job_id)
        if video_path and os.path.exists(video_path):
            # Get space title for filename
            space = get_space_component()
            space_data = space.get_space(space_id)
            
            title = "Space"
            if space_data:
                title = space_data.get('title', space_id)
                if space_data.get('metadata', {}).get('title'):
                    title = space_data['metadata']['title']
            
            # Clean filename
            import re
            safe_title = re.sub(r'[^\w\s-]', '', title)[:50]
            filename = f"{safe_title}_{space_id}.mp4"
            
            return send_file(
                video_path,
                as_attachment=True,
                download_name=filename,
                mimetype='video/mp4'
            )
        else:
            return jsonify({'error': 'Video file not found'}), 404
            
    except Exception as e:
        logger.error(f"Error downloading video for job {job_id}: {e}", exc_info=True)
        return jsonify({'error': 'Failed to download video'}), 500

@app.route('/admin/api/spaces/<space_id>/redo-tags', methods=['POST'])
def admin_redo_tags(space_id):
    """Regenerate tags for a space using its transcript."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        # Check if space exists and has a transcript
        cursor.execute("""
            SELECT st.transcript, st.language, s.space_id, s.title
            FROM spaces s
            LEFT JOIN space_transcripts st ON CONVERT(s.space_id USING utf8mb4) COLLATE utf8mb4_unicode_ci = st.space_id
            WHERE s.space_id = %s
        """, (space_id,))
        
        space_data = cursor.fetchone()
        cursor.close()
        
        if not space_data:
            return jsonify({'error': 'Space not found'}), 404
        
        if not space_data['transcript']:
            return jsonify({'error': 'No transcript available for this space'}), 400
        
        # Import the tag generation function
        from background_transcribe import generate_and_save_tags_with_ai
        from components.Tag import Tag
        
        # Remove existing tags for this space
        cursor = space.connection.cursor()
        cursor.execute("DELETE FROM space_tags WHERE space_id = %s", (space_id,))
        space.connection.commit()
        cursor.close()
        
        logger.info(f"Admin {session.get('user_id')} requested tag regeneration for space {space_id}")
        
        # Generate new tags using AI or keyword extraction
        generate_and_save_tags_with_ai(space_id, space_data['transcript'])
        
        # Get the newly generated tags to return to admin
        tag_component = Tag()
        new_tags = tag_component.get_space_tags(space_id)
        tag_names = [tag.get('name', tag.get('tag_name', 'Unknown')) for tag in new_tags]
        
        return jsonify({
            'success': True,
            'message': f'Successfully regenerated {len(new_tags)} tags',
            'tags': tag_names,
            'space_title': space_data['title'] or f'Space {space_id}'
        })
        
    except Exception as e:
        logger.error(f"Error regenerating tags for space {space_id}: {e}", exc_info=True)
        return jsonify({'error': f'Error regenerating tags: {str(e)}'}), 500

@app.route('/admin/api/spaces/<space_id>/re-transcribe', methods=['POST'])
def admin_re_transcribe(space_id):
    """Re-transcribe a space with specified model."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json() or {}
        model = data.get('model', 'base')
        overwrite = data.get('overwrite', True)
        
        # Validate model
        valid_models = ['tiny', 'base', 'small', 'medium', 'large']
        if model not in valid_models:
            return jsonify({'error': f'Invalid model. Must be one of: {", ".join(valid_models)}'}), 400
        
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        # Check if space exists and has audio file
        cursor.execute("""
            SELECT space_id, filename, format, status
            FROM spaces 
            WHERE space_id = %s
        """, (space_id,))
        
        space_data = cursor.fetchone()
        cursor.close()
        
        if not space_data:
            return jsonify({'error': 'Space not found'}), 404
        
        if not space_data['filename']:
            return jsonify({'error': 'No audio file available for this space'}), 400
        
        if space_data['status'] != 'completed':
            return jsonify({'error': f'Space download not completed (status: {space_data["status"]})'}), 400
        
        # Check if audio file exists
        import os
        audio_path = os.path.join('downloads', space_data['filename'])
        if not os.path.exists(audio_path):
            return jsonify({'error': 'Audio file not found on disk'}), 400
        
        # Create transcription job
        import uuid
        import json
        from datetime import datetime
        
        job_id = str(uuid.uuid4())
        job_data = {
            'job_id': job_id,
            'space_id': space_id,
            'audio_file': audio_path,
            'language': 'en',
            'model': model,
            'overwrite': overwrite,
            'created_at': datetime.now().isoformat(),
            'status': 'pending',
            'admin_requested': True
        }
        
        # Save job file
        os.makedirs('transcript_jobs', exist_ok=True)
        job_file = f'transcript_jobs/{job_id}.json'
        with open(job_file, 'w') as f:
            json.dump(job_data, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': f'Re-transcription job queued with {model} model',
            'job_id': job_id
        })
        
    except Exception as e:
        logger.error(f"Error creating re-transcription job for space {space_id}: {e}", exc_info=True)
        return jsonify({'error': f'Error creating transcription job: {str(e)}'}), 500

@app.route('/admin/api/transcription_config', methods=['GET', 'POST'])
def admin_transcription_config():
    """Get or update transcription configuration."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    config_file = 'transcription_config.json'
    
    if request.method == 'GET':
        # Load existing configuration
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    config = json.load(f)
            else:
                # Default configuration
                config = {
                    'provider': 'local',
                    'default_model': 'tiny',
                    'device': 'auto',
                    'openai_model': 'gpt-4o-mini-transcribe',
                    'enable_corrective_filter': False,
                    'correction_model': 'gpt-4o-mini'
                }
            
            # Check for OpenAI API key in environment variables
            env_openai_key = os.environ.get('OPENAI_API_KEY')
            has_env_key = bool(env_openai_key)
            
            # Don't send the actual API key for security, but indicate availability
            display_config = config.copy()
            if has_env_key:
                display_config['openai_api_key'] = '***from_env***'
                display_config['openai_key_source'] = 'environment'
            elif 'openai_api_key' in display_config and display_config['openai_api_key']:
                display_config['openai_api_key'] = '***hidden***'
                display_config['openai_key_source'] = 'config'
            else:
                display_config['openai_key_source'] = 'none'
            
            return jsonify({
                'success': True,
                'config': display_config
            })
            
        except Exception as e:
            logger.error(f"Error loading transcription config: {e}")
            return jsonify({'error': 'Failed to load configuration'}), 500
    
    elif request.method == 'POST':
        # Update configuration
        try:
            data = request.get_json()
            
            # Validate provider
            provider = data.get('provider', 'local')
            if provider not in ['local', 'openai']:
                return jsonify({'error': 'Invalid provider. Must be "local" or "openai"'}), 400
            
            # Build new configuration
            new_config = {
                'provider': provider,
                'default_model': data.get('default_model', 'tiny'),
                'device': data.get('device', 'auto'),
                'openai_model': data.get('openai_model', 'gpt-4o-mini-transcribe'),
                'enable_corrective_filter': data.get('enable_corrective_filter', False),
                'correction_model': data.get('correction_model', 'gpt-4o-mini')
            }
            
            # Handle OpenAI API key
            openai_api_key = data.get('openai_api_key', '').strip()
            env_openai_key = os.environ.get('OPENAI_API_KEY')
            
            if openai_api_key and openai_api_key not in ['***hidden***', '***from_env***']:
                # New API key provided - save to .env file
                try:
                    from load_env import save_env_var
                    save_env_var('OPENAI_API_KEY', openai_api_key)
                    logger.info("OpenAI API key saved to .env file")
                except Exception as e:
                    logger.error(f"Error saving API key to .env: {e}")
                    # Fallback to config file
                    new_config['openai_api_key'] = openai_api_key
            elif openai_api_key in ['***hidden***', '***from_env***']:
                # Keep existing key (either from env or config)
                if env_openai_key:
                    # Environment key exists, don't store in config
                    pass
                elif os.path.exists(config_file):
                    # Preserve existing API key from config if not in env
                    try:
                        with open(config_file, 'r') as f:
                            existing_config = json.load(f)
                            if 'openai_api_key' in existing_config:
                                new_config['openai_api_key'] = existing_config['openai_api_key']
                    except:
                        pass
            
            # Validate OpenAI settings if provider is OpenAI
            if provider == 'openai':
                has_api_key = env_openai_key or new_config.get('openai_api_key')
                if not has_api_key:
                    return jsonify({'error': 'OpenAI API key is required when using OpenAI provider. Please provide an API key or set OPENAI_API_KEY in environment variables.'}), 400
            
            # Save configuration
            with open(config_file, 'w') as f:
                json.dump(new_config, f, indent=2)
            
            return jsonify({
                'success': True,
                'message': 'Transcription configuration updated successfully'
            })
            
        except Exception as e:
            logger.error(f"Error updating transcription config: {e}")
            return jsonify({'error': 'Failed to update configuration'}), 500

@app.route('/admin/api/update_rate_limits', methods=['POST'])
def admin_update_rate_limits():
    """Update rate limit configuration."""
    try:
        # Check if user is logged in and is admin
        if not session.get('user_id') or not session.get('is_admin'):
            return jsonify({'success': False, 'error': 'Admin access required'}), 403
        
        data = request.get_json()
        
        # Validate inputs
        daily_limit = int(data.get('daily_limit', 200))
        hourly_limit = int(data.get('hourly_limit', 50))
        enabled = bool(data.get('enabled', True))
        
        # Load current config
        with open('mainconfig.json', 'r') as f:
            config = json.load(f)
        
        # Update rate limits
        config['rate_limits'] = {
            'daily_limit': daily_limit,
            'hourly_limit': hourly_limit,
            'enabled': enabled,
            'comment': 'Rate limiting configuration for download requests. Set enabled to false to disable rate limiting.'
        }
        
        # Save config
        with open('mainconfig.json', 'w') as f:
            json.dump(config, f, indent=4)
        
        # Update global rate limit config
        global rate_limit_config
        rate_limit_config = config['rate_limits']
        
        # Note: Rate limiter will use new values on app restart
        # For immediate effect, app needs to be restarted
        
        return jsonify({
            'success': True, 
            'message': 'Rate limits updated successfully. Restart app for changes to take effect.',
            'rate_limits': rate_limit_config
        })
        
    except Exception as e:
        logger.error(f"Error updating rate limits: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/tracking_config')
def admin_get_tracking_config():
    """Get tracking configuration settings."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        # Get all tracking config values
        query = "SELECT config_key, config_value FROM system_config WHERE config_key IN (%s, %s, %s, %s, %s, %s)"
        cursor.execute(query, (
            'play_cooldown_minutes',
            'play_minimum_duration_seconds',
            'download_daily_limit',
            'download_hourly_ip_limit',
            'play_tracking_enabled',
            'download_tracking_enabled'
        ))
        
        config = {}
        for row in cursor.fetchall():
            config[row['config_key']] = row['config_value']
        
        cursor.close()
        
        return jsonify({
            'success': True,
            'config': config
        })
        
    except Exception as e:
        logger.error(f"Error getting tracking config: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/update_tracking_config', methods=['POST'])
def admin_update_tracking_config():
    """Update tracking configuration settings."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.json
        space = get_space_component()
        cursor = space.connection.cursor()
        
        # Update each config value
        config_updates = [
            ('play_cooldown_minutes', data.get('play_cooldown_minutes', '30')),
            ('play_minimum_duration_seconds', data.get('play_minimum_duration_seconds', '30')),
            ('download_daily_limit', data.get('download_daily_limit', '1')),
            ('download_hourly_ip_limit', data.get('download_hourly_ip_limit', '10')),
            ('play_tracking_enabled', data.get('play_tracking_enabled', 'true')),
            ('download_tracking_enabled', data.get('download_tracking_enabled', 'true'))
        ]
        
        for key, value in config_updates:
            query = """
            UPDATE system_config 
            SET config_value = %s, updated_at = NOW() 
            WHERE config_key = %s
            """
            cursor.execute(query, (str(value), key))
        
        space.connection.commit()
        cursor.close()
        
        return jsonify({
            'success': True,
            'message': 'Tracking configuration updated successfully'
        })
        
    except Exception as e:
        logger.error(f"Error updating tracking config: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/stats/<stat_type>')
def admin_get_stats(stat_type):
    """Get various statistics for admin dashboard."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        period = request.args.get('period', 'all')  # daily, weekly, monthly, all
        
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        # Build date condition based on period
        date_condition = ""
        if period == 'daily':
            date_condition = "WHERE DATE(created_at) = CURDATE()"
        elif period == 'weekly':
            date_condition = "WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"
        elif period == 'monthly':
            date_condition = "WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)"
        
        if stat_type == 'submissions':
            # Space submissions over time
            if period == 'all':
                query = """
                    SELECT DATE(created_at) as date, COUNT(*) as count
                    FROM spaces
                    WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                    GROUP BY DATE(created_at)
                    ORDER BY date
                """
            else:
                query = f"""
                    SELECT DATE(created_at) as date, COUNT(*) as count
                    FROM spaces
                    {date_condition}
                    GROUP BY DATE(created_at)
                    ORDER BY date
                """
            
            cursor.execute(query)
            data = cursor.fetchall()
            
        elif stat_type == 'plays':
            # Most played spaces
            query = f"""
                SELECT s.space_id, s.playback_cnt, s.download_cnt,
                       s.title, sm.host
                FROM spaces s
                LEFT JOIN space_metadata sm ON s.space_id = sm.space_id
                {date_condition}
                ORDER BY s.playback_cnt DESC
                LIMIT 20
            """
            cursor.execute(query)
            data = cursor.fetchall()
            
        elif stat_type == 'downloads':
            # Most downloaded spaces
            query = f"""
                SELECT s.space_id, s.download_cnt, s.playback_cnt,
                       s.title, sm.host
                FROM spaces s
                LEFT JOIN space_metadata sm ON s.space_id = sm.space_id
                {date_condition}
                ORDER BY s.download_cnt DESC
                LIMIT 20
            """
            cursor.execute(query)
            data = cursor.fetchall()
            
        elif stat_type == 'active_users':
            # Most active users
            if period == 'all':
                # By total login count
                query = """
                    SELECT u.id, u.email, u.login_count, u.country,
                           COUNT(DISTINCT s.id) as space_count,
                           SUM(s.download_cnt) as total_downloads,
                           SUM(s.playback_cnt) as total_plays
                    FROM users u
                    LEFT JOIN spaces s ON u.id = s.user_id
                    GROUP BY u.id
                    ORDER BY u.login_count DESC
                    LIMIT 20
                """
            else:
                # By recent activity
                query = f"""
                    SELECT u.id, u.email, u.login_count, u.country,
                           COUNT(DISTINCT s.id) as space_count,
                           COUNT(DISTINCT CASE WHEN s.created_at >= DATE_SUB(CURDATE(), INTERVAL 
                               {1 if period == 'daily' else 7 if period == 'weekly' else 30} DAY) 
                               THEN s.id END) as recent_spaces
                    FROM users u
                    LEFT JOIN spaces s ON u.id = s.user_id
                    WHERE u.last_logged_in >= DATE_SUB(CURDATE(), INTERVAL 
                        {1 if period == 'daily' else 7 if period == 'weekly' else 30} DAY)
                    GROUP BY u.id
                    ORDER BY recent_spaces DESC
                    LIMIT 20
                """
            cursor.execute(query)
            data = cursor.fetchall()
            
        else:
            return jsonify({'error': 'Invalid stat type'}), 400
        
        cursor.close()
        
        # Convert datetime objects to strings
        for item in data:
            if 'date' in item and item['date']:
                item['date'] = item['date'].isoformat()
        
        return jsonify({
            'data': data,
            'period': period,
            'type': stat_type
        })
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/logs')
def admin_get_logs():
    """Get system logs for admin dashboard."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        offset = int(request.args.get('offset', 0))
        limit = int(request.args.get('limit', 100))
        
        # Read logs from the logs directory
        logs_dir = Path('./logs')
        log_files = []
        
        # Find all log files, prioritizing the main app log
        if logs_dir.exists():
            for log_file in logs_dir.glob('*.log'):
                if log_file.name in ['app.log', 'xspacedownloader.log']:
                    log_files.insert(0, log_file)  # Main logs first
                else:
                    log_files.append(log_file)
        
        # If no logs directory, try reading from root directory
        if not log_files:
            for pattern in ['*.log', 'app.log', 'xspacedownloader.log']:
                for log_file in Path('.').glob(pattern):
                    log_files.append(log_file)
        
        all_log_entries = []
        
        # Read logs from all files
        for log_file in log_files:
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    # Get recent lines (last 1000 to avoid memory issues)
                    recent_lines = lines[-1000:] if len(lines) > 1000 else lines
                    
                    for line in recent_lines:
                        line = line.strip()
                        if line:  # Skip empty lines
                            all_log_entries.append({
                                'message': line,
                                'source': log_file.name,
                                'timestamp': None  # We'll parse this if needed
                            })
            except Exception as e:
                logger.warning(f"Error reading log file {log_file}: {e}")
                continue
        
        # Sort by most recent (assuming logs are chronological)
        all_log_entries.reverse()
        
        # Apply offset and limit
        start_idx = offset
        end_idx = offset + limit
        logs_slice = all_log_entries[start_idx:end_idx]
        
        return jsonify({
            'success': True,
            'logs': logs_slice,
            'total': len(all_log_entries),
            'offset': offset,
            'next_offset': end_idx if end_idx < len(all_log_entries) else None,
            'has_more': end_idx < len(all_log_entries)
        })
        
    except Exception as e:
        logger.error(f"Error getting logs: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/system_stats')
def admin_get_system_stats():
    """Get system resource usage statistics."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        import psutil
        import shutil
        from datetime import datetime
        
        # CPU Usage
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()
        
        # Memory Usage
        memory = psutil.virtual_memory()
        memory_used_gb = memory.used / (1024**3)
        memory_total_gb = memory.total / (1024**3)
        
        # Disk Usage (for current directory)
        disk_usage = shutil.disk_usage('.')
        disk_total_gb = disk_usage.total / (1024**3)
        disk_used_gb = (disk_usage.total - disk_usage.free) / (1024**3)
        disk_percent = (disk_used_gb / disk_total_gb) * 100
        
        # GPU Usage (try to get GPU info - NVIDIA, Apple Silicon, etc.)
        gpu_info = None
        gpu_utilization = 0
        gpu_memory_percent = 0
        gpu_memory_used_gb = 0
        gpu_memory_total_gb = 0
        gpu_name = "Unknown GPU"
        
        # Try NVIDIA GPU first
        try:
            import pynvml
            pynvml.nvmlInit()
            device_count = pynvml.nvmlDeviceGetCount()
            
            if device_count > 0:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)  # First GPU
                gpu_info = {
                    'name': pynvml.nvmlDeviceGetName(handle).decode('utf-8'),
                    'memory_info': pynvml.nvmlDeviceGetMemoryInfo(handle),
                    'utilization': pynvml.nvmlDeviceGetUtilizationRates(handle),
                    'temperature': pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                }
                
                gpu_memory_used_gb = gpu_info['memory_info'].used / (1024**3)
                gpu_memory_total_gb = gpu_info['memory_info'].total / (1024**3)
                gpu_memory_percent = (gpu_memory_used_gb / gpu_memory_total_gb) * 100
                gpu_utilization = gpu_info['utilization'].gpu
                gpu_name = gpu_info['name']
                
        except (ImportError, Exception) as e:
            if "ImportError" not in str(type(e)):
                logger.warning(f"Error getting NVIDIA GPU info: {e}")
        
        # If no NVIDIA GPU found, try Apple Silicon or other methods
        if not gpu_info:
            try:
                import subprocess
                import platform
                
                if platform.system() == 'Darwin':  # macOS
                    # Try to get Apple Silicon GPU info
                    try:
                        result = subprocess.run(['system_profiler', 'SPDisplaysDataType'], 
                                              capture_output=True, text=True, timeout=10)
                        if result.returncode == 0:
                            output = result.stdout
                            
                            # Parse Apple GPU info
                            if 'Apple M' in output and 'Total Number of Cores:' in output:
                                lines = output.split('\n')
                                apple_gpu_name = None
                                gpu_cores = None
                                
                                for i, line in enumerate(lines):
                                    if 'Apple M' in line and ':' in line:
                                        apple_gpu_name = line.split(':')[0].strip()
                                    elif 'Total Number of Cores:' in line:
                                        cores_str = line.split(':')[1].strip()
                                        gpu_cores = int(cores_str)
                                
                                if apple_gpu_name and gpu_cores:
                                    # Extract just the chip name (e.g., "Apple M2 Ultra" -> "M2 Ultra")
                                    chip_name = apple_gpu_name.replace("Apple ", "")
                                    gpu_name = f"{chip_name} ({gpu_cores}c)"
                                    
                                    # For Apple Silicon, we can't get real-time utilization easily
                                    # But we can show it as detected
                                    gpu_info = {'apple_silicon': True}
                                    
                                    # Try to get memory info from activity monitor if available
                                    try:
                                        # Get total system memory as proxy for GPU memory (unified memory)
                                        total_memory_gb = memory_total_gb
                                        gpu_memory_total_gb = total_memory_gb  # Unified memory
                                        gpu_memory_used_gb = memory_used_gb * 0.1  # Rough estimate
                                        gpu_memory_percent = (gpu_memory_used_gb / gpu_memory_total_gb) * 100
                                        gpu_utilization = min(cpu_percent * 0.3, 100)  # Rough estimate based on CPU
                                    except:
                                        pass
                                        
                    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, Exception) as e:
                        logger.warning(f"Error getting Apple GPU info: {e}")
                        
            except Exception as e:
                logger.warning(f"Error getting system GPU info: {e}")
        
        # Prepare response
        stats = {
            'cpu': {
                'usage_percent': round(cpu_percent, 1),
                'cores': cpu_count,
                'frequency': round(cpu_freq.current, 0) if cpu_freq else None,
                'details': f"{cpu_count} cores @ {round(cpu_freq.current, 0)} MHz" if cpu_freq else f"{cpu_count} cores"
            },
            'memory': {
                'usage_percent': round(memory.percent, 1),
                'used_gb': round(memory_used_gb, 1),
                'total_gb': round(memory_total_gb, 1),
                'details': f"{round(memory_used_gb, 1)} GB / {round(memory_total_gb, 1)} GB"
            },
            'disk': {
                'usage_percent': round(disk_percent, 1),
                'used_gb': round(disk_used_gb, 1),
                'total_gb': round(disk_total_gb, 1),
                'details': f"{round(disk_used_gb, 1)} GB / {round(disk_total_gb, 1)} GB"
            }
        }
        
        if gpu_info:
            if gpu_info.get('apple_silicon'):
                # Apple Silicon GPU
                stats['gpu'] = {
                    'usage_percent': round(gpu_utilization, 1),
                    'memory_percent': round(gpu_memory_percent, 1),
                    'memory_used_gb': round(gpu_memory_used_gb, 1),
                    'memory_total_gb': round(gpu_memory_total_gb, 1),
                    'name': gpu_name,
                    'available': True,
                    'details': f"{gpu_name} - Unified"
                }
            else:
                # NVIDIA GPU
                stats['gpu'] = {
                    'usage_percent': gpu_utilization,
                    'memory_percent': round(gpu_memory_percent, 1),
                    'memory_used_gb': round(gpu_memory_used_gb, 1),
                    'memory_total_gb': round(gpu_memory_total_gb, 1),
                    'temperature': gpu_info['temperature'],
                    'name': gpu_info['name'],
                    'available': True,
                    'details': f"{gpu_info['name']} - {round(gpu_memory_used_gb, 1)} GB / {round(gpu_memory_total_gb, 1)} GB - {gpu_info['temperature']}°C"
                }
        else:
            stats['gpu'] = {
                'usage_percent': 0,
                'memory_percent': 0,
                'available': False,
                'details': "No GPU detected"
            }
        
        return jsonify({
            'success': True,
            'stats': stats,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting system stats: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/dev/clear_spaces_data', methods=['POST'])
def admin_dev_clear_spaces_data():
    """Development tool: Clear all spaces data and files (localhost only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Check if running on localhost
    if not (request.host.startswith('localhost') or request.host.startswith('127.0.0.1')):
        return jsonify({'error': 'Development tools only available on localhost'}), 403
    
    try:
        data = request.get_json()
        if data.get('confirm') != 'DELETE ALL SPACES':
            return jsonify({'error': 'Invalid confirmation'}), 400
        
        import glob
        import os
        from pathlib import Path
        
        space = get_space_component()
        cursor = space.connection.cursor()
        
        # List of all space-related tables to clear
        tables_to_clear = [
            'space_transcripts',
            'space_tags', 
            'space_reviews',
            'space_play_history',
            'space_notes',
            'space_metadata',
            'space_favs',
            'space_download_scheduler',
            'space_download_history',
            'space_clips',
            'spaces'  # This should be last due to foreign key constraints
        ]
        
        # Clear database tables
        tables_cleared = []
        for table in tables_to_clear:
            try:
                cursor.execute(f"DELETE FROM {table}")
                rows_affected = cursor.rowcount
                tables_cleared.append(f"{table} ({rows_affected} rows)")
                logger.info(f"[DEV] Cleared table {table}: {rows_affected} rows")
            except Exception as e:
                logger.warning(f"[DEV] Error clearing table {table}: {e}")
        
        space.connection.commit()
        
        # Clear audio files
        files_deleted = []
        downloads_dir = Path('./downloads')
        if downloads_dir.exists():
            for pattern in ['*.mp3', '*.m4a', '*.wav']:
                for file_path in downloads_dir.glob(pattern):
                    try:
                        file_path.unlink()
                        files_deleted.append(file_path.name)
                    except Exception as e:
                        logger.warning(f"[DEV] Error deleting file {file_path}: {e}")
        
        # Clear transcript job files
        transcript_jobs_dir = Path('./transcript_jobs')
        if transcript_jobs_dir.exists():
            for file_path in transcript_jobs_dir.glob('*.json'):
                try:
                    file_path.unlink()
                    files_deleted.append(f"transcript_jobs/{file_path.name}")
                except Exception as e:
                    logger.warning(f"[DEV] Error deleting transcript job {file_path}: {e}")
        
        cursor.close()
        
        message = f"Successfully cleared {len(tables_cleared)} database tables and {len(files_deleted)} files"
        logger.info(f"[DEV] {message}")
        
        return jsonify({
            'success': True,
            'message': message,
            'tables_cleared': tables_cleared,
            'files_deleted': len(files_deleted)
        })
        
    except Exception as e:
        logger.error(f"[DEV] Error clearing spaces data: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/dev/clear_non_admin_users', methods=['POST'])
def admin_dev_clear_non_admin_users():
    """Development tool: Clear all non-admin users (localhost only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Check if running on localhost
    if not (request.host.startswith('localhost') or request.host.startswith('127.0.0.1')):
        return jsonify({'error': 'Development tools only available on localhost'}), 403
    
    try:
        data = request.get_json()
        if data.get('confirm') != 'DELETE NON ADMIN USERS':
            return jsonify({'error': 'Invalid confirmation'}), 400
        
        space = get_space_component()
        cursor = space.connection.cursor()
        
        # Count users before deletion
        cursor.execute("SELECT COUNT(*) as total FROM users WHERE is_admin = 0")
        users_to_delete = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) as total FROM users WHERE is_admin = 1")
        admin_users = cursor.fetchone()[0]
        
        # Delete non-admin users
        cursor.execute("DELETE FROM users WHERE is_admin = 0")
        rows_affected = cursor.rowcount
        
        space.connection.commit()
        cursor.close()
        
        message = f"Deleted {rows_affected} non-admin users. {admin_users} admin users preserved."
        logger.info(f"[DEV] {message}")
        
        return jsonify({
            'success': True,
            'message': message,
            'users_deleted': rows_affected,
            'admins_preserved': admin_users
        })
        
    except Exception as e:
        logger.error(f"[DEV] Error clearing non-admin users: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# Route for FAQ page
@app.route('/faq')
def faq():
    """Display the FAQ page."""
    return render_template('faq.html')

# Route for About page
@app.route('/about')
def about():
    """Display the About page."""
    return render_template('about.html')

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
            model = request.json.get('model', 'tiny')
            detect_language = request.json.get('detect_language', False)
            translate_to = request.json.get('translate_to')
            overwrite = request.json.get('overwrite', True)
            include_timecodes = request.json.get('include_timecodes', True)  # Default to True for better UX
        else:
            # Form submission
            language = request.form.get('language', 'en')
            model = request.form.get('model', 'tiny')
            detect_language = request.form.get('detect_language', 'false') == 'true'
            translate_to = request.form.get('translate_to')
            overwrite = request.form.get('overwrite', 'true') == 'true'
            include_timecodes = request.form.get('include_timecodes', 'true') == 'true'  # Default to True for better UX
        
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
            
        # Check if transcript already exists in database
        # Determine target language for checking existing transcripts
        target_language = translate_to if translate_to else language
        if target_language and len(target_language) == 2:
            target_language = f"{target_language}-{target_language.upper()}"
        
        # Check for existing transcript
        existing_transcript = None
        try:
            cursor = space.connection.cursor(dictionary=True)
            
            # First try exact match
            query = "SELECT * FROM space_transcripts WHERE space_id = %s AND language = %s"
            cursor.execute(query, (space_id, target_language))
            existing_transcript = cursor.fetchone()
            
            # If no exact match, try language family match (e.g., en-US matches en-EN)
            if not existing_transcript and '-' in target_language:
                base_language = target_language.split('-')[0]
                query = "SELECT * FROM space_transcripts WHERE space_id = %s AND language LIKE %s"
                cursor.execute(query, (space_id, f"{base_language}-%"))
                existing_transcript = cursor.fetchone()
                if existing_transcript:
                    logger.info(f"Found compatible transcript in {existing_transcript['language']} for requested {target_language}")
            
            cursor.close()
        except Exception as db_err:
            logger.warning(f"Error checking existing transcript: {db_err}")
        
        # If transcript exists and overwrite is False, return it immediately
        if existing_transcript and not overwrite:
            if request.is_json:
                return jsonify({
                    'message': 'Transcript already exists',
                    'transcript_id': existing_transcript['id'],
                    'language': existing_transcript['language'],
                    'created_at': existing_transcript['created_at'].isoformat() if existing_transcript['created_at'] else None,
                    'from_database': True
                })
            flash('Transcript already exists for this language', 'info')
            return redirect(url_for('space_page', space_id=space_id))
        
        # ENHANCEMENT: Even if overwrite is True, check for database transcript and return it immediately 
        # if it exists to save AI processing time, unless user explicitly wants to regenerate
        if existing_transcript and overwrite:
            if request.is_json:
                # For API requests, give user option by returning existing transcript
                # but allowing them to specify force_regenerate=true to actually regenerate
                force_regenerate = request.json.get('force_regenerate', False)
                if not force_regenerate:
                    logger.info(f"Returning existing transcript for space {space_id} (overwrite=true but force_regenerate=false)")
                    return jsonify({
                        'message': 'Transcript loaded from database',
                        'transcript_id': existing_transcript['id'],
                        'language': existing_transcript['language'],
                        'created_at': existing_transcript['created_at'].isoformat() if existing_transcript['created_at'] else None,
                        'from_database': True
                    })
            
        # Create transcription job with additional parameters
        options = {
            'model': model,
            'detect_language': detect_language,
            'translate_to': translate_to if translate_to else None,
            'overwrite': overwrite,
            'include_timecodes': include_timecodes
        }
        
        # Create a background job file
        import uuid
        import json
        from pathlib import Path
        import datetime
        
        # Create transcript_jobs directory if it doesn't exist
        os.makedirs('./transcript_jobs', exist_ok=True)
        
        # Check for existing pending or in-progress jobs for this space
        transcript_jobs_dir = Path('./transcript_jobs')
        existing_job = None
        
        if transcript_jobs_dir.exists():
            for job_file in transcript_jobs_dir.glob('*.json'):
                try:
                    with open(job_file, 'r') as f:
                        job_data = json.load(f)
                        # Check if this job is for the same space and is still pending/in_progress
                        if (job_data.get('space_id') == space_id and 
                            job_data.get('status') in ['pending', 'in_progress']):
                            existing_job = job_data
                            break
                except Exception as e:
                    logger.error(f"Error reading job file {job_file}: {e}")
        
        # If there's already a pending/in_progress job, don't create a new one
        if existing_job:
            if request.is_json:
                return jsonify({
                    'error': 'A transcription job is already in progress for this space',
                    'existing_job_id': existing_job.get('id'),
                    'status': existing_job.get('status')
                }), 409  # Conflict
            flash('A transcription job is already pending or in progress for this space. Please wait for it to complete.', 'warning')
            return redirect(url_for('space_page', space_id=space_id))
        
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