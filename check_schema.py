#!/usr/bin/env python3
# check_schema.py - Check database schema

from components.Space import Space

def main():
    """Display database schema information"""
    space = Space()
    cursor = space.connection.cursor()
    
    # Check spaces table
    print("SPACES TABLE COLUMNS:")
    cursor.execute("DESCRIBE spaces")
    for column in cursor:
        print(f"  {column}")
    
    # Check space_download_scheduler table
    print("\nSPACE_DOWNLOAD_SCHEDULER TABLE COLUMNS:")
    cursor.execute("DESCRIBE space_download_scheduler")
    for column in cursor:
        print(f"  {column}")
    
    cursor.close()

if __name__ == "__main__":
    main()