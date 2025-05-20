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
                # Will try to reconnect below
        
        # Create fresh connection if previous checks failed
        space_component = Space()
        if hasattr(space_component, 'connection'):
            db_connection = space_component.connection
            logger.info("Recreated Space component with fresh connection")
    except Exception as e:
        logger.error(f"Error in get_space_component: {e}", exc_info=True)
        # Create a new instance as a final fallback
        try:
            space_component = Space()
            if hasattr(space_component, 'connection'):
                db_connection = space_component.connection
        except Exception as new_err:
            logger.error(f"Failed to create new Space component: {new_err}", exc_info=True)
    
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
    cursor = None
    try:
        # Get Space component with fresh connection if needed
        space = get_space_component()
        if not space or not hasattr(space, 'connection') or not space.connection:
            logger.error("Could not get valid Space component or connection")
            return jsonify({
                'job_id': job_id,
                'status': 'error',
                'error': 'Database connection unavailable'
            }), 500
        
        # Get job details directly from database for more reliability
        direct_job = None
        try:
            # First check if connection is valid
            if not space.connection.is_connected():
                logger.warning("Connection lost before cursor creation, getting new component")
                space = get_space_component()
                if not space.connection.is_connected():
                    raise Exception("Could not reestablish database connection")
            
            cursor = space.connection.cursor(dictionary=True)
            
            # Use a more detailed query to include all fields and join spaces table 
            # to get additional information for completed downloads
            query = """
            SELECT 
                sds.id, sds.space_id, sds.status, sds.progress_in_percent, 
                sds.progress_in_size, sds.error_message, sds.created_at, 
                sds.updated_at, sds.process_id, sds.end_time,
                s.status as space_status, s.format as space_format, s.download_cnt
            FROM space_download_scheduler sds
            LEFT JOIN spaces s ON sds.space_id = s.space_id
            WHERE sds.id = %s
            """
            cursor.execute(query, (job_id,))
            direct_job = cursor.fetchone()
            
            # If we found the job, also check directly for the file
            if direct_job and direct_job['space_id']:
                # Check if file exists on disk, regardless of database status
                space_id = direct_job['space_id']
                download_dir = app.config['DOWNLOAD_DIR']
                file_path = None
                file_size = 0
                
                import os  # Ensure os is imported here
                for ext in ['mp3', 'm4a', 'wav']:
                    path = os.path.join(download_dir, f"{space_id}.{ext}")
                    if os.path.exists(path) and os.path.getsize(path) > 1024*1024:  # > 1MB
                        file_path = path
                        file_size = os.path.getsize(path)
                        logger.info(f"Found file for job {job_id}, space {space_id}: {file_path}, size: {file_size}")
                        break
                
                # If file exists but job doesn't show completed, it should be considered completed
                if file_path and direct_job['status'] != 'completed':
                    logger.info(f"Job {job_id} shows status '{direct_job['status']}' but file exists, treating as completed")
                    direct_job['status'] = 'completed'
                    direct_job['progress_in_percent'] = 100
                    direct_job['progress_in_size'] = file_size
                    direct_job['file_exists'] = True
                    direct_job['file_path'] = file_path
                    
                    # Try to update the database to reflect the completed status
                    try:
                        if cursor:
                            update_query = """
                            UPDATE space_download_scheduler
                            SET status = 'completed', progress_in_percent = 100, 
                                progress_in_size = %s, end_time = NOW(), updated_at = NOW()
                            WHERE id = %s AND status != 'completed'
                            """
                            cursor.execute(update_query, (file_size, job_id))
                            space.connection.commit()
                            logger.info(f"Updated job {job_id} to completed status with size {file_size}")
                    except Exception as update_err:
                        logger.error(f"Error updating job status: {update_err}")
                
                # Also check for part file when job is in progress
                part_file_exists = False
                part_file_size = 0
                if direct_job['status'] in ['in_progress', 'downloading', 'pending']:
                    part_file = os.path.join(download_dir, f"{space_id}.mp3.part")
                    if os.path.exists(part_file):
                        part_file_exists = True
                        part_file_size = os.path.getsize(part_file)
                        logger.info(f"Found part file for job {job_id}, space {space_id}: {part_file}, size: {part_file_size}")
                        
                        # Always update progress_in_size with part file size for accurate progress display
                        direct_job['progress_in_size'] = part_file_size
                        direct_job['part_file_exists'] = True
                        direct_job['part_file_size'] = part_file_size
                        
                        # If part file exists but no progress in job, estimate progress
                        if (direct_job['progress_in_percent'] is None or direct_job['progress_in_percent'] == 0) and part_file_size > 1024*1024:
                            # Estimate progress based on file size (very rough estimate)
                            estimated_percent = max(1, min(10, int(part_file_size / (1024*1024) / 5)))
                            logger.info(f"Estimating progress as {estimated_percent}% based on part file size")
                            direct_job['progress_in_percent'] = estimated_percent
                            
                            # Try to update the database
                            try:
                                if cursor:
                                    # Always update progress_in_size regardless of progress_in_percent
                                    update_query = """
                                    UPDATE space_download_scheduler
                                    SET progress_in_size = %s, updated_at = NOW(),
                                        progress_in_percent = CASE 
                                            WHEN progress_in_percent IS NULL OR progress_in_percent = 0 
                                            THEN %s 
                                            ELSE progress_in_percent 
                                        END
                                    WHERE id = %s
                                    """
                                    cursor.execute(update_query, (part_file_size, estimated_percent, job_id))
                                    space.connection.commit()
                                    logger.info(f"Updated job {job_id} with estimated progress based on part file")
                            except Exception as update_err:
                                logger.error(f"Error updating job status from part file: {update_err}")
                
            # Always explicitly close cursor before using results
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
                cursor = None
            
            # If we found the job directly, use that data
            if direct_job:
                logger.info(f"Retrieved job {job_id} directly from database: {direct_job['status']}, progress: {direct_job['progress_in_percent']}%, size: {direct_job['progress_in_size']} bytes")
                
                # For completed jobs, make sure progress is 100% and size is set
                if direct_job['status'] == 'completed':
                    if direct_job['progress_in_percent'] != 100:
                        direct_job['progress_in_percent'] = 100
                    
                    # If space has format info (file size), use that as progress_in_size
                    # if it's bigger than the current value
                    if direct_job.get('space_format') and direct_job['space_format'] and str(direct_job['space_format']).isdigit():
                        format_size = int(direct_job['space_format'])
                        if format_size > (direct_job['progress_in_size'] or 0):
                            direct_job['progress_in_size'] = format_size
                
                # If the job has no progress info but the space has download_cnt, use that
                if (direct_job['progress_in_percent'] is None or direct_job['progress_in_percent'] == 0) and direct_job.get('download_cnt'):
                    space_progress = direct_job.get('download_cnt')
                    logger.info(f"Using download_cnt={space_progress} from spaces table as job has no progress")
                    direct_job['progress_in_percent'] = space_progress
                
                # Create a safe dict for response that doesn't reference MySQL objects
                safe_response = {
                    'job_id': job_id,
                    'space_id': direct_job['space_id'],
                    'status': direct_job['status'] or 'unknown',
                    'progress_in_percent': direct_job['progress_in_percent'] or 0,
                    'progress_in_size': direct_job['progress_in_size'] or 0,
                    'error_message': direct_job['error_message'] or '',
                    'direct_query': True
                }
                
                # Add space status if available
                if direct_job.get('space_status'):
                    safe_response['space_status'] = direct_job.get('space_status')
                
                # Add space format if available and valid
                if direct_job.get('space_format') and direct_job.get('space_format'):
                    safe_response['space_format'] = direct_job.get('space_format')
                
                # Add download_cnt if available
                if direct_job.get('download_cnt'):
                    safe_response['space_download_cnt'] = direct_job.get('download_cnt')
                
                # Add part file info if applicable
                if 'part_file_exists' in locals() and part_file_exists:
                    safe_response['part_file_exists'] = True
                    safe_response['part_file_size'] = part_file_size
                
                # Add process status (running or not)
                if direct_job['process_id']:
                    try:
                        # On Unix systems, can check if process is running
                        import os
                        process_running = False
                        try:
                            # This will raise an error if process is not running
                            os.kill(direct_job['process_id'], 0)
                            process_running = True
                        except OSError:
                            process_running = False
                        
                        safe_response['process_running'] = process_running
                    except Exception as proc_err:
                        logger.error(f"Error checking process: {proc_err}")
                
                # Add file existence information if we checked for it
                if 'file_path' in locals() and file_path:
                    safe_response['file_exists'] = True
                    safe_response['file_path'] = file_path
                
                # Use a new JSON object that doesn't reference any potential MySQL objects
                return jsonify(safe_response)
        except Exception as db_err:
            logger.error(f"Error with direct database query: {db_err}", exc_info=True)
            # Close cursor if it's still open
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
                finally:
                    cursor = None
            
            # Try to get a fresh connection for fallback method
            space = get_space_component()
        
        # Fallback: Get job via Space component method
        job = None
        try:
            job = space.get_download_job(job_id=job_id)
        except Exception as get_job_err:
            logger.error(f"Error getting job via Space component: {get_job_err}", exc_info=True)
            
        if not job:
            return jsonify({
                'job_id': job_id,
                'status': 'error',
                'error': 'Job not found'
            }), 404
        
        # Get additional information from spaces table
        space_details = None
        if job.get('space_id'):
            try:
                space_details = space.get_space(job.get('space_id'))
            except Exception as space_err:
                logger.error(f"Error getting space details: {space_err}")
        
        # Create a safe dict for response
        progress_percent = 0
        progress_size = 0
        try:
            # Convert any None values to defaults
            progress_percent = job.get('progress_in_percent', 0) or 0
            progress_size = job.get('progress_in_size', 0) or 0
        except Exception as val_err:
            logger.error(f"Error processing job values: {val_err}")
        
        # If progress is 0 but space has download_cnt, use that instead
        try:
            if progress_percent == 0 and space_details and space_details.get('download_cnt'):
                progress_percent = space_details.get('download_cnt')
                logger.info(f"Using download_cnt={progress_percent} from spaces table")
        except Exception as cnt_err:
            logger.error(f"Error processing download_cnt: {cnt_err}")
        
        # Check space_id
        space_id = None
        try:
            space_id = job.get('space_id')
        except Exception:
            logger.error("Error getting space_id from job")
            
        # Check for file existence
        file_exists = False
        file_path = None
        
        # Check for part file
        part_file_exists = False
        part_file_size = 0
        
        # If we have a space_id, check files
        if space_id:
            try:
                download_dir = app.config['DOWNLOAD_DIR']
                import os
                
                # Check for completed file
                for ext in ['mp3', 'm4a', 'wav']:
                    path = os.path.join(download_dir, f"{space_id}.{ext}")
                    if os.path.exists(path) and os.path.getsize(path) > 1024*1024:  # > 1MB
                        file_exists = True
                        file_path = path
                        progress_size = max(progress_size, os.path.getsize(path))
                        
                        # If job is not marked completed but file exists, ensure progress is 100%
                        if job.get('status') != 'completed':
                            progress_percent = 100
                            
                            # Try to update the database record
                            try:
                                space.update_download_job(
                                    job_id,
                                    status='completed',
                                    progress_in_percent=100,
                                    progress_in_size=os.path.getsize(path)
                                )
                                logger.info(f"Updated job {job_id} to completed based on file existence")
                            except Exception as update_err:
                                logger.error(f"Error updating job to completed: {update_err}")
                        
                        break
                
                # If checking for file failed, also check for part file
                if not file_exists and job.get('status') in ['in_progress', 'downloading', 'pending']:
                    part_file = os.path.join(download_dir, f"{space_id}.mp3.part")
                    if os.path.exists(part_file):
                        part_file_exists = True
                        part_file_size = os.path.getsize(part_file)
                        logger.info(f"Found part file for space {space_id}: {part_file}, size: {part_file_size}")
                        
                        # If part file exists but no progress, estimate progress
                        if progress_percent == 0 and part_file_size > 1024*1024:
                            # Estimate progress based on file size (very rough estimate)
                            estimated_percent = max(1, min(10, int(part_file_size / (1024*1024) / 5)))
                            logger.info(f"Estimating progress as {estimated_percent}% based on part file size")
                            progress_percent = estimated_percent
                            
                            # Try to update the database
                            try:
                                space.update_download_job(
                                    job_id,
                                    progress_in_percent=estimated_percent,
                                    progress_in_size=part_file_size
                                )
                                logger.info(f"Updated job {job_id} with estimated progress based on part file")
                            except Exception as update_err:
                                logger.error(f"Error updating job status from part file: {update_err}")
            except Exception as file_err:
                logger.error(f"Error checking file existence: {file_err}")
        
        # Return job data in a safe dict
        response = {
            'job_id': job_id,
            'space_id': space_id,
            'status': job.get('status', 'unknown'),
            'progress_in_percent': progress_percent,
            'progress_in_size': progress_size,
            'error_message': job.get('error_message', ''),
            'direct_query': False,
            'file_exists': file_exists
        }
        
        # Add space details if available
        if space_details:
            try:
                if space_details.get('status'):
                    response['space_status'] = space_details.get('status')
                if space_details.get('format'):
                    response['space_format'] = space_details.get('format')
                if space_details.get('download_cnt'):
                    response['space_download_cnt'] = space_details.get('download_cnt')
            except Exception as detail_err:
                logger.error(f"Error adding space details to response: {detail_err}")
        
        # Add part file info if applicable
        if part_file_exists:
            response['part_file_exists'] = True
            response['part_file_size'] = part_file_size
        
        # Return a clean JSON response that doesn't reference any MySQL objects
        return jsonify(response)
        
    except Exception as e:
        # Close cursor if still open
        if cursor:
            try:
                cursor.close()
            except:
                pass
        
        logger.error(f"Error in API status: {e}", exc_info=True)
        return jsonify({
            'job_id': job_id,
            'status': 'error',
            'error': f"Error retrieving job status: {str(e)}"
        }), 500
        
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
            
            # Check for any job for this space, prioritize active ones
            query = """
            SELECT * FROM space_download_scheduler
            WHERE space_id = %s
            ORDER BY 
                CASE 
                    WHEN status IN ('in_progress', 'downloading') THEN 1
                    WHEN status = 'pending' THEN 2
                    WHEN status = 'completed' THEN 3
                    ELSE 4
                END,
                updated_at DESC, 
                id DESC 
            LIMIT 1
            """
            cursor.execute(query, (space_id,))
            job = cursor.fetchone()
            
            # If we found a job, ensure that completed jobs have progress_in_percent = 100
            if job and job['status'] == 'completed' and job['progress_in_percent'] != 100:
                # Update the job to have 100% progress
                update_query = """
                UPDATE space_download_scheduler
                SET progress_in_percent = 100
                WHERE id = %s AND status = 'completed' AND progress_in_percent != 100
                """
                cursor.execute(update_query, (job['id'],))
                space.connection.commit()
                job['progress_in_percent'] = 100
                logger.info(f"Updated job {job['id']} to have 100% progress")
                
            # If there's a completed job but progress_in_size is 0, try to get size from the spaces table
            if job and job['status'] == 'completed' and (job['progress_in_size'] is None or job['progress_in_size'] == 0):
                # Check if we have a format value in the spaces table
                space_query = "SELECT format FROM spaces WHERE space_id = %s"
                cursor.execute(space_query, (space_id,))
                space_data = cursor.fetchone()
                
                if space_data and space_data['format'] and space_data['format'].isdigit():
                    format_size = int(space_data['format'])
                    if format_size > 0:
                        # Update the job with the size from spaces table
                        update_query = """
                        UPDATE space_download_scheduler
                        SET progress_in_size = %s
                        WHERE id = %s AND (progress_in_size IS NULL OR progress_in_size = 0)
                        """
                        cursor.execute(update_query, (format_size, job['id']))
                        space.connection.commit()
                        job['progress_in_size'] = format_size
                        logger.info(f"Updated job {job['id']} size to {format_size} from spaces table")
                
            cursor.close()
        except Exception as job_err:
            logger.error(f"Error getting job: {job_err}")
        
        # Check for partial file progress even if job is not active
        part_file_exists = False
        part_file_size = 0
        if not file_path:  # Only check if the final file doesn't exist
            # Check for partial file
            for ext in ['mp3', 'm4a', 'wav']:
                part_path = os.path.join(download_dir, f"{space_id}.{ext}.part")
                if os.path.exists(part_path):
                    part_file_exists = True
                    part_file_size = os.path.getsize(part_path)
                    logger.info(f"Found partial file: {part_path}, size: {part_file_size} bytes")
                    break
        
        # Ensure space status is consistent with file existence
        space_status = space_details.get('status', 'unknown')
        
        # If file exists but status doesn't show completed, update it
        if file_path and space_status != 'completed':
            try:
                # Update the space record
                cursor = space.connection.cursor()
                update_query = """
                UPDATE spaces
                SET status = 'completed', format = %s, downloaded_at = NOW()
                WHERE space_id = %s AND status != 'completed'
                """
                cursor.execute(update_query, (str(file_size), space_id))
                space.connection.commit()
                cursor.close()
                
                # Update local status
                space_status = 'completed'
                logger.info(f"Updated space {space_id} status to completed based on file existence")
            except Exception as space_update_err:
                logger.error(f"Error updating space status: {space_update_err}")
        
        # If we have a job that's completed but space status isn't, update space status
        if job and job['status'] == 'completed' and space_status != 'completed':
            try:
                # Update the space record
                cursor = space.connection.cursor()
                update_query = """
                UPDATE spaces
                SET status = 'completed'
                WHERE space_id = %s AND status != 'completed'
                """
                cursor.execute(update_query, (space_id,))
                space.connection.commit()
                cursor.close()
                
                # Update local status
                space_status = 'completed'
                logger.info(f"Updated space {space_id} status to completed based on job status")
            except Exception as space_job_err:
                logger.error(f"Error updating space status from job: {space_job_err}")
                
        # Return status data
        response = {
            'space_id': space_id,
            'status': space_status,
            'file_exists': file_path is not None,
            'file_size': file_size if file_path else 0,
            'part_file_exists': part_file_exists,
            'part_file_size': part_file_size
        }
        
        # Add job data if available
        if job:
            # Make sure values are not None
            job_status = job.get('status') or 'unknown'
            progress_percent = job.get('progress_in_percent') or 0
            progress_size = job.get('progress_in_size') or 0
            
            # Log for debugging
            logger.info(f"Job data for space {space_id}: status={job_status}, progress={progress_percent}%, size={progress_size} bytes")
            
            # If we have a part file but progress_size is very small, use part file size
            if part_file_exists and part_file_size > 0 and progress_size < part_file_size:
                logger.info(f"Using part file size ({part_file_size}) instead of progress_size ({progress_size})")
                progress_size = part_file_size
                
                # Update space record to store current part file size for other API endpoints
                try:
                    cursor = space.connection.cursor()
                    space_update_query = """
                    UPDATE spaces
                    SET format = %s, status = 'downloading'
                    WHERE space_id = %s
                    """
                    cursor.execute(space_update_query, (str(part_file_size), space_id))
                    space.connection.commit()
                    cursor.close()
                    logger.info(f"Updated space {space_id} format field with part file size {part_file_size}")
                except Exception as update_err:
                    logger.error(f"Error updating space format: {update_err}")
                
                # If we have a part file with substantial size but progress is 0, estimate progress
                if part_file_size > 0:  # Always estimate progress for any part file
                    # Use improved progress estimation based on file size
                    if part_file_size > 60*1024*1024:  # > 60MB
                        estimated_percent = 90 + min(9, int((part_file_size - 60*1024*1024) / (10*1024*1024)))
                    elif part_file_size > 40*1024*1024:  # > 40MB
                        estimated_percent = 75 + min(15, int((part_file_size - 40*1024*1024) / (1.33*1024*1024)))
                    elif part_file_size > 20*1024*1024:  # > 20MB
                        estimated_percent = 50 + min(25, int((part_file_size - 20*1024*1024) / (0.8*1024*1024)))
                    elif part_file_size > 10*1024*1024:  # > 10MB
                        estimated_percent = 25 + min(25, int((part_file_size - 10*1024*1024) / (0.4*1024*1024)))
                    elif part_file_size > 5*1024*1024:   # > 5MB
                        estimated_percent = 10 + min(15, int((part_file_size - 5*1024*1024) / (0.33*1024*1024)))
                    elif part_file_size > 1*1024*1024:   # > 1MB
                        estimated_percent = 1 + min(9, int((part_file_size - 1*1024*1024) / (0.44*1024*1024)))
                    else:
                        estimated_percent = 1
                        
                    # Only use our estimate if it's better than current progress
                    if estimated_percent > progress_percent:
                        progress_percent = estimated_percent 
                        logger.info(f"Estimated progress as {estimated_percent}% based on part file size: {part_file_size/1024/1024:.2f}MB")
            
            response.update({
                'job_id': job.get('id'),
                'job_status': job_status,
                'progress_in_percent': progress_percent,
                'progress_in_size': progress_size,
                'job_updated_at': job.get('updated_at'),
                'job_process_id': job.get('process_id')
            })
            
            # Check if process is still running
            if job.get('process_id'):
                try:
                    import os
                    process_running = False
                    try:
                        # This will raise an error if process is not running
                        os.kill(job.get('process_id'), 0)
                        process_running = True
                    except (OSError, TypeError):
                        process_running = False
                    
                    response['process_running'] = process_running
                except Exception as proc_err:
                    logger.error(f"Error checking process: {proc_err}")
            
            # Include error message for failed jobs
            if job_status == 'failed' and job.get('error_message'):
                response['error_message'] = job.get('error_message')
                
            # If job status is 'in_progress' but part file exists and is growing,
            # provide an estimate even if the bg_downloader isn't reporting progress
            if (job_status == 'in_progress' or job_status == 'downloading') and part_file_exists:
                # Get a timestamp from when job was last updated
                last_updated = job.get('updated_at')
                
                # If last update was more than 30 seconds ago but we have a part file,
                # the background process might not be reporting progress correctly
                if last_updated:
                    now = datetime.datetime.now()
                    try:
                        # Calculate time difference
                        if isinstance(last_updated, str):
                            from dateutil import parser
                            last_updated = parser.parse(last_updated)
                        
                        time_diff = now - last_updated
                        
                        # If we haven't had an update in a while but part file exists
                        if time_diff.total_seconds() > 30 and part_file_size > 1024*1024:
                            response['part_file_detected'] = True
                            
                            # Show at least 1% progress if file is substantial
                            if progress_percent == 0 and part_file_size > 1024*1024:
                                response['progress_in_percent'] = 1
                    except Exception as time_err:
                        logger.error(f"Error calculating time difference: {time_err}")
        
        # Even if no job was found, if we have a part file, report some progress
        elif part_file_exists and part_file_size > 0:
            # Estimate progress based on typical audio file size (30-100MB)
            estimated_percent = max(1, min(10, int(part_file_size / (1024*1024) / 5)))
            
            response.update({
                'part_file_detected': True,
                'job_status': 'in_progress',  # Assume download is in progress
                'progress_in_percent': estimated_percent,
                'progress_in_size': part_file_size
            })
        
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
        
        # Add debug logging to trace values being sent to template
        logger.info(f"Rendering template for space {space_id}:")
        logger.info(f"  file_path = {file_path}")
        logger.info(f"  space.status = {space_details.get('status')}")
        logger.info(f"  file_extension = {file_extension}")
        logger.info(f"  file_size = {file_size}")
        
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
            
        # For debugging - create a special endpoint for debug info
        if 'debug' in request.args:
            debug_info = {
                'space_id': space_id,
                'file_path': str(file_path) if file_path else None,
                'file_exists': file_path is not None,
                'file_size': file_size,
                'file_extension': file_extension,
                'content_type': content_type,
                'space_status': space_details.get('status'),
                'space_details': space_details
            }
            return jsonify(debug_info)
        
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