#!/usr/bin/env python3
# api_controller.py - API Controller for XSpace Downloader

"""
API Controller for XSpace Downloader
------------------------------------

This module provides a REST API interface to the XSpace Downloader application,
allowing external applications to manage users, spaces, downloads, and more
using API key authentication.

The API follows RESTful principles with JSON request/response formats.

Authentication:
- Every request requires an API key in the header: "X-API-Key"
- API keys are managed in the api_keys table

Endpoints:
- Users: CRUD operations on users
- Spaces: Manage X spaces, metadata, notes
- Tags: Manage and assign tags to spaces
- Downloads: Initiate and track space downloads
- Statistics: System-wide statistics and usage

Usage:
- Run this file directly to start the API server
- Set API_HOST and API_PORT environment variables to configure (defaults: 127.0.0.1:5000)

Example:
$ python3 api_controller.py
"""

import os
import sys
import uuid
import json
import time
import logging
from datetime import datetime, timedelta
from functools import wraps
import hashlib
import base64
import hmac
import secrets

# Add parent directory to path for importing components
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Try to import Flask and related packages
try:
    from flask import Flask, request, jsonify, g
    from flask_cors import CORS
    from werkzeug.exceptions import HTTPException
except ImportError:
    print("Error: Required packages not found. Installing...")
    import subprocess
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "flask", "flask-cors"])
        from flask import Flask, request, jsonify, g
        from flask_cors import CORS
        from werkzeug.exceptions import HTTPException
    except Exception as e:
        print(f"Failed to install required packages: {e}")
        sys.exit(1)

# Import application components
from components.User import User
from components.Space import Space
from components.Tag import Tag
from components.DownloadSpace import DownloadSpace

# Configure logging
logging.basicConfig(
    filename='api_server.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('api_controller')

# Create Flask application
app = Flask(__name__)
CORS(app)

# Configuration
API_HOST = os.getenv('API_HOST', '127.0.0.1')
API_PORT = int(os.getenv('API_PORT', 5000))
API_RATE_LIMIT = int(os.getenv('API_RATE_LIMIT', 100))  # Requests per minute
API_DEBUG = os.getenv('API_DEBUG', 'false').lower() == 'true'
API_ENVIRONMENT = os.getenv('API_ENVIRONMENT', 'development')

# API key cache to reduce database lookups
# Structure: {api_key: {'user_id': X, 'permissions': [], 'last_checked': timestamp}}
api_key_cache = {}

# Rate limiting cache
# Structure: {ip_address: {'count': X, 'reset_time': timestamp}}
rate_limit_cache = {}

# Database functions
def get_db_connection():
    """Get a database connection if not already set on the request context."""
    if not hasattr(g, 'db_connection'):
        # Import here to avoid circular imports
        from tests.test_config import get_db_connection as get_config_db
        g.db_connection = get_config_db()
    return g.db_connection

def close_db_connection(exception=None):
    """Close the database connection at the end of the request."""
    db_connection = getattr(g, 'db_connection', None)
    if db_connection is not None and db_connection.is_connected():
        db_connection.close()

# Register the close_db_connection function to be called when the application context ends
app.teardown_appcontext(close_db_connection)

# Middleware and decorators
def require_api_key(permissions=None):
    """
    Decorator to require a valid API key with specified permissions.
    
    Args:
        permissions (list, optional): List of permissions required
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            api_key = request.headers.get('X-API-Key')
            
            if not api_key:
                return jsonify({'error': 'API key is required'}), 401
            
            # Check cache first
            cached_key = api_key_cache.get(api_key)
            if cached_key and (time.time() - cached_key['last_checked']) < 300:  # 5 minute cache
                user_id = cached_key['user_id']
                user_permissions = cached_key['permissions']
            else:
                # Check API key in database
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
                
                query = """
                SELECT api_keys.user_id, api_keys.permissions, users.status
                FROM api_keys 
                JOIN users ON api_keys.user_id = users.id
                WHERE api_keys.key = %s AND api_keys.is_active = 1
                """
                cursor.execute(query, (api_key,))
                key_info = cursor.fetchone()
                cursor.close()
                
                if not key_info or key_info['status'] != 1:  # 1 = active in the user table
                    return jsonify({'error': 'Invalid or inactive API key'}), 401
                
                user_id = key_info['user_id']
                # Parse permissions JSON if it's stored as a string
                if isinstance(key_info['permissions'], str):
                    try:
                        user_permissions = json.loads(key_info['permissions'])
                    except json.JSONDecodeError:
                        user_permissions = []
                else:
                    user_permissions = key_info['permissions'] or []
                
                # Update cache
                api_key_cache[api_key] = {
                    'user_id': user_id,
                    'permissions': user_permissions,
                    'last_checked': time.time()
                }
            
            # Check permissions if specified
            if permissions:
                if not set(permissions).issubset(set(user_permissions)):
                    return jsonify({'error': 'Insufficient permissions'}), 403
            
            # Add user_id to request context
            g.user_id = user_id
            g.permissions = user_permissions
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def rate_limit(f):
    """Rate limiting decorator."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if API_ENVIRONMENT == 'production':
            ip = request.remote_addr
            current_time = time.time()
            
            # Initialize or get existing rate limit info
            if ip not in rate_limit_cache or rate_limit_cache[ip]['reset_time'] < current_time:
                rate_limit_cache[ip] = {'count': 0, 'reset_time': current_time + 60}
            
            # Increment request count
            rate_limit_cache[ip]['count'] += 1
            
            # Check limit
            if rate_limit_cache[ip]['count'] > API_RATE_LIMIT:
                return jsonify({'error': 'Rate limit exceeded'}), 429
        
        return f(*args, **kwargs)
    return decorated_function

# Error handler
@app.errorhandler(Exception)
def handle_exception(e):
    """Global exception handler to return JSON responses."""
    if isinstance(e, HTTPException):
        response = {
            'error': e.description,
            'status_code': e.code
        }
        return jsonify(response), e.code
    
    # Log unexpected errors
    logger.error(f"Unexpected error: {str(e)}", exc_info=True)
    
    if API_DEBUG:
        # Include traceback in development
        import traceback
        response = {
            'error': str(e),
            'traceback': traceback.format_exc()
        }
    else:
        response = {
            'error': 'An unexpected error occurred'
        }
    
    return jsonify(response), 500

# API endpoints

# Health check
@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint that doesn't require authentication."""
    try:
        # Check database connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        
        return jsonify({
            'status': 'ok',
            'timestamp': datetime.now().isoformat(),
            'environment': API_ENVIRONMENT
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# Authentication endpoints
@app.route('/api/auth/validate', methods=['GET'])
@require_api_key()
def validate_api_key():
    """Validate the API key and return user information."""
    return jsonify({
        'valid': True,
        'user_id': g.user_id,
        'permissions': g.permissions
    })

# User endpoints
@app.route('/api/users', methods=['GET'])
@rate_limit
@require_api_key(['manage_users'])
def list_users():
    """List all users (paginated)."""
    page = int(request.args.get('page', 1))
    limit = min(int(request.args.get('limit', 20)), 100)  # Max 100 per page
    offset = (page - 1) * limit
    
    # Optional filters
    status = request.args.get('status')
    username = request.args.get('username')
    
    try:
        user_component = User(get_db_connection())
        users = user_component.list_users(
            status=status,
            username=username,
            limit=limit,
            offset=offset
        )
        
        # Sanitize output (remove sensitive fields)
        for user in users:
            if 'password_hash' in user:
                del user['password_hash']
            if 'reset_token' in user:
                del user['reset_token']
        
        # Get total count for pagination
        total = user_component.count_users(status=status, username=username)
        
        return jsonify({
            'data': users,
            'page': page,
            'limit': limit,
            'total': total,
            'total_pages': (total + limit - 1) // limit
        })
    except Exception as e:
        logger.error(f"Error listing users: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<int:user_id>', methods=['GET'])
@rate_limit
@require_api_key(['view_users'])
def get_user(user_id):
    """Get a specific user."""
    # Check if user is requesting their own info or has manage_users permission
    if g.user_id != user_id and 'manage_users' not in g.permissions:
        return jsonify({'error': 'Permission denied'}), 403
    
    try:
        user_component = User(get_db_connection())
        user = user_component.get_user(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Sanitize output
        if 'password_hash' in user:
            del user['password_hash']
        if 'reset_token' in user:
            del user['reset_token']
        
        return jsonify(user)
    except Exception as e:
        logger.error(f"Error getting user: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users', methods=['POST'])
@rate_limit
@require_api_key(['manage_users'])
def create_user():
    """Create a new user."""
    data = request.json
    
    # Validate required fields
    required_fields = ['username', 'email', 'password']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    try:
        user_component = User(get_db_connection())
        
        # Check if username or email already exists
        if user_component.get_user_by_username(data['username']):
            return jsonify({'error': 'Username already exists'}), 409
        
        if user_component.get_user_by_email(data['email']):
            return jsonify({'error': 'Email already exists'}), 409
        
        # Create the user
        user_id = user_component.create_user(
            username=data['username'],
            email=data['email'],
            password=data['password'],
            full_name=data.get('full_name', ''),
            status=data.get('status', 'active'),
            role=data.get('role', 'user')
        )
        
        if not user_id:
            return jsonify({'error': 'Failed to create user'}), 500
        
        # Get the created user
        user = user_component.get_user(user_id)
        
        # Sanitize output
        if 'password_hash' in user:
            del user['password_hash']
        if 'reset_token' in user:
            del user['reset_token']
        
        return jsonify(user), 201
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@rate_limit
@require_api_key(['manage_users'])
def update_user(user_id):
    """Update a user."""
    # Check if user is updating their own info or has manage_users permission
    if g.user_id != user_id and 'manage_users' not in g.permissions:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.json
    
    try:
        user_component = User(get_db_connection())
        
        # Check if user exists
        if not user_component.get_user(user_id):
            return jsonify({'error': 'User not found'}), 404
        
        # Determine what fields to update
        update_fields = {}
        allowed_fields = ['email', 'full_name', 'status', 'role']
        
        for field in allowed_fields:
            if field in data:
                update_fields[field] = data[field]
        
        # Handle password separately (requires old password verification for regular users)
        if 'password' in data:
            if g.user_id == user_id and 'manage_users' not in g.permissions:
                # Regular users must provide old_password
                if 'old_password' not in data:
                    return jsonify({'error': 'Old password is required'}), 400
                
                # Verify old password
                if not user_component.verify_password(user_id, data['old_password']):
                    return jsonify({'error': 'Invalid old password'}), 401
            
            # Update password
            update_fields['password'] = data['password']
        
        if not update_fields:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        # Update the user
        success = user_component.update_user(user_id, **update_fields)
        
        if not success:
            return jsonify({'error': 'Failed to update user'}), 500
        
        # Get the updated user
        user = user_component.get_user(user_id)
        
        # Sanitize output
        if 'password_hash' in user:
            del user['password_hash']
        if 'reset_token' in user:
            del user['reset_token']
        
        return jsonify(user)
    except Exception as e:
        logger.error(f"Error updating user: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@rate_limit
@require_api_key(['manage_users'])
def delete_user(user_id):
    """Delete a user."""
    # Prevent users from deleting themselves
    if g.user_id == user_id:
        return jsonify({'error': 'Cannot delete your own account'}), 400
    
    try:
        user_component = User(get_db_connection())
        
        # Check if user exists
        if not user_component.get_user(user_id):
            return jsonify({'error': 'User not found'}), 404
        
        # Delete the user
        success = user_component.delete_user(user_id)
        
        if not success:
            return jsonify({'error': 'Failed to delete user'}), 500
        
        return jsonify({'message': 'User deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        return jsonify({'error': str(e)}), 500

# API Key management
@app.route('/api/users/<int:user_id>/api-keys', methods=['GET'])
@rate_limit
@require_api_key(['manage_api_keys'])
def list_api_keys(user_id):
    """List API keys for a user."""
    # Check if user is requesting their own keys or has manage_users permission
    if g.user_id != user_id and 'manage_users' not in g.permissions:
        return jsonify({'error': 'Permission denied'}), 403
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
        SELECT id, key, name, permissions, created_at, last_used_at, expires_at, is_active
        FROM api_keys
        WHERE user_id = %s
        ORDER BY created_at DESC
        """
        cursor.execute(query, (user_id,))
        keys = cursor.fetchall()
        cursor.close()
        
        # Parse permissions if stored as JSON string
        for key in keys:
            if isinstance(key['permissions'], str):
                try:
                    key['permissions'] = json.loads(key['permissions'])
                except json.JSONDecodeError:
                    key['permissions'] = []
            
            # Only show a part of the actual key for security
            if 'key' in key:
                key['key'] = key['key'][:8] + '...'
        
        return jsonify(keys)
    except Exception as e:
        logger.error(f"Error listing API keys: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<int:user_id>/api-keys', methods=['POST'])
@rate_limit
@require_api_key(['manage_api_keys'])
def create_api_key(user_id):
    """Create a new API key for a user."""
    # Check if user is creating their own key or has manage_users permission
    if g.user_id != user_id and 'manage_users' not in g.permissions:
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.json or {}
    
    # Validate input
    if 'name' not in data:
        return jsonify({'error': 'Name is required for the API key'}), 400
    
    try:
        # Generate a new API key
        new_api_key = secrets.token_hex(16)
        
        # Default expiration to 1 year if not specified
        expires_at = data.get('expires_at')
        if not expires_at:
            expires_at = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d %H:%M:%S')
        
        # Default permissions based on user role
        permissions = data.get('permissions', [])
        
        # Connect to database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Insert the new API key
        query = """
        INSERT INTO api_keys 
        (user_id, key, name, permissions, created_at, expires_at, is_active)
        VALUES (%s, %s, %s, %s, NOW(), %s, 1)
        """
        
        # Convert permissions to JSON string if it's a list
        if isinstance(permissions, list):
            permissions = json.dumps(permissions)
        
        cursor.execute(query, (user_id, new_api_key, data['name'], permissions, expires_at))
        key_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        
        # Show the full key only on creation
        result = {
            'id': key_id,
            'key': new_api_key,
            'name': data['name'],
            'permissions': permissions if isinstance(permissions, list) else json.loads(permissions),
            'expires_at': expires_at,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'is_active': True
        }
        
        # Add warning about showing the key only once
        result['message'] = 'Store this API key securely - it will not be shown again'
        
        return jsonify(result), 201
    except Exception as e:
        logger.error(f"Error creating API key: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<int:user_id>/api-keys/<int:key_id>', methods=['DELETE'])
@rate_limit
@require_api_key(['manage_api_keys'])
def delete_api_key(user_id, key_id):
    """Delete an API key."""
    # Check if user is deleting their own key or has manage_users permission
    if g.user_id != user_id and 'manage_users' not in g.permissions:
        return jsonify({'error': 'Permission denied'}), 403
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # First check if the key belongs to the user
        query = "SELECT user_id FROM api_keys WHERE id = %s"
        cursor.execute(query, (key_id,))
        key_info = cursor.fetchone()
        
        if not key_info:
            return jsonify({'error': 'API key not found'}), 404
        
        if key_info[0] != user_id:
            return jsonify({'error': 'Permission denied'}), 403
        
        # Delete the key
        query = "DELETE FROM api_keys WHERE id = %s"
        cursor.execute(query, (key_id,))
        conn.commit()
        cursor.close()
        
        # Clear from cache
        for api_key, data in list(api_key_cache.items()):
            if data['user_id'] == user_id:
                del api_key_cache[api_key]
        
        return jsonify({'message': 'API key deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting API key: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Space endpoints
@app.route('/api/spaces', methods=['GET'])
@rate_limit
@require_api_key(['view_spaces'])
def list_spaces():
    """List spaces (paginated)."""
    page = int(request.args.get('page', 1))
    limit = min(int(request.args.get('limit', 20)), 100)  # Max 100 per page
    offset = (page - 1) * limit
    
    # Optional filters
    user_id = request.args.get('user_id')
    status = request.args.get('status')
    search = request.args.get('search')
    tag = request.args.get('tag')
    
    # If user_id is not provided, default to current user unless they have view_all_spaces permission
    if not user_id and 'view_all_spaces' not in g.permissions:
        user_id = g.user_id
    
    try:
        space_component = Space(get_db_connection())
        
        # Special handling for tag filtering
        if tag:
            tag_component = Tag(get_db_connection())
            spaces = tag_component.get_spaces_by_tag(tag, user_id=user_id, limit=limit, offset=offset)
            total = tag_component.count_spaces_by_tag(tag, user_id=user_id)
        else:
            # Regular space listing
            spaces = space_component.list_spaces(
                user_id=user_id,
                status=status,
                search_term=search,
                limit=limit,
                offset=offset
            )
            
            # Get total count for pagination
            total = space_component.count_spaces(
                user_id=user_id,
                status=status,
                search_term=search
            )
        
        return jsonify({
            'data': spaces,
            'page': page,
            'limit': limit,
            'total': total,
            'total_pages': (total + limit - 1) // limit
        })
    except Exception as e:
        logger.error(f"Error listing spaces: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/spaces/<space_id>', methods=['GET'])
@rate_limit
@require_api_key(['view_spaces'])
def get_space(space_id):
    """Get a specific space with details."""
    try:
        space_component = Space(get_db_connection())
        space = space_component.get_space(space_id)
        
        if not space:
            return jsonify({'error': 'Space not found'}), 404
        
        # Check if user has permission to view this space
        if space['user_id'] != g.user_id and 'view_all_spaces' not in g.permissions:
            return jsonify({'error': 'Permission denied'}), 403
        
        # Get related data
        tag_component = Tag(get_db_connection())
        tags = tag_component.get_tags_for_space(space_id)
        
        # Get notes
        notes = space_component.get_space_notes(space_id)
        
        # Get download status
        download_status = space_component.get_download_status(space_id)
        
        # Combine all data
        result = {
            **space,
            'tags': tags,
            'notes': notes,
            'download': download_status
        }
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting space: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/spaces', methods=['POST'])
@rate_limit
@require_api_key(['create_spaces'])
def create_space():
    """Create a new space."""
    data = request.json
    
    # Validate required fields
    if 'space_url' not in data:
        return jsonify({'error': 'Space URL is required'}), 400
    
    try:
        space_component = Space(get_db_connection())
        
        # Extract space_id from URL
        space_id = space_component.extract_space_id(data['space_url'])
        if not space_id:
            return jsonify({'error': 'Invalid Space URL'}), 400
        
        # Check if space already exists for this user
        existing = space_component.get_space(space_id)
        if existing and existing['user_id'] == g.user_id:
            return jsonify({'error': 'Space already exists for this user', 'space': existing}), 409
        
        # Create the space
        space_id = space_component.create_space(
            url=data['space_url'],
            title=data.get('title', ''),
            notes=data.get('notes', ''),
            user_id=g.user_id
        )
        
        if not space_id:
            return jsonify({'error': 'Failed to create space'}), 500
        
        # Get the created space
        space = space_component.get_space(space_id)
        
        # Handle tags if provided
        if 'tags' in data and data['tags']:
            tag_component = Tag(get_db_connection())
            for tag_name in data['tags']:
                # Get or create tag
                tag_id = tag_component.get_tag_by_name(tag_name)
                if not tag_id:
                    tag_id = tag_component.create_tag(tag_name)
                
                # Assign tag to space
                tag_component.tag_space(space_id, tag_id)
            
            # Get updated tags
            space['tags'] = tag_component.get_tags_for_space(space_id)
        
        return jsonify(space), 201
    except Exception as e:
        logger.error(f"Error creating space: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/spaces/<space_id>', methods=['PUT'])
@rate_limit
@require_api_key(['edit_spaces'])
def update_space(space_id):
    """Update a space."""
    data = request.json
    
    try:
        space_component = Space(get_db_connection())
        
        # Get the space
        space = space_component.get_space(space_id)
        if not space:
            return jsonify({'error': 'Space not found'}), 404
        
        # Check if user has permission to update this space
        if space['user_id'] != g.user_id and 'edit_all_spaces' not in g.permissions:
            return jsonify({'error': 'Permission denied'}), 403
        
        # Determine what fields to update
        update_fields = {}
        allowed_fields = ['title', 'status']
        
        for field in allowed_fields:
            if field in data:
                update_fields[field] = data[field]
        
        # Handle notes separately if provided
        if 'notes' in data:
            space_component.update_space_notes(space_id, data['notes'])
        
        if update_fields:
            # Update the space
            success = space_component.update_space(space_id, **update_fields)
            if not success:
                return jsonify({'error': 'Failed to update space'}), 500
        
        # Handle tags if provided
        if 'tags' in data:
            tag_component = Tag(get_db_connection())
            
            # Remove all existing tags first
            tag_component.remove_all_tags_from_space(space_id)
            
            # Add new tags
            for tag_name in data['tags']:
                # Get or create tag
                tag_id = tag_component.get_tag_by_name(tag_name)
                if not tag_id:
                    tag_id = tag_component.create_tag(tag_name)
                
                # Assign tag to space
                tag_component.tag_space(space_id, tag_id)
        
        # Get the updated space with all data
        updated_space = space_component.get_space(space_id)
        
        # Get tags
        tag_component = Tag(get_db_connection())
        updated_space['tags'] = tag_component.get_tags_for_space(space_id)
        
        # Get notes
        updated_space['notes'] = space_component.get_space_notes(space_id)
        
        return jsonify(updated_space)
    except Exception as e:
        logger.error(f"Error updating space: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/spaces/<space_id>', methods=['DELETE'])
@rate_limit
@require_api_key(['delete_spaces'])
def delete_space(space_id):
    """Delete a space."""
    try:
        space_component = Space(get_db_connection())
        
        # Get the space
        space = space_component.get_space(space_id)
        if not space:
            return jsonify({'error': 'Space not found'}), 404
        
        # Check if user has permission to delete this space
        if space['user_id'] != g.user_id and 'delete_all_spaces' not in g.permissions:
            return jsonify({'error': 'Permission denied'}), 403
        
        # Delete the space
        success = space_component.delete_space(space_id)
        
        if not success:
            return jsonify({'error': 'Failed to delete space'}), 500
        
        return jsonify({'message': 'Space deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting space: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Download endpoints
@app.route('/api/spaces/<space_id>/download', methods=['POST'])
@rate_limit
@require_api_key(['download_spaces'])
def download_space(space_id):
    """Download a space."""
    data = request.json or {}
    
    try:
        # First verify space exists and user has permission
        space_component = Space(get_db_connection())
        space = space_component.get_space(space_id)
        
        if not space:
            return jsonify({'error': 'Space not found'}), 404
        
        # Check if user has permission to download this space
        if space['user_id'] != g.user_id and 'download_all_spaces' not in g.permissions:
            return jsonify({'error': 'Permission denied'}), 403
        
        # Get download parameters
        file_type = data.get('file_type', 'mp3')
        async_mode = data.get('async', True)
        
        # Initialize downloader
        downloader = DownloadSpace(get_db_connection())
        
        # Check if there's already a download in progress
        status = space_component.get_download_status(space_id)
        if status and status.get('status') == 'downloading':
            return jsonify({
                'message': 'Download already in progress',
                'status': status
            }), 409
        
        # Get space URL
        space_url = space.get('url')
        if not space_url:
            return jsonify({'error': 'Space URL not found'}), 400
        
        # Start the download
        result = downloader.download(
            space_url=space_url,
            file_type=file_type,
            async_mode=async_mode,
            user_id=g.user_id
        )
        
        if not result:
            return jsonify({'error': 'Failed to start download'}), 500
        
        if async_mode:
            # Return the job ID for async mode
            return jsonify({
                'message': 'Download started',
                'job_id': result,
                'async': True
            })
        else:
            # Return the file path for sync mode
            # Check if file exists
            import os
            file_exists = os.path.exists(result)
            
            return jsonify({
                'message': 'Download completed',
                'file_path': result,
                'async': False,
                'file_exists': file_exists
            })
            
    except Exception as e:
        logger.error(f"Error downloading space: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/downloads/<int:job_id>', methods=['GET'])
@rate_limit
@require_api_key(['view_downloads'])
def get_download_status(job_id):
    """Get status of a download job."""
    try:
        downloader = DownloadSpace(get_db_connection())
        job = downloader.get_download_status(job_id)
        
        if not job:
            return jsonify({'error': 'Download job not found'}), 404
        
        # Check if user has permission to view this download
        if job['user_id'] != g.user_id and 'view_all_downloads' not in g.permissions:
            return jsonify({'error': 'Permission denied'}), 403
        
        # Check if file exists and add file_exists flag to response
        if job['status'] == 'completed' and 'file_path' in job and job['file_path']:
            import os
            job['file_exists'] = os.path.exists(job['file_path'])
        
        return jsonify(job)
    except Exception as e:
        logger.error(f"Error getting download status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/downloads/<int:job_id>/cancel', methods=['POST'])
@rate_limit
@require_api_key(['manage_downloads'])
def cancel_download(job_id):
    """Cancel a download job."""
    try:
        downloader = DownloadSpace(get_db_connection())
        job = downloader.get_download_status(job_id)
        
        if not job:
            return jsonify({'error': 'Download job not found'}), 404
        
        # Check if user has permission to cancel this download
        if job['user_id'] != g.user_id and 'manage_all_downloads' not in g.permissions:
            return jsonify({'error': 'Permission denied'}), 403
        
        # Cancel the download
        success = downloader.cancel_download(job_id)
        
        if not success:
            return jsonify({'error': 'Failed to cancel download'}), 500
        
        return jsonify({'message': 'Download cancelled successfully'})
    except Exception as e:
        logger.error(f"Error cancelling download: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/downloads/check-file/<int:job_id>', methods=['GET'])
@rate_limit
@require_api_key(['view_downloads'])
def check_download_file(job_id):
    """Check if the download file exists for a job."""
    try:
        downloader = DownloadSpace(get_db_connection())
        job = downloader.get_download_status(job_id)
        
        if not job:
            return jsonify({'error': 'Download job not found'}), 404
        
        # Check if user has permission to view this download
        if job['user_id'] != g.user_id and 'view_all_downloads' not in g.permissions:
            return jsonify({'error': 'Permission denied'}), 403
        
        # Check if the job is completed and has a file path
        if job['status'] != 'completed':
            return jsonify({
                'job_id': job_id, 
                'file_exists': False,
                'message': f"Job is not completed (status: {job['status']})"
            })
        
        # Check for file_path in job
        file_path = job.get('file_path')
        if not file_path:
            # Try to find the file using space_id
            import os
            from pathlib import Path
            
            space_id = job.get('space_id')
            if not space_id:
                return jsonify({
                    'job_id': job_id, 
                    'file_exists': False,
                    'message': "No file path or space_id found in job"
                })
            
            # Look for files in downloads directory
            downloads_dir = Path(os.path.dirname(os.path.abspath(__file__))) / "downloads"
            file_exists = False
            found_path = None
            
            if os.path.exists(downloads_dir):
                # Try common filenames
                for ext in ['mp3', 'wav', 'm4a']:
                    potential_path = downloads_dir / f"{space_id}.{ext}"
                    if os.path.exists(potential_path):
                        file_exists = True
                        found_path = str(potential_path)
                        break
                
                # If not found by direct naming, search files containing space_id
                if not file_exists:
                    for file in os.listdir(downloads_dir):
                        if space_id in file and os.path.isfile(os.path.join(downloads_dir, file)):
                            file_exists = True
                            found_path = str(os.path.join(downloads_dir, file))
                            break
            
            return jsonify({
                'job_id': job_id,
                'file_exists': file_exists,
                'file_path': found_path,
                'space_id': space_id
            })
        else:
            # Check if the file exists
            import os
            file_exists = os.path.exists(file_path)
            
            return jsonify({
                'job_id': job_id,
                'file_exists': file_exists,
                'file_path': file_path
            })
    
    except Exception as e:
        logger.error(f"Error checking download file: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/downloads', methods=['GET'])
@rate_limit
@require_api_key(['view_downloads'])
def list_downloads():
    """List download jobs."""
    page = int(request.args.get('page', 1))
    limit = min(int(request.args.get('limit', 20)), 100)
    offset = (page - 1) * limit
    
    status = request.args.get('status')
    
    # If user doesn't have view_all_downloads permission, restrict to their own downloads
    user_id = None if 'view_all_downloads' in g.permissions else g.user_id
    
    try:
        downloader = DownloadSpace(get_db_connection())
        downloads = downloader.list_downloads(
            user_id=user_id,
            status=status,
            limit=limit,
            offset=offset
        )
        
        # Get total count for pagination (would need to implement this in the component)
        # For now, just use the length of the result
        total = len(downloads)
        
        return jsonify({
            'data': downloads,
            'page': page,
            'limit': limit,
            'total': total,
            'total_pages': (total + limit - 1) // limit
        })
    except Exception as e:
        logger.error(f"Error listing downloads: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Tag endpoints
@app.route('/api/tags', methods=['GET'])
@rate_limit
@require_api_key(['view_tags'])
def list_tags():
    """List all tags."""
    try:
        tag_component = Tag(get_db_connection())
        tags = tag_component.list_tags()
        
        return jsonify(tags)
    except Exception as e:
        logger.error(f"Error listing tags: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tags', methods=['POST'])
@rate_limit
@require_api_key(['manage_tags'])
def create_tag():
    """Create a new tag."""
    data = request.json
    
    if 'name' not in data:
        return jsonify({'error': 'Tag name is required'}), 400
    
    try:
        tag_component = Tag(get_db_connection())
        
        # Check if tag already exists
        existing_tag_id = tag_component.get_tag_by_name(data['name'])
        if existing_tag_id:
            return jsonify({'error': 'Tag already exists', 'id': existing_tag_id}), 409
        
        # Create the tag
        tag_id = tag_component.create_tag(data['name'])
        
        if not tag_id:
            return jsonify({'error': 'Failed to create tag'}), 500
        
        return jsonify({'id': tag_id, 'name': data['name']}), 201
    except Exception as e:
        logger.error(f"Error creating tag: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tags/<int:tag_id>', methods=['DELETE'])
@rate_limit
@require_api_key(['manage_tags'])
def delete_tag(tag_id):
    """Delete a tag."""
    try:
        tag_component = Tag(get_db_connection())
        
        # Check if tag exists
        tag = tag_component.get_tag(tag_id)
        if not tag:
            return jsonify({'error': 'Tag not found'}), 404
        
        # Delete the tag
        success = tag_component.delete_tag(tag_id)
        
        if not success:
            return jsonify({'error': 'Failed to delete tag'}), 500
        
        return jsonify({'message': 'Tag deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting tag: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/spaces/<space_id>/tags', methods=['POST'])
@rate_limit
@require_api_key(['edit_spaces'])
def add_tag_to_space(space_id):
    """Add a tag to a space."""
    data = request.json
    
    if 'tag_name' not in data:
        return jsonify({'error': 'Tag name is required'}), 400
    
    try:
        # First verify space exists and user has permission
        space_component = Space(get_db_connection())
        space = space_component.get_space(space_id)
        
        if not space:
            return jsonify({'error': 'Space not found'}), 404
        
        # Check if user has permission to update this space
        if space['user_id'] != g.user_id and 'edit_all_spaces' not in g.permissions:
            return jsonify({'error': 'Permission denied'}), 403
        
        # Get or create the tag
        tag_component = Tag(get_db_connection())
        tag_id = tag_component.get_tag_by_name(data['tag_name'])
        
        if not tag_id:
            # Create the tag if it doesn't exist
            tag_id = tag_component.create_tag(data['tag_name'])
        
        # Add tag to space
        success = tag_component.tag_space(space_id, tag_id)
        
        if not success:
            return jsonify({'error': 'Failed to add tag to space'}), 500
        
        # Get updated tags
        tags = tag_component.get_tags_for_space(space_id)
        
        return jsonify({'message': 'Tag added to space', 'tags': tags})
    except Exception as e:
        logger.error(f"Error adding tag to space: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/spaces/<space_id>/tags/<int:tag_id>', methods=['DELETE'])
@rate_limit
@require_api_key(['edit_spaces'])
def remove_tag_from_space(space_id, tag_id):
    """Remove a tag from a space."""
    try:
        # First verify space exists and user has permission
        space_component = Space(get_db_connection())
        space = space_component.get_space(space_id)
        
        if not space:
            return jsonify({'error': 'Space not found'}), 404
        
        # Check if user has permission to update this space
        if space['user_id'] != g.user_id and 'edit_all_spaces' not in g.permissions:
            return jsonify({'error': 'Permission denied'}), 403
        
        # Remove tag from space
        tag_component = Tag(get_db_connection())
        success = tag_component.remove_tag_from_space(space_id, tag_id)
        
        if not success:
            return jsonify({'error': 'Failed to remove tag from space'}), 500
        
        # Get updated tags
        tags = tag_component.get_tags_for_space(space_id)
        
        return jsonify({'message': 'Tag removed from space', 'tags': tags})
    except Exception as e:
        logger.error(f"Error removing tag from space: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Statistics endpoints
@app.route('/api/stats', methods=['GET'])
@rate_limit
@require_api_key(['view_stats'])
def get_stats():
    """Get system-wide statistics."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        stats = {}
        
        # Get user counts
        cursor.execute("SELECT COUNT(*) as total_users FROM users")
        stats['total_users'] = cursor.fetchone()['total_users']
        
        # Get space counts
        cursor.execute("SELECT COUNT(*) as total_spaces FROM spaces")
        stats['total_spaces'] = cursor.fetchone()['total_spaces']
        
        # Get download counts
        cursor.execute("SELECT COUNT(*) as total_downloads FROM space_download_scheduler")
        stats['total_downloads'] = cursor.fetchone()['total_downloads']
        
        # Get download status breakdown
        cursor.execute("""
        SELECT status, COUNT(*) as count 
        FROM space_download_scheduler 
        GROUP BY status
        """)
        stats['downloads_by_status'] = {row['status']: row['count'] for row in cursor.fetchall()}
        
        # Get tag counts
        cursor.execute("SELECT COUNT(*) as total_tags FROM tags")
        stats['total_tags'] = cursor.fetchone()['total_tags']
        
        # Get top tags
        cursor.execute("""
        SELECT t.name, COUNT(st.space_id) as space_count
        FROM tags t
        JOIN space_tags st ON t.id = st.tag_id
        GROUP BY t.id
        ORDER BY space_count DESC
        LIMIT 10
        """)
        stats['top_tags'] = {row['name']: row['space_count'] for row in cursor.fetchall()}
        
        # Get recent activity (last 7 days)
        cursor.execute("""
        SELECT 
            DATE(created_at) as date,
            COUNT(*) as count
        FROM spaces
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        GROUP BY DATE(created_at)
        ORDER BY date
        """)
        
        # Create a dictionary with all dates
        from datetime import datetime, timedelta
        today = datetime.now().date()
        
        # Initialize with zero counts
        activity = {}
        for i in range(7):
            date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
            activity[date] = 0
        
        # Fill in actual counts
        for row in cursor.fetchall():
            date_str = row['date'].strftime('%Y-%m-%d')
            activity[date_str] = row['count']
        
        # Sort by date
        stats['recent_activity'] = {k: activity[k] for k in sorted(activity.keys())}
        
        cursor.close()
        
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Run the application
if __name__ == '__main__':
    # Create api_keys table if it doesn't exist
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if api_keys table exists
        cursor.execute("SHOW TABLES LIKE 'api_keys'")
        if not cursor.fetchone():
            print("Creating api_keys table...")
            
            # Create api_keys table
            cursor.execute("""
            CREATE TABLE api_keys (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                `key` VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                permissions JSON NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP NULL,
                expires_at TIMESTAMP NULL,
                is_active TINYINT(1) NOT NULL DEFAULT 1,
                UNIQUE KEY `key` (`key`),
                INDEX idx_user_id (user_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            
            conn.commit()
            print("api_keys table created successfully")
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error checking/creating api_keys table: {e}")
    
    print(f"Starting API server on {API_HOST}:{API_PORT}...")
    app.run(host=API_HOST, port=API_PORT, debug=API_DEBUG)