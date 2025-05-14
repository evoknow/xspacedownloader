# XSpace Downloader Tests

This directory contains automated tests for the XSpace Downloader components.

## Test Components

- `test_user.py`: Tests for the User component
- `test_space.py`: Tests for the Space component
- `test_tag.py`: Tests for the Tag component
- `test_config.py`: Common test configuration and utilities

## Running Tests

You can run all tests using the `test.sh` script in the root directory:

```bash
./test.sh
```

This script will:
1. Activate the virtual environment if it exists
2. Clear any previous test logs
3. Run all component tests
4. Display a summary of test results
5. Write detailed test logs to `test.log`

## Individual Component Tests

You can also run tests for individual components:

```bash
# Run User tests
python -m tests.test_user

# Run Space tests
python -m tests.test_space

# Run Tag tests
python -m tests.test_tag
```

## Test Coverage

The tests cover:

### User Component
- Creating users
- Retrieving users by ID, username, and email
- Authenticating users
- Updating user information
- Deleting users

### Space Component
- Extracting space IDs from URLs
- Creating spaces as visitors and registered users
- Retrieving spaces by ID
- Updating space details
- Updating download progress
- Listing spaces with filtering
- Searching spaces by keyword
- Associating visitor spaces with users
- Deleting spaces

### Tag Component
- Creating tags
- Retrieving tags by ID and name
- Adding tags to spaces
- Retrieving tags for a space
- Listing all tags
- Searching for tags
- Removing tags from spaces
- Getting popular tags

## Test Log

All test actions are logged to `test.log` with timestamps and detailed information about each test step.