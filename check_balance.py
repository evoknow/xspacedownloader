#!/usr/bin/env python3
"""
Quick script to check user balance and verify cost tracking is working
"""

import json
import mysql.connector

# Load database config
with open('db_config.json', 'r') as f:
    db_config = json.load(f)

mysql_config = db_config["mysql"].copy()
if 'use_ssl' in mysql_config:
    del mysql_config['use_ssl']

try:
    conn = mysql.connector.connect(**mysql_config)
    cursor = conn.cursor(dictionary=True)
    
    # Check user 933 balance
    cursor.execute("SELECT id, credits FROM users WHERE id = 933")
    user = cursor.fetchone()
    print(f"User 933 balance: ${user['credits']:.6f}")
    
    # Check recent computes for space 1vOGwXRYAwbJB
    cursor.execute("""
        SELECT space_id, action, compute_time_seconds, total_cost, 
               balance_before, balance_after, created_at
        FROM computes 
        WHERE space_id = '1vOGwXRYAwbJB' 
        ORDER BY id DESC LIMIT 1
    """)
    compute = cursor.fetchone()
    
    if compute:
        print(f"\nLast compute record for space 1vOGwXRYAwbJB:")
        print(f"Action: {compute['action']}")
        print(f"Duration: {compute['compute_time_seconds']:.2f} seconds")
        print(f"Cost: ${compute['total_cost']:.6f}")
        print(f"Balance: ${compute['balance_before']:.6f} -> ${compute['balance_after']:.6f}")
        print(f"Created: {compute['created_at']}")
    else:
        print("No compute records found for space 1vOGwXRYAwbJB")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"ERROR: {e}")