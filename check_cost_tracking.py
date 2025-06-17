#!/usr/bin/env python3
"""
Diagnostic script to check cost tracking setup
"""

import json
import os
from pathlib import Path

def check_cost_tracking():
    print("=== Cost Tracking Diagnostic ===\n")
    
    # 1. Check if cost.log exists
    logs_dir = Path('logs')
    cost_log = logs_dir / 'cost.log'
    print(f"1. Cost log file: {cost_log}")
    if cost_log.exists():
        print(f"   ✅ EXISTS (size: {cost_log.stat().st_size} bytes)")
        if cost_log.stat().st_size > 0:
            print("   Last 5 lines:")
            with open(cost_log, 'r') as f:
                lines = f.readlines()
                for line in lines[-5:]:
                    print(f"   {line.strip()}")
    else:
        print("   ❌ MISSING")
    
    # 2. Check transcription config
    transcription_config = Path('transcription_config.json')
    print(f"\n2. Transcription config: {transcription_config}")
    if transcription_config.exists():
        with open(transcription_config, 'r') as f:
            config = json.load(f)
        print(f"   ✅ Provider: {config.get('provider', 'unknown')}")
        print(f"   ✅ Model: {config.get('openai_model', 'unknown')}")
    else:
        print("   ❌ MISSING")
    
    # 3. Check recent transcription jobs
    transcript_jobs_dir = Path('transcript_jobs')
    print(f"\n3. Recent transcription jobs:")
    if transcript_jobs_dir.exists():
        job_files = list(transcript_jobs_dir.glob('*.json'))
        job_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        for i, job_file in enumerate(job_files[:3]):
            print(f"   Job {i+1}: {job_file.name}")
            try:
                with open(job_file, 'r') as f:
                    job_data = json.load(f)
                print(f"   - Status: {job_data.get('status', 'unknown')}")
                print(f"   - User ID: {job_data.get('user_id', 'MISSING')}")
                print(f"   - Admin requested: {job_data.get('admin_requested', False)}")
                print(f"   - Model: {job_data.get('model') or job_data.get('options', {}).get('model', 'unknown')}")
            except Exception as e:
                print(f"   - Error reading job: {e}")
            print()
    else:
        print("   ❌ No transcript_jobs directory")
    
    # 4. Check database tables (if accessible)
    print("4. Database status:")
    try:
        from components.DatabaseManager import DatabaseManager
        db = DatabaseManager()
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check transactions table
            try:
                cursor.execute("SELECT COUNT(*) FROM transactions")
                count = cursor.fetchone()[0]
                print(f"   ✅ transactions table: {count} records")
            except Exception as e:
                print(f"   ❌ transactions table: {e}")
            
            # Check computes table  
            try:
                cursor.execute("SELECT COUNT(*) FROM computes")
                count = cursor.fetchone()[0]
                print(f"   ✅ computes table: {count} records")
            except Exception as e:
                print(f"   ❌ computes table: {e}")
                
    except Exception as e:
        print(f"   ❌ Database connection failed: {e}")
    
    print("\n=== Recommendations ===")
    print("1. Make sure background_transcribe.py daemon is running on your server")
    print("2. Check that transcription jobs include user_id")
    print("3. Video generation uses ffmpeg (no AI costs)")
    print("4. Only OpenAI transcriptions have API costs to track")

if __name__ == "__main__":
    check_cost_tracking()