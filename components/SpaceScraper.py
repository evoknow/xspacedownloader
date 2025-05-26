#!/usr/bin/env python3
# components/SpaceScraper.py
"""SpaceScraper component for fetching space metadata from spacesdashboard.com"""

import requests
from bs4 import BeautifulSoup
import json
import logging
import re
from datetime import datetime
from typing import Dict, Optional, List

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SpaceScraper:
    """Scrapes metadata for X/Twitter spaces from spacesdashboard.com"""
    
    BASE_URL = "https://spacesdashboard.com/space/"
    
    def __init__(self):
        """Initialize the scraper with a session and headers"""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        })
    
    def extract_space_id_from_url(self, url: str) -> Optional[str]:
        """Extract space ID from various URL formats"""
        # Pattern for X/Twitter space URLs
        patterns = [
            r'https?://(?:x\.com|twitter\.com)/i/spaces/([a-zA-Z0-9]+)',
            r'spaces/([a-zA-Z0-9]+)',
            r'^([a-zA-Z0-9]+)$'  # Just the ID
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def scrape(self, space_id_or_url: str) -> Dict:
        """
        Scrape metadata for a given space ID or URL
        
        Args:
            space_id_or_url: Space ID or full URL
            
        Returns:
            Dictionary containing scraped metadata
        """
        # Extract space ID if URL is provided
        space_id = self.extract_space_id_from_url(space_id_or_url)
        if not space_id:
            logger.error(f"Could not extract space ID from: {space_id_or_url}")
            return {"error": "Invalid space ID or URL"}
        
        url = f"{self.BASE_URL}{space_id}/"
        logger.info(f"Scraping metadata from: {url}")
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch page: {e}")
            return {"error": f"Failed to fetch page: {str(e)}"}
        
        try:
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Extract metadata
            metadata = {
                "space_id": space_id,
                "url": url,
                "scraped_at": datetime.now().isoformat()
            }
            
            # Extract title
            title_tag = soup.find("h1", class_=re.compile(r"text-gray-900"))
            if not title_tag:
                title_tag = soup.find("h1")
            
            if title_tag:
                # Get the direct text content, excluding nested tags
                title_text = ""
                for content in title_tag.contents:
                    if isinstance(content, str):
                        title_text += content.strip()
                
                # Clean up the title
                title_text = title_text.strip()
                metadata["title"] = title_text if title_text else None
            else:
                metadata["title"] = None
            
            # Extract host information
            # Look for the "Host:" header and then find the host info
            host_header = soup.find("h2", string=re.compile(r"Host:", re.I))
            if host_header:
                # Find the next grid container after the header
                host_container = host_header.find_next_sibling("div", class_=re.compile(r"grid"))
                if host_container:
                    # Find the link to the user profile
                    host_link = host_container.find("a", href=re.compile(r"spacesdashboard\.com/u/"))
                    if host_link:
                        # Extract handle from the link or text
                        host_handle_elem = host_link.find("span", class_="font-bold")
                        if host_handle_elem:
                            metadata["host_handle"] = host_handle_elem.get_text(strip=True)
                            # The display name is in the same div as the handle
                            parent_div = host_handle_elem.find_parent("div")
                            if parent_div:
                                # Get text content of the div, excluding nested elements
                                div_text = parent_div.get_text(strip=True)
                                # Remove the handle to get display name
                                display_name = div_text.replace(metadata["host_handle"], "").strip()
                                metadata["host"] = display_name if display_name else metadata["host_handle"].lstrip("@")
                            else:
                                metadata["host"] = metadata["host_handle"].lstrip("@")
                        else:
                            metadata["host_handle"] = None
                            metadata["host"] = None
                    else:
                        metadata["host"] = None
                        metadata["host_handle"] = None
                else:
                    metadata["host"] = None
                    metadata["host_handle"] = None
            else:
                metadata["host"] = None
                metadata["host_handle"] = None
            
            # Extract speakers/co-hosts
            speakers = []
            # Look for the "Speakers:" or "Co-hosts:" header
            speaker_header = soup.find("h2", string=re.compile(r"Speakers:|Co-hosts:", re.I))
            if speaker_header:
                # Find the next grid container after the header
                speaker_container = speaker_header.find_next_sibling("div", class_=re.compile(r"grid"))
                if speaker_container:
                    # Find all user profile links
                    speaker_links = speaker_container.find_all("a", href=re.compile(r"spacesdashboard\.com/u/"))
                    for speaker_link in speaker_links:
                        # Extract handle
                        handle_elem = speaker_link.find("span", class_="font-bold")
                        if handle_elem:
                            handle = handle_elem.get_text(strip=True)
                            # The display name is in the same div as the handle
                            parent_div = handle_elem.find_parent("div")
                            if parent_div:
                                # Get text content of the div, excluding nested elements
                                div_text = parent_div.get_text(strip=True)
                                # Remove the handle to get display name
                                display_name = div_text.replace(handle, "").strip()
                                if display_name:
                                    speakers.append(f"{handle} ({display_name})")
                                else:
                                    speakers.append(handle)
                            else:
                                speakers.append(handle)
            metadata["speakers"] = speakers
            
            # Extract tags/topics
            tags = []
            tag_section = soup.find("div", class_="tags") or soup.find("div", class_="topics")
            if tag_section:
                tag_elements = tag_section.find_all("span", class_="tag") or tag_section.find_all("a", class_="tag")
                for tag in tag_elements:
                    tag_text = tag.get_text(strip=True).lstrip("#")
                    if tag_text and tag_text not in tags:
                        tags.append(tag_text)
            metadata["tags"] = tags
            
            # Extract participant count
            participants_element = soup.find("span", class_="participants-count") or soup.find("div", {"class": ["attendees", "listeners"]})
            if participants_element:
                count_text = participants_element.get_text(strip=True)
                # Extract number from text like "1.2K listeners" or "500 participants"
                count_match = re.search(r'([\d,]+\.?\d*)\s*[kKmM]?', count_text)
                if count_match:
                    count_str = count_match.group(1).replace(',', '')
                    if 'k' in count_text.lower():
                        metadata["participants_count"] = int(float(count_str) * 1000)
                    elif 'm' in count_text.lower():
                        metadata["participants_count"] = int(float(count_str) * 1000000)
                    else:
                        metadata["participants_count"] = int(float(count_str))
                else:
                    metadata["participants_count"] = None
            else:
                metadata["participants_count"] = None
            
            # Extract timing information
            time_section = soup.find("div", class_="time-info") or soup.find("div", class_="duration")
            if time_section:
                start_time = time_section.find("span", class_="start-time") or time_section.find("time", {"class": "start"})
                end_time = time_section.find("span", class_="end-time") or time_section.find("time", {"class": "end"})
                duration = time_section.find("span", class_="duration") or time_section.find("span", {"class": "length"})
                
                metadata["start_time"] = start_time.get_text(strip=True) if start_time else None
                metadata["end_time"] = end_time.get_text(strip=True) if end_time else None
                metadata["duration"] = duration.get_text(strip=True) if duration else None
            else:
                metadata["start_time"] = None
                metadata["end_time"] = None
                metadata["duration"] = None
            
            # Extract description
            description_element = soup.find("div", class_="description") or soup.find("p", class_="space-description")
            metadata["description"] = description_element.get_text(strip=True) if description_element else None
            
            # Extract status (live, scheduled, ended)
            status_element = soup.find("span", class_="status") or soup.find("div", class_="space-status")
            metadata["status"] = status_element.get_text(strip=True).lower() if status_element else None
            
            # Extract recording availability
            recording_element = soup.find("div", class_="recording") or soup.find("span", {"class": ["recorded", "recording-available"]})
            metadata["is_recorded"] = bool(recording_element)
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error parsing page content: {e}")
            return {"error": f"Error parsing page content: {str(e)}"}
    
    def scrape_to_json(self, space_id_or_url: str) -> str:
        """
        Scrape metadata and return as formatted JSON string
        
        Args:
            space_id_or_url: Space ID or full URL
            
        Returns:
            JSON string of metadata
        """
        metadata = self.scrape(space_id_or_url)
        return json.dumps(metadata, indent=2, ensure_ascii=False)


# Example usage
if __name__ == "__main__":
    scraper = SpaceScraper()
    
    # Test with different URL formats
    test_urls = [
        "https://x.com/i/spaces/1dRJZEpyjlNGB",
        "https://x.com/i/spaces/1kvJpmvEmpaxE",
        "https://x.com/i/spaces/1OyKAWmLDqyJb",
        "1eaKbWmrnQkGX"  # Just the ID
    ]
    
    for url in test_urls:
        print(f"\nScraping: {url}")
        print("-" * 50)
        metadata_json = scraper.scrape_to_json(url)
        print(metadata_json)