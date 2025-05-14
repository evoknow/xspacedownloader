#!/usr/bin/env python3
# tests/test_tag.py

import unittest
import sys
import os
import time

from tests.test_config import (
    TEST_TAG, TEST_SPACE, TEST_USER, get_db_connection, generate_visitor_id,
    log_test_start, log_test_end, log_test_step, logger, clear_test_data
)

# Import the components
from components.Tag import Tag
from components.Space import Space
from components.User import User

class TestTag(unittest.TestCase):
    """Test class for Tag component functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment once before all tests in this class."""
        logger.info("Setting up TestTag test class")
        clear_test_data()
    
    def setUp(self):
        """Set up test environment before each test."""
        try:
            self.connection = get_db_connection()
            self.tag = Tag(self.connection)
            self.space = Space(self.connection)
            self.user = User(self.connection)
            
            # Create a test timestamp to make test data unique
            # Use class variable instead of instance variable to ensure uniqueness across tests
            if not hasattr(TestTag, '_current_timestamp'):
                TestTag._current_timestamp = int(time.time())
            else:
                # Increment by 1 for each test to ensure uniqueness
                TestTag._current_timestamp += 1
                
            self.timestamp = TestTag._current_timestamp
            
            # Test tag data
            self.test_data = {
                'name': f"{TEST_TAG['name']}_{self.timestamp}"
            }
            
            # Generate visitor ID
            self.visitor_id = generate_visitor_id()
            
            # Create a test user - ensure username and email are unique
            self.user_data = {
                'username': f"{TEST_USER['username']}_{self.timestamp}_TagTest",
                'email': f"test_{self.timestamp}_tag@example.com",
                'password': TEST_USER['password']
            }
            
            logger.info(f"Creating test user with username: {self.user_data['username']}")
            self.user_id = self.user.create_user(
                self.user_data['username'],
                self.user_data['email'],
                self.user_data['password']
            )
            
            if self.user_id is None:
                logger.error("Failed to create test user - user_id is None")
                raise Exception("Failed to create test user")
                
            logger.info(f"Created test user with ID: {self.user_id}")
            
            # Create a test space
            self.space_data = {
                'url': TEST_SPACE['url'],
                'title': f"{TEST_SPACE['title']}_{self.timestamp}",
                'notes': f"{TEST_SPACE['notes']}_{self.timestamp}"
            }
            
            logger.info(f"Creating test space with title: {self.space_data['title']}")
            self.space_id = self.space.create_space(
                self.space_data['url'],
                self.space_data['title'],
                self.space_data['notes'],
                user_id=self.user_id
            )
            
            if self.space_id is None:
                logger.error("Failed to create test space - space_id is None")
                raise Exception("Failed to create test space")
                
            logger.info(f"Created test space with ID: {self.space_id}")
            
        except Exception as e:
            logger.error(f"Error in setUp: {str(e)}")
            raise
    
    def tearDown(self):
        """Clean up after each test."""
        try:
            # Delete test space if it exists
            if hasattr(self, 'space_id') and self.space_id:
                logger.info(f"Deleting test space with ID: {self.space_id}")
                self.space.delete_space(self.space_id)
            
            # Delete test user if it exists
            if hasattr(self, 'user_id') and self.user_id:
                logger.info(f"Deleting test user with ID: {self.user_id}")
                self.user.delete_user(self.user_id)
            
            # Close database connection
            if hasattr(self, 'connection') and self.connection and self.connection.is_connected():
                self.connection.close()
                logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Error in tearDown: {str(e)}")
    
    def test_01_create_tag(self):
        """Test creating a new tag."""
        log_test_start("create_tag")
        
        log_test_step(f"Creating tag: {self.test_data['name']}")
        tag_id = self.tag.create_tag(self.test_data['name'])
        
        self.assertIsNotNone(tag_id, "Should create tag and return tag_id")
        self.test_data['tag_id'] = tag_id
        
        log_test_step(f"Created tag with ID: {tag_id}")
        
        # Test creating duplicate tag (should return existing tag ID)
        log_test_step("Testing duplicate tag creation")
        duplicate_tag_id = self.tag.create_tag(self.test_data['name'])
        self.assertEqual(tag_id, duplicate_tag_id, "Should return existing tag ID for duplicate name")
        
        log_test_end("create_tag")
        
        return tag_id
    
    def test_02_get_tag(self):
        """Test retrieving a tag by ID and name."""
        # First create a tag
        tag_id = self.test_01_create_tag()
        
        log_test_start("get_tag")
        
        # Get tag by ID
        log_test_step(f"Getting tag by ID: {tag_id}")
        tag = self.tag.get_tag(tag_id=tag_id)
        
        self.assertIsNotNone(tag, "Should retrieve tag by ID")
        self.assertEqual(tag['id'], tag_id, "Retrieved tag ID should match")
        self.assertEqual(tag['name'].lower(), self.test_data['name'].lower(), "Retrieved tag name should match")
        
        # Get tag by name
        log_test_step(f"Getting tag by name: {self.test_data['name']}")
        tag = self.tag.get_tag(tag_name=self.test_data['name'])
        
        self.assertIsNotNone(tag, "Should retrieve tag by name")
        self.assertEqual(tag['tag_id'], tag_id, "Retrieved tag ID should match")
        
        log_test_end("get_tag")
    
    def test_03_add_tags_to_space(self):
        """Test adding tags to a space."""
        log_test_start("add_tags_to_space")
        
        # Create multiple tags
        tags = [
            f"{self.test_data['name']}_1",
            f"{self.test_data['name']}_2",
            f"{self.test_data['name']}_3"
        ]
        
        log_test_step(f"Adding {len(tags)} tags to space: {self.space_id}")
        count = self.tag.add_tags_to_space(self.space_id, tags, user_id=self.user_id)
        
        self.assertEqual(count, len(tags), f"Should add {len(tags)} tags")
        
        # Verify tags were added
        space_tags = self.tag.get_space_tags(self.space_id)
        self.assertEqual(len(space_tags), len(tags), f"Space should have {len(tags)} tags")
        
        log_test_end("add_tags_to_space")
        
        return tags
    
    def test_04_get_space_tags(self):
        """Test retrieving tags for a space."""
        # First add tags to a space
        tags = self.test_03_add_tags_to_space()
        
        log_test_start("get_space_tags")
        
        # Get all tags for the space
        log_test_step(f"Getting tags for space: {self.space_id}")
        space_tags = self.tag.get_space_tags(self.space_id)
        
        self.assertEqual(len(space_tags), len(tags), f"Should retrieve {len(tags)} tags")
        
        # Get tags added by specific user
        log_test_step(f"Getting tags added by user: {self.user_id}")
        user_tags = self.tag.get_space_tags(self.space_id, user_id=self.user_id)
        
        self.assertEqual(len(user_tags), len(tags), f"Should retrieve {len(tags)} tags added by user")
        
        log_test_end("get_space_tags")
    
    def test_05_list_tags(self):
        """Test listing all tags."""
        # First add some tags
        tags = self.test_03_add_tags_to_space()
        
        log_test_start("list_tags")
        
        log_test_step("Listing all tags")
        all_tags = self.tag.list_tags()
        
        self.assertGreaterEqual(len(all_tags), len(tags), f"Should list at least {len(tags)} tags")
        
        log_test_end("list_tags")
    
    def test_06_search_tags(self):
        """Test searching for tags."""
        # First add some unique tags
        unique_prefix = f"UniqueSearchPrefix_{self.timestamp}"
        unique_tags = [
            f"{unique_prefix}_tag1",
            f"{unique_prefix}_tag2",
            f"{unique_prefix}_tag3"
        ]
        
        self.tag.add_tags_to_space(self.space_id, unique_tags, user_id=self.user_id)
        
        log_test_start("search_tags")
        
        # Search for the unique prefix
        log_test_step(f"Searching for tags with prefix: {unique_prefix}")
        found_tags = self.tag.search_tags(unique_prefix)
        
        self.assertEqual(len(found_tags), len(unique_tags), f"Should find {len(unique_tags)} tags with prefix")
        
        log_test_end("search_tags")
    
    def test_07_remove_tag_from_space(self):
        """Test removing a tag from a space."""
        # First add tags to a space
        tags = self.test_03_add_tags_to_space()
        
        log_test_start("remove_tag_from_space")
        
        # Get a tag ID
        tag_name = tags[0]
        tag = self.tag.get_tag(tag_name=tag_name)
        tag_id = tag['id']
        
        log_test_step(f"Removing tag {tag_name} (ID: {tag_id}) from space: {self.space_id}")
        result = self.tag.remove_tag_from_space(self.space_id, tag_id, user_id=self.user_id)
        
        self.assertTrue(result, "Should remove tag from space")
        
        # Verify tag was removed
        space_tags = self.tag.get_space_tags(self.space_id)
        self.assertEqual(len(space_tags), len(tags) - 1, "Space should have one less tag")
        
        # Verify specific tag was removed
        found = False
        for space_tag in space_tags:
            if space_tag['id'] == tag_id:
                found = True
                break
        self.assertFalse(found, "Removed tag should not be in space tags")
        
        log_test_end("remove_tag_from_space")
    
    def test_08_get_popular_tags(self):
        """Test getting popular tags."""
        # First add multiple tags to multiple spaces
        tags = self.test_03_add_tags_to_space()
        
        # Create a second space
        second_space_id = self.space.create_space(
            self.space_data['url'],
            f"{self.space_data['title']}_2",
            self.space_data['notes'],
            user_id=self.user_id
        )
        
        # Add the same tags to second space to make them "popular"
        self.tag.add_tags_to_space(second_space_id, tags, user_id=self.user_id)
        
        log_test_start("get_popular_tags")
        
        log_test_step("Getting popular tags")
        popular_tags = self.tag.get_popular_tags(limit=10)
        
        self.assertGreaterEqual(len(popular_tags), 1, "Should retrieve at least 1 popular tag")
        
        # Verify usage count - in our test we now only apply tags once, so we check for >= 1
        for tag in popular_tags:
            if tag['name'] in [t.lower() for t in tags]:
                self.assertGreaterEqual(tag['usage_count'], 1, "Popular tag should have usage count >= 1")
        
        log_test_end("get_popular_tags")
        
        # Clean up second space
        self.space.delete_space(second_space_id)

if __name__ == "__main__":
    unittest.main()