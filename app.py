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
from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, session, send_file, Response

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
        logger.info("Created new Space component instance")
        return space_component
        
    except Exception as e:
        logger.error(f"Error getting Space component: {e}")
        return None

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
        
        # Get all completed downloads
        completed_spaces = space.list_download_jobs(status='completed')
        
        # Check which files actually exist and add metadata
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
            
            # Add transcript/translation/summary metadata
            try:
                space_details = space.get_space(job['space_id'], include_transcript=True)
                if space_details:
                    job['has_transcript'] = bool(space_details.get('transcripts'))
                    job['transcript_count'] = len(space_details.get('transcripts', []))
                    transcripts = space_details.get('transcripts', [])
                    job['has_translation'] = len(transcripts) > 1 if transcripts else False
                    job['has_summary'] = any(t.get('summary') for t in transcripts)
                    job['title'] = space_details.get('title', '')
            except Exception as e:
                logger.warning(f"Error getting metadata for space {job.get('space_id')}: {e}")
                job['has_transcript'] = False
                job['has_translation'] = False
                job['has_summary'] = False
                job['transcript_count'] = 0
                job['title'] = ''
        
        return render_template('all_spaces.html', spaces=completed_spaces)
        
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
            queue_jobs.append(job)
        
        # Sort by created_at (oldest first, so they appear in queue order)
        queue_jobs.sort(key=lambda x: x.get('created_at', ''))
        
        return render_template('queue.html', queue_jobs=queue_jobs)
        
    except Exception as e:
        logger.error(f"Error viewing queue: {e}", exc_info=True)
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(url_for('index'))

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
def track_play(space_id):
    """API endpoint to track when a space is played."""
    try:
        space = get_space_component()
        success = space.increment_play_count(space_id)
        return jsonify({'success': success})
    except Exception as e:
        logger.error(f"Error tracking play: {e}")
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
        
        # Create a temporary file for the trimmed audio
        temp_file = file_path + '.tmp'
        
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
                
                # Update file size in database
                new_size = os.path.getsize(file_path)
                space = get_space_component()
                cursor = space.connection.cursor()
                cursor.execute(
                    "UPDATE spaces SET file_size = %s, updated_at = NOW() WHERE space_id = %s",
                    (new_size, space_id)
                )
                space.connection.commit()
                cursor.close()
                
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
            
        return render_template('space.html', 
                               space=space_details, 
                               file_path=file_path, 
                               file_size=file_size, 
                               file_extension=file_extension,
                               content_type=content_type,
                               job=job,
                               clips=clips)
        
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
                'progress_percent': 0,
                'progress_in_size': 0
            })
            
        # Process downloading jobs
        for job in downloading_jobs:
            progress = 0
            if hasattr(job, 'progress'):
                progress = job.progress
            elif hasattr(job, 'download_cnt'):
                progress = job.download_cnt
            elif isinstance(job, dict):
                progress = job.get('progress', job.get('download_cnt', 0))
                
            queue_jobs.append({
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
            })
        
        # Sort by created_at (oldest first)
        queue_jobs.sort(key=lambda x: x.get('created_at', ''))
        
        return jsonify({
            'jobs': queue_jobs,
            'total': len(queue_jobs)
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
        
        # Get Space component
        space = get_space_component()
        
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
        
        # Build query based on authentication
        cursor = space.connection.cursor(dictionary=True)
        if user_id > 0:
            # Logged-in user: get notes by user_id
            query = """
                SELECT id, space_id, notes, user_id, cookie_id, created_at, updated_at
                FROM space_notes
                WHERE space_id = %s AND user_id = %s
                ORDER BY updated_at DESC
            """
            cursor.execute(query, (space_id, user_id))
        elif cookie_id:
            # Non-logged-in user: get notes by cookie_id
            query = """
                SELECT id, space_id, notes, user_id, cookie_id, created_at, updated_at
                FROM space_notes
                WHERE space_id = %s AND cookie_id = %s AND user_id = 0
                ORDER BY updated_at DESC
            """
            cursor.execute(query, (space_id, cookie_id))
        else:
            # No identification: return empty
            return jsonify({'notes': []})
        
        notes = cursor.fetchall()
        cursor.close()
        
        # Convert datetime objects to strings
        for note in notes:
            if note['created_at']:
                note['created_at'] = note['created_at'].isoformat()
            if note['updated_at']:
                note['updated_at'] = note['updated_at'].isoformat()
        
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
        
        # Debug logging
        logger.info(f"Translation request - Text length: {len(text) if text else 0}, Source: {source_lang}, Target: {target_lang}, Space ID: {space_id}")
        if text:
            logger.info(f"First 200 chars: {text[:200]}...")
            logger.info(f"Last 200 chars: ...{text[-200:]}")
        
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
        
        # Update last login time
        cursor.execute(
            "UPDATE users SET last_logged_in = NOW() WHERE id = %s",
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
        cursor.close()
        
        # Set session variables
        session['user_id'] = token_data['user_id']
        session['user_email'] = token_data['email']
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
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('index'))

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