#!/usr/bin/env python3
# app.py - Flask app for XSpace Downloader

# Load environment variables from .env file
from load_env import load_env
load_env()

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
import time
from functools import wraps
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
    # Also try loading from htdocs directory if current directory doesn't work
    if not os.getenv('OPENAI_API_KEY') and not os.getenv('ANTHROPIC_API_KEY'):
        load_env('../htdocs/.env')
    print("Environment variables loaded from .env file")
    # Verify critical env vars are loaded
    if os.getenv('OPENAI_API_KEY'):
        print("✓ OPENAI_API_KEY loaded successfully")
    elif os.getenv('ANTHROPIC_API_KEY'):
        print("✓ ANTHROPIC_API_KEY loaded successfully")
    else:
        print("⚠ Warning: No AI API keys found in environment")
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
from components.Ad import Ad
from components.LoggingCursor import wrap_cursor
from components.Affiliate import Affiliate
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

# Import SQLLogger and SystemStatus components
try:
    from components.SQLLogger import sql_logger
    SQL_LOGGER_AVAILABLE = True
except ImportError:
    SQL_LOGGER_AVAILABLE = False
    logger.warning("SQLLogger component not available - SQL logging will be disabled")

try:
    from components.SystemStatus import system_status
    SYSTEM_STATUS_AVAILABLE = True
except ImportError:
    SYSTEM_STATUS_AVAILABLE = False
    logger.warning("SystemStatus component not available - system monitoring will be limited")

# Import cost tracking and visitor tracking components
try:
    from components.CostTracker import CostTracker
    COST_TRACKING_AVAILABLE = True
except ImportError:
    COST_TRACKING_AVAILABLE = False
    logger.warning("CostTracker component not available - cost tracking will be disabled")

try:
    from components.VisitorTracker import VisitorTracker
    VISITOR_TRACKING_AVAILABLE = True
except ImportError:
    VISITOR_TRACKING_AVAILABLE = False
    logger.warning("VisitorTracker component not available - visitor limitations will be disabled")

# Application version
__version__ = "1.1.1"

# Create Flask application
app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)

# Add context processor to inject user info into all templates
@app.context_processor
def inject_user_info():
    """Inject user info into all templates automatically."""
    # Skip for API routes to avoid unnecessary database queries
    if request.endpoint and (request.endpoint.startswith('api_') or '/api/' in request.path):
        return {
            'user_email': None,
            'user_credits': None
        }
    
    if session.get('user_id'):
        try:
            space = get_space_component()
            if not space:
                logger.warning("Space component not available for user info context")
                return {
                    'user_email': None,
                    'user_credits': None
                }
            
            cursor = space.connection.cursor(dictionary=True)
            cursor.execute("SELECT email, credits FROM users WHERE id = %s", (session['user_id'],))
            user_info = cursor.fetchone()
            cursor.close()
            if user_info:
                return {
                    'user_email': user_info['email'],
                    'user_credits': float(user_info['credits'])
                }
        except Exception as e:
            logger.warning(f"Could not fetch user info for context: {e}")
    
    # Return empty values if not logged in or error
    return {
        'user_email': None,
        'user_credits': None
    }

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
    DOWNLOAD_DIR=os.path.abspath(os.environ.get('DOWNLOAD_DIR', './downloads')),
    MAX_CONCURRENT_DOWNLOADS=int(os.environ.get('MAX_CONCURRENT_DOWNLOADS', 5)),
    DEBUG=os.environ.get('DEBUG', 'false').lower() == 'true'
)

# Create download directory if it doesn't exist
os.makedirs(app.config['DOWNLOAD_DIR'], exist_ok=True)

# Cache for the /spaces endpoint
spaces_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 600  # 600 seconds (10 minutes)
}

# Cache for the index route
index_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 600  # 600 seconds (10 minutes)
}

def invalidate_spaces_cache():
    """Invalidate the spaces cache."""
    global spaces_cache
    spaces_cache['data'] = None
    spaces_cache['timestamp'] = 0
    logger.info("Spaces cache invalidated")

def trigger_cache_invalidation():
    """Create a trigger file to signal cache invalidation from background processes."""
    try:
        trigger_file = Path('./temp/cache_invalidate.trigger')
        trigger_file.parent.mkdir(exist_ok=True)
        trigger_file.touch()
        logger.info("Created cache invalidation trigger file")
    except Exception as e:
        logger.warning(f"Could not create cache invalidation trigger: {e}")

def check_cache_invalidation_trigger():
    """Check if background processes have signaled cache invalidation."""
    trigger_file = Path('./temp/cache_invalidate.trigger')
    if trigger_file.exists():
        try:
            invalidate_spaces_cache()
            trigger_file.unlink()  # Remove the trigger file
            logger.info("Processed cache invalidation trigger from background process")
            return True
        except Exception as e:
            logger.warning(f"Error processing cache invalidation trigger: {e}")
    return False

def invalidate_index_cache():
    """Invalidate the index cache."""
    global index_cache
    index_cache['data'] = None
    index_cache['timestamp'] = 0
    logger.info("Index cache invalidated")

def invalidate_all_caches():
    """Invalidate all caches."""
    invalidate_spaces_cache()
    invalidate_index_cache()

def get_cached_spaces_data():
    """Get cached spaces data if valid, otherwise return None."""
    global spaces_cache
    current_time = time.time()
    
    # Check for cache invalidation trigger from background processes
    check_cache_invalidation_trigger()
    
    # Check if cache is valid
    if (spaces_cache['data'] is not None and 
        current_time - spaces_cache['timestamp'] < spaces_cache['ttl']):
        logger.info(f"Using cached spaces data (age: {current_time - spaces_cache['timestamp']:.1f}s)")
        return spaces_cache['data']
    
    return None

def get_cached_index_data():
    """Get cached index data if valid, otherwise return None."""
    global index_cache
    current_time = time.time()
    
    # Check if cache is valid
    if (index_cache['data'] is not None and 
        current_time - index_cache['timestamp'] < index_cache['ttl']):
        logger.info(f"Using cached index data (age: {current_time - index_cache['timestamp']:.1f}s)")
        return index_cache['data']
    
    return None

def set_spaces_cache(data):
    """Set the spaces cache with new data."""
    global spaces_cache
    spaces_cache['data'] = data
    spaces_cache['timestamp'] = time.time()
    logger.info("Spaces cache updated")

def set_index_cache(data):
    """Set the index cache with new data."""
    global index_cache
    index_cache['data'] = data
    index_cache['timestamp'] = time.time()
    logger.info("Index cache updated")

# Register cache invalidation callback with Space component
try:
    from components.Space import set_cache_invalidation_callback
    set_cache_invalidation_callback(invalidate_all_caches)
except ImportError:
    logger.warning("Could not register cache invalidation callback")

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

def check_service_enabled(service_name):
    """Check if a service is enabled in app settings."""
    try:
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT setting_value 
            FROM app_settings 
            WHERE setting_name = %s
        """, (service_name,))
        
        result = cursor.fetchone()
        cursor.close()
        
        if result:
            return result['setting_value'].lower() == 'true'
        
        # Default to enabled if setting not found
        return True
        
    except Exception as e:
        logger.error(f"Error checking service setting {service_name}: {e}")
        # Default to enabled on error
        return True

def get_active_system_messages():
    """Get currently active system messages."""
    try:
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT id, message
            FROM system_messages
            WHERE status = 1
              AND start_date <= NOW()
              AND end_date >= NOW()
            ORDER BY start_date DESC
        """)
        
        messages = cursor.fetchall()
        cursor.close()
        
        return messages
        
    except Exception as e:
        logger.error(f"Error getting system messages: {e}")
        return []

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
        # Load advertisement for all users (logged in or not)
        advertisement_html = None
        advertisement_bg = '#ffffff'
        try:
            ad = Ad.get_active_ad()
            if ad and ad.copy:
                advertisement_html = ad.copy
                advertisement_bg = ad.background_color or '#ffffff'
        except Exception as e:
            logger.warning(f"Error loading advertisement: {e}")
        
        # Check if we have cached data
        cached_data = get_cached_spaces_data()
        if cached_data:
            return render_template('all_spaces.html', 
                                 spaces=cached_data['completed_spaces'], 
                                 popular_tags=cached_data['popular_tags'],
                                 advertisement_html=advertisement_html,
                                 advertisement_bg=advertisement_bg)
        
        # No valid cache, generate fresh data
        logger.info("Generating fresh spaces data (cache miss or expired)")
        
        # Get Space component
        space = get_space_component()
        
        # Get all completed spaces directly from spaces table - only latest entry per space_id
        raw_cursor = space.connection.cursor(dictionary=True)
        cursor = wrap_cursor(raw_cursor, "SpacesList")
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
        
        # Cache the data
        cache_data = {
            'completed_spaces': completed_spaces,
            'popular_tags': popular_tags
        }
        set_spaces_cache(cache_data)
        
        return render_template('all_spaces.html', spaces=completed_spaces, popular_tags=popular_tags, advertisement_html=advertisement_html, advertisement_bg=advertisement_bg)
        
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
        
        # Get transcription jobs from both old and new locations
        transcript_jobs = []
        transcript_jobs_dirs = [
            Path('transcript_jobs'),  # Old location
            Path('/var/www/production/xspacedownload.com/website/htdocs/transcript_jobs')  # New location
        ]
        
        for transcript_jobs_dir in transcript_jobs_dirs:
            if not transcript_jobs_dir.exists():
                continue
                
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
        
        # Also get standalone translation jobs from translation_jobs directory
        translation_jobs_dir = Path('/var/www/production/xspacedownload.com/website/htdocs/translation_jobs')
        if translation_jobs_dir.exists():
            for job_file in translation_jobs_dir.glob('*.json'):
                try:
                    with open(job_file, 'r') as f:
                        job_data = json.load(f)
                        # Only include pending, in_progress, or processing translation jobs
                        if job_data.get('status') in ['pending', 'in_progress', 'processing']:
                            # Get space details for title
                            space_details = space.get_space(job_data.get('space_id'))
                            if space_details:
                                job_data['title'] = space_details.get('title', f"Space {job_data.get('space_id')}")
                            else:
                                job_data['title'] = f"Space {job_data.get('space_id')}"
                            
                            job_data['is_translation'] = True
                            job_data['target_language'] = job_data.get('target_lang')
                            
                            if job_data.get('status') == 'pending':
                                job_data['status_label'] = 'Pending Translation'
                                job_data['status_class'] = 'warning'
                            elif job_data.get('status') == 'processing':
                                job_data['status_label'] = f'Translating to {job_data.get("target_lang")}'
                                job_data['status_class'] = 'info'
                                job_data['progress_percent'] = job_data.get('progress', 0)
                            else:
                                job_data['status_label'] = 'Translating'
                                job_data['status_class'] = 'success'
                                job_data['progress_percent'] = job_data.get('progress', 0)
                            
                            transcript_jobs.append(job_data)
                except Exception as e:
                    logger.error(f"Error reading translation job file {job_file}: {e}")
        
        # Separate transcription and translation jobs  
        transcription_only_jobs = [job for job in transcript_jobs if not job.get('is_translation')]
        translation_jobs = [job for job in transcript_jobs if job.get('is_translation')]
        
        # Get video generation jobs from transcript_jobs directory
        video_jobs = []
        for transcript_jobs_dir in transcript_jobs_dirs:
            if not transcript_jobs_dir.exists():
                continue
                
            for job_file in transcript_jobs_dir.glob('*_video.json'):
                try:
                    with open(job_file, 'r') as f:
                        job_data = json.load(f)
                        # Only include pending, in_progress, or processing video jobs
                        if job_data.get('status') in ['pending', 'in_progress', 'processing']:
                            # Get space details for title
                            space_details = space.get_space(job_data.get('space_id'))
                            if space_details:
                                job_data['title'] = space_details.get('title', f"Space {job_data.get('space_id')}")
                            else:
                                job_data['title'] = f"Space {job_data.get('space_id')}"
                            
                            job_data['is_video_generation'] = True
                            
                            if job_data.get('status') == 'pending':
                                job_data['status_label'] = 'Pending Video Generation'
                                job_data['status_class'] = 'warning'
                            elif job_data.get('status') == 'processing':
                                job_data['status_label'] = 'Generating Video'
                                job_data['status_class'] = 'info'
                                job_data['progress_percent'] = job_data.get('progress', 0)
                            else:
                                job_data['status_label'] = 'Processing Video'
                                job_data['status_class'] = 'success'
                                job_data['progress_percent'] = job_data.get('progress', 0)
                            
                            video_jobs.append(job_data)
                except Exception as e:
                    logger.error(f"Error reading video job file {job_file}: {e}")
        
        # Sort video jobs by created_at
        video_jobs.sort(key=lambda x: x.get('created_at', ''))
        
        # Get TTS jobs from database
        tts_jobs = []
        try:
            cursor = space.connection.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, space_id, user_id, target_language, status, progress, 
                       created_at, error_message
                FROM tts_jobs
                WHERE status IN ('pending', 'in_progress')
                ORDER BY created_at ASC
            """)
            tts_jobs_data = cursor.fetchall()
            
            for job_data in tts_jobs_data:
                # Get space details for title
                space_details = space.get_space(job_data.get('space_id'))
                if space_details:
                    job_data['title'] = space_details.get('title', f"Space {job_data.get('space_id')}")
                else:
                    job_data['title'] = f"Space {job_data.get('space_id')}"
                
                job_data['is_tts'] = True
                
                if job_data.get('status') == 'pending':
                    job_data['status_label'] = 'Pending TTS'
                    job_data['status_class'] = 'warning'
                elif job_data.get('status') == 'in_progress':
                    job_data['status_label'] = f'Generating TTS ({job_data.get("target_language")})'
                    job_data['status_class'] = 'info'
                    job_data['progress_percent'] = job_data.get('progress', 0)
                
                tts_jobs.append(job_data)
            
            cursor.close()
        except Exception as e:
            logger.error(f"Error getting TTS jobs: {e}")
        
        # Deduplicate jobs by space_id - keep only the most recent job per space
        def deduplicate_jobs(jobs_list):
            space_jobs = {}
            for job in jobs_list:
                space_id = job.get('space_id')
                if space_id:
                    created_at = job.get('created_at', '')
                    if space_id not in space_jobs or created_at > space_jobs[space_id].get('created_at', ''):
                        space_jobs[space_id] = job
            return list(space_jobs.values())
        
        # Apply deduplication to prevent the same space appearing multiple times
        transcription_only_jobs = deduplicate_jobs(transcription_only_jobs)
        translation_jobs = deduplicate_jobs(translation_jobs)
        video_jobs = deduplicate_jobs(video_jobs)
        tts_jobs = deduplicate_jobs(tts_jobs)
        
        # Load advertisement for all users (logged in or not)
        advertisement_html = None
        advertisement_bg = '#ffffff'
        try:
            ad = Ad.get_active_ad()
            if ad and ad.copy:
                advertisement_html = ad.copy
                advertisement_bg = ad.background_color or '#ffffff'
        except Exception as e:
            logger.warning(f"Error loading advertisement: {e}")
        
        return render_template('queue.html', 
                             queue_jobs=queue_jobs, 
                             transcript_jobs=transcript_jobs,
                             transcription_only_jobs=transcription_only_jobs,
                             translation_jobs=translation_jobs,
                             video_jobs=video_jobs,
                             tts_jobs=tts_jobs,
                             advertisement_html=advertisement_html,
                             advertisement_bg=advertisement_bg)
        
    except Exception as e:
        logger.error(f"Error viewing queue: {e}", exc_info=True)
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/favicon.ico')
def favicon():
    """Serve favicon to avoid 404 errors."""
    return send_from_directory('static', 'favicon.svg', mimetype='image/svg+xml')

@app.route('/a/<int:affiliate_user_id>')
def affiliate_tracking(affiliate_user_id):
    """Track affiliate visits and redirect to home page."""
    try:
        # Get visitor information
        visitor_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if visitor_ip and ',' in visitor_ip:
            visitor_ip = visitor_ip.split(',')[0].strip()
        visitor_user_agent = request.headers.get('User-Agent', '')
        
        # Track the visit
        affiliate = Affiliate()
        tracking_id = affiliate.track_visit(affiliate_user_id, visitor_ip, visitor_user_agent)
        
        if tracking_id:
            # Store tracking info in session for conversion tracking
            session['affiliate_tracking'] = {
                'affiliate_user_id': affiliate_user_id,
                'tracking_id': tracking_id
            }
            logger.info(f"Tracked affiliate visit from user {affiliate_user_id}")
        else:
            logger.warning(f"Failed to track affiliate visit from user {affiliate_user_id}")
        
        # Redirect to home page
        return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f"Error in affiliate tracking: {e}", exc_info=True)
        # Still redirect to home even on error
        return redirect(url_for('index'))

@app.route('/affiliate-program')
def affiliate_program():
    """Display information about the affiliate program."""
    try:
        # Load advertisement for all users (logged in or not)
        advertisement_html = None
        advertisement_bg = '#ffffff'
        try:
            ad = Ad.get_active_ad()
            if ad and ad.copy:
                advertisement_html = ad.copy
                advertisement_bg = ad.background_color or '#ffffff'
        except Exception as e:
            logger.warning(f"Error loading advertisement: {e}")
        
        # Get current affiliate settings for display
        affiliate = Affiliate()
        settings = affiliate.get_affiliate_settings()
        
        return render_template('affiliate-program.html',
                             settings=settings,
                             advertisement_html=advertisement_html,
                             advertisement_bg=advertisement_bg)
    except Exception as e:
        logger.error(f"Error loading affiliate program page: {e}", exc_info=True)
        flash('Error loading page. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/pricing')
def pricing():
    """Display pricing page with available credit packages."""
    try:
        # Import Product component
        from components.Product import Product
        
        product = Product()
        
        # Get active products for display
        products = product.get_active_products()
        
        # Load advertisement for all users (logged in or not)
        advertisement_html = None
        advertisement_bg = '#ffffff'
        try:
            ad = Ad.get_active_ad()
            if ad and ad.copy:
                advertisement_html = ad.copy
                advertisement_bg = ad.background_color or '#ffffff'
        except Exception as e:
            logger.warning(f"Error loading advertisement: {e}")
        
        return render_template('pricing.html',
                             products=products,
                             advertisement_html=advertisement_html,
                             advertisement_bg=advertisement_bg)
    except Exception as e:
        logger.error(f"Error loading pricing page: {e}", exc_info=True)
        flash('Error loading pricing information. Please try again.', 'error')
        return redirect(url_for('index'))

# Ticket/Support Routes
@app.route('/tickets')
def tickets():
    """Display support tickets page."""
    try:
        # Import Ticket component
        from components.Ticket import Ticket
        
        # Check if user is logged in
        user_id = session.get('user_id')
        if not user_id:
            return render_template('tickets.html', logged_in=False)
        
        # Get DB config
        with open('db_config.json', 'r') as f:
            config = json.load(f)
        db_config = config['mysql']
        ticket = Ticket(db_config)
        
        # Check if user is staff
        is_staff = False
        if user_id:
            from components.User import User
            user_comp = User()
            user_data = user_comp.get_user(user_id=user_id)
            is_staff = user_data and user_data.get('is_staff', False)
        
        # Get ticket ID from query params if provided
        ticket_id = request.args.get('id', type=int)
        
        # If specific ticket requested
        if ticket_id:
            ticket_data = ticket.get_ticket(ticket_id, user_id)
            if ticket_data['success'] and ticket_data['ticket']:
                ticket.close()
                return render_template('tickets.html', 
                                     logged_in=True,
                                     single_ticket=ticket_data['ticket'],
                                     is_staff=is_staff)
            else:
                flash('Ticket not found or access denied.', 'error')
                return redirect(url_for('tickets'))
        
        # Get user's tickets
        page = request.args.get('page', 1, type=int)
        tickets_data = ticket.get_user_tickets(user_id, is_staff, page)
        
        # Get previous responses for staff
        previous_responses = []
        if is_staff:
            previous_responses = ticket.get_previous_responses()
        
        ticket.close()
        
        return render_template('tickets.html',
                             logged_in=True,
                             tickets=tickets_data.get('tickets', []),
                             total_pages=tickets_data.get('total_pages', 1),
                             current_page=page,
                             is_staff=is_staff,
                             previous_responses=previous_responses)
    except Exception as e:
        logger.error(f"Error loading tickets page: {e}", exc_info=True)
        flash('Error loading support tickets. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/tickets/create', methods=['POST'])
def create_ticket():
    """Create a new support ticket."""
    try:
        # Check if user is logged in
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'Please log in to create a ticket'}), 401
            
        from components.Ticket import Ticket
        
        issue_title = request.form.get('issue_title', '').strip()
        issue_detail = request.form.get('issue_detail', '').strip()
        
        if not issue_title or not issue_detail:
            return jsonify({'success': False, 'error': 'Title and details are required'}), 400
        
        with open('db_config.json', 'r') as f:
            config = json.load(f)
        db_config = config['mysql']
        ticket = Ticket(db_config)
        
        result = ticket.create_ticket(user_id, issue_title, issue_detail)
        ticket.close()
        
        if result['success']:
            return jsonify({
                'success': True,
                'ticket_id': result['ticket_id'],
                'priority': result['priority'],
                'ai_response': result.get('ai_response', '')
            })
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Failed to create ticket')}), 400
            
    except Exception as e:
        logger.error(f"Error creating ticket: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Server error'}), 500

@app.route('/tickets/<int:ticket_id>/update', methods=['POST'])
def update_ticket(ticket_id):
    """Update a ticket."""
    try:
        # Check if user is logged in
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'Please log in to update a ticket'}), 401
            
        from components.Ticket import Ticket
        
        update_data = request.get_json()
        
        with open('db_config.json', 'r') as f:
            config = json.load(f)
        db_config = config['mysql']
        ticket = Ticket(db_config)
        
        result = ticket.update_ticket(ticket_id, user_id, update_data)
        ticket.close()
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error updating ticket: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Server error'}), 500

@app.route('/tickets/<int:ticket_id>/respond', methods=['POST'])
def respond_to_ticket(ticket_id):
    """Add a response to a ticket (staff only)."""
    try:
        # Check if user is logged in
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'Please log in to respond to a ticket'}), 401
            
        from components.Ticket import Ticket
        
        response_text = request.form.get('response', '').strip()
        
        if not response_text:
            return jsonify({'success': False, 'error': 'Response text is required'}), 400
        
        with open('db_config.json', 'r') as f:
            config = json.load(f)
        db_config = config['mysql']
        ticket = Ticket(db_config)
        
        result = ticket.add_response(ticket_id, user_id, response_text)
        ticket.close()
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error responding to ticket: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Server error'}), 500

@app.route('/tickets/<int:ticket_id>/add-info', methods=['POST'])
def add_ticket_info(ticket_id):
    """Add additional information to a ticket (ticket owner only)."""
    try:
        # Check if user is logged in
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'Please log in to add information'}), 401
            
        from components.Ticket import Ticket
        
        additional_info = request.form.get('additional_info', '').strip()
        
        if not additional_info:
            return jsonify({'success': False, 'error': 'Additional information is required'}), 400
        
        with open('db_config.json', 'r') as f:
            config = json.load(f)
        db_config = config['mysql']
        ticket = Ticket(db_config)
        
        result = ticket.add_user_update(ticket_id, user_id, additional_info)
        ticket.close()
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error adding ticket info: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Server error'}), 500

# Payment Routes
@app.route('/payment/create-checkout-session', methods=['POST'])
def create_checkout_session():
    """Create Stripe checkout session for product purchase."""
    try:
        # Check if user is logged in
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Please log in to purchase credits'}), 401
        
        data = request.get_json()
        product_id = data.get('product_id')
        
        if not product_id:
            return jsonify({'error': 'Product ID is required'}), 400
        
        # Import Payment component
        from components.Payment import Payment
        payment = Payment()
        
        # Create checkout session
        success_url = request.url_root.rstrip('/') + '/payment/success'
        cancel_url = request.url_root.rstrip('/') + '/payment/cancel'
        
        result = payment.create_checkout_session(
            user_id=user_id,
            product_id=product_id,
            success_url=success_url,
            cancel_url=cancel_url
        )
        
        if 'error' in result:
            return jsonify({'error': result['error']}), 400
        
        return jsonify({
            'session_id': result['session_id'],
            'session_url': result['session_url']
        })
        
    except Exception as e:
        logger.error(f"Error creating checkout session: {e}", exc_info=True)
        return jsonify({'error': 'Payment system error'}), 500

@app.route('/payment/success')
def payment_success():
    """Payment success page - immediately apply credits."""
    try:
        session_id = request.args.get('session_id')
        if not session_id:
            flash('Invalid payment session.', 'error')
            return redirect(url_for('pricing'))
        
        # Import Payment component
        from components.Payment import Payment
        payment = Payment()
        
        # Process the successful payment immediately
        result = payment.process_successful_payment(session_id)
        
        if result.get('success'):
            flash(f'Payment successful! {result.get("credits", 0)} credits have been added to your account.', 'success')
            
            # Send email receipt
            if result.get('user_email'):
                payment.send_receipt_email(result)
        else:
            error_msg = result.get('error', 'Payment processing error')
            if 'already processed' in error_msg.lower():
                flash('Payment already processed. Please check your credit balance.', 'info')
            else:
                flash(f'Payment received but there was an error applying credits: {error_msg}', 'warning')
        
        return redirect(url_for('profile'))
        
    except Exception as e:
        logger.error(f"Error on payment success page: {e}", exc_info=True)
        flash('Payment completed, but there was an error displaying the confirmation.', 'warning')
        return redirect(url_for('profile'))

@app.route('/payment/cancel')
def payment_cancel():
    """Payment cancellation page."""
    flash('Payment was cancelled. You can try again anytime.', 'info')
    return redirect(url_for('pricing'))

@app.route('/payment/webhook', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhook events."""
    try:
        payload = request.get_data()
        sig_header = request.headers.get('Stripe-Signature')
        
        if not sig_header:
            logger.error("Missing Stripe signature header")
            return '', 400
        
        # Import Payment component
        from components.Payment import Payment
        payment = Payment()
        
        result = payment.handle_webhook(payload, sig_header)
        
        if 'error' in result:
            logger.error(f"Webhook error: {result['error']}")
            return '', 400
        
        return '', 200
        
    except Exception as e:
        logger.error(f"Error handling Stripe webhook: {e}", exc_info=True)
        return '', 400

@app.route('/api/stripe-config')
def get_stripe_config():
    """Get Stripe publishable key for frontend."""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        from components.Payment import Payment
        payment = Payment()
        
        return jsonify({
            'publishable_key': payment.get_stripe_publishable_key()
        })
        
    except Exception as e:
        logger.error(f"Error getting Stripe config: {e}", exc_info=True)
        return jsonify({'error': 'Configuration error'}), 500

@app.route('/', methods=['GET'])
def index():
    """Home page with form to submit a space URL."""
    try:
        # Check if we have cached data
        cached_data = get_cached_index_data()
        if cached_data:
            # Load advertisement for all users (logged in or not)
            advertisement_html = None
            advertisement_bg = '#ffffff'
            try:
                ad = Ad.get_active_ad()
                if ad and ad.copy:
                    advertisement_html = ad.copy
                    advertisement_bg = ad.background_color or '#ffffff'
            except Exception as e:
                logger.warning(f"Error loading advertisement: {e}")
            
            return render_template('index.html', completed_spaces=cached_data, advertisement_html=advertisement_html, advertisement_bg=advertisement_bg)
        
        # No valid cache, generate fresh data
        logger.info("Generating fresh index data (cache miss or expired)")
        
        # Get a list of completed downloads to display
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
        
        # Cache the data
        set_index_cache(completed_spaces)
        
        # Load advertisement for all users (logged in or not)
        advertisement_html = None
        advertisement_bg = '#ffffff'
        try:
            ad = Ad.get_active_ad()
            if ad and ad.copy:
                advertisement_html = ad.copy
                advertisement_bg = ad.background_color or '#ffffff'
        except Exception as e:
            logger.warning(f"Error loading advertisement: {e}")
        
        return render_template('index.html', completed_spaces=completed_spaces, advertisement_html=advertisement_html, advertisement_bg=advertisement_bg)
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
        
        # Check permissions: space owner OR admin
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        query = "SELECT user_id, cookie_id FROM spaces WHERE space_id = %s"
        cursor.execute(query, (space_id,))
        space_record = cursor.fetchone()
        cursor.close()
        
        if not space_record:
            return jsonify({'error': 'Space not found'}), 404
        
        # Check permissions: space owner OR admin
        is_admin = session.get('is_admin', False)
        can_edit = False
        
        if is_admin:
            can_edit = True
        elif user_id > 0:
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
                            job_data.get('status') in ['pending', 'in_progress', 'processing']):
                            has_pending_transcript_job = True
                            logger.info(f"Found pending transcription job {job_data.get('id')} for space {space_id} with status {job_data.get('status')}")
                            break
                except Exception as e:
                    logger.error(f"Error reading transcript job file {job_file}: {e}")
        
        logger.info(f"Space {space_id}: has_pending_transcript_job = {has_pending_transcript_job}")
        
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
        
        # Get translation jobs
        translation_jobs = []
        translation_jobs_dir = Path('/var/www/production/xspacedownload.com/website/htdocs/translation_jobs')
        if translation_jobs_dir.exists():
            for job_file in translation_jobs_dir.glob('*.json'):
                try:
                    with open(job_file, 'r') as f:
                        job_data = json.load(f)
                        # Only include pending or in_progress translation jobs
                        if job_data.get('status') in ['pending', 'in_progress']:
                            # Get space details for title
                            space_details = space.get_space(job_data.get('space_id'))
                            if space_details:
                                title = space_details.get('title', f"Space {job_data.get('space_id')}")
                            else:
                                title = f"Space {job_data.get('space_id')}"
                            
                            # Get target language name
                            target_lang = job_data.get('target_lang', 'Unknown')
                            
                            translation_jobs.append({
                                'id': job_data.get('id'),
                                'space_id': job_data.get('space_id'),
                                'title': title,
                                'status': job_data.get('status'),
                                'status_label': f'Pending Translation to {target_lang}' if job_data.get('status') == 'pending' else f'Translating to {target_lang}',
                                'status_class': 'info' if job_data.get('status') == 'pending' else 'primary',
                                'created_at': job_data.get('created_at', ''),
                                'progress_percent': job_data.get('progress', 0),
                                'target_lang': target_lang,
                                'type': 'translation'
                            })
                except Exception as e:
                    logger.error(f"Error reading translation job file {job_file}: {e}")
        
        # Sort translation jobs by created_at
        translation_jobs.sort(key=lambda x: x.get('created_at', ''))
        
        # Get video generation jobs
        video_jobs = []
        transcript_jobs_dirs = [
            Path('transcript_jobs'),  # Old location
            Path('/var/www/production/xspacedownload.com/website/htdocs/transcript_jobs')  # New location
        ]
        
        for transcript_jobs_dir in transcript_jobs_dirs:
            if not transcript_jobs_dir.exists():
                continue
                
            for job_file in transcript_jobs_dir.glob('*_video.json'):
                try:
                    with open(job_file, 'r') as f:
                        job_data = json.load(f)
                        # Only include pending, in_progress, or processing video jobs
                        if job_data.get('status') in ['pending', 'in_progress', 'processing']:
                            # Get space details for title
                            space_details = space.get_space(job_data.get('space_id'))
                            if space_details:
                                title = space_details.get('title', f"Space {job_data.get('space_id')}")
                            else:
                                title = f"Space {job_data.get('space_id')}"
                            
                            video_jobs.append({
                                'id': job_data.get('id') or job_data.get('job_id'),
                                'space_id': job_data.get('space_id'),
                                'title': title,
                                'status': job_data.get('status'),
                                'status_label': 'Pending Video Generation' if job_data.get('status') == 'pending' else 'Generating Video',
                                'status_class': 'warning' if job_data.get('status') == 'pending' else 'info',
                                'created_at': job_data.get('created_at', ''),
                                'progress_percent': job_data.get('progress', 0),
                                'type': 'video'
                            })
                except Exception as e:
                    logger.error(f"Error reading video job file {job_file}: {e}")
        
        # Sort video jobs by created_at
        video_jobs.sort(key=lambda x: x.get('created_at', ''))
        
        return jsonify({
            'jobs': queue_jobs,
            'transcript_jobs': transcript_jobs,
            'translation_jobs': translation_jobs,
            'video_jobs': video_jobs,
            'total': len(queue_jobs) + len(transcript_jobs) + len(translation_jobs) + len(video_jobs)
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
        # Load advertisement for all users (logged in or not)
        advertisement_html = None
        advertisement_bg = '#ffffff'
        try:
            ad = Ad.get_active_ad()
            if ad and ad.copy:
                advertisement_html = ad.copy
                advertisement_bg = ad.background_color or '#ffffff'
        except Exception as e:
            logger.warning(f"Error loading advertisement: {e}")
        
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
        
        return render_template('favorites.html', favorites=favorites, advertisement_html=advertisement_html, advertisement_bg=advertisement_bg)
        
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
        
        # Return the file directly from Flask with range request support
        if attachment:
            # Download as attachment
            return send_file(file_path, as_attachment=True, download_name=filename, mimetype=content_type)
        else:
            # Manual range request handling to avoid HTTP/2 issues
            range_header = request.headers.get('Range')
            
            if not range_header:
                # No range request - return full file
                response = send_file(file_path, mimetype=content_type, as_attachment=False)
                response.headers['Accept-Ranges'] = 'bytes'
                response.headers['Content-Length'] = str(file_size)
                return response
            
            # Handle range request manually
            try:
                # Parse range header (e.g., "bytes=1024-2048" or "bytes=1024-")
                range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
                if not range_match:
                    # Invalid range header
                    response = send_file(file_path, mimetype=content_type, as_attachment=False)
                    response.headers['Accept-Ranges'] = 'bytes'
                    return response
                
                start = int(range_match.group(1))
                end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
                
                # Ensure valid range
                if start >= file_size or end >= file_size or start > end:
                    return Response(status=416)  # Range Not Satisfiable
                
                # Read the specific byte range
                length = end - start + 1
                
                with open(file_path, 'rb') as f:
                    f.seek(start)
                    data = f.read(length)
                
                # Return partial content response
                response = Response(
                    data,
                    status=206,  # Partial Content
                    mimetype=content_type
                )
                response.headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
                response.headers['Accept-Ranges'] = 'bytes'
                response.headers['Content-Length'] = str(length)
                response.headers['Cache-Control'] = 'no-cache'
                
                return response
                
            except Exception as e:
                logger.error(f"Error handling range request: {e}")
                # Fall back to full file
                response = send_file(file_path, mimetype=content_type, as_attachment=False)
                response.headers['Accept-Ranges'] = 'bytes'
                return response
            
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

# Global component instances
translate_component = None
cost_tracker = None
visitor_tracker = None

def get_cost_tracker():
    """Get a CostTracker component instance."""
    global cost_tracker
    
    if not COST_TRACKING_AVAILABLE:
        return None
        
    try:
        if not cost_tracker:
            cost_tracker = CostTracker()
            logger.info("Created new CostTracker component instance")
        
        return cost_tracker
    except Exception as e:
        logger.error(f"Error creating CostTracker instance: {e}")
        return None

def get_visitor_tracker():
    """Get a VisitorTracker component instance."""
    global visitor_tracker
    
    if not VISITOR_TRACKING_AVAILABLE:
        return None
        
    try:
        if not visitor_tracker:
            visitor_tracker = VisitorTracker()
            logger.info("Created new VisitorTracker component instance")
        
        return visitor_tracker
    except Exception as e:
        logger.error(f"Error creating VisitorTracker instance: {e}")
        return None

def check_user_credits(required_amount=0.0):
    """
    Check if user has sufficient credits for an operation.
    
    Args:
        required_amount (float): Amount of credits needed
        
    Returns:
        tuple: (has_sufficient_credits, current_balance, message)
    """
    if not session.get('user_id'):
        return False, 0.0, "Please log in to use this feature"
    
    tracker = get_cost_tracker()
    if not tracker:
        # If cost tracking is disabled, allow operation
        return True, float('inf'), "Cost tracking disabled"
    
    user_id = session['user_id']
    current_balance = tracker.check_user_credits(user_id)
    
    if current_balance < required_amount:
        return False, current_balance, f"Insufficient credits. Required: ${required_amount:.2f}, Available: ${current_balance:.2f}"
    
    return True, current_balance, "Sufficient credits"

def get_user_info_for_template():
    """
    Get user email and credits for template rendering.
    
    Returns:
        dict: Dictionary with user_email and user_credits keys
    """
    user_info = {
        'user_email': None,
        'user_credits': None
    }
    
    if session.get('user_id'):
        try:
            space = get_space_component()
            cursor = space.connection.cursor(dictionary=True)
            cursor.execute("SELECT email, credits FROM users WHERE id = %s", (session['user_id'],))
            result = cursor.fetchone()
            cursor.close()
            if result:
                user_info['user_email'] = result['email']
                user_info['user_credits'] = float(result['credits'])
        except Exception as e:
            logger.warning(f"Could not fetch user info for template: {e}")
    
    return user_info

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
    # Check if transcription service is enabled (translation is part of transcription)
    if not check_service_enabled('transcription_enabled'):
        return jsonify({'error': 'Translation service is temporarily disabled'}), 503
    
    if not TRANSLATE_AVAILABLE:
        return jsonify({'error': 'Translation service is not available'}), 503
    
    # Check if user is logged in
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401
        
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
        
        # If no space_id provided, create user-level tracking ID
        if not space_id:
            space_id = f"user_{user_id}_translate"
        
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
        
        # Check if translator component is available
        translator = get_translate_component()
        logger.info(f"Translator available: {translator is not None}")
        if translator:
            logger.info(f"Translator AI available: {translator.ai is not None}")
            if translator.ai:
                logger.info(f"AI provider: {translator.ai.get_provider_name()}")
        
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
        
        try:
            success, result = translator.translate(text, source_lang, target_lang, space_id)
            logger.info(f"Translation call completed - Success: {success}")
            if not success:
                logger.error(f"Translation failed with result: {result}")
        except Exception as translate_exception:
            logger.error(f"Translation threw exception: {translate_exception}")
            import traceback
            logger.error(f"Translation traceback: {traceback.format_exc()}")
            return jsonify({'error': f'Translation error: {str(translate_exception)}'}), 500
        
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
        # Check if user is logged in
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
            
        # Validate request
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400
            
        # Get request data
        data = request.json
        text = data.get('text')
        max_length = data.get('max_length')  # Optional parameter
        language = data.get('language')  # Optional language parameter (now ignored)
        space_id = data.get('space_id')  # Optional space_id for context
        
        # Validate required fields
        if not text:
            return jsonify({'error': 'Missing text parameter'}), 400
            
        # Get Translate component (which now includes AI functionality)
        translator = get_translate_component()
        if not translator:
            return jsonify({'error': 'Could not initialize AI service'}), 500
            
        # Generate summary with cost tracking
        # If space_id is provided, use it for context; otherwise use user_id as fallback
        if space_id:
            success, result = translator.summary(text, max_length, language, space_id=space_id)
        else:
            # For user-level summaries, we'll track costs without space context
            # Use a special space_id format to indicate user-level operation
            user_space_id = f"user_{user_id}_summary"
            success, result = translator.summary(text, max_length, language, space_id=user_space_id)
        
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
            
        # Generate summary with cost tracking
        space_id = transcript_record['space_id']
        success, result = translator.summary(transcript_text, max_length, space_id=space_id)
        
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
            
            # Check for affiliate tracking and record conversion
            if session.get('affiliate_tracking'):
                try:
                    affiliate = Affiliate()
                    visitor_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
                    if visitor_ip and ',' in visitor_ip:
                        visitor_ip = visitor_ip.split(',')[0].strip()
                    
                    # Record the conversion
                    if affiliate.convert_visitor(user_id, visitor_ip):
                        logger.info(f"Recorded affiliate conversion for new user {user_id}")
                        # Clear the tracking from session
                        session.pop('affiliate_tracking', None)
                except Exception as aff_error:
                    logger.error(f"Error recording affiliate conversion: {aff_error}")
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

# Route for user profile
@app.route('/profile')
def profile():
    """Display user profile with balance and transaction history."""
    if not session.get('user_id'):
        flash('Please log in to view your profile.', 'error')
        return redirect(url_for('index'))
    
    try:
        # Load advertisement for all users (logged in or not)
        advertisement_html = None
        advertisement_bg = '#ffffff'
        try:
            ad = Ad.get_active_ad()
            if ad and ad.copy:
                advertisement_html = ad.copy
                advertisement_bg = ad.background_color or '#ffffff'
        except Exception as e:
            logger.warning(f"Error loading advertisement: {e}")
        
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        user_id = session.get('user_id')
        
        # Get user information
        cursor.execute("""
            SELECT email, credits, created_at, last_logged_in, login_count, country
            FROM users 
            WHERE id = %s
        """, (user_id,))
        user_info = cursor.fetchone()
        
        if not user_info:
            flash('User not found.', 'error')
            return redirect(url_for('index'))
        
        # Get transaction history from computes table
        cursor.execute("""
            SELECT action, compute_time_seconds, cost_per_second, total_cost, 
                   balance_before, balance_after, created_at, space_id
            FROM computes 
            WHERE user_id = %s 
            ORDER BY created_at DESC 
            LIMIT 100
        """, (user_id,))
        compute_transactions = cursor.fetchall()
        
        # Get transaction history from transactions table (AI operations)
        cursor.execute("""
            SELECT action, ai_model, input_tokens, output_tokens, cost, 
                   balance_before, balance_after, created_at, space_id
            FROM transactions 
            WHERE user_id = %s 
            ORDER BY created_at DESC 
            LIMIT 100
        """, (user_id,))
        ai_transactions = cursor.fetchall()
        
        # Get purchase history from credit_txn table
        cursor.execute("""
            SELECT ct.id, ct.product_id, ct.amount, ct.credits_purchased, 
                   ct.payment_status, ct.stripe_payment_intent_id, 
                   ct.paid_date, ct.created_at,
                   p.name as product_name, p.sku as product_sku
            FROM credit_txn ct
            LEFT JOIN products p ON ct.product_id = p.id
            WHERE ct.user_id = %s 
            ORDER BY ct.created_at DESC 
            LIMIT 100
        """, (user_id,))
        purchase_history = cursor.fetchall()
        
        # Get affiliate statistics
        affiliate_stats = None
        try:
            affiliate = Affiliate()
            affiliate_stats = affiliate.get_affiliate_stats(user_id)
        except Exception as aff_error:
            logger.error(f"Error getting affiliate stats: {aff_error}")
        
        cursor.close()
        
        return render_template('profile.html', 
                             user_info=user_info, 
                             compute_transactions=compute_transactions,
                             ai_transactions=ai_transactions,
                             purchase_history=purchase_history,
                             affiliate_stats=affiliate_stats,
                             advertisement_html=advertisement_html,
                             advertisement_bg=advertisement_bg)
                             
    except Exception as e:
        logger.error(f"Error loading profile: {e}", exc_info=True)
        flash('Error loading profile. Please try again.', 'error')
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
        
        # Get basic stats with error handling
        try:
            # Total users
            cursor.execute("SELECT COUNT(*) as total FROM users")
            total_users = cursor.fetchone()['total']
        except Exception as e:
            logger.warning(f"Error getting user count: {e}")
            total_users = 0
        
        try:
            # Total spaces
            cursor.execute("SELECT COUNT(*) as total FROM spaces")
            total_spaces = cursor.fetchone()['total']
        except Exception as e:
            logger.warning(f"Error getting space count: {e}")
            total_spaces = 0
        
        try:
            # Total downloads
            cursor.execute("SELECT SUM(download_cnt) as total FROM spaces")
            total_downloads = cursor.fetchone()['total'] or 0
        except Exception as e:
            logger.warning(f"Error getting download count: {e}")
            total_downloads = 0
        
        try:
            # Total plays
            cursor.execute("SELECT SUM(playback_cnt) as total FROM spaces")
            total_plays = cursor.fetchone()['total'] or 0
        except Exception as e:
            logger.warning(f"Error getting play count: {e}")
            total_plays = 0
        
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
        # Log the full traceback for debugging
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error in admin dashboard: {e}")
        logger.error(f"Full traceback:\n{error_details}")
        
        # Also write to a specific admin error log for easier debugging
        try:
            with open('logs/admin_errors.log', 'a') as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"Admin Dashboard Error - {datetime.datetime.now()}\n")
                f.write(f"User: {session.get('user_id')} (Admin: {session.get('is_admin')})\n")
                f.write(f"Error: {e}\n")
                f.write(f"Traceback:\n{error_details}\n")
        except:
            pass
            
        flash('An error occurred loading the admin dashboard.', 'error')
        return redirect(url_for('index'))

# Template editor routes
@app.route('/templates')
def templates_redirect():
    """Redirect /templates to admin templates editor."""
    return redirect('/admin/templates')

@app.route('/admin/templates')
def admin_templates():
    """Admin template editor page."""
    if not session.get('user_id') or not session.get('is_admin'):
        flash('Admin access required.', 'error')
        return redirect(url_for('index'))
    
    return render_template('admin_template_editor.html')

@app.route('/admin/templates/preview')
def admin_template_preview():
    """Preview a template with sample data (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return "Access denied", 403
    
    template_name = request.args.get('template')
    if not template_name:
        return "No template specified", 400
    
    try:
        # For preview, we'll render the template with some sample data
        # to show how it would look in production
        preview_data = {
            'preview_mode': True,
            'user': {'id': 1, 'username': 'admin', 'email': 'admin@example.com'},
            'spaces': [],  # Empty list for space-related templates
            'messages': ['This is a preview of the template'],
            'config': app.config,
            'now': datetime.datetime.now()
        }
        
        return render_template(template_name, **preview_data)
    except Exception as e:
        logger.error(f"Error previewing template {template_name}: {e}", exc_info=True)
        return f"Error previewing template: {str(e)}", 500

# Dedicated admin pages
@app.route('/admin/tickets')
def admin_tickets():
    """Admin tickets page - for staff and admin to manage support tickets."""
    user_id = session.get('user_id')
    is_admin = session.get('is_admin', False)
    is_staff = session.get('is_staff', False)
    
    if not user_id or not (is_admin or is_staff):
        flash('Staff or admin access required.', 'error')
        return redirect(url_for('index'))
    
    return render_template('admin_tickets.html')

@app.route('/admin/logs')
def admin_logs():
    """Admin logs page - dedicated page for viewing system logs."""
    if not session.get('user_id') or not session.get('is_admin'):
        flash('Admin access required.', 'error')
        return redirect(url_for('index'))
    
    return render_template('admin_logs.html')

@app.route('/admin/sql')
def admin_sql():
    """Admin SQL page - dedicated page for SQL query monitoring."""
    if not session.get('user_id') or not session.get('is_admin'):
        flash('Admin access required.', 'error')
        return redirect(url_for('index'))
    
    return render_template('admin_sql.html')

@app.route('/admin/status')
def admin_status():
    """Admin system status page - dedicated page for system monitoring."""
    if not session.get('user_id') or not session.get('is_admin'):
        flash('Admin access required.', 'error')
        return redirect(url_for('index'))
    
    return render_template('admin_status.html')

# Admin template routes for dynamic loading
@app.route('/admin/templates/logs')
def admin_logs_template():
    """Serve the logs template for dynamic loading."""
    if not session.get('user_id') or not session.get('is_admin'):
        return 'Unauthorized', 403
    return render_template('logs.html')

@app.route('/admin/templates/sql')
def admin_sql_template():
    """Serve the SQL template for dynamic loading."""
    if not session.get('user_id') or not session.get('is_admin'):
        return 'Unauthorized', 403
    return render_template('sql.html')

@app.route('/admin/templates/system-status')
def admin_system_status_template():
    """Serve the system status template for dynamic loading."""
    if not session.get('user_id') or not session.get('is_admin'):
        return 'Unauthorized', 403
    return render_template('system-status.html')

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
                   last_logged_in, created_at, credits,
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
        
        if 'credits' in data:
            updates.append("credits = %s")
            params.append(float(data['credits']))
        
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
        # Check if video generation service is enabled
        if not check_service_enabled('video_generation_enabled'):
            return jsonify({'error': 'Video generation service is temporarily disabled'}), 503
        
        # Check if user is logged in
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Get space details to verify space exists and check ownership
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        cursor.execute("SELECT user_id, cookie_id FROM spaces WHERE space_id = %s", (space_id,))
        space_details = cursor.fetchone()
        cursor.close()
        
        if not space_details:
            return jsonify({'error': 'Space not found'}), 404
        
        # Check user credits before starting expensive video generation
        try:
            from components.AICost import AICost
            ai_cost = AICost()
            
            # Check if user has sufficient credits (estimate $0.10 minimum for video generation)
            user_credits = ai_cost.get_user_balance(user_id)
            min_required_credits = 0.10  # Minimum estimated cost
            
            if user_credits < min_required_credits:
                return jsonify({
                    'error': 'Insufficient credits for video generation',
                    'current_credits': user_credits,
                    'required_credits': min_required_credits
                }), 402  # Payment Required
                
        except Exception as e:
            logger.warning(f"Could not check user credits for video generation: {e}")
            # Continue anyway if credit check fails to avoid breaking existing functionality
        
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
        video_generator = VideoGenerator(downloads_dir=app.config['DOWNLOAD_DIR'])
        
        # Get current user ID if logged in
        user_id = session.get('user_id', 0)
        
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
        
        # Log to video.log as well
        try:
            from components.VideoGenerator import video_logger
            video_logger.error("=" * 60)
            video_logger.error(f"ERROR IN /api/spaces/{space_id}/generate-video ENDPOINT")
            video_logger.error(f"Exception type: {type(e).__name__}")
            video_logger.error(f"Exception message: {str(e)}")
            video_logger.error("Full traceback:")
            import traceback
            video_logger.error(traceback.format_exc())
            video_logger.error("=" * 60)
        except:
            pass
            
        return jsonify({'error': f'Failed to generate video: {str(e)}'}), 500

@app.route('/api/spaces/<space_id>/video-status/<job_id>', methods=['GET'])
def get_video_status(space_id, job_id):
    """Get video generation status."""
    try:
        from components.VideoGenerator import VideoGenerator
        video_generator = VideoGenerator(downloads_dir=app.config['DOWNLOAD_DIR'])
        
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
        video_generator = VideoGenerator(downloads_dir=app.config['DOWNLOAD_DIR'])
        
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

@app.route('/api/spaces/<space_id>/silence-offset', methods=['GET'])
def get_space_silence_offset(space_id):
    """Get silence offset for a space to correct transcription timecodes."""
    try:
        # Look for video generation job files for this space
        import glob
        job_files = glob.glob(f"transcript_jobs/*_video.json")
        
        silence_offset = 0  # Default to no offset
        
        for job_file in job_files:
            try:
                with open(job_file, 'r') as f:
                    job_data = json.load(f)
                
                # Check if this job is for the requested space
                if job_data.get('space_id') == space_id and 'silence_offset' in job_data:
                    silence_offset = job_data['silence_offset']
                    break
                    
            except Exception as e:
                logger.warning(f"Error reading job file {job_file}: {e}")
                continue
        
        return jsonify({
            'space_id': space_id,
            'silence_offset': silence_offset
        })
        
    except Exception as e:
        logger.error(f"Error getting silence offset for space {space_id}: {e}", exc_info=True)
        return jsonify({'error': 'Failed to get silence offset'}), 500

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
            'admin_requested': True,
            'user_id': session.get('user_id', 0)  # Include admin user_id for cost tracking
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

@app.route('/admin/api/branding_config', methods=['GET'])
def admin_get_branding_config():
    """Get branding configuration for video generation."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        # Load branding configuration from mainconfig.json
        config_file = 'mainconfig.json'
        default_config = {
            'brand_name': 'XSpace',
            'brand_color': '#FF6B35',
            'brand_logo_url': None,
            'video_title_branding': 'XSpace Downloader',
            'video_watermark_text': '',
            'font_family': 'Arial',
            'branding_enabled': True,
            'background_color': '#808080'
        }
        
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config = json.load(f)
                # Extract branding-related settings
                branding_config = {
                    'brand_name': config.get('brand_name', default_config['brand_name']),
                    'brand_color': config.get('brand_color', default_config['brand_color']),
                    'brand_logo_url': config.get('brand_logo_url', default_config['brand_logo_url']),
                    'video_title_branding': config.get('video_title_branding', default_config['video_title_branding']),
                    'video_watermark_text': config.get('video_watermark_text', default_config['video_watermark_text']),
                    'font_family': config.get('font_family', default_config['font_family']),
                    'branding_enabled': config.get('branding_enabled', default_config['branding_enabled']),
                    'background_color': config.get('background_color', default_config['background_color'])
                }
                return jsonify({'success': True, 'config': branding_config})
        else:
            return jsonify({'success': True, 'config': default_config})
            
    except Exception as e:
        logger.error(f"Error getting branding config: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/branding_config', methods=['POST'])
def admin_update_branding_config():
    """Update branding configuration for video generation."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Validate color format if provided
        brand_color = data.get('brand_color', '#FF6B35')
        if brand_color and not brand_color.startswith('#'):
            brand_color = '#' + brand_color
        if not re.match(r'^#[0-9A-Fa-f]{6}$', brand_color):
            return jsonify({'success': False, 'error': 'Invalid color format. Use hex format like #FF6B35'}), 400
        
        # Load existing config or create new
        config_file = 'mainconfig.json'
        config = {}
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config = json.load(f)
        
        # Validate background color format if provided
        background_color = data.get('background_color', '#808080')
        if background_color and not background_color.startswith('#'):
            background_color = '#' + background_color
        if not re.match(r'^#[0-9A-Fa-f]{6}$', background_color):
            background_color = '#808080'  # Default fallback for invalid color
        
        # Update branding settings
        config.update({
            'brand_name': data.get('brand_name', 'XSpace'),
            'brand_color': brand_color,
            'brand_logo_url': data.get('brand_logo_url'),
            'video_title_branding': data.get('video_title_branding', 'XSpace Downloader'),
            'video_watermark_text': data.get('video_watermark_text', ''),
            'font_family': data.get('font_family', 'Arial'),
            'branding_enabled': data.get('branding_enabled', True),
            'background_color': background_color
        })
        
        # Save updated config
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        logger.info(f"Branding configuration updated by admin user {session.get('user_id')}")
        return jsonify({'success': True, 'message': 'Branding configuration updated successfully'})
        
    except Exception as e:
        logger.error(f"Error updating branding config: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/spaces/upload', methods=['POST'])
def admin_upload_space_file():
    """Upload MP3/MP4 file for a space."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        space_id = request.form.get('space_id')
        
        if not space_id:
            return jsonify({'success': False, 'error': 'Space ID is required'}), 400
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        # Validate file type
        allowed_extensions = {'mp3', 'mp4', 'wav', 'm4a', 'webm', 'ogg'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            return jsonify({'success': False, 'error': f'Invalid file type. Allowed: {", ".join(allowed_extensions)}'}), 400
        
        # Check if space exists
        space = get_space_component()
        space_data = space.get_space(space_id)
        if not space_data:
            return jsonify({'success': False, 'error': 'Space not found'}), 404
        
        # Generate filename and save path
        filename = f"{space_id}.{file_ext}"
        file_path = os.path.join(app.config['DOWNLOAD_DIR'], filename)
        
        # Ensure downloads directory exists
        os.makedirs(app.config['DOWNLOAD_DIR'], exist_ok=True)
        
        # Save the uploaded file
        file.save(file_path)
        file_size = os.path.getsize(file_path)
        
        # Update database with new file info
        space.update_space(space_id,
            filename=filename,
            format=file_ext,
            status='completed',
            downloaded_at=datetime.datetime.now()
        )
        
        logger.info(f"Admin uploaded file for space {space_id}: {filename} ({file_size} bytes)")
        
        return jsonify({
            'success': True, 
            'message': f'File uploaded successfully: {filename}',
            'filename': filename,
            'size': file_size,
            'format': file_ext
        })
        
    except Exception as e:
        logger.error(f"Error uploading file for space: {e}")
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
    # Debug session state
    logger.info(f"Admin logs API called - user_id: {session.get('user_id')}, is_admin: {session.get('is_admin')}, session: {dict(session)}")
    
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({
            'error': 'Unauthorized', 
            'debug': {
                'user_id': session.get('user_id'),
                'is_admin': session.get('is_admin'),
                'has_session': bool(session)
            }
        }), 403
    
    try:
        offset = int(request.args.get('offset', 0))
        limit = int(request.args.get('limit', 100))
        
        all_log_entries = []
        
        # Try to read from log files first
        logs_dir = Path('/var/www/production/xspacedownload.com/website/htdocs/logs')
        logger.info(f"DEBUG: Starting admin_get_logs, offset={offset}, limit={limit}")
        logger.info(f"DEBUG: Logs directory path: {logs_dir}")
        log_files = []
        
        # Find all log files, prioritizing the main app log
        logger.info(f"DEBUG: Checking logs directory: {logs_dir}, exists: {logs_dir.exists()}")
        if logs_dir.exists():
            found_files = list(logs_dir.glob('*.log'))
            logger.info(f"DEBUG: Found {len(found_files)} log files: {[f.name for f in found_files]}")
            for log_file in found_files:
                if log_file.name in ['app.log', 'xspacedownloader.log']:
                    log_files.insert(0, log_file)  # Main logs first
                else:
                    log_files.append(log_file)
        else:
            logger.warning(f"DEBUG: Logs directory does not exist: {logs_dir}")
        
        # Read logs from files if available
        logger.info(f"DEBUG: Processing {len(log_files)} log files: {[f.name for f in log_files]}")
        for log_file in log_files:
            try:
                logger.info(f"DEBUG: Reading log file: {log_file}")
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    # Get recent lines (last 500 to avoid memory issues)
                    recent_lines = lines[-500:] if len(lines) > 500 else lines
                    
                    logger.info(f"DEBUG: Read {len(lines)} total lines, using {len(recent_lines)} recent lines from {log_file.name}")
                    
                    for line in recent_lines:
                        line = line.strip()
                        if line:  # Skip empty lines
                            all_log_entries.append({
                                'message': line,
                                'source': log_file.stem,
                                'level': 'INFO',
                                'timestamp': None
                            })
                    
                    logger.info(f"DEBUG: Added {len([l for l in recent_lines if l.strip()])} log entries from {log_file.name}")
            except Exception as e:
                logger.warning(f"Error reading log file {log_file}: {e}")
                continue
        
        logger.info(f"DEBUG: Total log entries collected: {len(all_log_entries)}")
        
        # If no log files found, try to read from systemd journal
        if not all_log_entries:
            try:
                import subprocess
                # Get recent logs from gunicorn service
                result = subprocess.run([
                    'journalctl', '-u', 'xspacedownloader-gunicorn.service', 
                    '--no-pager', '--lines', str(limit), '--output', 'json'
                ], capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0:
                    import json
                    for line in result.stdout.strip().split('\n'):
                        if line.strip():
                            try:
                                log_entry = json.loads(line)
                                message = log_entry.get('MESSAGE', '')
                                if message:
                                    # Parse log level from message if possible
                                    level = 'INFO'
                                    if ' - ERROR - ' in message:
                                        level = 'ERROR'
                                    elif ' - WARNING - ' in message:
                                        level = 'WARNING'
                                    elif ' - DEBUG - ' in message:
                                        level = 'DEBUG'
                                    
                                    all_log_entries.append({
                                        'message': message,
                                        'source': 'gunicorn',
                                        'level': level,
                                        'timestamp': log_entry.get('__REALTIME_TIMESTAMP')
                                    })
                            except json.JSONDecodeError:
                                continue
                else:
                    # Fallback to simple journalctl output
                    result = subprocess.run([
                        'journalctl', '-u', 'xspacedownloader-gunicorn.service', 
                        '--no-pager', '--lines', str(limit)
                    ], capture_output=True, text=True, timeout=10)
                    
                    if result.returncode == 0:
                        for line in result.stdout.strip().split('\n'):
                            if line.strip() and not line.startswith('--'):
                                all_log_entries.append({
                                    'message': line.strip(),
                                    'source': 'systemd',
                                    'level': 'INFO',
                                    'timestamp': None
                                })
                                
            except Exception as e:
                logger.warning(f"Error reading from systemd journal: {e}")
                # If all else fails, create a sample log entry
                all_log_entries.append({
                    'message': f"Live logging from systemd journal. Last updated: {datetime.datetime.now().isoformat()}",
                    'source': 'system',
                    'level': 'INFO',
                    'timestamp': datetime.datetime.now().isoformat()
                })
        
        # Sort by most recent (reverse chronological)
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
            'has_more': end_idx < len(all_log_entries),
            'debug_info': {
                'logs_dir_exists': logs_dir.exists(),
                'log_files_found': [f.name for f in logs_dir.glob('*.log')] if logs_dir.exists() else [],
                'total_entries_collected': len(all_log_entries),
                'slice_start': start_idx,
                'slice_end': end_idx,
                'slice_length': len(logs_slice)
            }
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
                
        except ImportError:
            # pynvml not installed - this is fine, not all systems have NVIDIA GPUs
            pass
        except Exception as e:
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
        downloads_dir = Path('/var/www/production/xspacedownload.com/website/xspacedownloader/downloads')
        if downloads_dir.exists():
            for pattern in ['*.mp3', '*.m4a', '*.wav']:
                for file_path in downloads_dir.glob(pattern):
                    try:
                        file_path.unlink()
                        files_deleted.append(file_path.name)
                    except Exception as e:
                        logger.warning(f"[DEV] Error deleting file {file_path}: {e}")
        
        # Clear transcript job files
        transcript_jobs_dir = Path('/var/www/production/xspacedownload.com/website/xspacedownloader/transcript_jobs')
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
    # Load advertisement for all users (logged in or not)
    advertisement_html = None
    advertisement_bg = '#ffffff'
    try:
        ad = Ad.get_active_ad()
        if ad and ad.copy:
            advertisement_html = ad.copy
            advertisement_bg = ad.background_color or '#ffffff'
    except Exception as e:
        logger.warning(f"Error loading advertisement: {e}")
    
    return render_template('faq.html', advertisement_html=advertisement_html, advertisement_bg=advertisement_bg)

@app.route('/admin/api/jobs/<int:job_id>/priority', methods=['PUT'])
def admin_set_job_priority(job_id):
    """Set job priority (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        priority = data.get('priority')
        
        if not priority or priority not in [1, 2, 3, 4, 5]:
            return jsonify({'error': 'Invalid priority. Must be 1-5'}), 400
        
        space = get_space_component()
        success = space.set_job_priority(job_id, priority)
        
        if success:
            # Invalidate caches since queue order might change
            invalidate_all_caches()
            return jsonify({'success': True, 'message': 'Priority updated successfully'})
        else:
            return jsonify({'error': 'Failed to update priority'}), 400
            
    except Exception as e:
        logger.error(f"Error setting job priority: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/jobs/priorities')
def admin_get_priority_options():
    """Get available priority options (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        space = get_space_component()
        priorities = space.get_priority_options()
        return jsonify({'priorities': priorities})
        
    except Exception as e:
        logger.error(f"Error getting priority options: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/queue')
def admin_get_queue():
    """Get download queue with priority information (admin only) - backward compatibility."""
    return admin_get_download_queue()

@app.route('/admin/api/queue/download')
def admin_get_download_queue():
    """Get download queue with priority information (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        space = get_space_component()
        
        # Get pending and in-progress jobs
        pending_jobs = space.list_download_jobs(status='pending', limit=100)
        in_progress_jobs = space.list_download_jobs(status='downloading', limit=50)
        
        # Get completed and failed jobs from last 24 hours
        from datetime import datetime, timedelta
        yesterday = datetime.now() - timedelta(days=1)
        completed_jobs = space.list_download_jobs(status='completed', limit=50, since=yesterday)
        failed_jobs = space.list_download_jobs(status='failed', limit=20, since=yesterday)
        
        # Add priority labels
        priorities = space.get_priority_options()
        for job in pending_jobs + in_progress_jobs + completed_jobs + failed_jobs:
            job['priority_label'] = priorities.get(job.get('priority', 3), 'Normal')
        
        return jsonify({
            'pending': pending_jobs,
            'in_progress': in_progress_jobs,
            'completed': completed_jobs,
            'failed': failed_jobs,
            'priorities': priorities
        })
        
    except Exception as e:
        logger.error(f"Error getting download queue: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/queue/transcription')
def admin_get_transcription_queue():
    """Get transcription queue status (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        import os
        import json
        from pathlib import Path
        from datetime import datetime, timedelta
        
        # Check both old and new locations for transcript jobs
        transcript_jobs_dir_old = Path('/var/www/production/xspacedownload.com/website/xspacedownloader/transcript_jobs')
        transcript_jobs_dir_new = Path('/var/www/production/xspacedownload.com/website/htdocs/transcript_jobs')
        
        if not transcript_jobs_dir_old.exists() and not transcript_jobs_dir_new.exists():
            return jsonify({
                'pending': [],
                'processing': [],
                'completed': [],
                'failed': []
            })
        
        yesterday = datetime.now() - timedelta(days=1)
        
        pending_jobs = []
        processing_jobs = []
        completed_jobs = []
        failed_jobs = []
        
        # Read all job files from both directories
        job_files = []
        if transcript_jobs_dir_old.exists():
            job_files.extend(transcript_jobs_dir_old.glob('*.json'))
        if transcript_jobs_dir_new.exists():
            job_files.extend(transcript_jobs_dir_new.glob('*.json'))
            
        for job_file in job_files:
            try:
                with open(job_file, 'r') as f:
                    job_data = json.load(f)
                
                # Skip video jobs (they have '_video' in filename)
                if '_video' in job_file.name:
                    continue
                    
                status = job_data.get('status', 'unknown')
                created_at = datetime.fromisoformat(job_data.get('created_at', '2020-01-01'))
                
                # Only include recent completed/failed jobs
                if status in ['completed', 'failed'] and created_at < yesterday:
                    continue
                
                job_info = {
                    'job_id': job_data.get('job_id', job_data.get('id')),
                    'space_id': job_data.get('space_id'),
                    'status': status,
                    'progress': job_data.get('progress', 0),
                    'created_at': job_data.get('created_at'),
                    'updated_at': job_data.get('updated_at'),
                    'model': job_data.get('model'),
                    'language': job_data.get('language'),
                    'options': job_data.get('options', {}),
                    'error': job_data.get('error')
                }
                
                if status == 'pending':
                    pending_jobs.append(job_info)
                elif status == 'processing':
                    processing_jobs.append(job_info)
                elif status == 'completed':
                    completed_jobs.append(job_info)
                elif status == 'failed':
                    failed_jobs.append(job_info)
                    
            except Exception as e:
                logger.warning(f"Error reading transcription job file {job_file}: {e}")
                continue
        
        return jsonify({
            'pending': sorted(pending_jobs, key=lambda x: x.get('created_at', '')),
            'processing': sorted(processing_jobs, key=lambda x: x.get('created_at', '')),
            'completed': sorted(completed_jobs, key=lambda x: x.get('updated_at', ''), reverse=True)[:10],
            'failed': sorted(failed_jobs, key=lambda x: x.get('updated_at', ''), reverse=True)[:5]
        })
        
    except Exception as e:
        logger.error(f"Error getting transcription queue: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/queue/translation')
def admin_get_translation_queue():
    """Get translation queue status (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        import os
        import json
        from pathlib import Path
        from datetime import datetime, timedelta
        
        # Translation jobs are part of transcription jobs with translate_to option
        transcript_jobs_dir = Path('/var/www/production/xspacedownload.com/website/xspacedownloader/transcript_jobs')
        # Also check the new translation_jobs directory
        translation_jobs_dir = Path('/var/www/production/xspacedownload.com/website/htdocs/translation_jobs')
        
        if not transcript_jobs_dir.exists() and not translation_jobs_dir.exists():
            return jsonify({
                'pending': [],
                'processing': [],
                'completed': []
            })
        
        yesterday = datetime.now() - timedelta(days=1)
        
        pending_jobs = []
        processing_jobs = []
        completed_jobs = []
        
        # Read all job files and filter for translation jobs from both directories
        job_files = []
        if transcript_jobs_dir.exists():
            job_files.extend(transcript_jobs_dir.glob('*.json'))
        if translation_jobs_dir.exists():
            job_files.extend(translation_jobs_dir.glob('*.json'))
            
        for job_file in job_files:
            try:
                with open(job_file, 'r') as f:
                    job_data = json.load(f)
                
                # Skip video jobs
                if '_video' in job_file.name:
                    continue
                
                # Check if this is a new-style translation job (from translation_jobs dir)
                is_new_translation_job = str(job_file.parent).endswith('translation_jobs')
                
                # For old-style transcription jobs, check if they have translate_to option
                options = job_data.get('options', {})
                if not is_new_translation_job and not options.get('translate_to'):
                    continue
                    
                status = job_data.get('status', 'unknown')
                created_at = datetime.fromisoformat(job_data.get('created_at', '2020-01-01'))
                
                # Only include recent completed jobs
                if status == 'completed' and created_at < yesterday:
                    continue
                
                # Handle different job formats
                if is_new_translation_job:
                    # New translation job format
                    job_info = {
                        'job_id': job_data.get('id'),
                        'space_id': job_data.get('space_id'),
                        'status': status,
                        'progress': job_data.get('progress', 0),
                        'created_at': job_data.get('created_at'),
                        'updated_at': job_data.get('updated_at'),
                        'source_language': job_data.get('source_lang', 'auto'),
                        'target_language': job_data.get('target_lang'),
                        'options': {},
                        'error': job_data.get('error')
                    }
                else:
                    # Old transcription job format with translate_to option
                    job_info = {
                        'job_id': job_data.get('job_id', job_data.get('id')),
                        'space_id': job_data.get('space_id'),
                        'status': status,
                        'progress': job_data.get('progress', 0),
                        'created_at': job_data.get('created_at'),
                        'updated_at': job_data.get('updated_at'),
                        'source_language': job_data.get('language', 'auto'),
                        'target_language': options.get('translate_to'),
                        'options': options,
                        'error': job_data.get('error')
                    }
                
                if status == 'pending':
                    pending_jobs.append(job_info)
                elif status == 'processing':
                    processing_jobs.append(job_info)
                elif status == 'completed':
                    completed_jobs.append(job_info)
                    
            except Exception as e:
                logger.warning(f"Error reading translation job file {job_file}: {e}")
                continue
        
        return jsonify({
            'pending': sorted(pending_jobs, key=lambda x: x.get('created_at', '')),
            'processing': sorted(processing_jobs, key=lambda x: x.get('created_at', '')),
            'completed': sorted(completed_jobs, key=lambda x: x.get('updated_at', ''), reverse=True)[:10]
        })
        
    except Exception as e:
        logger.error(f"Error getting translation queue: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/service_settings', methods=['GET', 'POST'])
def admin_service_settings():
    """Get or update service settings (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        if request.method == 'GET':
            try:
                # Check if table exists first
                cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM information_schema.tables 
                    WHERE table_schema = DATABASE() 
                    AND table_name = 'app_settings'
                """)
                table_exists = cursor.fetchone()['count'] > 0
                
                if not table_exists:
                    logger.warning("app_settings table does not exist")
                    cursor.close()
                    return jsonify({
                        'settings': {
                            'transcription_enabled': {'value': True, 'type': 'boolean', 'description': 'Transcription service enabled by default'},
                            'video_generation_enabled': {'value': True, 'type': 'boolean', 'description': 'Video generation enabled by default'}
                        }
                    })
                
                # Try to ensure default settings exist
                try:
                    cursor.execute("""
                        INSERT IGNORE INTO app_settings (setting_name, setting_value, setting_type, description)
                        VALUES 
                            ('transcription_enabled', 'true', 'boolean', 'Enable/disable transcription service'),
                            ('video_generation_enabled', 'true', 'boolean', 'Enable/disable video generation service')
                    """)
                    space.connection.commit()
                except Exception as insert_error:
                    logger.warning(f"Could not insert default settings: {insert_error}")
                    # Continue anyway - maybe they already exist
                
                # Get current settings
                cursor.execute("""
                    SELECT setting_name, setting_value, setting_type, description
                    FROM app_settings
                    WHERE setting_name IN ('transcription_enabled', 'video_generation_enabled')
                """)
                settings = cursor.fetchall()
                
                # If no settings found, return defaults
                if not settings:
                    cursor.close()
                    return jsonify({
                        'settings': {
                            'transcription_enabled': {'value': True, 'type': 'boolean', 'description': 'Transcription service enabled by default'},
                            'video_generation_enabled': {'value': True, 'type': 'boolean', 'description': 'Video generation enabled by default'}
                        }
                    })
                    
            except Exception as query_error:
                logger.error(f"Error querying app_settings: {query_error}")
                cursor.close()
                # Return defaults on any error
                return jsonify({
                    'settings': {
                        'transcription_enabled': {'value': True, 'type': 'boolean', 'description': 'Transcription service enabled by default'},
                        'video_generation_enabled': {'value': True, 'type': 'boolean', 'description': 'Video generation enabled by default'}
                    }
                })
            
            # Convert to dictionary
            settings_dict = {}
            for setting in settings:
                value = setting['setting_value']
                if setting['setting_type'] == 'boolean':
                    value = value.lower() == 'true'
                settings_dict[setting['setting_name']] = {
                    'value': value,
                    'type': setting['setting_type'],
                    'description': setting['description']
                }
            
            cursor.close()
            return jsonify({'settings': settings_dict})
        
        else:  # POST
            data = request.get_json()
            updated = []
            
            # Update transcription setting
            if 'transcription_enabled' in data:
                value = 'true' if data['transcription_enabled'] else 'false'
                cursor.execute("""
                    UPDATE app_settings 
                    SET setting_value = %s, updated_at = NOW()
                    WHERE setting_name = 'transcription_enabled'
                """, (value,))
                updated.append('transcription_enabled')
            
            # Update video generation setting
            if 'video_generation_enabled' in data:
                value = 'true' if data['video_generation_enabled'] else 'false'
                cursor.execute("""
                    UPDATE app_settings 
                    SET setting_value = %s, updated_at = NOW()
                    WHERE setting_name = 'video_generation_enabled'
                """, (value,))
                updated.append('video_generation_enabled')
            
            space.connection.commit()
            cursor.close()
            
            logger.info(f"Admin updated service settings: {updated}")
            
            return jsonify({
                'success': True,
                'message': f'Updated settings: {", ".join(updated)}',
                'updated': updated
            })
            
    except Exception as e:
        logger.error(f"Error managing service settings: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/system_messages', methods=['GET', 'POST'])
def admin_system_messages():
    """Get or create system messages (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        if request.method == 'GET':
            try:
                # Get all non-deleted messages
                cursor.execute("""
                    SELECT id, message, start_date, end_date, status,
                           created_at, updated_at
                    FROM system_messages
                    WHERE status != -1
                    ORDER BY start_date DESC
                """)
                messages = cursor.fetchall()
                logger.info(f"Admin system messages query returned {len(messages)} messages")
                
                # Log first message structure for debugging
                if messages:
                    logger.info(f"First message keys: {list(messages[0].keys())}")
                
                # Convert datetime objects to strings
                for msg in messages:
                    msg['start_date'] = msg['start_date'].isoformat() if msg['start_date'] else None
                    msg['end_date'] = msg['end_date'].isoformat() if msg['end_date'] else None
                    msg['created_at'] = msg['created_at'].isoformat() if msg['created_at'] else None
                    msg['updated_at'] = msg['updated_at'].isoformat() if msg['updated_at'] else None
                
                cursor.close()
                return jsonify({'messages': messages})
            except Exception as query_error:
                logger.error(f"Error executing admin system messages query: {query_error}", exc_info=True)
                cursor.close()
                # Fallback to simple query if full query fails
                cursor = space.connection.cursor(dictionary=True)
                cursor.execute("SELECT id, message FROM system_messages WHERE status != -1")
                messages = cursor.fetchall()
                cursor.close()
                logger.warning("Falling back to simple system messages query")
                return jsonify({'messages': messages})
        
        else:  # POST - Create new message
            data = request.get_json()
            
            # Validate required fields
            if not all(k in data for k in ['message', 'start_date', 'end_date']):
                return jsonify({'error': 'Missing required fields'}), 400
            
            cursor.execute("""
                INSERT INTO system_messages (message, start_date, end_date, status)
                VALUES (%s, %s, %s, 1)
            """, (data['message'], data['start_date'], data['end_date']))
            
            message_id = cursor.lastrowid
            space.connection.commit()
            cursor.close()
            
            logger.info(f"Admin created system message ID: {message_id}")
            
            return jsonify({
                'success': True,
                'message': 'System message created successfully',
                'id': message_id
            }), 201
            
    except Exception as e:
        logger.error(f"Error managing system messages: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/service_status')
def api_service_status():
    """Get current service status for frontend."""
    try:
        transcription_enabled = check_service_enabled('transcription_enabled')
        video_generation_enabled = check_service_enabled('video_generation_enabled')
        
        return jsonify({
            'transcription_enabled': transcription_enabled,
            'video_generation_enabled': video_generation_enabled,
            'translation_enabled': transcription_enabled  # Translation is part of transcription
        })
        
    except Exception as e:
        logger.error(f"Error getting service status: {e}")
        return jsonify({
            'transcription_enabled': True,
            'video_generation_enabled': True,
            'translation_enabled': True
        })

@app.route('/api/system_messages')
def api_system_messages():
    """Get active system messages for display."""
    try:
        messages = get_active_system_messages()
        return jsonify({'messages': messages})
        
    except Exception as e:
        logger.error(f"Error getting system messages: {e}")
        return jsonify({'messages': []})

@app.route('/admin/api/system_messages/<int:message_id>', methods=['PUT', 'DELETE'])
def admin_update_system_message(message_id):
    """Update or delete a system message (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        if request.method == 'DELETE':
            # Soft delete by setting status to -1
            cursor.execute("""
                UPDATE system_messages 
                SET status = -1, updated_at = NOW()
                WHERE id = %s
            """, (message_id,))
            
            if cursor.rowcount == 0:
                cursor.close()
                return jsonify({'error': 'Message not found'}), 404
            
            space.connection.commit()
            cursor.close()
            
            logger.info(f"Admin deleted system message ID: {message_id}")
            
            return jsonify({
                'success': True,
                'message': 'System message deleted successfully'
            })
        
        else:  # PUT - Update message
            data = request.get_json()
            
            # Build update query dynamically
            update_fields = []
            params = []
            
            if 'message' in data:
                update_fields.append('message = %s')
                params.append(data['message'])
            
            if 'start_date' in data:
                update_fields.append('start_date = %s')
                params.append(data['start_date'])
            
            if 'end_date' in data:
                update_fields.append('end_date = %s')
                params.append(data['end_date'])
            
            if 'status' in data:
                update_fields.append('status = %s')
                params.append(data['status'])
            
            if not update_fields:
                return jsonify({'error': 'No fields to update'}), 400
            
            update_fields.append('updated_at = NOW()')
            params.append(message_id)
            
            query = f"UPDATE system_messages SET {', '.join(update_fields)} WHERE id = %s"
            cursor.execute(query, params)
            
            if cursor.rowcount == 0:
                cursor.close()
                return jsonify({'error': 'Message not found'}), 404
            
            space.connection.commit()
            cursor.close()
            
            logger.info(f"Admin updated system message ID: {message_id}")
            
            return jsonify({
                'success': True,
                'message': 'System message updated successfully'
            })
            
    except Exception as e:
        logger.error(f"Error updating system message: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# Template Management Routes
@app.route('/admin/api/templates', methods=['GET'])
def admin_list_templates():
    """List all templates available for editing (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from components.Template import Template
        template_manager = Template()
        
        templates = template_manager.list_templates()
        info = template_manager.get_template_info()
        
        return jsonify({
            'templates': templates,
            'info': info
        })
    except Exception as e:
        logger.error(f"Error listing templates: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/templates/<template_name>', methods=['GET', 'PUT'])
def admin_template_operations(template_name):
    """Get or update a specific template (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from components.Template import Template
        template_manager = Template()
        
        if request.method == 'GET':
            # Get template content and backups
            template_data = template_manager.get_template_content(template_name)
            return jsonify(template_data)
        
        elif request.method == 'PUT':
            # Update template content
            data = request.get_json()
            content = data.get('content')
            
            if not content:
                return jsonify({'error': 'No content provided'}), 400
            
            # First validate the template
            validation = template_manager.validate_template(content)
            if not validation['valid']:
                return jsonify({
                    'error': 'Template validation failed',
                    'validation': validation
                }), 400
            
            # Save the template
            result = template_manager.save_template(template_name, content)
            return jsonify(result)
            
    except FileNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error in template operation: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/templates/<template_name>/validate', methods=['POST'])
def admin_validate_template(template_name):
    """Validate template syntax without saving (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from components.Template import Template
        template_manager = Template()
        
        data = request.get_json()
        content = data.get('content')
        
        if not content:
            return jsonify({'error': 'No content provided'}), 400
        
        validation = template_manager.validate_template(content)
        return jsonify(validation)
        
    except Exception as e:
        logger.error(f"Error validating template: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/templates/<template_name>/restore', methods=['POST'])
def admin_restore_template(template_name):
    """Restore a template from backup (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from components.Template import Template
        template_manager = Template()
        
        data = request.get_json()
        backup_filename = data.get('backup_filename')
        
        if not backup_filename:
            return jsonify({'error': 'No backup filename provided'}), 400
        
        result = template_manager.restore_backup(template_name, backup_filename)
        return jsonify(result)
        
    except FileNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error restoring template: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/templates/cache/clear', methods=['POST'])
def admin_clear_template_cache():
    """Clear template cache (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from components.Template import Template
        template_manager = Template()
        
        # Clear the template cache
        template_manager._clear_template_cache()
        
        return jsonify({
            'success': True,
            'message': 'Template cache cleared successfully'
        })
        
    except Exception as e:
        logger.error(f"Error clearing template cache: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# Ticket Management API Routes (for staff and admin)
@app.route('/admin/api/tickets', methods=['GET'])
def admin_api_tickets():
    """Get tickets list for admin/staff management."""
    user_id = session.get('user_id')
    is_admin = session.get('is_admin', False)
    is_staff = session.get('is_staff', False)
    
    if not user_id or not (is_admin or is_staff):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        status_filter = request.args.get('status', 'all')
        
        with open('db_config.json', 'r') as f:
            config = json.load(f)
        db_config = config['mysql']
        
        from components.Ticket import Ticket
        ticket_manager = Ticket(db_config)
        
        # Build query based on status filter
        if status_filter == 'open':
            query = """
                SELECT t.*, u.email as user_email, u.email, 
                       COALESCE(s.email, '') as staff_email,
                       CASE 
                           WHEN t.priority = 3 THEN 'Critical'
                           WHEN t.priority = 2 THEN 'High'
                           WHEN t.priority = 1 THEN 'Medium'
                           ELSE 'Normal'
                       END as priority_label
                FROM tickets t
                LEFT JOIN users u ON t.user_id = u.id
                LEFT JOIN users s ON t.responded_by_staff_id = s.id
                WHERE t.status IN (0, 1)
                ORDER BY t.priority DESC, t.opened_at DESC
            """
        elif status_filter == 'closed':
            query = """
                SELECT t.*, u.email as user_email, u.email,
                       COALESCE(s.email, '') as staff_email,
                       CASE 
                           WHEN t.priority = 3 THEN 'Critical'
                           WHEN t.priority = 2 THEN 'High'
                           WHEN t.priority = 1 THEN 'Medium'
                           ELSE 'Normal'
                       END as priority_label
                FROM tickets t
                LEFT JOIN users u ON t.user_id = u.id
                LEFT JOIN users s ON t.responded_by_staff_id = s.id
                WHERE t.status = 2
                ORDER BY t.last_updated_by_staff DESC
                LIMIT 100
            """
        else:  # all
            query = """
                SELECT t.*, u.email as user_email, u.email,
                       COALESCE(s.email, '') as staff_email,
                       CASE 
                           WHEN t.priority = 3 THEN 'Critical'
                           WHEN t.priority = 2 THEN 'High'
                           WHEN t.priority = 1 THEN 'Medium'
                           ELSE 'Normal'
                       END as priority_label
                FROM tickets t
                LEFT JOIN users u ON t.user_id = u.id
                LEFT JOIN users s ON t.responded_by_staff_id = s.id
                WHERE t.status >= 0
                ORDER BY t.opened_at DESC
                LIMIT 200
            """
        
        ticket_manager.cursor.execute(query)
        tickets = ticket_manager.cursor.fetchall()
        
        # Process tickets for JSON serialization
        for ticket in tickets:
            # Convert datetime objects to ISO format
            for field in ['opened_at', 'last_updated_by_owner', 'response_date', 'last_updated_by_staff']:
                if ticket.get(field) and hasattr(ticket[field], 'isoformat'):
                    ticket[field] = ticket[field].isoformat()
            
            # Parse JSON fields
            if ticket.get('issue_detail'):
                try:
                    ticket['issue_detail'] = json.loads(ticket['issue_detail']) if isinstance(ticket['issue_detail'], str) else ticket['issue_detail']
                except:
                    ticket['issue_detail'] = {'detail': ticket['issue_detail']}
            
            if ticket.get('response'):
                try:
                    ticket['response'] = json.loads(ticket['response']) if isinstance(ticket['response'], str) else ticket['response']
                except:
                    ticket['response'] = []
        
        ticket_manager.close()
        
        return jsonify({
            'tickets': tickets,
            'total': len(tickets)
        })
        
    except Exception as e:
        logger.error(f"Error fetching tickets for admin: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/tickets/<int:ticket_id>/respond', methods=['POST'])
def admin_api_ticket_respond(ticket_id):
    """Admin/staff respond to a ticket."""
    user_id = session.get('user_id')
    is_admin = session.get('is_admin', False)
    is_staff = session.get('is_staff', False)
    
    if not user_id or not (is_admin or is_staff):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        response_text = data.get('response', '').strip()
        
        if not response_text:
            return jsonify({'error': 'Response text is required'}), 400
        
        with open('db_config.json', 'r') as f:
            config = json.load(f)
        db_config = config['mysql']
        
        from components.Ticket import Ticket
        ticket_manager = Ticket(db_config)
        
        result = ticket_manager.add_response(ticket_id, user_id, response_text)
        ticket_manager.close()
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error responding to ticket: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/tickets/<int:ticket_id>/status', methods=['PUT'])
def admin_api_ticket_status(ticket_id):
    """Update ticket status (admin/staff only)."""
    user_id = session.get('user_id')
    is_admin = session.get('is_admin', False)
    is_staff = session.get('is_staff', False)
    
    if not user_id or not (is_admin or is_staff):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        new_status = data.get('status')
        
        if new_status is None:
            return jsonify({'error': 'Status is required'}), 400
        
        # Validate status values
        valid_statuses = {
            0: 'open',
            1: 'responded', 
            2: 'closed',
            -1: 'deleted by owner',
            -9: 'deleted by staff',
            -6: 'archived'
        }
        
        if new_status not in valid_statuses:
            return jsonify({'error': 'Invalid status value'}), 400
        
        with open('db_config.json', 'r') as f:
            config = json.load(f)
        db_config = config['mysql']
        
        from components.Ticket import Ticket
        ticket_manager = Ticket(db_config)
        
        # Update ticket status
        ticket_manager.cursor.execute("""
            UPDATE tickets 
            SET status = %s, last_updated_by_staff = NOW()
            WHERE id = %s
        """, (new_status, ticket_id))
        
        ticket_manager.conn.commit()
        
        # Add a system response if closing ticket
        if new_status == 2:  # closed
            ticket_manager.add_response(ticket_id, user_id, "[System: Ticket closed by staff]")
        
        ticket_manager.close()
        
        return jsonify({
            'success': True,
            'message': f'Ticket status updated to {valid_statuses[new_status]}'
        })
        
    except Exception as e:
        logger.error(f"Error updating ticket status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# Stripe Configuration Routes
@app.route('/admin/api/stripe_config', methods=['GET', 'POST'])
def admin_stripe_config():
    """Get or update Stripe configuration (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from components.EnvManager import EnvManager
        env_manager = EnvManager()
        
        if request.method == 'GET':
            # Get current Stripe configuration
            config = env_manager.get_stripe_config()
            
            # Don't send actual keys in response for security
            return jsonify({
                'success': True,
                'config': {
                    'mode': config['mode'],
                    'test': {
                        'has_publishable_key': config['test']['has_publishable_key'],
                        'has_secret_key': config['test']['has_secret_key'],
                        'has_webhook_secret': config['test']['has_webhook_secret'],
                        'publishable_key_preview': config['test']['publishable_key'][:20] + '...' if config['test']['publishable_key'] else '',
                        'secret_key_preview': config['test']['secret_key'][:20] + '...' if config['test']['secret_key'] else '',
                        'webhook_secret_preview': config['test']['webhook_secret'][:20] + '...' if config['test']['webhook_secret'] else ''
                    },
                    'live': {
                        'has_publishable_key': config['live']['has_publishable_key'],
                        'has_secret_key': config['live']['has_secret_key'],
                        'has_webhook_secret': config['live']['has_webhook_secret'],
                        'publishable_key_preview': config['live']['publishable_key'][:20] + '...' if config['live']['publishable_key'] else '',
                        'secret_key_preview': config['live']['secret_key'][:20] + '...' if config['live']['secret_key'] else '',
                        'webhook_secret_preview': config['live']['webhook_secret'][:20] + '...' if config['live']['webhook_secret'] else ''
                    },
                    'env_file_path': env_manager.get_env_file_path()
                }
            })
        
        elif request.method == 'POST':
            # Update Stripe configuration
            data = request.get_json()
            
            mode = data.get('mode')
            test_keys = data.get('test_keys')
            live_keys = data.get('live_keys')
            
            # Validate at least one update is provided
            if not any([mode, test_keys, live_keys]):
                return jsonify({'error': 'At least one configuration update must be provided'}), 400
            
            # Update configuration
            result = env_manager.update_stripe_config(
                mode=mode,
                test_keys=test_keys,
                live_keys=live_keys
            )
            
            if 'error' in result:
                return jsonify({'error': result['error']}), 400
            
            logger.info(f"Admin user {session['user_id']} updated Stripe configuration")
            
            return jsonify({
                'success': True,
                'message': 'Stripe configuration updated successfully'
            })
        
    except Exception as e:
        logger.error(f"Error handling Stripe config: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/queue/video')
def admin_get_video_queue():
    """Get video generation queue status (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        import os
        import json
        from pathlib import Path
        from datetime import datetime, timedelta
        
        transcript_jobs_dir = Path('/var/www/production/xspacedownload.com/website/xspacedownloader/transcript_jobs')
        if not transcript_jobs_dir.exists():
            return jsonify({
                'pending': [],
                'processing': [],
                'completed': []
            })
        
        yesterday = datetime.now() - timedelta(days=1)
        
        pending_jobs = []
        processing_jobs = []
        completed_jobs = []
        
        # Read all video job files
        for job_file in transcript_jobs_dir.glob('*_video.json'):
            try:
                with open(job_file, 'r') as f:
                    job_data = json.load(f)
                    
                status = job_data.get('status', 'unknown')
                created_at = datetime.fromisoformat(job_data.get('created_at', '2020-01-01'))
                
                # Only include recent completed jobs
                if status == 'completed' and created_at < yesterday:
                    continue
                
                job_info = {
                    'job_id': job_data.get('job_id', job_data.get('id')),
                    'space_id': job_data.get('space_id'),
                    'user_id': job_data.get('user_id'),
                    'status': status,
                    'progress': job_data.get('progress', 0),
                    'created_at': job_data.get('created_at'),
                    'updated_at': job_data.get('updated_at'),
                    'video_path': job_data.get('video_path'),
                    'error': job_data.get('error')
                }
                
                if status == 'pending':
                    pending_jobs.append(job_info)
                elif status == 'processing':
                    processing_jobs.append(job_info)
                elif status == 'completed':
                    completed_jobs.append(job_info)
                    
            except Exception as e:
                logger.warning(f"Error reading video job file {job_file}: {e}")
                continue
        
        return jsonify({
            'pending': sorted(pending_jobs, key=lambda x: x.get('created_at', '')),
            'processing': sorted(processing_jobs, key=lambda x: x.get('created_at', '')),
            'completed': sorted(completed_jobs, key=lambda x: x.get('updated_at', ''), reverse=True)[:10]
        })
        
    except Exception as e:
        logger.error(f"Error getting video queue: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/queue/tts')
def admin_get_tts_queue():
    """Get TTS queue status (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from datetime import datetime, timedelta
        
        # Get database connection
        db_manager = get_db_manager()
        connection = db_manager.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Get current time and yesterday for filtering
        yesterday = datetime.now() - timedelta(days=1)
        
        # Get pending jobs
        cursor.execute("""
            SELECT id, space_id, user_id, target_language, status, progress, 
                   created_at, updated_at, error_message, output_file
            FROM tts_jobs 
            WHERE status = 'pending' 
            ORDER BY priority DESC, created_at ASC 
            LIMIT 100
        """)
        pending_jobs = cursor.fetchall()
        
        # Get in-progress jobs
        cursor.execute("""
            SELECT id, space_id, user_id, target_language, status, progress, 
                   created_at, updated_at, error_message, output_file
            FROM tts_jobs 
            WHERE status = 'in_progress' 
            ORDER BY updated_at DESC 
            LIMIT 50
        """)
        in_progress_jobs = cursor.fetchall()
        
        # Get completed jobs from last 24 hours
        cursor.execute("""
            SELECT id, space_id, user_id, target_language, status, progress, 
                   created_at, updated_at, completed_at, output_file
            FROM tts_jobs 
            WHERE status = 'completed' AND updated_at >= %s
            ORDER BY completed_at DESC 
            LIMIT 20
        """, (yesterday,))
        completed_jobs = cursor.fetchall()
        
        # Get failed jobs from last 24 hours
        cursor.execute("""
            SELECT id, space_id, user_id, target_language, status, progress, 
                   created_at, updated_at, failed_at, error_message
            FROM tts_jobs 
            WHERE status = 'failed' AND updated_at >= %s
            ORDER BY failed_at DESC 
            LIMIT 10
        """, (yesterday,))
        failed_jobs = cursor.fetchall()
        
        # Convert datetime objects to strings for JSON serialization
        def format_job(job):
            if job:
                for key in ['created_at', 'updated_at', 'completed_at', 'failed_at']:
                    if job.get(key):
                        job[key] = job[key].isoformat()
            return job
        
        pending_jobs = [format_job(job) for job in pending_jobs]
        in_progress_jobs = [format_job(job) for job in in_progress_jobs]
        completed_jobs = [format_job(job) for job in completed_jobs]
        failed_jobs = [format_job(job) for job in failed_jobs]
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'pending': pending_jobs,
            'in_progress': in_progress_jobs,
            'completed': completed_jobs,
            'failed': failed_jobs
        })
        
    except Exception as e:
        logger.error(f"Error getting TTS queue: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/cache/status')
def admin_cache_status():
    """Get cache status information (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        current_time = time.time()
        
        # Calculate cache ages and time until expiration
        spaces_cache_age = current_time - spaces_cache['timestamp'] if spaces_cache['timestamp'] > 0 else None
        spaces_cache_expires = spaces_cache['ttl'] - spaces_cache_age if spaces_cache_age is not None else None
        
        index_cache_age = current_time - index_cache['timestamp'] if index_cache['timestamp'] > 0 else None
        index_cache_expires = index_cache['ttl'] - index_cache_age if index_cache_age is not None else None
        
        return jsonify({
            'spaces_cache': {
                'active': spaces_cache['data'] is not None,
                'age_seconds': round(spaces_cache_age, 1) if spaces_cache_age else None,
                'expires_in_seconds': round(spaces_cache_expires, 1) if spaces_cache_expires and spaces_cache_expires > 0 else None,
                'ttl': spaces_cache['ttl']
            },
            'index_cache': {
                'active': index_cache['data'] is not None,
                'age_seconds': round(index_cache_age, 1) if index_cache_age else None,
                'expires_in_seconds': round(index_cache_expires, 1) if index_cache_expires and index_cache_expires > 0 else None,
                'ttl': index_cache['ttl']
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting cache status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/transcription/<job_id>')
def admin_get_transcription_job(job_id):
    """Get transcription job details (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        import os
        import json
        from pathlib import Path
        
        transcript_jobs_dir = Path('./transcript_jobs')
        job_file = transcript_jobs_dir / f"{job_id}.json"
        
        if not job_file.exists():
            return jsonify({'error': 'Job not found'}), 404
        
        with open(job_file, 'r') as f:
            job_data = json.load(f)
        
        return jsonify({
            'success': True,
            'job': job_data
        })
        
    except Exception as e:
        logger.error(f"Error getting transcription job {job_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/transcription/<job_id>/cancel', methods=['DELETE'])
def admin_cancel_transcription_job(job_id):
    """Cancel a transcription job (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        import os
        import json
        from pathlib import Path
        
        transcript_jobs_dir = Path('./transcript_jobs')
        job_file = transcript_jobs_dir / f"{job_id}.json"
        
        if not job_file.exists():
            return jsonify({'error': 'Job not found'}), 404
        
        # Load job data
        with open(job_file, 'r') as f:
            job_data = json.load(f)
        
        # Check if job can be cancelled
        if job_data.get('status') not in ['pending', 'processing']:
            return jsonify({'error': 'Job cannot be cancelled in its current state'}), 400
        
        # Update job status to cancelled
        from datetime import datetime
        job_data['status'] = 'cancelled'
        job_data['updated_at'] = datetime.now().isoformat()
        job_data['error'] = 'Cancelled by admin'
        
        # Save updated job data
        with open(job_file, 'w') as f:
            json.dump(job_data, f, indent=4)
        
        # Create a signal file for background processes to check
        signal_file = Path(f'./temp/cancel_{job_id}.signal')
        signal_file.parent.mkdir(exist_ok=True)
        signal_file.touch()
        
        logger.info(f"Admin user {session.get('user_id')} cancelled transcription job {job_id}")
        
        return jsonify({
            'success': True,
            'message': 'Job cancelled successfully'
        })
        
    except Exception as e:
        logger.error(f"Error cancelling transcription job {job_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/translation/<job_id>')
def admin_get_translation_job(job_id):
    """Get translation job details (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        import os
        import json
        from pathlib import Path
        
        transcript_jobs_dir = Path('./transcript_jobs')
        job_file = transcript_jobs_dir / f"{job_id}.json"
        
        if not job_file.exists():
            return jsonify({'error': 'Job not found'}), 404
        
        with open(job_file, 'r') as f:
            job_data = json.load(f)
        
        # Check if this is actually a translation job
        options = job_data.get('options', {})
        if not options.get('translate_to'):
            return jsonify({'error': 'Not a translation job'}), 400
        
        return jsonify({
            'success': True,
            'job': job_data
        })
        
    except Exception as e:
        logger.error(f"Error getting translation job {job_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/video/<job_id>')
def admin_get_video_job(job_id):
    """Get video generation job details (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        import os
        import json
        from pathlib import Path
        
        transcript_jobs_dir = Path('./transcript_jobs')
        job_file = transcript_jobs_dir / f"{job_id}_video.json"
        
        if not job_file.exists():
            return jsonify({'error': 'Job not found'}), 404
        
        with open(job_file, 'r') as f:
            job_data = json.load(f)
        
        return jsonify({
            'success': True,
            'job': job_data
        })
        
    except Exception as e:
        logger.error(f"Error getting video job {job_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/translation/<job_id>/cancel', methods=['DELETE'])
def admin_cancel_translation_job(job_id):
    """Cancel a translation job (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        import os
        import json
        from pathlib import Path
        
        transcript_jobs_dir = Path('./transcript_jobs')
        job_file = transcript_jobs_dir / f"{job_id}.json"
        
        if not job_file.exists():
            return jsonify({'error': 'Translation job not found'}), 404
        
        with open(job_file, 'r') as f:
            job_data = json.load(f)
        
        # Verify this is a translation job
        if not job_data.get('options', {}).get('translate_to'):
            return jsonify({'error': 'This is not a translation job'}), 400
        
        # Check if job can be cancelled
        current_status = job_data.get('status', '')
        if current_status not in ['pending', 'processing']:
            return jsonify({'error': f'Cannot cancel job with status: {current_status}'}), 400
        
        # Update job status to cancelled
        job_data['status'] = 'cancelled'
        job_data['updated_at'] = datetime.datetime.now().isoformat()
        job_data['error'] = 'Job cancelled by admin'
        
        with open(job_file, 'w') as f:
            json.dump(job_data, f, indent=2)
        
        # Create a signal file for background processes to check
        signal_file = Path(f'./temp/cancel_{job_id}.signal')
        signal_file.parent.mkdir(exist_ok=True)
        signal_file.touch()
        
        logger.info(f"Translation job {job_id} cancelled by admin")
        
        return jsonify({
            'success': True,
            'message': 'Translation job cancelled successfully'
        })
        
    except Exception as e:
        logger.error(f"Error cancelling translation job {job_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/video/<job_id>/cancel', methods=['DELETE'])
def admin_cancel_video_job(job_id):
    """Cancel a video generation job (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        import os
        import json
        from pathlib import Path
        
        transcript_jobs_dir = Path('./transcript_jobs')
        job_file = transcript_jobs_dir / f"{job_id}_video.json"
        
        if not job_file.exists():
            return jsonify({'error': 'Video job not found'}), 404
        
        with open(job_file, 'r') as f:
            job_data = json.load(f)
        
        # Check if job can be cancelled
        current_status = job_data.get('status', '')
        if current_status not in ['pending', 'processing']:
            return jsonify({'error': f'Cannot cancel job with status: {current_status}'}), 400
        
        # Update job status to cancelled
        job_data['status'] = 'cancelled'
        job_data['updated_at'] = datetime.datetime.now().isoformat()
        job_data['error'] = 'Job cancelled by admin'
        
        with open(job_file, 'w') as f:
            json.dump(job_data, f, indent=2)
        
        # Create a signal file for background processes to check
        signal_file = Path(f'./temp/cancel_{job_id}.signal')
        signal_file.parent.mkdir(exist_ok=True)
        signal_file.touch()
        
        logger.info(f"Video job {job_id} cancelled by admin")
        
        return jsonify({
            'success': True,
            'message': 'Video job cancelled successfully'
        })
        
    except Exception as e:
        logger.error(f"Error cancelling video job {job_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/download/<int:job_id>/cancel', methods=['DELETE'])
def admin_cancel_download_job(job_id):
    """Cancel a download job (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        import os
        import signal
        import time
        
        # Get Space component to access download job methods
        space = get_space_component()
        
        # Get job details first
        cursor = space.connection.cursor(dictionary=True)
        query = "SELECT * FROM space_download_scheduler WHERE id = %s"
        cursor.execute(query, (job_id,))
        job = cursor.fetchone()
        cursor.close()
        
        if not job:
            return jsonify({'error': 'Download job not found'}), 404
        
        # Check if job can be cancelled
        if job['status'] in ['completed', 'failed']:
            return jsonify({'error': f'Cannot cancel job with status: {job["status"]}'}), 400
        
        # Try to terminate the process if it's running
        process_killed = False
        if job['process_id']:
            try:
                # Send SIGTERM first (graceful termination)
                os.kill(job['process_id'], signal.SIGTERM)
                logger.info(f"Sent SIGTERM to process {job['process_id']} for job {job_id}")
                
                # Wait a bit for graceful termination
                time.sleep(1.0)
                
                # Check if process is still running
                try:
                    os.kill(job['process_id'], 0)  # Check if process exists
                    # Process still running, force kill
                    os.kill(job['process_id'], signal.SIGKILL)
                    logger.info(f"Sent SIGKILL to process {job['process_id']} for job {job_id}")
                    process_killed = True
                except OSError:
                    # Process already terminated
                    process_killed = True
                    logger.info(f"Process {job['process_id']} for job {job_id} already terminated")
                    
            except OSError as e:
                # Process doesn't exist or can't be killed
                logger.warning(f"Could not kill process {job['process_id']} for job {job_id}: {e}")
        
        # Update job status to cancelled in database
        cursor = space.connection.cursor()
        update_query = """
            UPDATE space_download_scheduler 
            SET status = 'failed', 
                error_message = 'Job cancelled by admin',
                end_time = NOW(),
                updated_at = NOW()
            WHERE id = %s
        """
        cursor.execute(update_query, (job_id,))
        space.connection.commit()
        cursor.close()
        
        # Create a signal file for background processes to check
        signal_file = Path(f'./temp/cancel_{job_id}.signal')
        signal_file.parent.mkdir(exist_ok=True)
        signal_file.touch()
        
        logger.info(f"Download job {job_id} cancelled by admin (process_killed: {process_killed})")
        
        return jsonify({
            'success': True,
            'message': 'Download job cancelled successfully',
            'process_killed': process_killed
        })
        
    except Exception as e:
        logger.error(f"Error cancelling download job {job_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/download/<int:job_id>/remove', methods=['DELETE'])
def admin_remove_download_job(job_id):
    """Remove a completed download job record (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        # Get Space component
        space = get_space_component()
        
        # Get job details first to check status
        cursor = space.connection.cursor(dictionary=True)
        query = "SELECT * FROM space_download_scheduler WHERE id = %s"
        cursor.execute(query, (job_id,))
        job = cursor.fetchone()
        cursor.close()
        
        if not job:
            return jsonify({'error': 'Download job not found'}), 404
        
        # Only allow removal of completed or failed jobs
        if job['status'] not in ['completed', 'failed']:
            return jsonify({'error': 'Can only remove completed or failed jobs'}), 400
        
        # Delete the job record
        cursor = space.connection.cursor()
        delete_query = "DELETE FROM space_download_scheduler WHERE id = %s"
        cursor.execute(delete_query, (job_id,))
        space.connection.commit()
        cursor.close()
        
        logger.info(f"Download job {job_id} removed by admin")
        
        return jsonify({
            'success': True,
            'message': 'Download job record removed successfully'
        })
        
    except Exception as e:
        logger.error(f"Error removing download job {job_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/transcription/<job_id>/remove', methods=['DELETE'])
def admin_remove_transcription_job(job_id):
    """Remove a completed transcription job record (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        import os
        import json
        from pathlib import Path
        
        transcript_jobs_dir = Path('./transcript_jobs')
        job_file = transcript_jobs_dir / f"{job_id}.json"
        
        if not job_file.exists():
            return jsonify({'error': 'Transcription job not found'}), 404
        
        # Read job data to check status
        with open(job_file, 'r') as f:
            job_data = json.load(f)
        
        # Only allow removal of completed, failed, or cancelled jobs
        if job_data.get('status') not in ['completed', 'failed', 'cancelled']:
            return jsonify({'error': 'Can only remove completed, failed, or cancelled jobs'}), 400
        
        # Remove the job file
        job_file.unlink()
        
        # Also remove any associated video job file if it exists
        video_job_file = transcript_jobs_dir / f"{job_id}_video.json"
        if video_job_file.exists():
            video_job_file.unlink()
        
        logger.info(f"Transcription job {job_id} removed by admin")
        
        return jsonify({
            'success': True,
            'message': 'Transcription job record removed successfully'
        })
        
    except Exception as e:
        logger.error(f"Error removing transcription job {job_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/translation/<job_id>/remove', methods=['DELETE'])
def admin_remove_translation_job(job_id):
    """Remove a completed translation job record (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        import os
        import json
        from pathlib import Path
        
        transcript_jobs_dir = Path('./transcript_jobs')
        job_file = transcript_jobs_dir / f"{job_id}.json"
        
        if not job_file.exists():
            return jsonify({'error': 'Translation job not found'}), 404
        
        # Read job data to verify it's a translation job and check status
        with open(job_file, 'r') as f:
            job_data = json.load(f)
        
        # Verify this is a translation job
        if not job_data.get('options', {}).get('translate_to'):
            return jsonify({'error': 'This is not a translation job'}), 400
        
        # Only allow removal of completed, failed, or cancelled jobs
        if job_data.get('status') not in ['completed', 'failed', 'cancelled']:
            return jsonify({'error': 'Can only remove completed, failed, or cancelled jobs'}), 400
        
        # Remove the job file
        job_file.unlink()
        
        logger.info(f"Translation job {job_id} removed by admin")
        
        return jsonify({
            'success': True,
            'message': 'Translation job record removed successfully'
        })
        
    except Exception as e:
        logger.error(f"Error removing translation job {job_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/video/<job_id>/remove', methods=['DELETE'])
def admin_remove_video_job(job_id):
    """Remove a completed video job record (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        import os
        import json
        from pathlib import Path
        
        transcript_jobs_dir = Path('./transcript_jobs')
        job_file = transcript_jobs_dir / f"{job_id}_video.json"
        
        if not job_file.exists():
            return jsonify({'error': 'Video job not found'}), 404
        
        # Read job data to check status
        with open(job_file, 'r') as f:
            job_data = json.load(f)
        
        # Only allow removal of completed, failed, or cancelled jobs
        if job_data.get('status') not in ['completed', 'failed', 'cancelled']:
            return jsonify({'error': 'Can only remove completed, failed, or cancelled jobs'}), 400
        
        # Remove the job file
        job_file.unlink()
        
        logger.info(f"Video job {job_id} removed by admin")
        
        return jsonify({
            'success': True,
            'message': 'Video job record removed successfully'
        })
        
    except Exception as e:
        logger.error(f"Error removing video job {job_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/cache/clear', methods=['POST'])
def admin_clear_cache():
    """Clear all caches (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        # Clear all caches
        invalidate_all_caches()
        
        # Also remove any trigger files
        trigger_file = Path('./temp/cache_invalidate.trigger')
        if trigger_file.exists():
            trigger_file.unlink()
        
        logger.info(f"Admin user {session.get('user_id')} cleared all caches")
        
        return jsonify({
            'success': True,
            'message': 'All caches have been cleared successfully'
        })
        
    except Exception as e:
        logger.error(f"Error clearing caches: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/system_status')
def admin_system_status():
    """Get comprehensive system status (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        import psutil
        import os
        import time
        from datetime import datetime
        
        # Get CPU usage
        cpu_usage = round(psutil.cpu_percent(interval=1), 1)
        
        # Get memory usage
        memory = psutil.virtual_memory()
        memory_usage = round(memory.percent, 1)
        
        # Get disk usage
        disk = psutil.disk_usage('/')
        disk_usage = round((disk.used / disk.total) * 100, 1)
        
        # Get uptime
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        if uptime_seconds < 3600:
            uptime = f"{int(uptime_seconds / 60)}m"
        elif uptime_seconds < 86400:
            uptime = f"{int(uptime_seconds / 3600)}h {int((uptime_seconds % 3600) / 60)}m"
        else:
            days = int(uptime_seconds / 86400)
            hours = int((uptime_seconds % 86400) / 3600)
            uptime = f"{days}d {hours}h"
        
        # Get system info
        os_info = f"{os.uname().sysname} {os.uname().release}"
        python_version = f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}"
        
        # Get Flask version
        try:
            import flask
            flask_version = flask.__version__
        except:
            flask_version = "Unknown"
        
        # Get load average
        try:
            load_avg = os.getloadavg()
            load_average = f"{load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}"
        except:
            load_average = "N/A"
        
        # Get current time
        server_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Check database connection
        db_status = "Unknown"
        db_connections = "N/A"
        db_queries = "N/A"
        cache_hit_rate = "N/A"
        
        try:
            space = get_space_component()
            if space and space.connection:
                db_status = "Connected"
                # Try to get some basic stats
                cursor = space.connection.cursor(dictionary=True)
                cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
                result = cursor.fetchone()
                if result:
                    db_connections = result['Value']
                
                cursor.execute("SHOW STATUS LIKE 'Queries'")
                result = cursor.fetchone()
                if result:
                    db_queries = result['Value']
                    
                cursor.close()
        except Exception as e:
            logger.warning(f"Could not get database status: {e}")
            db_status = "Error"
        
        # Get background processes
        processes = []
        process_names = ['background_transcribe.py', 'background_translate.py', 'bg_downloader.py', 'bg_progress_watcher.py']
        
        for proc_name in process_names:
            found = False
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time', 'memory_info', 'cpu_percent']):
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if proc_name in cmdline:
                        processes.append({
                            'name': proc_name.replace('.py', '').replace('_', ' ').title(),
                            'status': 'running',
                            'pid': proc.info['pid'],
                            'cpu': round(proc.info['cpu_percent'], 1),
                            'memory': round(proc.info['memory_info'].rss / 1024 / 1024, 1),
                            'started': datetime.fromtimestamp(proc.info['create_time']).strftime('%Y-%m-%d %H:%M:%S')
                        })
                        found = True
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if not found:
                processes.append({
                    'name': proc_name.replace('.py', '').replace('_', ' ').title(),
                    'status': 'stopped',
                    'pid': 'N/A',
                    'cpu': 'N/A',
                    'memory': 'N/A',
                    'started': 'N/A'
                })
        
        return jsonify({
            'cpu_usage': cpu_usage,
            'memory_usage': memory_usage,
            'disk_usage': disk_usage,
            'uptime': uptime,
            'os_info': os_info,
            'python_version': python_version,
            'flask_version': flask_version,
            'server_time': server_time,
            'load_average': load_average,
            'db_status': db_status,
            'db_connections': db_connections,
            'db_queries': db_queries,
            'cache_hit_rate': cache_hit_rate,
            'processes': processes
        })
        
    except Exception as e:
        logger.error(f"Error getting system status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# SQL Logging API endpoints
@app.route('/admin/api/sql_logging_status')
def admin_sql_logging_status():
    """Get SQL logging status (admin only)."""
    # Debug session state
    logger.info(f"SQL logging status API called - user_id: {session.get('user_id')}, is_admin: {session.get('is_admin')}")
    
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({
            'error': 'Unauthorized',
            'debug': {
                'user_id': session.get('user_id'),
                'is_admin': session.get('is_admin'),
                'has_session': bool(session)
            }
        }), 403
    
    try:
        if not SQL_LOGGER_AVAILABLE:
            return jsonify({'enabled': False, 'error': 'SQL Logger not available'}), 200
        
        enabled = sql_logger.is_enabled()
        return jsonify({'enabled': enabled})
        
    except Exception as e:
        logger.error(f"Error checking SQL logging status: {e}", exc_info=True)
        return jsonify({'enabled': False, 'error': str(e)}), 200

@app.route('/admin/api/toggle_sql_logging', methods=['POST'])
def admin_toggle_sql_logging():
    """Toggle SQL logging on/off (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        if not SQL_LOGGER_AVAILABLE:
            return jsonify({'error': 'SQL Logger not available'}), 500
        
        data = request.json
        enabled = data.get('enabled', False)
        
        if enabled:
            success = sql_logger.enable_logging()
            action = 'enabled'
        else:
            success = sql_logger.disable_logging()
            action = 'disabled'
        
        if success:
            logger.info(f"Admin user {session.get('user_id')} {action} SQL logging")
            return jsonify({'success': True, 'message': f'SQL logging {action}'})
        else:
            return jsonify({'error': f'Failed to {action[:-1]} SQL logging'}), 500
            
    except Exception as e:
        logger.error(f"Error toggling SQL logging: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/sql_logs')
def admin_get_sql_logs():
    """Get SQL query logs (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        if not SQL_LOGGER_AVAILABLE:
            return jsonify({'error': 'SQL Logger not available', 'logs': []}), 200
        
        logs = sql_logger.get_logs()
        stats = sql_logger.get_stats()
        
        return jsonify({
            'logs': logs,
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Error getting SQL logs: {e}", exc_info=True)
        return jsonify({'error': str(e), 'logs': []}), 200

@app.route('/admin/api/clear_sql_logs', methods=['POST'])
def admin_clear_sql_logs():
    """Clear SQL query logs (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        if not SQL_LOGGER_AVAILABLE:
            return jsonify({'error': 'SQL Logger not available'}), 500
        
        sql_logger.clear_logs()
        logger.info(f"Admin user {session.get('user_id')} cleared SQL logs")
        
        return jsonify({'success': True, 'message': 'SQL logs cleared'})
        
    except Exception as e:
        logger.error(f"Error clearing SQL logs: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/sql-logging/enable', methods=['POST'])
def admin_enable_sql_logging():
    """Enable SQL query logging (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        if not SQL_LOGGER_AVAILABLE:
            return jsonify({'error': 'SQL Logger not available'}), 500
        
        success = sql_logger.enable_logging()
        if success:
            logger.info(f"Admin user {session.get('user_id')} enabled SQL logging")
            return jsonify({'success': True, 'message': 'SQL logging enabled'})
        else:
            return jsonify({'error': 'Failed to enable SQL logging'}), 500
        
    except Exception as e:
        logger.error(f"Error enabling SQL logging: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/sql-logging/disable', methods=['POST'])
def admin_disable_sql_logging():
    """Disable SQL query logging (admin only)."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        if not SQL_LOGGER_AVAILABLE:
            return jsonify({'error': 'SQL Logger not available'}), 500
        
        success = sql_logger.disable_logging()
        if success:
            logger.info(f"Admin user {session.get('user_id')} disabled SQL logging")
            return jsonify({'success': True, 'message': 'SQL logging disabled'})
        else:
            return jsonify({'error': 'Failed to disable SQL logging'}), 500
        
    except Exception as e:
        logger.error(f"Error disabling SQL logging: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/admin/api/administrator-guide', methods=['GET'])
def admin_administrator_guide():
    """Return administrator guide as HTML."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        import markdown
        from datetime import datetime
        import os
        
        # Read the markdown file
        guide_path = os.path.join(os.path.dirname(__file__), 'ADMINISTRATOR_GUIDE.md')
        
        if not os.path.exists(guide_path):
            return 'Administrator Guide not found. Please ensure ADMINISTRATOR_GUIDE.md exists.', 404
        
        with open(guide_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        
        # Replace template variables
        current_date = datetime.now().strftime('%B %d, %Y')
        markdown_content = markdown_content.replace('{{ current_date }}', current_date)
        
        # Convert markdown to HTML
        html_content = markdown.markdown(
            markdown_content,
            extensions=[
                'markdown.extensions.tables',
                'markdown.extensions.fenced_code',
                'markdown.extensions.toc',
                'markdown.extensions.codehilite'
            ]
        )
        
        return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}
        
    except ImportError:
        return 'Markdown library not available. Please install: pip install markdown', 500
    except Exception as e:
        logger.error(f"Error serving administrator guide: {e}", exc_info=True)
        return f'Error loading administrator guide: {str(e)}', 500

@app.route('/admin/api/administrator-guide/download', methods=['GET'])
def admin_administrator_guide_download():
    """Return administrator guide as downloadable markdown file."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from datetime import datetime
        import os
        
        # Read the markdown file
        guide_path = os.path.join(os.path.dirname(__file__), 'ADMINISTRATOR_GUIDE.md')
        
        if not os.path.exists(guide_path):
            return 'Administrator Guide not found. Please ensure ADMINISTRATOR_GUIDE.md exists.', 404
        
        with open(guide_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        
        # Replace template variables
        current_date = datetime.now().strftime('%B %d, %Y')
        markdown_content = markdown_content.replace('{{ current_date }}', current_date)
        
        # Return as downloadable file
        response = Response(
            markdown_content,
            mimetype='text/markdown',
            headers={
                'Content-Disposition': f'attachment; filename="XSpace_Downloader_Administrator_Guide_{datetime.now().strftime("%Y%m%d")}.md"'
            }
        )
        return response
        
    except Exception as e:
        logger.error(f"Error downloading administrator guide: {e}", exc_info=True)
        return f'Error downloading administrator guide: {str(e)}', 500

# Cost Management API Endpoints
@app.route('/admin/api/compute_cost', methods=['GET', 'POST'])
def admin_compute_cost():
    """Get or update compute cost settings."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from components.DatabaseManager import DatabaseManager
        db = DatabaseManager()
        
        if request.method == 'GET':
            # Get current compute cost setting
            with db.get_connection() as connection:
                cursor = connection.cursor(dictionary=True)
                
                cursor.execute("""
                    SELECT setting_value FROM app_settings 
                    WHERE setting_name = 'compute_cost_per_second'
                """)
                result = cursor.fetchone()
                cursor.close()
            
            cost_per_second = float(result['setting_value']) if result else 0.001
            return jsonify({'cost_per_second': cost_per_second})
            
        else:  # POST
            data = request.get_json()
            cost_per_second = float(data.get('cost_per_second', 0.001))
            
            with db.get_connection() as connection:
                cursor = connection.cursor()
                
                # Update or insert the setting
                cursor.execute("""
                    INSERT INTO app_settings (setting_name, setting_value, setting_type, description)
                    VALUES ('compute_cost_per_second', %s, 'decimal', 'Cost per second for compute operations')
                    ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
                """, (str(cost_per_second),))
                
                connection.commit()
                cursor.close()
            
            logger.info(f"Admin updated compute cost to ${cost_per_second}/second")
            
            return jsonify({
                'success': True,
                'cost_per_second': cost_per_second,
                'message': f'Compute cost updated to ${cost_per_second}/second'
            })
            
    except Exception as e:
        logger.error(f"Error managing compute cost: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/ai_costs', methods=['GET'])
def admin_get_ai_costs():
    """Get all AI model costs."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from components.DatabaseManager import DatabaseManager
        db = DatabaseManager()
        
        # Get connection directly from pool without context manager
        connection = db.pool.get_connection()
        
        try:
            cursor = connection.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT id, vendor, model, input_token_cost_per_million_tokens, 
                       output_token_cost_per_million_tokens, updated_at
                FROM ai_api_cost
                ORDER BY vendor, model
            """)
            
            costs = cursor.fetchall()
            cursor.close()
            
            if costs is None:
                costs = []
            
            return jsonify({'costs': costs})
            
        finally:
            connection.close()  # Return to pool
        
    except Exception as e:
        logger.error(f"Error getting AI costs: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/ai_costs', methods=['POST'])
def admin_add_ai_cost():
    """Add or update AI model cost."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        vendor = data.get('vendor')
        model = data.get('model')
        input_cost = float(data.get('input_cost', 0))
        output_cost = float(data.get('output_cost', 0))
        
        if not vendor or not model:
            return jsonify({'error': 'Vendor and model are required'}), 400
        
        from components.DatabaseManager import DatabaseManager
        db = DatabaseManager()
        
        with db.get_connection() as connection:
            cursor = connection.cursor()
            
            cursor.execute("""
                INSERT INTO ai_api_cost 
                (vendor, model, input_token_cost_per_million_tokens, output_token_cost_per_million_tokens)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                input_token_cost_per_million_tokens = VALUES(input_token_cost_per_million_tokens),
                output_token_cost_per_million_tokens = VALUES(output_token_cost_per_million_tokens),
                updated_at = NOW()
            """, (vendor, model, input_cost, output_cost))
            
            connection.commit()
            cursor.close()
        
        logger.info(f"Admin added/updated AI cost: {vendor}/{model}")
        
        return jsonify({
            'success': True,
            'message': f'AI model cost updated: {vendor}/{model}'
        })
        
    except Exception as e:
        logger.error(f"Error adding AI cost: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/ai_costs/<int:cost_id>', methods=['GET'])
def get_ai_cost(cost_id):
    """Get a specific AI cost entry."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from components.DatabaseManager import DatabaseManager
        db = DatabaseManager()
        
        # Get connection directly from pool without context manager
        connection = db.pool.get_connection()
        
        try:
            cursor = connection.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT id, vendor, model, input_token_cost_per_million_tokens, 
                       output_token_cost_per_million_tokens, created_at, updated_at
                FROM ai_api_cost 
                WHERE id = %s
            """, (cost_id,))
            
            cost = cursor.fetchone()
            cursor.close()
            
            if not cost:
                return jsonify({'error': 'AI cost entry not found'}), 404
            
            return jsonify({
                'success': True,
                'cost': cost
            })
            
        finally:
            connection.close()  # Return to pool
        
    except Exception as e:
        logger.error(f"Error getting AI cost: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/ai_costs/<int:cost_id>', methods=['PUT'])
def update_ai_cost(cost_id):
    """Update a specific AI cost entry."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        vendor = data.get('vendor', '').strip()
        model = data.get('model', '').strip()
        input_cost = float(data.get('input_token_cost_per_million_tokens', 0))
        output_cost = float(data.get('output_token_cost_per_million_tokens', 0))
        
        if not vendor or not model:
            return jsonify({'error': 'Vendor and model are required'}), 400
        
        if input_cost < 0 or output_cost < 0:
            return jsonify({'error': 'Costs cannot be negative'}), 400
        
        from components.DatabaseManager import DatabaseManager
        db = DatabaseManager()
        
        # Get connection directly from pool without context manager
        connection = db.pool.get_connection()
        
        try:
            cursor = connection.cursor()
            
            # Check if the cost entry exists
            cursor.execute("SELECT id FROM ai_api_cost WHERE id = %s", (cost_id,))
            if not cursor.fetchone():
                cursor.close()
                connection.close()
                return jsonify({'error': 'AI cost entry not found'}), 404
            
            # Update the entry
            cursor.execute("""
                UPDATE ai_api_cost 
                SET vendor = %s, model = %s, 
                    input_token_cost_per_million_tokens = %s, 
                    output_token_cost_per_million_tokens = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (vendor, model, input_cost, output_cost, cost_id))
            
            connection.commit()
            cursor.close()
            
            logger.info(f"Admin updated AI cost ID {cost_id}: {vendor}/{model}")
            
            return jsonify({
                'success': True,
                'message': f'AI model cost updated: {vendor}/{model}'
            })
            
        finally:
            connection.close()  # Return to pool
        
    except Exception as e:
        logger.error(f"Error updating AI cost: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/ai_costs/<int:cost_id>', methods=['DELETE'])
def delete_ai_cost(cost_id):
    """Delete a specific AI cost entry."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from components.DatabaseManager import DatabaseManager
        db = DatabaseManager()
        
        # Get connection directly from pool without context manager
        connection = db.pool.get_connection()
        
        try:
            cursor = connection.cursor()
            
            # Check if the cost entry exists
            cursor.execute("SELECT vendor, model FROM ai_api_cost WHERE id = %s", (cost_id,))
            result = cursor.fetchone()
            if not result:
                cursor.close()
                connection.close()
                return jsonify({'error': 'AI cost entry not found'}), 404
            
            vendor, model = result
            
            # Delete the entry
            cursor.execute("DELETE FROM ai_api_cost WHERE id = %s", (cost_id,))
            connection.commit()
            cursor.close()
            
            logger.info(f"Admin deleted AI cost ID {cost_id}: {vendor}/{model}")
            
            return jsonify({
                'success': True,
                'message': f'AI model cost deleted: {vendor}/{model}'
            })
            
        finally:
            connection.close()  # Return to pool
        
    except Exception as e:
        logger.error(f"Error deleting AI cost: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/credit_stats', methods=['GET'])
def admin_credit_stats():
    """Get credit statistics and cost analytics."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from components.DatabaseManager import DatabaseManager
        db = DatabaseManager()
        
        # Get connection directly from pool without context manager
        connection = db.pool.get_connection()
        
        try:
            cursor = connection.cursor(dictionary=True)
            
            # Get user credit statistics
            cursor.execute("""
                SELECT 
                    COUNT(*) as user_count,
                    COALESCE(SUM(credits), 0) as total_credits,
                    COALESCE(AVG(credits), 0) as avg_credits,
                    COALESCE(MIN(credits), 0) as min_credits,
                    COALESCE(MAX(credits), 0) as max_credits
                FROM users 
                WHERE status = 1
            """)
            credit_stats = cursor.fetchone()
            
            # Get cost breakdown by type (last 30 days) - calculate from individual columns
            cursor.execute("""
                SELECT 
                    SUM(mp3_compute_cost) as mp3_total,
                    SUM(mp4_compute_cost) as mp4_total,
                    SUM(transcription_cost) as transcription_total,
                    SUM(translation_cost) as translation_total
                FROM space_cost 
                WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
            """)
            cost_result = cursor.fetchone()
            
            cost_by_type = {}
            if cost_result:
                cost_by_type = {
                    'mp3_compute': float(cost_result['mp3_total'] or 0),
                    'mp4_compute': float(cost_result['mp4_total'] or 0),
                    'transcription': float(cost_result['transcription_total'] or 0),
                    'translation': float(cost_result['translation_total'] or 0)
                }
            
            # For vendor breakdown, combine compute costs as 'compute' vendor
            total_compute = cost_by_type.get('mp3_compute', 0) + cost_by_type.get('mp4_compute', 0)
            total_ai = cost_by_type.get('transcription', 0) + cost_by_type.get('translation', 0)
            
            cost_by_vendor = {
                'compute': total_compute,
                'openai': total_ai  # Assuming transcription/translation use OpenAI
            }
            
            cursor.close()
            
            # Handle case where no credit stats found
            if not credit_stats:
                credit_stats = {
                    'user_count': 0,
                    'total_credits': 0,
                    'avg_credits': 0,
                    'min_credits': 0,
                    'max_credits': 0
                }
            
            return jsonify({
                'user_count': credit_stats['user_count'],
                'total_credits': float(credit_stats['total_credits']),
                'avg_credits': float(credit_stats['avg_credits']),
                'min_credits': float(credit_stats['min_credits']),
                'max_credits': float(credit_stats['max_credits']),
                'cost_by_type': cost_by_type,
                'cost_by_vendor': cost_by_vendor
            })
            
        finally:
            connection.close()  # Return to pool
        
    except Exception as e:
        logger.error(f"Error getting credit stats: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/add_weekly_credits', methods=['POST'])
def admin_add_weekly_credits():
    """Add $5 credits to all active users."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from components.DatabaseManager import DatabaseManager
        db = DatabaseManager()
        
        with db.get_connection() as connection:
            cursor = connection.cursor()
            
            # Add $5 to all active users
            cursor.execute("""
                UPDATE users 
                SET credits = credits + 5.00,
                    updated_at = NOW()
                WHERE status = 1
            """)
            
            users_updated = cursor.rowcount
            connection.commit()
            cursor.close()
        
        logger.info(f"Admin added $5 credits to {users_updated} users")
        
        return jsonify({
            'success': True,
            'users_updated': users_updated,
            'credits_added': 5.00,
            'total_credits_added': users_updated * 5.00,
            'message': f'Added $5 credits to {users_updated} active users'
        })
        
    except Exception as e:
        logger.error(f"Error adding weekly credits: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/update_openai_pricing', methods=['POST'])
def admin_update_openai_pricing():
    """Update OpenAI pricing from external API."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        import subprocess
        import os
        
        # Run the OpenAI pricing update script
        script_path = os.path.join(os.path.dirname(__file__), 'update_openai_pricing.py')
        if not os.path.exists(script_path):
            return jsonify({'error': 'OpenAI pricing update script not found'}), 404
        
        # Run the script and capture output
        # Check if we're in a virtual environment and use the correct Python
        python_executable = sys.executable
        
        # If we're in a venv, make sure to use that Python
        venv_python = os.path.join(os.path.dirname(__file__), 'venv', 'bin', 'python')
        if os.path.exists(venv_python):
            python_executable = venv_python
        
        result = subprocess.run([
            python_executable, script_path
        ], capture_output=True, text=True, timeout=60, cwd=os.path.dirname(__file__))
        
        if result.returncode == 0:
            logger.info(f"Admin successfully updated OpenAI pricing")
            
            # Count how many models were updated
            lines = result.stdout.split('\n')
            updated_count = 0
            for line in lines:
                if 'models updated' in line.lower():
                    try:
                        updated_count = int(line.split(':')[1].split('models')[0].strip())
                    except:
                        pass
            
            return jsonify({
                'success': True,
                'message': f'OpenAI pricing updated successfully. {updated_count} models updated.',
                'output': result.stdout
            })
        else:
            logger.error(f"OpenAI pricing update failed: {result.stderr}")
            return jsonify({
                'error': 'Failed to update OpenAI pricing',
                'details': result.stderr
            }), 500
            
    except subprocess.TimeoutExpired:
        logger.error("OpenAI pricing update timed out")
        return jsonify({'error': 'Update request timed out'}), 500
    except Exception as e:
        logger.error(f"Error updating OpenAI pricing: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# Test route to verify ads routes are loaded
@app.route('/test-ads-routes')
def test_ads_routes():
    """Test route to check if ads routes are registered."""
    routes = []
    for rule in app.url_map.iter_rules():
        if '/admin/ads' in rule.rule:
            routes.append(f"{rule.rule} -> {rule.endpoint}")
    return f"Ads routes found: {routes}"

# Simple test route that should always work
@app.route('/simple-test')
def simple_test():
    return "Simple test works!"

# Admin page to manage ads
@app.route('/admin/ads')
def admin_ads_page():
    """Render the ads management page."""
    try:
        # Check if user is logged in and is admin
        if not session.get('user_id') or not session.get('is_admin'):
            flash('Admin access required.', 'error')
            return redirect(url_for('index'))
            
        ads = Ad.get_all_ads()
        ads_list = []
        for ad in ads:
            ads_list.append({
                'id': ad['id'],
                'copy': ad['copy'],
                'background_color': ad.get('background_color', '#ffffff'),
                'start_date': ad['start_date'].strftime('%Y-%m-%d %H:%M:%S') if ad['start_date'] else '',
                'end_date': ad['end_date'].strftime('%Y-%m-%d %H:%M:%S') if ad['end_date'] else '',
                'status': ad['status'],
                'status_text': 'Active' if ad['status'] == 1 else 'Suspended' if ad['status'] == -9 else 'Pending' if ad['status'] == 0 else 'Deleted',
                'impressions': ad['impression_count'],
                'max_impressions': ad['max_impressions'] or 'Unlimited',
                'created_at': ad['created_at'].strftime('%Y-%m-%d %H:%M:%S') if ad['created_at'] else '',
                'updated_at': ad['updated_at'].strftime('%Y-%m-%d %H:%M:%S') if ad['updated_at'] else ''
            })
        return render_template('admin_ads.html', ads=ads_list)
    except Exception as e:
        logger.error(f"Error loading ads page: {e}", exc_info=True)
        flash('Error loading ads', 'danger')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/ads/create', methods=['POST'])
def admin_ads_create():
    """Create a new ad."""
    try:
        # Check if user is logged in and is admin
        if not session.get('user_id') or not session.get('is_admin'):
            flash('Admin access required.', 'error')
            return redirect(url_for('index'))
        ad = Ad()
        ad.copy = request.form.get('copy', '')
        ad.background_color = request.form.get('background_color', '#ffffff')
        
        # Handle datetime format from datetime-local input
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        
        # Try multiple datetime formats to handle both datetime-local and standard formats
        for fmt in ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
            try:
                ad.start_date = datetime.datetime.strptime(start_date_str, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Invalid start date format: {start_date_str}")
            
        for fmt in ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
            try:
                ad.end_date = datetime.datetime.strptime(end_date_str, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Invalid end date format: {end_date_str}")
        
        max_impressions_str = request.form.get('max_impressions', '').strip()
        ad.max_impressions = int(max_impressions_str) if max_impressions_str else 0
        ad.status = 0  # Start as pending
        
        ad.save()
        flash('Advertisement created successfully!', 'success')
    except Exception as e:
        logger.error(f"Error creating ad: {e}", exc_info=True)
        flash(f'Error creating ad: {str(e)}', 'danger')
    
    return redirect(url_for('admin_ads_page'))

@app.route('/admin/ads/<int:ad_id>/activate', methods=['POST'])
def admin_ads_activate(ad_id):
    """Activate an ad."""
    try:
        # Check if user is logged in and is admin
        if not session.get('user_id') or not session.get('is_admin'):
            flash('Admin access required.', 'error')
            return redirect(url_for('index'))
        ad = Ad(ad_id)
        ad.activate()
        flash('Advertisement activated!', 'success')
    except Exception as e:
        logger.error(f"Error activating ad: {e}", exc_info=True)
        flash(f'Error activating ad: {str(e)}', 'danger')
    
    return redirect(url_for('admin_ads_page'))

@app.route('/admin/ads/<int:ad_id>/suspend', methods=['POST'])
def admin_ads_suspend(ad_id):
    """Suspend an ad."""
    try:
        # Check if user is logged in and is admin
        if not session.get('user_id') or not session.get('is_admin'):
            flash('Admin access required.', 'error')
            return redirect(url_for('index'))
        ad = Ad(ad_id)
        ad.suspend()
        flash('Advertisement suspended!', 'warning')
    except Exception as e:
        logger.error(f"Error suspending ad: {e}", exc_info=True)
        flash(f'Error suspending ad: {str(e)}', 'danger')
    
    return redirect(url_for('admin_ads_page'))

@app.route('/admin/ads/<int:ad_id>/delete', methods=['POST'])
def admin_ads_delete(ad_id):
    """Delete an ad."""
    try:
        # Check if user is logged in and is admin
        if not session.get('user_id') or not session.get('is_admin'):
            flash('Admin access required.', 'error')
            return redirect(url_for('index'))
        ad = Ad(ad_id)
        ad.delete()
        flash('Advertisement deleted!', 'success')
    except Exception as e:
        logger.error(f"Error deleting ad: {e}", exc_info=True)
        flash(f'Error deleting ad: {str(e)}', 'danger')
    
    return redirect(url_for('admin_ads_page'))

@app.route('/admin/ads/<int:ad_id>/edit', methods=['POST'])
def admin_ads_edit(ad_id):
    """Edit an existing ad."""
    try:
        # Check if user is logged in and is admin
        if not session.get('user_id') or not session.get('is_admin'):
            flash('Admin access required.', 'error')
            return redirect(url_for('index'))
        
        ad = Ad(ad_id)
        if not ad.copy:
            flash('Advertisement not found.', 'danger')
            return redirect(url_for('admin_ads_page'))
        
        # Update ad properties
        ad.copy = request.form.get('copy', '')
        ad.background_color = request.form.get('background_color', '#ffffff')
        
        # Handle datetime format from datetime-local input
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        
        # Try multiple datetime formats to handle both datetime-local and standard formats
        for fmt in ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
            try:
                ad.start_date = datetime.datetime.strptime(start_date_str, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Invalid start date format: {start_date_str}")
            
        for fmt in ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
            try:
                ad.end_date = datetime.datetime.strptime(end_date_str, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Invalid end date format: {end_date_str}")
        
        max_impressions_str = request.form.get('max_impressions', '').strip()
        ad.max_impressions = int(max_impressions_str) if max_impressions_str else 0
        
        ad.save()
        flash('Advertisement updated successfully!', 'success')
    except Exception as e:
        logger.error(f"Error updating ad: {e}", exc_info=True)
        flash(f'Error updating ad: {str(e)}', 'danger')
    
    return redirect(url_for('admin_ads_page'))

# Route for About page
@app.route('/about')
def about():
    """Display the About page."""
    # Load advertisement for all users (logged in or not)
    advertisement_html = None
    advertisement_bg = '#ffffff'
    try:
        ad = Ad.get_active_ad()
        if ad and ad.copy:
            advertisement_html = ad.copy
            advertisement_bg = ad.background_color or '#ffffff'
    except Exception as e:
        logger.warning(f"Error loading advertisement: {e}")
    
    return render_template('about.html', advertisement_html=advertisement_html, advertisement_bg=advertisement_bg)

# Route to check transcription job status for a space
@app.route('/api/transcribe/<space_id>/status', methods=['GET'])
def check_transcription_status(space_id):
    """Check if there's a pending/in-progress transcription job for a space."""
    try:
        from pathlib import Path
        import json
        
        transcript_jobs_dir = Path('./transcript_jobs')
        
        if not transcript_jobs_dir.exists():
            return jsonify({
                'has_pending_job': False,
                'status': None,
                'job_id': None
            })
        
        # Check for existing job
        for job_file in transcript_jobs_dir.glob('*.json'):
            try:
                with open(job_file, 'r') as f:
                    job_data = json.load(f)
                    if (job_data.get('space_id') == space_id and 
                        job_data.get('status') in ['pending', 'in_progress', 'processing']):
                        return jsonify({
                            'has_pending_job': True,
                            'status': job_data.get('status'),
                            'job_id': job_data.get('id'),
                            'created_at': job_data.get('created_at'),
                            'language': job_data.get('language', 'en')
                        })
            except Exception as e:
                logger.error(f"Error reading transcript job file {job_file}: {e}")
        
        return jsonify({
            'has_pending_job': False,
            'status': None,
            'job_id': None
        })
        
    except Exception as e:
        logger.error(f"Error checking transcription status for space {space_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# Route for transcribing a space
@app.route('/api/transcribe/<space_id>', methods=['POST'])
@app.route('/spaces/<space_id>/transcribe', methods=['POST'])
def transcribe_space(space_id):
    """Submit a space for transcription."""
    try:
        # Check if transcription service is enabled
        if not check_service_enabled('transcription_enabled'):
            if request.is_json:
                return jsonify({'error': 'Transcription service is temporarily disabled'}), 503
            flash('Transcription service is temporarily disabled', 'warning')
            return redirect(url_for('space_page', space_id=space_id))
        
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
                        # Check if this job is for the same space and is still pending/in_progress/processing
                        if (job_data.get('space_id') == space_id and 
                            job_data.get('status') in ['pending', 'in_progress', 'processing']):
                            existing_job = job_data
                            logger.warning(f"Found existing job {job_data.get('id')} for space {space_id} with status {job_data.get('status')}")
                            break
                except Exception as e:
                    logger.error(f"Error reading job file {job_file}: {e}")
        
        # If there's already a pending/in_progress job, don't create a new one
        if existing_job:
            logger.warning(f"Rejecting duplicate transcription request for space {space_id} - existing job: {existing_job.get('id')}")
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
        
        # Get user_id for cost tracking
        user_id = session.get('user_id', 0)
        
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
            'updated_at': datetime.datetime.now().isoformat(),
            'user_id': user_id  # Include user_id for cost tracking in background process
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

@app.route('/api/translate/queue', methods=['POST'])
def queue_translation():
    """Queue a translation job for background processing."""
    try:
        # Check if translation service is enabled
        if not check_service_enabled('transcription_enabled'):
            return jsonify({'error': 'Translation service is temporarily disabled'}), 503
        
        if not TRANSLATE_AVAILABLE:
            return jsonify({'error': 'Translation service is not available'}), 503
        
        # Check if user is logged in
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Validate request
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400
        
        # Get request data
        data = request.json
        space_id = data.get('space_id')
        source_lang = data.get('source_lang', 'auto')
        target_lang = data.get('target_lang')
        
        # Validate required fields
        if not space_id:
            return jsonify({'error': 'Missing space_id parameter'}), 400
        if not target_lang:
            return jsonify({'error': 'Missing target_lang parameter'}), 400
        
        # Check if transcript exists for this space
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        # Check for English transcript first
        query = "SELECT * FROM space_transcripts WHERE space_id = %s AND language LIKE 'en%'"
        cursor.execute(query, (space_id,))
        transcript = cursor.fetchone()
        
        if not transcript:
            cursor.close()
            return jsonify({'error': 'No transcript found for this space'}), 404
        
        # Format target language consistently
        if target_lang and len(target_lang) == 2:
            target_lang_formatted = f"{target_lang}-{target_lang.upper()}"
        else:
            target_lang_formatted = target_lang
        
        # Check if translation already exists
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
            return jsonify({
                'error': 'Translation already exists',
                'existing_language': existing_translation['language']
            }), 409
        
        # Create translation jobs directory if it doesn't exist
        os.makedirs('/var/www/production/xspacedownload.com/website/htdocs/translation_jobs', exist_ok=True)
        
        # Check for existing pending jobs
        from pathlib import Path
        translation_jobs_dir = Path('/var/www/production/xspacedownload.com/website/htdocs/translation_jobs')
        existing_job = None
        
        if translation_jobs_dir.exists():
            for job_file in translation_jobs_dir.glob('*.json'):
                try:
                    with open(job_file, 'r') as f:
                        job_data = json.load(f)
                        if (job_data.get('space_id') == space_id and 
                            job_data.get('target_lang') == target_lang_formatted and
                            job_data.get('status') in ['pending', 'in_progress']):
                            existing_job = job_data
                            break
                except Exception as e:
                    logger.error(f"Error reading translation job file {job_file}: {e}")
        
        if existing_job:
            return jsonify({
                'error': 'Translation job already in progress',
                'job_id': existing_job.get('id'),
                'status': existing_job.get('status')
            }), 409
        
        # Create translation job
        import uuid
        import datetime
        
        job_id = str(uuid.uuid4())
        job_data = {
            'id': job_id,
            'space_id': space_id,
            'user_id': user_id,
            'source_lang': source_lang,
            'target_lang': target_lang_formatted,
            'transcript_text': transcript['transcript'],
            'status': 'pending',
            'progress': 0,
            'created_at': datetime.datetime.now().isoformat(),
            'updated_at': datetime.datetime.now().isoformat()
        }
        
        # Save job file
        job_file = Path(f'/var/www/production/xspacedownload.com/website/htdocs/translation_jobs/{job_id}.json')
        with open(job_file, 'w') as f:
            json.dump(job_data, f)
        
        logger.info(f"Created translation job {job_id} for space {space_id} to {target_lang_formatted}")
        
        return jsonify({
            'job_id': job_id,
            'status': 'pending',
            'message': 'Translation job queued for background processing'
        })
        
    except Exception as e:
        logger.error(f"Error queuing translation: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/tts/generate', methods=['POST'])
def generate_tts():
    """Generate text-to-speech audio from transcript."""
    try:
        data = request.get_json()
        space_id = data.get('space_id')
        language = data.get('language', 'en')
        transcript_id = data.get('transcript_id')
        
        if not space_id:
            return jsonify({'error': 'Space ID is required'}), 400
        
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User must be logged in'}), 401
        
        # Get space component
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        # Get transcript text
        cursor.execute("""
            SELECT transcript, language as original_language
            FROM transcripts 
            WHERE space_id = %s AND language = %s
            LIMIT 1
        """, (space_id, language))
        
        transcript = cursor.fetchone()
        if not transcript:
            cursor.close()
            return jsonify({'error': 'Transcript not found for specified language'}), 404
        
        transcript_text = transcript['transcript']
        if not transcript_text or len(transcript_text.strip()) < 10:
            cursor.close()
            return jsonify({'error': 'Transcript text is too short for TTS generation'}), 400
        
        # Check for existing TTS job
        cursor.execute("""
            SELECT id, status, output_file
            FROM tts_jobs 
            WHERE space_id = %s AND target_language = %s AND user_id = %s
            AND status IN ('pending', 'in_progress', 'completed')
            ORDER BY created_at DESC
            LIMIT 1
        """, (space_id, language, user_id))
        
        existing_job = cursor.fetchone()
        if existing_job:
            if existing_job['status'] in ['pending', 'in_progress']:
                cursor.close()
                return jsonify({
                    'error': 'TTS job already in progress',
                    'job_id': existing_job['id'],
                    'status': existing_job['status']
                }), 409
            elif existing_job['status'] == 'completed':
                cursor.close()
                return jsonify({
                    'error': 'TTS already exists for this transcript',
                    'job_id': existing_job['id'],
                    'output_file': existing_job['output_file']
                }), 409
        
        # Check user balance
        cursor.execute("SELECT credits FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            cursor.close()
            return jsonify({'error': 'User not found'}), 404
        
        # Calculate estimated cost
        character_count = len(transcript_text)
        estimated_cost = max(1, character_count / 100 * 0.1)  # 0.1 credits per 100 characters
        
        if float(user['credits']) < estimated_cost:
            cursor.close()
            return jsonify({
                'error': 'Insufficient credits',
                'required': estimated_cost,
                'available': float(user['credits'])
            }), 400
        
        # Create TTS job
        cursor.execute("""
            INSERT INTO tts_jobs 
            (space_id, user_id, source_text, target_language, job_data, priority)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (space_id, user_id, transcript_text, language, 
              json.dumps({'transcript_id': transcript_id, 'character_count': character_count}), 
              1))
        
        job_id = cursor.lastrowid
        space.connection.commit()
        cursor.close()
        
        logger.info(f"Created TTS job {job_id} for space {space_id} in {language}")
        
        return jsonify({
            'job_id': job_id,
            'status': 'pending',
            'estimated_cost': estimated_cost,
            'character_count': character_count,
            'message': 'TTS job queued for background processing'
        })
        
    except Exception as e:
        logger.error(f"Error generating TTS: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/tts/status/<int:job_id>', methods=['GET'])
def get_tts_status(job_id):
    """Get TTS job status."""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User must be logged in'}), 401
        
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT id, space_id, status, progress, output_file, error_message,
                   created_at, updated_at, completed_at
            FROM tts_jobs 
            WHERE id = %s AND user_id = %s
        """, (job_id, user_id))
        
        job = cursor.fetchone()
        cursor.close()
        
        if not job:
            return jsonify({'error': 'TTS job not found'}), 404
        
        # Convert datetime objects to strings
        for field in ['created_at', 'updated_at', 'completed_at']:
            if job[field]:
                job[field] = job[field].isoformat()
        
        return jsonify(job)
        
    except Exception as e:
        logger.error(f"Error getting TTS status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/tts/download/<int:job_id>')
def download_tts(job_id):
    """Download generated TTS audio file."""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User must be logged in'}), 401
        
        space = get_space_component()
        cursor = space.connection.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT output_file, space_id, target_language
            FROM tts_jobs 
            WHERE id = %s AND user_id = %s AND status = 'completed'
        """, (job_id, user_id))
        
        job = cursor.fetchone()
        cursor.close()
        
        if not job or not job['output_file']:
            return jsonify({'error': 'TTS file not found or not ready'}), 404
        
        output_file = job['output_file']
        if not os.path.exists(output_file):
            return jsonify({'error': 'TTS file not found on disk'}), 404
        
        # Generate download filename
        filename = f"tts_{job['space_id']}_{job['target_language']}.mp3"
        
        return send_file(output_file, as_attachment=True, download_name=filename)
        
    except Exception as e:
        logger.error(f"Error downloading TTS: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# Affiliate Admin Routes
@app.route('/admin/affiliates')
def admin_affiliates():
    """Admin page for managing affiliates."""
    if not session.get('user_id') or not session.get('is_admin'):
        flash('Admin access required.', 'error')
        return redirect(url_for('index'))
    
    try:
        affiliate = Affiliate()
        
        # Get dashboard stats
        stats = affiliate.get_admin_dashboard_stats()
        
        # Get pending earnings
        pending_credit_earnings = affiliate.get_pending_earnings('credit')
        pending_money_earnings = affiliate.get_pending_earnings('money')
        
        # Get settings
        settings = affiliate.get_affiliate_settings()
        
        return render_template('admin_affiliates.html',
                             stats=stats,
                             pending_credit_earnings=pending_credit_earnings,
                             pending_money_earnings=pending_money_earnings,
                             settings=settings)
        
    except Exception as e:
        logger.error(f"Error loading affiliate admin page: {e}", exc_info=True)
        flash('Error loading affiliate data.', 'error')
        return redirect(url_for('admin'))

@app.route('/admin/api/affiliates/approve', methods=['POST'])
def admin_approve_affiliate_earnings():
    """Approve affiliate earnings."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        earning_ids = data.get('earning_ids', [])
        earning_type = data.get('earning_type', 'credit')
        
        if not earning_ids:
            return jsonify({'error': 'No earnings selected'}), 400
        
        affiliate = Affiliate()
        success, message = affiliate.approve_earnings(
            earning_ids, earning_type, session['user_id']
        )
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'error': message}), 400
            
    except Exception as e:
        logger.error(f"Error approving earnings: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/affiliates/pay-credits', methods=['POST'])
def admin_pay_affiliate_credits():
    """Pay all approved credit earnings."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        affiliate = Affiliate()
        success, message = affiliate.pay_credits(session['user_id'])
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'error': message}), 400
            
    except Exception as e:
        logger.error(f"Error paying credits: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/affiliates/create-payout-csv', methods=['POST'])
def admin_create_affiliate_payout_csv():
    """Create CSV for money payouts."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        affiliate = Affiliate()
        success, message, csv_path = affiliate.create_money_payout_csv(session['user_id'])
        
        if success and csv_path:
            # Return the file
            return send_file(csv_path, as_attachment=True, 
                           download_name=os.path.basename(csv_path))
        else:
            return jsonify({'message': message})
            
    except Exception as e:
        logger.error(f"Error creating payout CSV: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/affiliates/settings', methods=['PUT'])
def admin_update_affiliate_settings():
    """Update affiliate settings."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        
        affiliate = Affiliate()
        success = affiliate.update_affiliate_settings(data, session['user_id'])
        
        if success:
            return jsonify({'success': True, 'message': 'Settings updated successfully'})
        else:
            return jsonify({'error': 'Failed to update settings'}), 400
            
    except Exception as e:
        logger.error(f"Error updating affiliate settings: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# Product Admin Routes
@app.route('/admin/products')
def admin_products():
    """Admin page for managing products."""
    if not session.get('user_id') or not session.get('is_admin'):
        flash('Admin access required.', 'error')
        return redirect(url_for('index'))
    
    try:
        # Import Product component here to avoid circular imports
        from components.Product import Product
        
        product = Product()
        
        # Get all products for display
        products = product.get_all_products()
        
        return render_template('admin_products.html', products=products)
        
    except Exception as e:
        logger.error(f"Error loading product admin page: {e}", exc_info=True)
        flash('Error loading product data.', 'error')
        return redirect(url_for('admin'))

@app.route('/admin/api/products', methods=['GET'])
def admin_get_products():
    """Get all products for admin."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from components.Product import Product
        
        product = Product()
        products = product.get_all_products()
        
        return jsonify({'success': True, 'products': products})
        
    except Exception as e:
        logger.error(f"Error getting products: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/products', methods=['POST'])
def admin_create_product():
    """Create a new product."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['sku', 'name', 'price', 'credits']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        from components.Product import Product
        
        product = Product()
        result = product.create_product(data)
        
        if 'error' in result:
            return jsonify({'error': result['error']}), 400
        else:
            return jsonify({'success': True, 'message': 'Product created successfully', 'product_id': result['product_id']})
            
    except Exception as e:
        logger.error(f"Error creating product: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/products/<product_id>', methods=['PUT'])
def admin_update_product(product_id):
    """Update an existing product."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        
        from components.Product import Product
        
        product = Product()
        result = product.update_product(product_id, data)
        
        if 'error' in result:
            return jsonify({'error': result['error']}), 400
        else:
            return jsonify({'success': True, 'message': 'Product updated successfully'})
            
    except Exception as e:
        logger.error(f"Error updating product: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/products/<product_id>', methods=['DELETE'])
def admin_delete_product(product_id):
    """Delete a product."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from components.Product import Product
        
        product = Product()
        result = product.delete_product(product_id)
        
        if 'error' in result:
            return jsonify({'error': result['error']}), 400
        else:
            return jsonify({'success': True, 'message': 'Product deleted successfully'})
            
    except Exception as e:
        logger.error(f"Error deleting product: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/products/<product_id>/toggle-status', methods=['POST'])
def admin_toggle_product_status(product_id):
    """Toggle product active status."""
    if not session.get('user_id') or not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        from components.Product import Product
        
        product = Product()
        result = product.toggle_product_status(product_id)
        
        if 'error' in result:
            return jsonify({'error': result['error']}), 400
        else:
            return jsonify({'success': True, 'message': f'Product status changed to {result["new_status"]}'})
            
    except Exception as e:
        logger.error(f"Error toggling product status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

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