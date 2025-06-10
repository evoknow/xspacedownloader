#!/usr/bin/env python3
# components/Tag.py

import json
import mysql.connector
from mysql.connector import Error

# Import cache invalidation function from Space component
try:
    from components.Space import invalidate_spaces_cache
except ImportError:
    # If we can't import, create a dummy function
    def invalidate_spaces_cache():
        pass

class Tag:
    """
    Class to manage database actions on tags.
    Handles CRUD operations for tags.
    """
    
    def __init__(self, db_connection=None):
        """Initialize the Tag component with a database connection."""
        self.connection = db_connection
        if not self.connection:
            try:
                with open('db_config.json', 'r') as config_file:
                    config = json.load(config_file)
                    if config["type"] == "mysql":
                        db_config = config["mysql"].copy()
                        # Remove unsupported parameters
                        if 'use_ssl' in db_config:
                            del db_config['use_ssl']
                    else:
                        raise ValueError(f"Unsupported database type: {config['type']}")
                self.connection = mysql.connector.connect(**db_config)
            except Error as e:
                print(f"Error connecting to MySQL Database: {e}")
                raise
    
    def __del__(self):
        """Close the database connection when the object is destroyed."""
        if hasattr(self, 'connection') and self.connection and self.connection.is_connected():
            self.connection.close()
    
    def create_tag(self, tag_name):
        """
        Create a new tag if it doesn't exist.
        Tags are normalized (lowercase).
        
        Args:
            tag_name (str): Tag name
            
        Returns:
            int: Tag ID
        """
        try:
            cursor = self.connection.cursor()
            
            # Normalize tag name (lowercase)
            normalized_tag = tag_name.lower().strip()
            
            # Check if tag already exists
            cursor.execute("SELECT id FROM tags WHERE name = %s", (normalized_tag,))
            result = cursor.fetchone()
            
            if result:
                return result[0]
            
            # Create the tag
            cursor.execute("INSERT INTO tags (name) VALUES (%s)", (normalized_tag,))
            tag_id = cursor.lastrowid
            
            self.connection.commit()
            return tag_id
            
        except Error as e:
            print(f"Error creating tag: {e}")
            self.connection.rollback()
            return None
        finally:
            if cursor:
                cursor.close()
    
    def get_tag(self, tag_id=None, tag_name=None):
        """
        Get tag by ID or name.
        
        Args:
            tag_id (int, optional): Tag ID
            tag_name (str, optional): Tag name
            
        Returns:
            dict: Tag details or None if not found
        """
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            if tag_id:
                query = "SELECT * FROM tags WHERE id = %s"
                cursor.execute(query, (tag_id,))
            elif tag_name:
                normalized_tag = tag_name.lower().strip()
                query = "SELECT * FROM tags WHERE name = %s"
                cursor.execute(query, (normalized_tag,))
            else:
                return None
                
            tag = cursor.fetchone()
            
            # For backwards compatibility with tests, map id to tag_id and name to tag_name
            if tag:
                if 'id' in tag and 'tag_id' not in tag:
                    tag['tag_id'] = tag['id']
                if 'name' in tag and 'tag_name' not in tag:
                    tag['tag_name'] = tag['name']
                    
            return tag
            
        except Error as e:
            print(f"Error getting tag: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
                
    def get_tag_by_name(self, tag_name):
        """
        Get tag ID by name.
        
        Args:
            tag_name (str): Tag name
            
        Returns:
            int: Tag ID or None if not found
        """
        try:
            cursor = self.connection.cursor()
            
            # Normalize tag name (lowercase)
            normalized_tag = tag_name.lower().strip()
            
            # Check if tag exists
            cursor.execute("SELECT id FROM tags WHERE name = %s", (normalized_tag,))
            result = cursor.fetchone()
            
            return result[0] if result else None
            
        except Error as e:
            print(f"Error getting tag by name: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
    
    def list_tags(self, limit=100, offset=0):
        """
        List all tags.
        
        Args:
            limit (int, optional): Maximum number of results
            offset (int, optional): Pagination offset
            
        Returns:
            list: List of tag dictionaries
        """
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            query = """
            SELECT t.*, COUNT(st.space_id) as usage_count
            FROM tags t
            LEFT JOIN space_tags st ON t.id = st.tag_id
            GROUP BY t.id
            ORDER BY usage_count DESC, t.name
            LIMIT %s OFFSET %s
            """
            cursor.execute(query, (limit, offset))
            tags = cursor.fetchall()
            
            # For backwards compatibility with tests, map id to tag_id and name to tag_name
            for tag in tags:
                if 'id' in tag and 'tag_id' not in tag:
                    tag['tag_id'] = tag['id']
                if 'name' in tag and 'tag_name' not in tag:
                    tag['tag_name'] = tag['name']
                
            return tags
            
        except Error as e:
            print(f"Error listing tags: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
    
    def search_tags(self, search_term, limit=100):
        """
        Search for tags containing the search term.
        
        Args:
            search_term (str): Search term
            limit (int, optional): Maximum number of results
            
        Returns:
            list: List of tag dictionaries matching search
        """
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            query = """
            SELECT * FROM tags
            WHERE name LIKE %s
            ORDER BY name
            LIMIT %s
            """
            cursor.execute(query, (f'%{search_term.lower()}%', limit))
            tags = cursor.fetchall()
            
            # For backwards compatibility with tests, map id to tag_id and name to tag_name
            for tag in tags:
                if 'id' in tag and 'tag_id' not in tag:
                    tag['tag_id'] = tag['id']
                if 'name' in tag and 'tag_name' not in tag:
                    tag['tag_name'] = tag['name']
            
            return tags
            
        except Error as e:
            print(f"Error searching tags: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
    
    def add_tags_to_space(self, space_id, tags, user_id=0, visitor_id=None):
        """
        Add multiple tags to a space.
        
        Args:
            space_id (str): The unique space identifier
            tags (list): List of tag names
            user_id (int, optional): User ID. Defaults to 0 for visitors.
            visitor_id (str, optional): Visitor unique ID (not used in current schema)
            
        Returns:
            int: Number of tags added
        """
        try:
            cursor = self.connection.cursor()
            count = 0
            
            for tag_name in tags:
                if not tag_name.strip():
                    continue
                    
                # Create or get tag ID
                tag_id = self.create_tag(tag_name)
                if not tag_id:
                    continue
                
                # Add relationship between space and tag
                try:
                    cursor.execute(
                        """
                        INSERT INTO space_tags (space_id, tag_id, user_id)
                        VALUES (%s, %s, %s)
                        """,
                        (space_id, tag_id, user_id)
                    )
                    count += 1
                except Error as e:
                    # Silently ignore duplicate key errors (code 1062)
                    if not (isinstance(e, mysql.connector.errors.IntegrityError) and "1062" in str(e)):
                        print(f"Error adding tag to space: {e}")
                    # Tag might already be associated with this space
                    pass
            
            self.connection.commit()
            
            # Invalidate cache if tags were added
            if count > 0:
                invalidate_spaces_cache()
            
            return count
            
        except Error as e:
            print(f"Error adding tags to space: {e}")
            self.connection.rollback()
            return 0
        finally:
            if cursor:
                cursor.close()
    
    def remove_tag_from_space(self, space_id, tag_id, user_id=None, visitor_id=None, force_remove=False):
        """
        Remove a tag from a space.
        
        Args:
            space_id (str): The unique space identifier
            tag_id (int): Tag ID
            user_id (int, optional): User ID - if provided, only removes tags added by this user
            visitor_id (str, optional): Visitor unique ID (not used in current schema)
            force_remove (bool): If True, removes tag regardless of who added it
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cursor = self.connection.cursor()
            
            if force_remove:
                # Remove tag regardless of who added it (for admins or space owners)
                query = """
                DELETE FROM space_tags
                WHERE space_id = %s AND tag_id = %s
                """
                params = [space_id, tag_id]
            else:
                # Original behavior - respect user_id constraint
                query = """
                DELETE FROM space_tags
                WHERE space_id = %s AND tag_id = %s
                """
                params = [space_id, tag_id]
                
                if user_id is not None:
                    query += " AND user_id = %s"
                    params.append(user_id)
            
            cursor.execute(query, params)
            self.connection.commit()
            
            # Invalidate cache if tag was removed
            result = cursor.rowcount > 0
            if result:
                invalidate_spaces_cache()
            
            return result
            
        except Error as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error removing tag {tag_id} from space {space_id}: {e}")
            self.connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
    
    def get_space_tags(self, space_id, user_id=None, visitor_id=None):
        """
        Get all tags for a space.
        
        Args:
            space_id (str): The unique space identifier
            user_id (int, optional): Filter tags by user_id
            visitor_id (str, optional): Filter tags by visitor_id
            
        Returns:
            list: List of tag dictionaries
        """
        cursor = None
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            query = """
            SELECT t.*
            FROM tags t
            JOIN space_tags st ON t.id = st.tag_id
            WHERE st.space_id = %s
            """
            params = [space_id]
            
            if user_id:
                query += " AND st.user_id = %s"
                params.append(user_id)
                
            if visitor_id:
                # Our schema does not have visitor_id in space_tags, so we skip this filter
                pass
                
            query += " ORDER BY t.name"
            
            cursor.execute(query, params)
            tags = cursor.fetchall()
            
            # For backwards compatibility with tests, map id to tag_id and name to tag_name
            for tag in tags:
                if 'id' in tag and 'tag_id' not in tag:
                    tag['tag_id'] = tag['id']
                if 'name' in tag and 'tag_name' not in tag:
                    tag['tag_name'] = tag['name']
            
            return tags
            
        except Error as e:
            print(f"Error getting space tags: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
                
    def get_tags_for_space(self, space_id):
        """
        Alias for get_space_tags for backwards compatibility.
        
        Args:
            space_id (str): The unique space identifier
            
        Returns:
            list: List of tag dictionaries
        """
        return self.get_space_tags(space_id)
        
    def tag_space(self, space_id, tag_id, user_id=0):
        """
        Add a tag to a space.
        
        Args:
            space_id (str): The unique space identifier
            tag_id (int): Tag ID
            user_id (int, optional): User ID. Defaults to 0 for visitors.
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cursor = self.connection.cursor()
            
            # Add relationship between space and tag
            try:
                cursor.execute(
                    """
                    INSERT INTO space_tags (space_id, tag_id, user_id)
                    VALUES (%s, %s, %s)
                    """,
                    (space_id, tag_id, user_id)
                )
                self.connection.commit()
                return True
            except Error as e:
                # Silently ignore duplicate key errors (code 1062)
                if not (isinstance(e, mysql.connector.errors.IntegrityError) and "1062" in str(e)):
                    print(f"Error adding tag to space: {e}")
                # Return True even if tag was already associated (for API compatibility)
                return True
            
        except Error as e:
            print(f"Error tagging space: {e}")
            self.connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
                
    def remove_all_tags_from_space(self, space_id):
        """
        Remove all tags from a space.
        
        Args:
            space_id (str): The unique space identifier
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cursor = self.connection.cursor()
            
            query = "DELETE FROM space_tags WHERE space_id = %s"
            cursor.execute(query, (space_id,))
            self.connection.commit()
            
            # Invalidate cache if any tags were removed
            if cursor.rowcount > 0:
                invalidate_spaces_cache()
            
            return True
            
        except Error as e:
            print(f"Error removing all tags from space: {e}")
            self.connection.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
                
    def get_spaces_by_tag(self, tag_name, user_id=None, limit=10, offset=0):
        """
        Get spaces with a specific tag.
        
        Args:
            tag_name (str): Tag name
            user_id (int, optional): Filter by user_id
            limit (int, optional): Maximum number of results
            offset (int, optional): Pagination offset
            
        Returns:
            list: List of space dictionaries
        """
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            # First get the tag ID
            tag_id = self.get_tag_by_name(tag_name)
            if not tag_id:
                return []
            
            # Then query spaces with this tag
            query = """
            SELECT s.*
            FROM spaces s
            JOIN space_tags st ON s.space_id = st.space_id
            WHERE st.tag_id = %s
            """
            params = [tag_id]
            
            if user_id is not None:
                query += " AND s.user_id = %s"
                params.append(user_id)
                
            query += " ORDER BY s.created_at DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            spaces = cursor.fetchall()
            
            # For compatibility, add title and map fields
            for space in spaces:
                if 'filename' in space and 'title' not in space:
                    # Extract title from filename
                    filename = space['filename']
                    # Default title
                    title = f"Space {space['space_id']}"
                    
                    # Try to extract a better title
                    if '_' in filename and '.' in filename:
                        # Remove extension
                        base = filename.split('.')[0]
                        # Remove space_id suffix if present
                        if space['space_id'] in base:
                            title = base.split('_' + space['space_id'])[0].replace('_', ' ')
                    
                    space['title'] = title
                
                # Map other fields for backwards compatibility
                if 'download_cnt' in space and 'download_progress' not in space:
                    space['download_progress'] = space['download_cnt']
                    
                # Status mapping
                if 'status' in space:
                    if space['status'] == 'completed':
                        space['status'] = 'downloaded'
                    elif space['status'] == 'pending' and space.get('download_progress', 0) > 0:
                        space['status'] = 'downloading'
            
            return spaces
            
        except Error as e:
            print(f"Error getting spaces by tag: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
                
    def count_spaces_by_tag(self, tag_name, user_id=None):
        """
        Count spaces with a specific tag.
        
        Args:
            tag_name (str): Tag name
            user_id (int, optional): Filter by user_id
            
        Returns:
            int: Total number of spaces with the tag
        """
        try:
            cursor = self.connection.cursor()
            
            # First get the tag ID
            tag_id = self.get_tag_by_name(tag_name)
            if not tag_id:
                return 0
            
            # Then count spaces with this tag
            query = """
            SELECT COUNT(*)
            FROM space_tags st
            JOIN spaces s ON st.space_id = s.space_id
            WHERE st.tag_id = %s
            """
            params = [tag_id]
            
            if user_id is not None:
                query += " AND s.user_id = %s"
                params.append(user_id)
                
            cursor.execute(query, params)
            count = cursor.fetchone()[0]
            
            return count
            
        except Error as e:
            print(f"Error counting spaces by tag: {e}")
            return 0
        finally:
            if cursor:
                cursor.close()
    
    def get_popular_tags(self, limit=10):
        """
        Get the most popular tags.
        
        Args:
            limit (int, optional): Maximum number of results
            
        Returns:
            list: List of tag dictionaries with usage count
        """
        try:
            cursor = self.connection.cursor(dictionary=True)
            
            query = """
            SELECT t.id, t.name, COUNT(st.space_id) as usage_count
            FROM tags t
            JOIN space_tags st ON t.id = st.tag_id
            GROUP BY t.id
            ORDER BY usage_count DESC
            LIMIT %s
            """
            cursor.execute(query, (limit,))
            tags = cursor.fetchall()
            
            # For backwards compatibility with tests, map id to tag_id and name to tag_name
            for tag in tags:
                if 'id' in tag and 'tag_id' not in tag:
                    tag['tag_id'] = tag['id']
                if 'name' in tag and 'tag_name' not in tag:
                    tag['tag_name'] = tag['name']
            
            return tags
            
        except Error as e:
            print(f"Error getting popular tags: {e}")
            return []
        finally:
            if cursor:
                cursor.close()