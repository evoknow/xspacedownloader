#!/usr/bin/env python3
"""
Test script to verify queue issues and fixes
"""

import os
import sys
import json
import time
import random
from pathlib import Path
from datetime import datetime

def create_test_translation_job():
    """Create a test translation job"""
    # Create test translation job
    job_id = f"test_trans_{int(time.time())}_{random.randint(1000, 9999)}"
    space_id = f"test_space_{random.randint(1000, 9999)}"
    
    job_data = {
        "id": job_id,
        "space_id": space_id,
        "source_lang": "en",
        "target_lang": "es",
        "status": "pending",
        "progress": 0,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "user_id": 1,
        "transcript_id": 123
    }
    
    # Save to translation_jobs directory
    jobs_dir = Path('/var/www/production/xspacedownload.com/website/htdocs/translation_jobs')
    jobs_dir.mkdir(exist_ok=True)
    
    job_file = jobs_dir / f"{job_id}.json"
    with open(job_file, 'w') as f:
        json.dump(job_data, f, indent=2)
    
    print(f"✓ Created test translation job: {job_file}")
    return job_id, job_file

def create_test_video_job():
    """Create a test video generation job"""
    job_id = f"test_video_{int(time.time())}_{random.randint(1000, 9999)}"
    space_id = f"test_space_{random.randint(1000, 9999)}"
    
    job_data = {
        "job_id": job_id,
        "space_id": space_id,
        "job_type": "video",
        "status": "pending",
        "progress": 0,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "options": {
            "style": "podcast",
            "quality": "high"
        }
    }
    
    # Save to transcript_jobs directory with _video suffix
    jobs_dir = Path('/var/www/production/xspacedownload.com/website/xspacedownloader/transcript_jobs')
    jobs_dir.mkdir(exist_ok=True)
    
    job_file = jobs_dir / f"{job_id}_video.json"
    with open(job_file, 'w') as f:
        json.dump(job_data, f, indent=2)
    
    print(f"✓ Created test video job: {job_file}")
    return job_id, job_file

def test_queue_endpoints():
    """Test various queue endpoints"""
    import requests
    
    base_url = "http://localhost:5000"  # Adjust if needed
    
    print("\n=== Testing Queue Endpoints ===")
    
    # Test regular queue
    try:
        resp = requests.get(f"{base_url}/queue")
        print(f"Regular Queue Status: {resp.status_code}")
        if resp.status_code == 200:
            # Check if our test jobs appear
            content = resp.text
            if "test_trans_" in content:
                print("✓ Translation job appears in regular queue")
            else:
                print("✗ Translation job NOT in regular queue")
            
            if "test_video_" in content:
                print("✓ Video job appears in regular queue")
            else:
                print("✗ Video job NOT in regular queue (expected)")
    except Exception as e:
        print(f"✗ Error testing regular queue: {e}")
    
    # Test admin translation queue
    try:
        resp = requests.get(f"{base_url}/admin/api/queue/translation")
        print(f"\nAdmin Translation Queue Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            pending = data.get('pending', [])
            print(f"Pending translation jobs: {len(pending)}")
            for job in pending:
                if job['job_id'].startswith('test_trans_'):
                    print(f"✓ Found test translation job: {job['job_id']}")
    except Exception as e:
        print(f"✗ Error testing admin translation queue: {e}")
    
    # Test admin video queue
    try:
        resp = requests.get(f"{base_url}/admin/api/queue/video")
        print(f"\nAdmin Video Queue Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            pending = data.get('pending', [])
            print(f"Pending video jobs: {len(pending)}")
            for job in pending:
                if job['job_id'].startswith('test_video_'):
                    print(f"✓ Found test video job: {job['job_id']}")
    except Exception as e:
        print(f"✗ Error testing admin video queue: {e}")

def test_translation_cost_description():
    """Test if translation costs include language information"""
    print("\n=== Testing Translation Cost Description ===")
    
    # Check a recent translation cost entry
    try:
        import mysql.connector
        with open('db_config.json', 'r') as f:
            config = json.load(f)['mysql']
        
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor(dictionary=True)
        
        # Get recent translation costs
        cursor.execute("""
            SELECT * FROM computes 
            WHERE service = 'translation' 
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        
        results = cursor.fetchall()
        if results:
            print(f"Found {len(results)} recent translation costs:")
            for cost in results:
                print(f"  - Description: {cost['description']}")
                if 'to' in cost['description'] or '->' in cost['description']:
                    print("    ✓ Contains language information")
                else:
                    print("    ✗ Missing language information")
        else:
            print("No translation costs found")
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"✗ Error checking translation costs: {e}")

def cleanup_test_jobs(job_files):
    """Clean up test job files"""
    print("\n=== Cleaning up test jobs ===")
    for job_file in job_files:
        try:
            if job_file.exists():
                job_file.unlink()
                print(f"✓ Removed {job_file}")
        except Exception as e:
            print(f"✗ Error removing {job_file}: {e}")

def main():
    print("XSpace Queue Issues Test Script")
    print("=" * 50)
    
    # Create test jobs
    test_files = []
    
    trans_job_id, trans_job_file = create_test_translation_job()
    test_files.append(trans_job_file)
    
    video_job_id, video_job_file = create_test_video_job()
    test_files.append(video_job_file)
    
    # Test queue endpoints (if running locally)
    # test_queue_endpoints()
    
    # Test translation cost descriptions
    test_translation_cost_description()
    
    # Clean up
    cleanup_test_jobs(test_files)
    
    print("\n=== Manual Verification Steps ===")
    print("1. Visit /queue and check if translation jobs appear")
    print("2. Visit /admin -> Queue Management -> Translation Queue")
    print("3. Visit /admin -> Queue Management -> Video Generation Queue")
    print("4. Check /profile Usage History for translation descriptions")
    print("5. Generate a test video and check if it produces valid MP4")

if __name__ == "__main__":
    main()