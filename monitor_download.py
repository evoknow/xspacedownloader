#!/usr/bin/env python3
"""
Monitor download jobs and cost tracking
"""

import sys
import os
import time
import json
from datetime import datetime

# Check if we're already in a virtual environment
if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
    pass
else:
    # Try to find and use virtual environment
    VENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'venv')
    if os.path.exists(os.path.join(VENV_PATH, 'bin', 'python')):
        venv_python = os.path.join(VENV_PATH, 'bin', 'python')
        os.execl(venv_python, venv_python, *sys.argv)

import mysql.connector

def monitor_downloads():
    """Monitor download jobs and cost tracking."""
    
    # Load database config
    with open('db_config.json', 'r') as f:
        db_config = json.load(f)
    
    mysql_config = db_config['mysql'].copy()
    if 'use_ssl' in mysql_config:
        del mysql_config['use_ssl']
    
    last_job_id = None
    last_balance = None
    
    print("🔍 Monitoring downloads for cost tracking...")
    print("Looking for space: 1BRJjmXAnPBGw")
    print("=" * 60)
    
    while True:
        try:
            conn = mysql.connector.connect(**mysql_config)
            cursor = conn.cursor(dictionary=True)
            
            # Check for new jobs
            cursor.execute("""
                SELECT id, space_id, user_id, status, start_time, end_time, 
                       progress_in_percent, created_at, updated_at
                FROM space_download_scheduler 
                ORDER BY id DESC 
                LIMIT 3
            """)
            jobs = cursor.fetchall()
            
            # Look for the specific space we're monitoring
            target_job = None
            for job in jobs:
                if job['space_id'] == '1BRJjmXAnPBGw':
                    target_job = job
                    break
            
            if target_job:
                current_job_id = target_job['id']
                
                # If this is a new job or status changed
                if current_job_id != last_job_id:
                    print(f"\n📥 NEW JOB DETECTED!")
                    print(f"Job ID: {target_job['id']}")
                    print(f"Space: {target_job['space_id']}")
                    print(f"User: {target_job['user_id']}")
                    print(f"Status: {target_job['status']}")
                    print(f"Progress: {target_job['progress_in_percent']}%")
                    print(f"Start: {target_job['start_time']}")
                    print(f"Created: {target_job['created_at']}")
                    last_job_id = current_job_id
                    
                    # Get user's current balance
                    if target_job['user_id']:
                        cursor.execute("SELECT credits FROM users WHERE id = %s", (target_job['user_id'],))
                        user_result = cursor.fetchone()
                        if user_result:
                            current_balance = float(user_result['credits'])
                            print(f"💰 User balance: ${current_balance:.2f}")
                            last_balance = current_balance
                
                # Check if job completed and track cost changes
                if target_job['status'] == 'completed' and target_job['end_time']:
                    print(f"\n✅ JOB COMPLETED!")
                    print(f"End time: {target_job['end_time']}")
                    
                    # Calculate duration
                    if target_job['start_time'] and target_job['end_time']:
                        start_dt = target_job['start_time']
                        end_dt = target_job['end_time']
                        if isinstance(start_dt, str):
                            start_dt = datetime.fromisoformat(start_dt)
                        if isinstance(end_dt, str):
                            end_dt = datetime.fromisoformat(end_dt)
                        
                        duration = (end_dt - start_dt).total_seconds()
                        print(f"⏱️  Duration: {duration:.2f} seconds ({duration/60:.2f} minutes)")
                    
                    # Check final balance
                    if target_job['user_id']:
                        cursor.execute("SELECT credits FROM users WHERE id = %s", (target_job['user_id'],))
                        user_result = cursor.fetchone()
                        if user_result:
                            final_balance = float(user_result['credits'])
                            print(f"💰 Final balance: ${final_balance:.2f}")
                            
                            if last_balance is not None:
                                cost_deducted = last_balance - final_balance
                                if cost_deducted > 0:
                                    print(f"✅ COST DEDUCTED: ${cost_deducted:.6f}")
                                else:
                                    print(f"❌ NO COST DEDUCTED! Balance unchanged.")
                    
                    # Check for compute transactions
                    cursor.execute("""
                        SELECT * FROM computes 
                        WHERE space_id = %s 
                        ORDER BY id DESC 
                        LIMIT 1
                    """, (target_job['space_id'],))
                    compute_result = cursor.fetchone()
                    
                    if compute_result:
                        print(f"💳 COMPUTE TRANSACTION FOUND:")
                        print(f"   Cost: ${compute_result['total_cost']:.6f}")
                        print(f"   Duration: {compute_result['compute_time_seconds']:.2f}s")
                        print(f"   Rate: ${compute_result['cost_per_second']:.6f}/sec")
                    else:
                        print(f"❌ NO COMPUTE TRANSACTION FOUND!")
                    
                    print("\n🎉 MONITORING COMPLETE!")
                    break
                
                elif target_job['status'] in ['in_progress', 'downloading']:
                    print(f"📊 Progress: {target_job['progress_in_percent']}% (Status: {target_job['status']})")
            
            cursor.close()
            conn.close()
            
            time.sleep(2)  # Check every 2 seconds
            
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    monitor_downloads()