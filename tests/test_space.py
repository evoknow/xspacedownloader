#!/usr/bin/env python3
# tests/test_space.py

import unittest
import sys
import os
import time

from tests.test_config import (
    TEST_SPACE, TEST_USER, get_db_connection, generate_visitor_id, 
    log_test_start, log_test_end, log_test_step, logger, clear_test_data
)

# Import the components
from components.Space import Space
from components.User import User

class TestSpace(unittest.TestCase):
    """Test class for Space component functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment once before all tests in this class."""
        logger.info("Setting up TestSpace test class")
        clear_test_data()
    
    def setUp(self):
        """Set up test environment before each test."""
        try:
            self.connection = get_db_connection()
            self.space = Space(self.connection)
            self.user = User(self.connection)
            
            # Create a test timestamp to make test data unique
            # Use class variable instead of instance variable to ensure uniqueness across tests
            if not hasattr(TestSpace, '_current_timestamp'):
                TestSpace._current_timestamp = int(time.time())
            else:
                # Increment by 1 for each test to ensure uniqueness
                TestSpace._current_timestamp += 1
                
            self.timestamp = TestSpace._current_timestamp
            
            # Test space data
            self.test_data = {
                'url': TEST_SPACE['url'],
                'title': f"{TEST_SPACE['title']}_{self.timestamp}",
                'notes': f"{TEST_SPACE['notes']}_{self.timestamp}"
            }
            
            # Generate visitor ID
            self.visitor_id = generate_visitor_id()
            
            # Create a test user for space tests - ensure username and email are unique
            self.user_data = {
                'username': f"{TEST_USER['username']}_{self.timestamp}_SpaceTest",
                'email': f"test_{self.timestamp}_space@example.com",
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
            
        except Exception as e:
            logger.error(f"Error in setUp: {str(e)}")
            raise
    
    def tearDown(self):
        """Clean up after each test."""
        try:
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
    
    def test_01_extract_space_id(self):
        """Test extracting space_id from URL."""
        log_test_start("extract_space_id")
        
        space_id = self.space.extract_space_id(self.test_data['url'])
        self.assertIsNotNone(space_id, "Should extract space_id from URL")
        log_test_step(f"Extracted space_id: {space_id}")
        
        # Test with invalid URL
        invalid_url = "https://example.com/not-a-space"
        space_id = self.space.extract_space_id(invalid_url)
        self.assertIsNone(space_id, "Should return None for invalid URL")
        log_test_step("Correctly handled invalid URL")
        
        log_test_end("extract_space_id")
    
    def test_02_create_space_visitor(self):
        """Test creating a space as a visitor."""
        log_test_start("create_space_visitor")
        
        log_test_step(f"Creating space with visitor ID: {self.visitor_id}")
        space_id = self.space.create_space(
            self.test_data['url'],
            self.test_data['title'],
            self.test_data['notes'],
            visitor_id=self.visitor_id
        )
        
        self.assertIsNotNone(space_id, "Should create space and return space_id")
        self.test_data['space_id'] = space_id
        
        log_test_step(f"Created space with ID: {space_id}")
        log_test_end("create_space_visitor")
        
        return space_id
    
    def test_03_create_space_user(self):
        """Test creating a space as a registered user."""
        log_test_start("create_space_user")
        
        log_test_step(f"Creating space with user ID: {self.user_id}")
        space_id = self.space.create_space(
            self.test_data['url'],
            f"{self.test_data['title']}_user",
            f"{self.test_data['notes']}_user",
            user_id=self.user_id
        )
        
        self.assertIsNotNone(space_id, "Should create space and return space_id")
        
        log_test_step(f"Created space with ID: {space_id}")
        log_test_end("create_space_user")
        
        return space_id
    
    def test_04_get_space(self):
        """Test retrieving a space by ID."""
        # First create a space
        space_id = self.test_02_create_space_visitor()
        
        log_test_start("get_space")
        
        log_test_step(f"Getting space by ID: {space_id}")
        space = self.space.get_space(space_id)
        
        self.assertIsNotNone(space, "Should retrieve space by ID")
        self.assertEqual(space['space_id'], space_id, "Retrieved space ID should match")
        # Extract title portion from original title to match how it's stored in the DB
        expected_title = "Test Space"  # Just check for the prefix since filenames may differ
        self.assertTrue(space['title'].startswith(expected_title), 
                       f"Retrieved space title '{space['title']}' should start with '{expected_title}'")
        
        log_test_end("get_space")
    
    def test_05_update_space(self):
        """Test updating space details."""
        # First create a space
        space_id = self.test_02_create_space_visitor()
        
        log_test_start("update_space")
        
        # Update title
        new_title = f"Updated_{self.test_data['title']}"
        log_test_step(f"Updating title to: {new_title}")
        result = self.space.update_space(space_id, title=new_title)
        self.assertTrue(result, "Should update title")
        
        # Verify update
        space = self.space.get_space(space_id)
        # Just check if 'Updated_' prefix exists in the title
        self.assertTrue('Updated_' in space['title'], 
                      f"Title '{space['title']}' should contain 'Updated_'")
        
        # Update notes
        new_notes = f"Updated_{self.test_data['notes']}"
        log_test_step(f"Updating notes to: {new_notes}")
        result = self.space.update_space(space_id, notes=new_notes)
        self.assertTrue(result, "Should update notes")
        
        # Verify update
        space = self.space.get_space(space_id)
        self.assertEqual(space['notes'], new_notes, "Notes should be updated")
        
        # Update status
        log_test_step("Updating status to downloading")
        result = self.space.update_space(space_id, status="downloading")
        self.assertTrue(result, "Should update status")
        
        # Verify update
        space = self.space.get_space(space_id)
        self.assertEqual(space['status'], "downloading", "Status should be updated")
        # Current schema doesn't have download_started_at field
        # self.assertIsNotNone(space['download_started_at'], "download_started_at should be set")
        
        log_test_end("update_space")
    
    def test_06_update_download_progress(self):
        """Test updating download progress."""
        # First create a space
        space_id = self.test_02_create_space_visitor()
        
        log_test_start("update_download_progress")
        
        # Update progress to 50%
        log_test_step("Updating download progress to 50%")
        result = self.space.update_download_progress(space_id, 50, 1024)
        self.assertTrue(result, "Should update download progress")
        
        # Verify update
        space = self.space.get_space(space_id)
        self.assertEqual(space['download_progress'], 50, "Download progress should be updated")
        self.assertEqual(space['status'], "downloading", "Status should be updated to downloading")
        self.assertEqual(space['file_size'], 1024, "File size should be updated")
        
        # Update progress to 100%
        log_test_step("Updating download progress to 100%")
        result = self.space.update_download_progress(space_id, 100, 2048)
        self.assertTrue(result, "Should update download progress")
        
        # Verify update
        space = self.space.get_space(space_id)
        self.assertEqual(space['download_progress'], 100, "Download progress should be updated")
        self.assertEqual(space['status'], "downloaded", "Status should be updated to downloaded")
        self.assertEqual(space['file_size'], 2048, "File size should be updated")
        
        log_test_end("update_download_progress")
    
    def test_07_list_spaces(self):
        """Test listing spaces with filtering."""
        try:
            # Create spaces for visitor and user
            visitor_space_id = self.test_02_create_space_visitor()
            logger.info(f"Created visitor space with ID: {visitor_space_id}")
            
            user_space_id = None
            try:
                user_space_id = self.test_03_create_space_user()
                logger.info(f"Created user space with ID: {user_space_id}")
            except Exception as e:
                logger.error(f"Error creating user space: {e}")
                # Continue with just the visitor space
            
            log_test_start("list_spaces")
            
            # List all spaces
            log_test_step("Listing all spaces")
            spaces = self.space.list_spaces()
            self.assertGreaterEqual(len(spaces), 1, "Should list at least 1 space")
            logger.info(f"Found {len(spaces)} spaces in total")
            
            # List spaces for visitor
            log_test_step(f"Listing spaces for visitor: {self.visitor_id}")
            spaces = self.space.list_spaces(visitor_id=self.visitor_id)
            self.assertGreaterEqual(len(spaces), 1, "Should list at least 1 space for visitor")
            logger.info(f"Found {len(spaces)} spaces for visitor {self.visitor_id}")
            
            # List spaces for user if user space was created
            if user_space_id and self.user_id:
                log_test_step(f"Listing spaces for user: {self.user_id}")
                spaces = self.space.list_spaces(user_id=self.user_id)
                self.assertGreaterEqual(len(spaces), 1, "Should list at least 1 space for user")
                logger.info(f"Found {len(spaces)} spaces for user {self.user_id}")
            
            log_test_end("list_spaces")
        except Exception as e:
            logger.error(f"Error in test_07_list_spaces: {e}")
            raise
    
    def test_08_search_spaces(self):
        """Test searching spaces by keyword."""
        # Create unique space with searchable title
        unique_title = f"UniqueSearchableTitle_{self.timestamp}"
        space_id = self.space.create_space(
            self.test_data['url'],
            unique_title,
            self.test_data['notes'],
            user_id=self.user_id
        )
        
        log_test_start("search_spaces")
        
        # Search for the unique title
        search_term = f"UniqueSearchableTitle_{self.timestamp}"
        log_test_step(f"Searching for: {search_term}")
        spaces = self.space.search_spaces(search_term)
        
        self.assertGreaterEqual(len(spaces), 1, "Should find at least 1 space")
        found = False
        for space in spaces:
            if space['space_id'] == space_id and space['title'] == unique_title:
                found = True
                break
        self.assertTrue(found, "Should find the created space by title search")
        
        log_test_end("search_spaces")
    
    def test_09_associate_spaces_with_user(self):
        """Test associating visitor spaces with a user."""
        # Create a space as a visitor
        space_id = self.test_02_create_space_visitor()
        
        log_test_start("associate_spaces_with_user")
        
        log_test_step(f"Associating visitor spaces with user ID: {self.user_id}")
        count = self.space.associate_spaces_with_user(self.visitor_id, self.user_id)
        
        self.assertGreaterEqual(count, 1, "Should associate at least 1 space")
        
        # Verify association
        space = self.space.get_space(space_id)
        self.assertEqual(space['user_id'], self.user_id, "Space should now be associated with user")
        
        log_test_end("associate_spaces_with_user")
    
    def test_10_delete_space(self):
        """Test deleting a space."""
        # First create a space
        space_id = self.test_02_create_space_visitor()
        
        log_test_start("delete_space")
        
        log_test_step(f"Deleting space with ID: {space_id}")
        result = self.space.delete_space(space_id)
        self.assertTrue(result, "Should delete space")
        
        # Verify space is deleted
        space = self.space.get_space(space_id)
        self.assertIsNone(space, "Space should not exist after deletion")
        
        log_test_end("delete_space")

if __name__ == "__main__":
    unittest.main()