#!/usr/bin/env python3
# test_api_simulation.py - Simulate API behavior with string progress_in_size

# Create a dummy job object with a string progress_in_size
direct_job = {
    'id': 92,
    'space_id': '1rmxPyBeEZEKN',
    'status': 'completed',
    'progress_in_percent': 100,
    'progress_in_size': '3340199',  # String representation
    'error_message': None,
}

print("Before fix:")
print(f"progress_in_size = {direct_job['progress_in_size']} (type: {type(direct_job['progress_in_size'])})")

# Apply the fix
progress_size = direct_job['progress_in_size']
if progress_size is None:
    progress_size = 0
elif isinstance(progress_size, str) and progress_size.isdigit():
    progress_size = int(progress_size)

# Create response with fixed value
safe_response = {
    'job_id': direct_job['id'],
    'space_id': direct_job['space_id'],
    'status': direct_job['status'] or 'unknown',
    'progress_in_percent': direct_job['progress_in_percent'] or 0,
    'progress_in_size': progress_size,
    'error_message': direct_job['error_message'] or '',
    'direct_query': True
}

print("\nAfter fix:")
print(f"progress_in_size = {safe_response['progress_in_size']} (type: {type(safe_response['progress_in_size'])})")

# Verify the fix worked
if isinstance(safe_response['progress_in_size'], int):
    print("\nSUCCESS: progress_in_size correctly converted to integer type!")
else:
    print("\nFAILED: progress_in_size is still not an integer!")