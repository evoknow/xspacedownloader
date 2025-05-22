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

if __name__ == "__main__":
    import sys
    env_file = sys.argv[1] if len(sys.argv) > 1 else '.env'
    load_env(env_file)
    print(f"Environment variables loaded from {env_file}")