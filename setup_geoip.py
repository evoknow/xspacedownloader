#!/usr/bin/env python3
"""Download and setup GeoLite2 database for country detection"""

import os
import requests
import tarfile
import shutil

def download_geolite2():
    """Download GeoLite2 Country database"""
    # Note: MaxMind requires registration for GeoLite2 databases
    # This uses a direct download link that may need to be updated
    
    print("Setting up GeoIP2 database...")
    
    # Create data directory if it doesn't exist
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    
    # Check if database already exists
    db_path = os.path.join(data_dir, 'GeoLite2-Country.mmdb')
    if os.path.exists(db_path):
        print(f"GeoLite2 database already exists at {db_path}")
        return db_path
    
    print("\nIMPORTANT: To use GeoIP2, you need to:")
    print("1. Sign up for a free MaxMind account at https://www.maxmind.com/en/geolite2/signup")
    print("2. Download the GeoLite2 Country database (mmdb format)")
    print("3. Place the GeoLite2-Country.mmdb file in the 'data' directory")
    print(f"\nExpected location: {db_path}")
    
    # Alternative: Use the test database
    test_db_url = "https://github.com/maxmind/MaxMind-DB/raw/main/test-data/GeoIP2-Country-Test.mmdb"
    
    response = input("\nWould you like to download a test database for development? (y/n): ")
    if response.lower() == 'y':
        print("Downloading test database...")
        try:
            r = requests.get(test_db_url)
            if r.status_code == 200:
                test_db_path = os.path.join(data_dir, 'GeoLite2-Country-Test.mmdb')
                with open(test_db_path, 'wb') as f:
                    f.write(r.content)
                print(f"Test database downloaded to {test_db_path}")
                print("Note: This is a TEST database with limited data!")
                return test_db_path
        except Exception as e:
            print(f"Failed to download test database: {e}")
    
    return None

if __name__ == "__main__":
    download_geolite2()