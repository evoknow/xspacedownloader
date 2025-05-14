#!/usr/bin/env python3
# run_tests.py

import unittest
import logging
import os
import sys
import time
import io
import re
from datetime import datetime

# Configure logging
logging.basicConfig(
    filename='test.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('xspace_tests')

class CompactTestResult(unittest.TextTestResult):
    """Custom test result class that outputs results in a compact format."""
    
    def __init__(self, stream, descriptions, verbosity):
        # Force descriptions to False to avoid duplication
        super(CompactTestResult, self).__init__(stream, False, verbosity)
        self.stream = stream
        self.verbosity = verbosity
        self.descriptions = False  # Always use False to avoid duplication
        self.dots = verbosity == 1
        
    def getDescription(self, test):
        """Get a compact description of the test."""
        # Get just the method name or test id
        if hasattr(test, 'shortDescription') and test.shortDescription():
            return test.shortDescription()
        else:
            return str(test).split()[0]
    
    def startTest(self, test):
        """Called when a test starts."""
        super(CompactTestResult, self).startTest(test)
        if self.verbosity > 1:
            desc = self.getDescription(test)
            self.stream.write(f"{desc} ... ")
            self.stream.flush()
    
    def addSuccess(self, test):
        """Called when a test succeeds."""
        super(CompactTestResult, self).addSuccess(test)
        if self.verbosity > 1:
            self.stream.writeln("ok")
    
    def addError(self, test, err):
        """Called when a test raises an error."""
        super(CompactTestResult, self).addError(test, err)
        if self.verbosity > 1:
            self.stream.writeln("ERROR")
    
    def addFailure(self, test, err):
        """Called when a test fails."""
        super(CompactTestResult, self).addFailure(test, err)
        if self.verbosity > 1:
            self.stream.writeln("FAIL")
    
    def addSkip(self, test, reason):
        """Called when a test is skipped."""
        super(CompactTestResult, self).addSkip(test, reason)
        if self.verbosity > 1:
            self.stream.writeln(f"skipped {reason!r}")

class CompactTestRunner(unittest.TextTestRunner):
    """Custom test runner that uses CompactTestResult."""
    
    resultclass = CompactTestResult

def run_all_tests():
    """Run all component tests."""
    logger.info("======== STARTING TEST SUITE ========")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test the database connection first
    try:
        from tests.test_config import get_db_connection
        connection = get_db_connection()
        if connection.is_connected():
            logger.info("Initial database connection test successful")
            connection.close()
        else:
            logger.error("Initial database connection test failed: not connected")
            print("ERROR: Could not connect to the database. Check db_config.json and network connectivity.")
            return 1
    except Exception as e:
        logger.error(f"Initial database connection test failed: {str(e)}")
        print(f"ERROR: Could not connect to the database: {str(e)}")
        return 1
    
    # Discover and run all tests
    start_time = time.time()
    
    loader = unittest.TestLoader()
    suite = loader.discover('tests', pattern='test_*.py')
    
    # Capture stderr to filter out deprecation warnings
    # Create a stream to capture stderr
    stderr_capture = io.StringIO()
    original_stderr = sys.stderr
    sys.stderr = stderr_capture
    
    # Run the tests with our custom runner
    runner = CompactTestRunner(verbosity=2)
    
    # Filter out Storing test_user_id debug lines
    original_stdout = sys.stdout
    stdout_capture = io.StringIO()
    sys.stdout = stdout_capture
    
    result = runner.run(suite)
    
    # Restore stdout and filter out test_user_id spam
    sys.stdout = original_stdout
    stdout_output = stdout_capture.getvalue()
    
    # Filter lines
    filtered_lines = []
    for line in stdout_output.splitlines():
        if "Storing test_user_id" not in line and "DEBUG" not in line and "Handling" not in line:
            filtered_lines.append(line)
    
    # Print filtered output
    for line in filtered_lines:
        print(line)
    
    # Restore stderr and filter out deprecation warnings
    sys.stderr = original_stderr
    stderr_output = stderr_capture.getvalue()
    
    # Only print non-deprecation warning lines
    for line in stderr_output.splitlines():
        if "DeprecationWarning" not in line:
            print(line, file=sys.stderr)
    
    end_time = time.time()
    
    # Log results
    logger.info(f"Tests run: {result.testsRun}")
    logger.info(f"Errors: {len(result.errors)}")
    logger.info(f"Failures: {len(result.failures)}")
    logger.info(f"Skipped: {len(result.skipped)}")
    logger.info(f"Time elapsed: {end_time - start_time:.2f} seconds")
    
    # Log error details
    if result.errors:
        logger.error("=== TEST ERRORS ===")
        for test, error in result.errors:
            logger.error(f"\nERROR: {test}\n{error}")
            
    # Log failure details
    if result.failures:
        logger.error("=== TEST FAILURES ===")
        for test, failure in result.failures:
            logger.error(f"\nFAILURE: {test}\n{failure}")
    
    if result.wasSuccessful():
        logger.info("ALL TESTS PASSED")
        print("\nALL TESTS PASSED")
        return 0
    else:
        logger.error("SOME TESTS FAILED")
        print("\nSOME TESTS FAILED")
        print(f"Tests run: {result.testsRun}")
        print(f"Errors: {len(result.errors)}")
        print(f"Failures: {len(result.failures)}")
        print("See test.log for details")
        return 1

if __name__ == "__main__":
    sys.exit(run_all_tests())