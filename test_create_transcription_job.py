#!/usr/bin/env python3
"""
Create a test transcription job
"""

import json
import os
from datetime import datetime
import uuid

# Find a space with an audio file
download_dir = "./downloads"
space_id = None
for file in os.listdir(download_dir):
    if file.endswith('.mp3'):
        space_id = file.replace('.mp3', '')
        break

if not space_id:
    print("No MP3 files found in downloads directory")
    exit(1)

print(f"Creating transcription job for space: {space_id}")

# Create job data
job_id = str(uuid.uuid4())
job_data = {
    "id": job_id,
    "space_id": space_id,
    "file_path": f"./downloads/{space_id}.mp3",
    "language": "en",
    "options": {
        "model": "tiny",  # Use tiny model for testing
        "detect_language": False,
        "translate_to": None,
        "overwrite": True
    },
    "status": "pending",
    "progress": 0,
    "created_at": datetime.now().isoformat(),
    "updated_at": datetime.now().isoformat(),
    "result": None,
    "error": None
}

# Save job file
job_file = f"./transcript_jobs/{job_id}.json"
with open(job_file, 'w') as f:
    json.dump(job_data, f, indent=4)

print(f"Created job file: {job_file}")
print("The transcription worker should pick this up within 5 seconds...")