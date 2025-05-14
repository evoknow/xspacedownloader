#!/bin/bash
# test.sh - Run all component tests

set -e  # Exit on error

# Directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"  # Change to script directory

# Activate virtual environment if it exists
if [ -d "venv" ]; then
  echo "Activating virtual environment..."
  source venv/bin/activate
fi

# Clear previous log file
if [ -f "test.log" ]; then
  echo "Clearing previous test log..."
  > test.log
fi

echo "Starting component tests..."
echo "Test results will be logged to test.log"
echo ""

# First run database schema tests to make sure we can connect
echo "Testing database connection and schema..."
python -m tests.test_db_schema TestDBSchema.test_01_database_connection TestDBSchema.test_02_required_tables_exist

# If database tests fail, exit
if [ $? -ne 0 ]; then
  echo "ERROR: Database connection or schema tests failed."
  echo "Please check your database connection and settings."
  echo "See test.log for details."
  exit 1
fi

echo ""
echo "Database connection and schema tests passed."
echo "Running all component tests..."
echo ""

# Run the Python test runner
python run_tests.py 2>/dev/null | grep -v "Ran .* tests in .*s" | grep -v "^$"

# Get the exit code (preserve the exit code of the python command)
exit_code=${PIPESTATUS[0]}

# Print test log summary
echo ""
echo "=== Test Log Summary ==="
echo ""
echo "Database connection:"
grep -E "Connected to database:" test.log | tail -1

echo ""
echo "Test results:"
grep -E "Tests run:|Errors:|Failures:|Skipped:" test.log | tail -4

echo ""
echo "Test status:"
grep -E "ALL TESTS PASSED|SOME TESTS FAILED" test.log | tail -1

echo ""
echo "Full test details available in test.log"

exit $exit_code