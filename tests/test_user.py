#!/usr/bin/env python3
# tests/test_user.py

import unittest
import sys
import os
import time

from tests.test_config import (
    TEST_USER, get_db_connection, generate_visitor_id,
    log_test_start, log_test_end, log_test_step, logger, clear_test_data
)

# Import the User component
from components.User import User

class TestUser(unittest.TestCase):
    """Test class for User component functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment once before all tests in this class."""
        logger.info("Setting up TestUser test class")
        clear_test_data()
    
    def setUp(self):
        """Set up test environment before each test."""
        try:
            self.connection = get_db_connection()
            self.user = User(self.connection)
            
            # Create a test timestamp to make test data unique
            # Use class variable instead of instance variable to ensure uniqueness across tests
            if not hasattr(TestUser, '_current_timestamp'):
                TestUser._current_timestamp = int(time.time())
            else:
                # Increment by 1 for each test to ensure uniqueness
                TestUser._current_timestamp += 1
                
            self.timestamp = TestUser._current_timestamp
            
            # Create unique test data for each test run
            self.test_data = {
                'username': f"{TEST_USER['username']}_{self.timestamp}_UserTest",
                'email': f"test_{self.timestamp}_user@example.com",
                'password': TEST_USER['password']
            }
            self.visitor_id = generate_visitor_id()
            
            logger.info(f"Test user setup complete with username: {self.test_data['username']}")
        except Exception as e:
            logger.error(f"Error in setUp: {str(e)}")
            raise
    
    def tearDown(self):
        """Clean up after each test."""
        try:
            # Close database connection
            if hasattr(self, 'connection') and self.connection and self.connection.is_connected():
                self.connection.close()
                logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Error in tearDown: {str(e)}")
    
    def test_01_create_user(self):
        """Test creating a new user."""
        log_test_start("create_user")
        
        log_test_step("Creating new user")
        user_id = self.user.create_user(
            self.test_data['username'],
            self.test_data['email'],
            self.test_data['password'],
            self.visitor_id
        )
        
        self.assertIsNotNone(user_id, "User creation should return a user ID")
        self.test_data['user_id'] = user_id
        
        log_test_step(f"Created user with ID: {user_id}")
        log_test_end("create_user")
        
        return user_id
    
    def test_02_get_user(self):
        """Test retrieving a user by ID, username, and email."""
        # First create a user
        user_id = self.test_01_create_user()
        
        log_test_start("get_user")
        
        # Test get by ID
        log_test_step(f"Getting user by ID: {user_id}")
        user_by_id = self.user.get_user(user_id=user_id)
        self.assertIsNotNone(user_by_id, "Should retrieve user by ID")
        self.assertEqual(user_by_id['user_id'], user_id, "Retrieved user ID should match")
        
        # Test get by username
        log_test_step(f"Getting user by username: {self.test_data['username']}")
        user_by_username = self.user.get_user(username=self.test_data['username'])
        self.assertIsNotNone(user_by_username, "Should retrieve user by username")
        self.assertEqual(user_by_username['user_id'], user_id, "Retrieved user ID should match")
        
        # Test get by email
        log_test_step(f"Getting user by email: {self.test_data['email']}")
        user_by_email = self.user.get_user(email=self.test_data['email'])
        self.assertIsNotNone(user_by_email, "Should retrieve user by email")
        self.assertEqual(user_by_email['user_id'], user_id, "Retrieved user ID should match")
        
        log_test_end("get_user")
    
    def test_03_authenticate_user(self):
        """Test user authentication with correct and incorrect credentials."""
        # First create a user
        user_id = self.test_01_create_user()
        
        log_test_start("authenticate_user")
        
        # Test authentication with username
        log_test_step(f"Authenticating with username: {self.test_data['username']}")
        auth_user = self.user.authenticate_user(
            self.test_data['username'],
            self.test_data['password']
        )
        self.assertIsNotNone(auth_user, "Should authenticate with correct username and password")
        self.assertEqual(auth_user['user_id'], user_id, "Authenticated user ID should match")
        
        # Test authentication with email
        log_test_step(f"Authenticating with email: {self.test_data['email']}")
        auth_user = self.user.authenticate_user(
            self.test_data['email'],
            self.test_data['password']
        )
        self.assertIsNotNone(auth_user, "Should authenticate with correct email and password")
        self.assertEqual(auth_user['user_id'], user_id, "Authenticated user ID should match")
        
        # Test authentication with incorrect password
        log_test_step("Authenticating with incorrect password")
        auth_user = self.user.authenticate_user(
            self.test_data['username'],
            "WrongPassword123!"
        )
        self.assertIsNone(auth_user, "Should not authenticate with incorrect password")
        
        log_test_end("authenticate_user")
    
    def test_04_update_user(self):
        """Test updating user information."""
        # First create a user
        user_id = self.test_01_create_user()
        
        log_test_start("update_user")
        
        # Update username
        new_username = f"updated_{self.test_data['username']}"
        log_test_step(f"Updating username to: {new_username}")
        result = self.user.update_user(user_id, username=new_username)
        self.assertTrue(result, "Should update username")
        
        # Verify update
        user = self.user.get_user(user_id=user_id)
        self.assertEqual(user['username'], new_username, "Username should be updated")
        
        # Update email
        new_email = f"updated_{self.test_data['email']}"
        log_test_step(f"Updating email to: {new_email}")
        result = self.user.update_user(user_id, email=new_email)
        self.assertTrue(result, "Should update email")
        
        # Verify update
        user = self.user.get_user(user_id=user_id)
        self.assertEqual(user['email'], new_email, "Email should be updated")
        
        # Update password
        new_password = "NewPassword123!"
        log_test_step("Updating password")
        result = self.user.update_user(user_id, password=new_password)
        self.assertTrue(result, "Should update password")
        
        # Verify password update by authentication
        auth_user = self.user.authenticate_user(new_username, new_password)
        self.assertIsNotNone(auth_user, "Should authenticate with new password")
        self.assertEqual(auth_user['user_id'], user_id, "Authenticated user ID should match")
        
        log_test_end("update_user")
    
    def test_05_delete_user(self):
        """Test deleting a user."""
        # First create a user
        user_id = self.test_01_create_user()
        
        log_test_start("delete_user")
        
        log_test_step(f"Deleting user with ID: {user_id}")
        result = self.user.delete_user(user_id)
        self.assertTrue(result, "Should delete user")
        
        # Verify user is deleted
        user = self.user.get_user(user_id=user_id)
        self.assertIsNone(user, "User should not exist after deletion")
        
        log_test_end("delete_user")

if __name__ == "__main__":
    unittest.main()