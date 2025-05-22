#!/usr/bin/env python3
# space_x_extractor.py
# Custom XSpace extractor for yt-dlp

"""
Custom extractor for yt-dlp that allows downloading from X space URLs.
This adapter handles different X URL formats for compatibility
with the existing spaces extractor.

This extractor enables downloading from URLs like:
- https://x.com/space/1dRJZEpyjlNGB
- https://x.com/1dRJZEpyjlNGB

Usage:
1. This file is loaded by yt-dlp when using the --extractor-args parameter
2. It converts different X URL formats to the standard spaces URL format before downloading
"""

import re
import sys
import os

class XSpaceIE:
    """X space URL extractor that adapts to the standard X spaces format."""
    
    # Unique ID for this extractor
    _VALID_URL = r'https?://(?:www\.)?x\.com/(?:space/)?(?P<id>[a-zA-Z0-9]+)'
    
    # Regular expression to capture the space ID
    _SPACE_ID_RE = re.compile(r'x\.com/(?:space/)?([a-zA-Z0-9]+)')
    
    # Information about this extractor
    IE_NAME = 'xspace'
    IE_DESC = 'X Space'
    COMPATIBLE_NAMES = ['twitter:spaces', 'TwitterSpaces', 'TwitterSpacesV2']
    
    def _real_extract(self, url):
        """
        Extract the space ID from an X URL and convert it to the standard X space URL format.
        
        Args:
            url (str): The XSpace URL
            
        Returns:
            dict: Information for yt-dlp to process
        """
        # Extract the space ID from the URL
        space_id = self._match_id(url)
        
        if not space_id:
            raise Exception(f"Could not extract space ID from X URL: {url}")
        
        # Convert to X/Twitter spaces URL format
        x_space_url = f"https://x.com/i/spaces/{space_id}"
        
        # Print debug information
        print(f"X space extractor: Converting {url} to {x_space_url}")
        
        # Return a dict that tells yt-dlp to use the twitter:spaces extractor
        return {
            '_type': 'url',
            'url': x_space_url,
            'ie_key': 'TwitterSpacesV2',
            'id': space_id,
            'title': f"X Space {space_id}"
        }
    
    def _match_id(self, url):
        """
        Extract the space ID from an X URL.
        
        Args:
            url (str): The X URL
            
        Returns:
            str: The space ID or None if not found
        """
        match = self._SPACE_ID_RE.search(url)
        if match:
            return match.group(1)
        return None


def register_extractors(ie_list):
    """Register our custom extractors with yt-dlp."""
    ie_list.append(XSpaceIE)


# For testing purposes, this will run when the script is executed directly
if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
        extractor = XSpaceIE()
        try:
            result = extractor._real_extract(url)
            print(f"Extracted information: {result}")
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("Usage: python space_x_extractor.py [X URL]")
        print("Example: python space_x_extractor.py https://x.com/space/1dRJZEpyjlNGB")