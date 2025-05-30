#!/usr/bin/env python3
"""
Clean up failed transcription jobs
"""

import os
import json
from pathlib import Path

jobs_dir = Path('./transcript_jobs')
failed_count = 0
removed_count = 0

for job_file in jobs_dir.glob('*.json'):
    try:
        with open(job_file, 'r') as f:
            job_data = json.load(f)
            
        if job_data.get('status') == 'failed':
            failed_count += 1
            # Remove failed job files
            os.remove(job_file)
            removed_count += 1
            print(f"Removed failed job: {job_file.name}")
            
    except Exception as e:
        print(f"Error processing {job_file}: {e}")

print(f"\nSummary:")
print(f"Found {failed_count} failed jobs")
print(f"Removed {removed_count} job files")