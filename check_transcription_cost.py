#!/usr/bin/env python3
"""
Script to check transcription cost tracking issue
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from load_env import load_env
load_env()

import json
from components.DatabaseManager import DatabaseManager

# Initialize database connection
db = DatabaseManager()
connection = db.get_connection()
cursor = connection.cursor(dictionary=True)

print("=== Checking OpenAI Transcription Models in Database ===")
cursor.execute("""
    SELECT * FROM ai_api_cost 
    WHERE vendor = 'openai' 
    AND (model LIKE '%transcribe%' OR model = 'whisper-1')
    ORDER BY model
""")
results = cursor.fetchall()

if results:
    for row in results:
        print(f"\nModel: {row['model']}")
        print(f"  Input cost per million: ${row['input_token_cost_per_million_tokens']}")
        print(f"  Output cost per million: ${row['output_token_cost_per_million_tokens']}")
        print(f"  Updated at: {row['updated_at']}")
else:
    print("No OpenAI transcription models found in database!")

print("\n=== Checking Recent Transcription Transactions ===")
cursor.execute("""
    SELECT * FROM transactions 
    WHERE action = 'transcription' 
    AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
    ORDER BY created_at DESC
    LIMIT 10
""")
transactions = cursor.fetchall()

if transactions:
    for tx in transactions:
        print(f"\nTransaction ID: {tx['id']}")
        print(f"  User ID: {tx['user_id']}")
        print(f"  Space ID: {tx['space_id']}")
        print(f"  Model: {tx['ai_model']}")
        print(f"  Input tokens: {tx['input_tokens']}")
        print(f"  Output tokens: {tx['output_tokens']}")
        print(f"  Cost: ${tx['cost']}")
        print(f"  Created at: {tx['created_at']}")
else:
    print("No recent transcription transactions found!")

print("\n=== Checking Transcription Config ===")
try:
    with open('transcription_config.json', 'r') as f:
        trans_config = json.load(f)
    print(f"Provider: {trans_config.get('provider')}")
    print(f"OpenAI Model: {trans_config.get('openai_model')}")
    print(f"Corrective Filter: {trans_config.get('enable_corrective_filter')}")
except Exception as e:
    print(f"Error reading transcription config: {e}")

cursor.close()
connection.close()