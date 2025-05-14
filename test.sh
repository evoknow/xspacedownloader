#!/bin/bash
# test.sh - Run all component tests with improved output

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
pip install -q requests >/dev/null 2>&1 || true

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

# Discover and run all test files
for test_file in tests/test_*.py; do
  # Skip email tests if this is CI environment without email credentials
  if [[ "$test_file" == "tests/test_email.py" && -n "$CI" ]]; then
    echo -e "  ${YELLOW}⚠${RESET} Skipping email tests in CI environment"
    ((TEST_SKIPPED++))
    continue
  fi
  
  run_test "$test_file"
done

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