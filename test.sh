#!/bin/bash
# test.sh - Run all component tests with improved output
#
# Environment variables:
#   NO_TEST_EMAIL=1   - Set this to disable sending test emails
#                       Example: NO_TEST_EMAIL=1 ./test.sh

# Color definitions
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
RESET='\033[0m'

# Test count tracking
TEST_TOTAL=0
TEST_PASSED=0
TEST_FAILED=0
TEST_SKIPPED=0

set -e  # Exit on error

# Directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"  # Change to script directory

# Check for virtual environment - create one if it doesn't exist
if [ ! -d "venv" ]; then
  echo -e "${YELLOW}Creating virtual environment...${RESET}"
  python3 -m venv venv
fi

# Activate virtual environment
echo -e "${BLUE}Activating virtual environment...${RESET}"
source venv/bin/activate

# Install required packages
echo -e "${BLUE}Checking required packages...${RESET}"
pip install -q requests mysql-connector-python yt-dlp >/dev/null 2>&1 || true

# Clear previous log file
if [ -f "test.log" ]; then
  echo -e "${BLUE}Clearing previous test log...${RESET}"
  > test.log
fi

# Print header with timestamp
echo -e "\n${BOLD}=== XSpace Downloader Component Tests ====${RESET}"
echo -e "Started: $(date '+%Y-%m-%d %H:%M:%S')\n"

# Verify tests directory exists
if [ ! -d "tests" ]; then
  echo -e "${RED}ERROR: Tests directory not found${RESET}"
  exit 1
fi

# First run database connection test
echo -e "${BOLD}Testing Database Connection${RESET}"
if python3 -m tests.test_db_schema TestDBSchema.test_01_database_connection 2>/dev/null; then
  echo -e "  ${GREEN}✓${RESET} Database connection: OK"
  ((TEST_PASSED++))
  ((TEST_TOTAL++))
else
  echo -e "  ${RED}✗${RESET} Database connection: FAILED"
  echo -e "${RED}ERROR: Database connection failed. Please check your database connection and settings.${RESET}"
  echo -e "See test.log for details."
  ((TEST_FAILED++))
  ((TEST_TOTAL++))
  exit 1
fi

# Check database schema
echo -e "\n${BOLD}Testing Database Schema${RESET}"
if python3 -m tests.test_db_schema TestDBSchema.test_02_required_tables_exist 2>/dev/null; then
  echo -e "  ${GREEN}✓${RESET} Database schema: OK"
  ((TEST_PASSED++))
  ((TEST_TOTAL++))
else
  echo -e "  ${RED}✗${RESET} Database schema: FAILED"
  echo -e "${RED}ERROR: Database schema test failed. Please check your database schema.${RESET}"
  ((TEST_FAILED++))
  ((TEST_TOTAL++))
  exit 1
fi

echo -e "\n${BOLD}Running Component Tests${RESET}"

# Function to run a test file and print results
run_test() {
  local test_file=$1
  local test_name=$(basename "$test_file" .py | sed 's/test_//')
  local test_class_name=$(grep -m 1 "class.*Test" "$test_file" | sed -E 's/class ([A-Za-z0-9]+).*/\1/')
  
  echo -e "\n${BLUE}Testing ${test_name} Component...${RESET}"
  
  # Run the test and capture output
  local test_output=$(python3 -m unittest "$test_file" 2>&1)
  local result=$?
  
  # Count the tests
  local tests_run=$(echo "$test_output" | grep -o "Ran [0-9]* test" | awk '{print $2}')
  if [ -z "$tests_run" ]; then
    tests_run=0
  fi
  
  # Count failures, errors, skipped
  local failures=$(echo "$test_output" | grep -o "FAILED (failures=[0-9]*)" | grep -o "[0-9]*" || echo "0")
  local errors=$(echo "$test_output" | grep -o "FAILED (errors=[0-9]*)" | grep -o "[0-9]*" || echo "0")
  local skipped=$(echo "$test_output" | grep -o "skipped=[0-9]*" | grep -o "[0-9]*" || echo "0")
  
  # Update counters
  TEST_TOTAL=$((TEST_TOTAL + tests_run))
  TEST_FAILED=$((TEST_FAILED + failures + errors))
  TEST_SKIPPED=$((TEST_SKIPPED + skipped))
  TEST_PASSED=$((TEST_PASSED + tests_run - failures - errors - skipped))
  
  # Print test results
  if [ $result -eq 0 ]; then
    echo -e "  ${GREEN}✓${RESET} $test_class_name: All $tests_run tests passed"
  else
    echo -e "  ${RED}✗${RESET} $test_class_name: $failures failures, $errors errors (out of $tests_run tests)"
    # Print failures and errors
    echo "$test_output" | grep -A 2 "FAIL\|ERROR" | grep -v "^Ran" | grep -v "^$" | 
      sed "s/^FAIL: /${RED}FAIL:${RESET} /g" | sed "s/^ERROR: /${RED}ERROR:${RESET} /g"
  fi
  
  # Save output to log
  echo "=== $test_class_name Output ===" >> test.log
  echo "$test_output" >> test.log
  echo "" >> test.log
}

# Run all component tests
echo -e "\n${BOLD}Running All Component Tests${RESET}"

# List of components to test
COMPONENTS=(
  "email"
  "space" 
  "download_space"
)

for component in "${COMPONENTS[@]}"; do
  test_file="tests/test_${component}.py"
  
  # Skip if test file doesn't exist
  if [ ! -f "$test_file" ]; then
    echo -e "  ${YELLOW}⚠${RESET} Test file not found: $test_file"
    continue
  fi
  
  # Run the component test
  run_test "$test_file"
done

# Run practical component tests
echo -e "\n${BOLD}Running Practical Component Tests${RESET}"

# Test Email send to test address
echo -e "\n${BLUE}Testing Email Component...${RESET}"
python3 -c "
from components.Email import Email
import sys
from datetime import datetime

try:
    email = Email()
    if not email.email_config:
        print('Failed to load email configuration')
        sys.exit(1)
    
    print('Email configuration loaded successfully')
    
    # Always send test email by default, unless NO_TEST_EMAIL is set
    if not (len(sys.argv) > 1 and sys.argv[1] == '--no-test-email'):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f'Sending test email at {now}...')
        
        result = email.test()
        if result:
            print(f'Test email sent successfully via {email.email_config[\"provider\"]}')
        else:
            print('Failed to send test email')
            sys.exit(2)
    
    sys.exit(0)
except Exception as e:
    print(f'Error: {e}')
    sys.exit(1)
" ${NO_TEST_EMAIL:+--no-test-email} > email_test_output.txt 2>&1
EMAIL_RESULT=$?

if [ $EMAIL_RESULT -eq 0 ]; then
  # Check if the output contains the email sent message
  if grep -q "Test email sent successfully" email_test_output.txt; then
    echo -e "  ${GREEN}✓${RESET} Email: Configuration loaded and test email sent successfully"
  else
    echo -e "  ${GREEN}✓${RESET} Email: Configuration loaded successfully (no test email sent)"
  fi
  ((TEST_PASSED++))
  ((TEST_TOTAL++))
elif [ $EMAIL_RESULT -eq 2 ]; then
  echo -e "  ${YELLOW}⚠${RESET} Email: Configuration loaded but sending test email failed"
  cat email_test_output.txt
  ((TEST_FAILED++))
  ((TEST_TOTAL++))
else
  echo -e "  ${RED}✗${RESET} Email: Configuration failed"
  cat email_test_output.txt
  ((TEST_FAILED++))
  ((TEST_TOTAL++))
fi

# Test DownloadSpace component with a sample URL
echo -e "\n${BLUE}Testing DownloadSpace Component...${RESET}"

# Create downloads directory if it doesn't exist
mkdir -p downloads

# Define test space URL - we'll use a short clip to save bandwidth 
TEST_SPACE_URL="https://x.com/i/spaces/1dRJZEpyjlNGB"

# Clean up existing test files to ensure fresh test
rm -f downloads/*1dRJZEpyjlNGB.mp3

# Run the download.py script with the test URL
echo -e "  Running download test..."
./download.py "$TEST_SPACE_URL" > download_test_output.txt 2>&1
DOWNLOAD_RESULT=$?

# Check the result
if [ $DOWNLOAD_RESULT -eq 0 ] && [ -f "$(find downloads -name "*1dRJZEpyjlNGB.mp3" | head -1)" ]; then
  echo -e "  ${GREEN}✓${RESET} DownloadSpace: Download successful"
  ((TEST_PASSED++))
  ((TEST_TOTAL++))
  
  # Test file existence check (re-download should use existing file)
  echo -e "  Testing file existence check..."
  ./download.py "$TEST_SPACE_URL" > download_test_output2.txt 2>&1
  if grep -q "File already exists" download_test_output2.txt; then
    echo -e "  ${GREEN}✓${RESET} DownloadSpace: File existence check works"
    ((TEST_PASSED++))
    ((TEST_TOTAL++))
  else
    echo -e "  ${RED}✗${RESET} DownloadSpace: File existence check failed"
    ((TEST_FAILED++))
    ((TEST_TOTAL++))
  fi
else
  echo -e "  ${RED}✗${RESET} DownloadSpace: Download failed"
  cat download_test_output.txt
  ((TEST_FAILED++))
  ((TEST_TOTAL++))
fi

# Clean up test output files
rm -f download_test_output.txt download_test_output2.txt email_test_output.txt

# Print summary
echo -e "\n${BOLD}=== Test Summary ===${RESET}"
echo -e "Total tests: ${BOLD}$TEST_TOTAL${RESET}"
echo -e "  ${GREEN}Passed: $TEST_PASSED${RESET}"
if [ $TEST_FAILED -gt 0 ]; then
  echo -e "  ${RED}Failed: $TEST_FAILED${RESET}"
else
  echo -e "  Failed: 0"
fi
echo -e "  ${YELLOW}Skipped: $TEST_SKIPPED${RESET}"

# Print overall status
if [ $TEST_FAILED -eq 0 ]; then
  echo -e "\n${GREEN}${BOLD}✅ ALL TESTS PASSED${RESET}"
  exit_code=0
else
  echo -e "\n${RED}${BOLD}❌ SOME TESTS FAILED${RESET}"
  echo -e "See test.log for details"
  exit_code=1
fi

echo -e "\nTest completed at: $(date '+%Y-%m-%d %H:%M:%S')"
echo -e "Full test details available in test.log"

exit $exit_code