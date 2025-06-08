#!/usr/bin/env python3
"""
Simple .env file loader utility.
This is optional - environment variables can be set directly in the shell.
"""

import os

def load_env(env_file='.env'):
    """
    Load environment variables from a .env file.
    
    Args:
        env_file (str): Path to the .env file
    """
    if not os.path.exists(env_file):
        return
    
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                
                os.environ[key] = value

def save_env_var(key, value, env_file='.env'):
    """
    Save or update a single environment variable in the .env file.
    
    Args:
        key (str): Environment variable name
        value (str): Environment variable value
        env_file (str): Path to the .env file
    """
    # Read existing lines
    lines = []
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            lines = f.readlines()
    
    # Find and update existing key or add new one
    key_found = False
    for i, line in enumerate(lines):
        if line.strip() and not line.strip().startswith('#') and '=' in line:
            existing_key = line.split('=', 1)[0].strip()
            if existing_key == key:
                lines[i] = f"{key}={value}\n"
                key_found = True
                break
    
    # Add new key if not found
    if not key_found:
        lines.append(f"{key}={value}\n")
    
    # Write back to file
    with open(env_file, 'w') as f:
        f.writelines(lines)
    
    # Update current environment
    os.environ[key] = value

if __name__ == "__main__":
    import sys
    env_file = sys.argv[1] if len(sys.argv) > 1 else '.env'
    load_env(env_file)
    print(f"Environment variables loaded from {env_file}")