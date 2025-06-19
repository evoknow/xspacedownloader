#!/usr/bin/env python3
"""
Retroactive cost tracking fix for job 270 (space 1vOGwXRYAwbJB)
that completed without cost deduction.
"""

import sys
import os
from datetime import datetime

# Virtual environment setup
if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
    pass
else:
    # Use production venv path
    VENV_PATH = '/var/www/production/xspacedownload.com/website/htdocs/venv'
    if os.path.exists(os.path.join(VENV_PATH, 'bin', 'python')):
        venv_python = os.path.join(VENV_PATH, 'bin', 'python')
        os.execl(venv_python, venv_python, *sys.argv)

import json
import mysql.connector

def retroactive_fix_job270():
    """Apply cost tracking to job 270 that completed without cost deduction."""
    
    print("=== Retroactive Cost Fix for Job 270 ===")
    
    # Load database config
    with open('db_config.json', 'r') as f:
        db_config = json.load(f)
    
    mysql_config = db_config["mysql"].copy()
    if 'use_ssl' in mysql_config:
        del mysql_config['use_ssl']
    
    try:
        conn = mysql.connector.connect(**mysql_config)
        cursor = conn.cursor(dictionary=True)
        
        # Get job 270 details
        cursor.execute("""
            SELECT id, space_id, user_id, start_time, end_time, status
            FROM space_download_scheduler 
            WHERE id = 270
        """)
        job = cursor.fetchone()
        
        if not job:
            print("ERROR: Job 270 not found")
            return
        
        print(f"Job {job['id']}: Space {job['space_id']}")
        print(f"User ID: {job['user_id']}")
        print(f"Status: {job['status']}")
        print(f"Start: {job['start_time']}")
        print(f"End: {job['end_time']}")
        
        if job['status'] != 'completed':
            print(f"ERROR: Job status is {job['status']}, not completed")
            return
        
        if not job['start_time'] or not job['end_time']:
            print("ERROR: Missing start_time or end_time")
            return
        
        # Calculate duration
        start_time = job['start_time']
        end_time = job['end_time']
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)
        
        duration_seconds = (end_time - start_time).total_seconds()
        print(f"Duration: {duration_seconds:.2f} seconds ({duration_seconds/60:.2f} minutes)")
        
        # Get current user balance
        cursor.execute("SELECT credits FROM users WHERE id = %s", (job['user_id'],))
        user_result = cursor.fetchone()
        current_balance = float(user_result['credits']) if user_result else 0.0
        print(f"Current balance: ${current_balance:.2f}")
        
        # Get compute cost per second
        cursor.execute("SELECT setting_value FROM app_settings WHERE setting_name = 'compute_cost_per_second'")
        cost_result = cursor.fetchone()
        cost_per_second = float(cost_result['setting_value']) if cost_result else 0.001
        
        # Calculate total cost
        total_cost = round(duration_seconds * cost_per_second, 6)
        print(f"Cost per second: ${cost_per_second:.6f}")
        print(f"Total cost: ${total_cost:.6f}")
        
        # Check if already charged
        cursor.execute("SELECT * FROM computes WHERE space_id = %s", (job['space_id'],))
        existing = cursor.fetchone()
        if existing:
            print("WARNING: Cost already tracked for this space!")
            print(f"Existing charge: ${existing['total_cost']:.6f}")
            return
        
        # Check sufficient credits
        if current_balance < total_cost:
            print(f"ERROR: Insufficient credits - required ${total_cost:.6f}, available ${current_balance:.2f}")
            return
        
        # Apply cost
        new_balance = current_balance - total_cost
        cursor.execute("UPDATE users SET credits = %s WHERE id = %s", (new_balance, job['user_id']))
        
        # Record transaction
        cursor.execute("""
            INSERT INTO computes 
            (user_id, cookie_id, space_id, action, compute_time_seconds, 
             cost_per_second, total_cost, balance_before, balance_after)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (job['user_id'], None, job['space_id'], 'mp3', duration_seconds,
              cost_per_second, total_cost, current_balance, new_balance))
        
        conn.commit()
        
        print(f"\n✅ SUCCESS: Retroactive cost applied to job 270")
        print(f"   Balance: ${current_balance:.2f} -> ${new_balance:.2f}")
        print(f"   Deducted: ${total_cost:.6f}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    retroactive_fix_job270()