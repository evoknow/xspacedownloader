#!/usr/bin/env python3
"""
Visitor Tracking Component
Handles visitor download limitations and tracking.
"""

import logging
import uuid
from typing import Tuple, Optional
from flask import request, session
from .DatabaseManager import DatabaseManager

logger = logging.getLogger(__name__)

class VisitorTracker:
    """Handles visitor download tracking and limitations."""
    
    def __init__(self):
        """Initialize the VisitorTracker."""
        try:
            self.db = DatabaseManager()
        except Exception as e:
            logger.error(f"Failed to initialize DatabaseManager in VisitorTracker: {e}")
            self.db = None
    
    def get_or_create_visitor_id(self) -> str:
        """
        Get or create a visitor ID from session/cookie.
        
        Returns:
            str: Visitor ID (cookie_id)
        """
        # Check if visitor ID exists in session
        if 'visitor_id' not in session:
            # Generate new visitor ID
            session['visitor_id'] = str(uuid.uuid4())
            session.permanent = True  # Make session persistent
        
        return session['visitor_id']
    
    def get_visitor_ip(self) -> str:
        """
        Get visitor's IP address, handling proxies.
        
        Returns:
            str: IP address
        """
        # Check for forwarded IP (from proxy/load balancer)
        if request.environ.get('HTTP_X_FORWARDED_FOR'):
            ip = request.environ['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
        elif request.environ.get('HTTP_X_REAL_IP'):
            ip = request.environ['HTTP_X_REAL_IP']
        else:
            ip = request.environ.get('REMOTE_ADDR', '0.0.0.0')
        
        return ip
    
    def check_visitor_download_limit(self, space_id: str) -> Tuple[bool, str]:
        """
        Check if visitor has exceeded download limits.
        
        Args:
            space_id (str): Space ID being downloaded
            
        Returns:
            tuple: (allowed, reason)
        """
        # If user is logged in, allow unlimited downloads
        if session.get('user_id'):
            return True, "logged_in_user"
        
        visitor_id = self.get_or_create_visitor_id()
        ip_address = self.get_visitor_ip()
        
        if not self.db:
            logger.warning("Database not available for visitor limit check")
            return True, "database_unavailable"
        
        try:
            cursor = self.db.connection.cursor(dictionary=True)
            
            # Check existing downloads for this visitor (by IP and cookie)
            query = """
                SELECT COUNT(*) as download_count
                FROM visitor_download_log
                WHERE (ip_address = %s OR cookie_id = %s) 
                AND downloaded = 1
            """
            
            cursor.execute(query, (ip_address, visitor_id))
            result = cursor.fetchone()
            cursor.close()
            
            download_count = result['download_count'] if result else 0
            
            # Limit: 1 download for non-logged-in visitors
            if download_count >= 1:
                logger.info(f"Visitor {visitor_id} ({ip_address}) exceeded download limit: {download_count} downloads")
                return False, f"download_limit_exceeded"
            
            return True, "within_limit"
            
        except Exception as e:
            logger.error(f"Error checking visitor download limit: {e}")
            # On error, be conservative and deny
            return False, "error_checking_limit"
    
    def record_visitor_download(self, space_id: str, success: bool = True) -> bool:
        """
        Record a visitor download attempt.
        
        Args:
            space_id (str): Space ID
            success (bool): Whether the download was successful
            
        Returns:
            bool: True if recorded successfully
        """
        # Don't track downloads for logged-in users in visitor table
        if session.get('user_id'):
            return True
        
        visitor_id = self.get_or_create_visitor_id()
        ip_address = self.get_visitor_ip()
        
        if not self.db:
            logger.warning("Database not available for visitor download recording")
            return True
        
        try:
            cursor = self.db.connection.cursor()
            
            query = """
                INSERT INTO visitor_download_log (
                    ip_address, cookie_id, space_id, downloaded, created_at
                ) VALUES (%s, %s, %s, %s, NOW())
            """
            
            cursor.execute(query, (ip_address, visitor_id, space_id, success))
            self.db.connection.commit()
            cursor.close()
            
            logger.info(f"Recorded visitor download: {visitor_id} ({ip_address}) - space {space_id} - success: {success}")
            return True
            
        except Exception as e:
            logger.error(f"Error recording visitor download: {e}")
            return False
    
    def can_visitor_transcribe(self) -> Tuple[bool, str]:
        """
        Check if visitor can use transcription (they can't).
        
        Returns:
            tuple: (allowed, reason)
        """
        if session.get('user_id'):
            return True, "logged_in_user"
        
        return False, "transcription_requires_login"
    
    def can_visitor_translate(self) -> Tuple[bool, str]:
        """
        Check if visitor can use translation (they can't).
        
        Returns:
            tuple: (allowed, reason)
        """
        if session.get('user_id'):
            return True, "logged_in_user"
        
        return False, "translation_requires_login"
    
    def get_visitor_stats(self, visitor_id: str = None, ip_address: str = None) -> dict:
        """
        Get statistics for a specific visitor.
        
        Args:
            visitor_id (str, optional): Visitor ID
            ip_address (str, optional): IP address
            
        Returns:
            dict: Visitor statistics
        """
        if not visitor_id and not ip_address:
            visitor_id = self.get_or_create_visitor_id()
            ip_address = self.get_visitor_ip()
        
        try:
            cursor = self.db.connection.cursor(dictionary=True)
            
            query = """
                SELECT 
                    COUNT(*) as total_attempts,
                    SUM(downloaded) as successful_downloads,
                    MIN(created_at) as first_visit,
                    MAX(created_at) as last_visit
                FROM visitor_download_log
                WHERE ip_address = %s OR cookie_id = %s
            """
            
            cursor.execute(query, (ip_address, visitor_id))
            result = cursor.fetchone()
            cursor.close()
            
            if result and result['total_attempts'] > 0:
                return {
                    'total_attempts': result['total_attempts'],
                    'successful_downloads': result['successful_downloads'] or 0,
                    'first_visit': result['first_visit'],
                    'last_visit': result['last_visit'],
                    'download_limit_reached': result['successful_downloads'] >= 1
                }
            else:
                return {
                    'total_attempts': 0,
                    'successful_downloads': 0,
                    'first_visit': None,
                    'last_visit': None,
                    'download_limit_reached': False
                }
                
        except Exception as e:
            logger.error(f"Error getting visitor stats: {e}")
            return {
                'total_attempts': 0,
                'successful_downloads': 0,
                'first_visit': None,
                'last_visit': None,
                'download_limit_reached': False,
                'error': str(e)
            }