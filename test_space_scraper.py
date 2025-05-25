#!/usr/bin/env python3
"""Test script for SpaceScraper component"""

from components.SpaceScraper import SpaceScraper
import json
import time

def test_space_scraper():
    """Test the SpaceScraper with multiple space URLs"""
    
    print("=" * 60)
    print("Testing SpaceScraper Component")
    print("=" * 60)
    
    scraper = SpaceScraper()
    
    # Test URLs provided
    test_spaces = [
        {
            "url": "https://x.com/i/spaces/1dRJZEpyjlNGB",
            "description": "Test Space 1"
        },
        {
            "url": "https://x.com/i/spaces/1kvJpmvEmpaxE",
            "description": "Test Space 2"
        },
        {
            "url": "https://x.com/i/spaces/1OyKAWmLDqyJb",
            "description": "Test Space 3"
        },
        {
            "url": "1eaKbWmrnQkGX",  # Just the ID
            "description": "Test with just ID"
        }
    ]
    
    results = []
    
    for i, test_case in enumerate(test_spaces, 1):
        print(f"\nTest {i}: {test_case['description']}")
        print(f"URL: {test_case['url']}")
        print("-" * 40)
        
        try:
            # Scrape metadata
            metadata = scraper.scrape(test_case['url'])
            
            # Check for errors
            if "error" in metadata:
                print(f"❌ Error: {metadata['error']}")
                results.append({"test": i, "status": "failed", "error": metadata['error']})
            else:
                print(f"✅ Success!")
                print(f"   Space ID: {metadata.get('space_id')}")
                print(f"   Title: {metadata.get('title', 'N/A')}")
                print(f"   Host: {metadata.get('host', 'N/A')}")
                print(f"   Speakers: {len(metadata.get('speakers', []))} found")
                print(f"   Tags: {', '.join(metadata.get('tags', [])) if metadata.get('tags') else 'None'}")
                print(f"   Participants: {metadata.get('participants_count', 'N/A')}")
                print(f"   Status: {metadata.get('status', 'N/A')}")
                
                # Save full result
                results.append({
                    "test": i,
                    "status": "success",
                    "metadata": metadata
                })
                
                # Save to file
                filename = f"test_space_{metadata.get('space_id')}.json"
                with open(filename, 'w') as f:
                    json.dump(metadata, f, indent=2)
                print(f"   💾 Saved to: {filename}")
        
        except Exception as e:
            print(f"❌ Exception: {str(e)}")
            results.append({"test": i, "status": "error", "exception": str(e)})
        
        # Small delay between requests to be polite
        if i < len(test_spaces):
            time.sleep(1)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    success_count = sum(1 for r in results if r["status"] == "success")
    fail_count = sum(1 for r in results if r["status"] != "success")
    
    print(f"Total tests: {len(test_spaces)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {fail_count}")
    
    # Save all results
    with open("test_space_scraper_results.json", 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n📊 Full results saved to: test_space_scraper_results.json")
    
    return results


if __name__ == "__main__":
    test_space_scraper()