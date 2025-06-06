#!/usr/bin/env python3
# components/VideoGenerator.py
"""Video generation component for creating MP4 files with audio visualization."""

import os
import json
import uuid
import subprocess
import logging
import requests
from typing import Dict, Optional, Tuple
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class VideoGenerator:
    """Generates MP4 videos with audio visualization from audio files."""
    
    def __init__(self, jobs_dir: str = None, downloads_dir: str = None, config_file: str = None):
        """Initialize VideoGenerator."""
        self.jobs_dir = jobs_dir or "transcript_jobs"  # Reuse existing jobs directory
        self.downloads_dir = downloads_dir or "downloads"
        self.config_file = config_file or "mainconfig.json"
        
        # Ensure directories exist
        os.makedirs(self.jobs_dir, exist_ok=True)
        os.makedirs(self.downloads_dir, exist_ok=True)
        os.makedirs("temp", exist_ok=True)  # For downloaded images
        
        logger.info("VideoGenerator initialized")
    
    def create_video_job(self, space_id: str, audio_path: str, space_data: Dict, user_id: str = None) -> str:
        """
        Create a video generation job.
        
        Args:
            space_id (str): Space ID
            audio_path (str): Path to audio file
            space_data (Dict): Space metadata
            user_id (str, optional): User ID who requested generation
            
        Returns:
            str: Job ID
        """
        job_id = str(uuid.uuid4())
        
        # Clean space_data to ensure it's JSON serializable
        clean_space_data = self._clean_for_json(space_data)
        
        job_data = {
            "job_id": job_id,
            "space_id": space_id,
            "audio_path": audio_path,
            "space_data": clean_space_data,
            "user_id": user_id,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "progress": 0,
            "error": None,
            "video_path": None
        }
        
        # Save job data
        job_file = os.path.join(self.jobs_dir, f"{job_id}_video.json")
        with open(job_file, 'w') as f:
            json.dump(job_data, f, indent=2)
        
        logger.info(f"Created video generation job {job_id} for space {space_id}")
        
        # Start video generation in background (simplified for now)
        self._generate_video_sync(job_id)
        
        return job_id
    
    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """
        Get status of a video generation job.
        
        Args:
            job_id (str): Job ID
            
        Returns:
            Optional[Dict]: Job status data or None if not found
        """
        job_file = os.path.join(self.jobs_dir, f"{job_id}_video.json")
        
        if not os.path.exists(job_file):
            return None
        
        try:
            with open(job_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading job file {job_file}: {e}")
            return None
    
    def get_video_path(self, job_id: str) -> Optional[str]:
        """
        Get path to generated video file.
        
        Args:
            job_id (str): Job ID
            
        Returns:
            Optional[str]: Path to video file or None if not found
        """
        job_data = self.get_job_status(job_id)
        if job_data and job_data.get('status') == 'completed':
            video_path = job_data.get('video_path')
            if video_path and os.path.exists(video_path):
                return video_path
        return None
    
    def _generate_video_sync(self, job_id: str) -> bool:
        """
        Generate video synchronously (simplified implementation).
        
        Args:
            job_id (str): Job ID
            
        Returns:
            bool: Success flag
        """
        job_file = os.path.join(self.jobs_dir, f"{job_id}_video.json")
        
        try:
            # Load job data
            with open(job_file, 'r') as f:
                job_data = json.load(f)
            
            space_id = job_data['space_id']
            audio_path = job_data['audio_path']
            
            # Update status to processing
            job_data['status'] = 'processing'
            job_data['updated_at'] = datetime.now().isoformat()
            job_data['progress'] = 10
            
            with open(job_file, 'w') as f:
                json.dump(job_data, f, indent=2)
            
            logger.info(f"Starting video generation for job {job_id}")
            
            # Output video path
            video_path = os.path.join(self.downloads_dir, f"{space_id}.mp4")
            
            # Check if ffmpeg is available
            if not self._check_ffmpeg():
                raise Exception("ffmpeg not found. Please install ffmpeg to generate videos.")
            
            # Generate video with audio waveform
            success = self._create_video_with_waveform(audio_path, video_path, job_file, job_data)
            
            if success:
                # Update job as completed
                job_data['status'] = 'completed'
                job_data['progress'] = 100
                job_data['video_path'] = video_path
                logger.info(f"Video generation completed for job {job_id}: {video_path}")
            else:
                job_data['status'] = 'failed'
                job_data['error'] = 'Video generation failed'
                logger.error(f"Video generation failed for job {job_id}")
            
            job_data['updated_at'] = datetime.now().isoformat()
            
            with open(job_file, 'w') as f:
                json.dump(job_data, f, indent=2)
            
            return success
            
        except Exception as e:
            logger.error(f"Error generating video for job {job_id}: {e}")
            
            # Update job as failed
            try:
                with open(job_file, 'r') as f:
                    job_data = json.load(f)
                
                job_data['status'] = 'failed'
                job_data['error'] = str(e)
                job_data['updated_at'] = datetime.now().isoformat()
                
                with open(job_file, 'w') as f:
                    json.dump(job_data, f, indent=2)
                    
            except Exception as save_error:
                logger.error(f"Error saving failed job status: {save_error}")
            
            return False
    
    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available."""
        try:
            subprocess.run(['ffmpeg', '-version'], 
                         capture_output=True, check=True, timeout=10)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def _create_video_with_waveform(self, audio_path: str, video_path: str, job_file: str, job_data: Dict) -> bool:
        """
        Create MP4 video with styled cover and audio waveform bar at bottom.
        
        Args:
            audio_path (str): Input audio file path
            video_path (str): Output video file path
            job_file (str): Job file path for progress updates
            job_data (Dict): Job data for updates
            
        Returns:
            bool: Success flag
        """
        try:
            # Update progress
            job_data['progress'] = 25
            with open(job_file, 'w') as f:
                json.dump(job_data, f, indent=2)
            
            # Extract space information
            space_data = job_data.get('space_data', {})
            title = space_data.get('title', 'Audio Space')
            host = space_data.get('metadata', {}).get('host', 'Unknown Host')
            job_id = job_data.get('job_id')
            
            # Get branding configuration
            brand_config = self._get_brand_config()
            brand_name = brand_config['brand_name']
            brand_color = brand_config['brand_color']
            
            # Download host profile picture
            profile_pic_path = self._get_host_profile_picture(space_data, job_id)
            
            # Clean text for ffmpeg (escape special characters)
            clean_title = self._escape_ffmpeg_text(title)
            clean_host = self._escape_ffmpeg_text(host)
            clean_brand = self._escape_ffmpeg_text(brand_name)
            
            # Build filter complex with profile picture and configurable branding
            if profile_pic_path and os.path.exists(profile_pic_path):
                # Use downloaded profile picture
                filter_complex = f"""
                    color=c=0x808080:s=1920x1080:d=1[bg_base];
                    [bg_base]drawbox=x=0:y=0:w=1920:h=1080:
                    color=0x4A90A4@0.3:thickness=fill[bg_gradient];
                    
                    [bg_gradient]drawtext=text='{clean_brand}':
                    fontsize=32:fontcolor=white:x=50:y=50:
                    box=1:boxcolor={brand_color}@0.8:boxborderw=10[bg_logo];
                    
                    [bg_logo]drawtext=text='{clean_title}':
                    fontsize=64:fontcolor=white:x=(w-text_w)/2:y=200:
                    shadowcolor=black@0.5:shadowx=3:shadowy=3[bg_title];
                    
                    [bg_title]drawtext=text='Host\\: {clean_host}':
                    fontsize=36:fontcolor=0xF0F0F0:x=(w-text_w)/2:y=300[bg_host];
                    
                    [1:v]scale=400:400:force_original_aspect_ratio=1,
                    pad=400:400:(ow-iw)/2:(oh-ih)/2:black[profile_scaled];
                    
                    [bg_host][profile_scaled]overlay=760:400[bg_with_profile];
                    
                    [0:a]aformat=channel_layouts=mono,
                    showwaves=s=1920x200:mode=p2p:colors=white:
                    scale=sqrt:split_channels=1:
                    draw=scale[waveform_base];
                    
                    [waveform_base]crop=1920:150:0:25[waveform];
                    
                    [bg_with_profile][waveform]overlay=0:880[v]
                """
                # Add profile picture as second input
                cmd = [
                    'ffmpeg',
                    '-i', audio_path,  # Input audio
                    '-i', profile_pic_path,  # Profile picture
                    '-filter_complex', filter_complex,
                    '-map', '[v]',     # Video from complex filter
                    '-map', '0:a',     # Audio from first input
                    '-c:v', 'libx264', # Video codec
                    '-c:a', 'aac',     # Audio codec
                    '-shortest',       # Stop when shortest stream ends
                    '-r', '30',        # 30 FPS
                    '-y',              # Overwrite output file
                    video_path
                ]
            else:
                # Fallback without profile picture
                filter_complex = f"""
                    color=c=0x808080:s=1920x1080:d=1[bg_base];
                    [bg_base]drawbox=x=0:y=0:w=1920:h=1080:
                    color=0x4A90A4@0.3:thickness=fill[bg_gradient];
                    
                    [bg_gradient]drawtext=text='{clean_brand}':
                    fontsize=32:fontcolor=white:x=50:y=50:
                    box=1:boxcolor={brand_color}@0.8:boxborderw=10[bg_logo];
                    
                    [bg_logo]drawtext=text='{clean_title}':
                    fontsize=64:fontcolor=white:x=(w-text_w)/2:y=200:
                    shadowcolor=black@0.5:shadowx=3:shadowy=3[bg_title];
                    
                    [bg_title]drawtext=text='Host\\: {clean_host}':
                    fontsize=36:fontcolor=0xF0F0F0:x=(w-text_w)/2:y=300[bg_host];
                    
                    [bg_host]drawbox=x=710:y=400:w=500:h=400:
                    color=white@0.9:thickness=fill[bg_placeholder_bg];
                    [bg_placeholder_bg]drawbox=x=710:y=400:w=500:h=400:
                    color=0x2C3E50:thickness=8[bg_placeholder];
                    
                    [bg_placeholder]drawtext=text='🎤':fontsize=150:
                    fontcolor=0x34495E:x=960-75:y=600-75[bg_with_placeholder];
                    
                    [0:a]aformat=channel_layouts=mono,
                    showwaves=s=1920x200:mode=p2p:colors=white:
                    scale=sqrt:split_channels=1:
                    draw=scale[waveform_base];
                    
                    [waveform_base]crop=1920:150:0:25[waveform];
                    
                    [bg_with_placeholder][waveform]overlay=0:880[v]
                """
                cmd = [
                    'ffmpeg',
                    '-i', audio_path,  # Input audio
                    '-filter_complex', filter_complex,
                    '-map', '[v]',     # Video from complex filter
                    '-map', '0:a',     # Audio from input
                    '-c:v', 'libx264', # Video codec
                    '-c:a', 'aac',     # Audio codec
                    '-shortest',       # Stop when shortest stream ends
                    '-r', '30',        # 30 FPS
                    '-y',              # Overwrite output file
                    video_path
                ]
            
            logger.info(f"Creating styled video cover for: {title}")
            logger.info(f"Running ffmpeg command: {' '.join(cmd)}")
            
            # Update progress
            job_data['progress'] = 50
            with open(job_file, 'w') as f:
                json.dump(job_data, f, indent=2)
            
            # Run ffmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                logger.info(f"Video created successfully: {video_path}")
                
                # Update progress
                job_data['progress'] = 90
                with open(job_file, 'w') as f:
                    json.dump(job_data, f, indent=2)
                
                # Verify file was created and has reasonable size
                if os.path.exists(video_path) and os.path.getsize(video_path) > 1024:
                    return True
                else:
                    logger.error(f"Video file not created or too small: {video_path}")
                    return False
            else:
                logger.error(f"FFmpeg failed with return code {result.returncode}")
                logger.error(f"FFmpeg stderr: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg command timed out")
            return False
        except Exception as e:
            logger.error(f"Error creating video: {e}")
            return False
    
    def _escape_ffmpeg_text(self, text: str) -> str:
        """
        Escape text for use in ffmpeg drawtext filter.
        
        Args:
            text (str): Text to escape
            
        Returns:
            str: Escaped text
        """
        if not text:
            return ""
        
        # Escape special characters for ffmpeg drawtext
        text = text.replace('\\', '\\\\')
        text = text.replace(':', '\\:')
        text = text.replace("'", "\\'")
        text = text.replace('"', '\\"')
        text = text.replace('\n', ' ')
        text = text.replace('\r', ' ')
        
        # Limit length to prevent overflow
        if len(text) > 80:
            text = text[:77] + "..."
            
        return text
    
    def _get_brand_config(self) -> Dict:
        """Get branding configuration from config file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    return {
                        'brand_name': config.get('brand_name', 'XSpace'),
                        'brand_color': config.get('brand_color', '#FF6B35'),
                        'brand_logo_url': config.get('brand_logo_url', None)
                    }
        except Exception as e:
            logger.warning(f"Could not load brand config: {e}")
        
        # Default fallback
        return {
            'brand_name': 'XSpace',
            'brand_color': '#FF6B35',
            'brand_logo_url': None
        }
    
    def _download_image(self, url: str, filename: str) -> Optional[str]:
        """Download image from URL and save to temp directory."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            filepath = os.path.join("temp", filename)
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"Downloaded image: {url} -> {filepath}")
            return filepath
            
        except Exception as e:
            logger.warning(f"Failed to download image {url}: {e}")
            return None
    
    def _get_host_profile_picture(self, space_data: Dict, job_id: str) -> Optional[str]:
        """Get host profile picture from Twitter via unavatar.io."""
        try:
            # Extract host handle from metadata
            host_handle = None
            metadata = space_data.get('metadata', {})
            
            # Try different fields for host handle
            if metadata.get('host_handle'):
                host_handle = metadata['host_handle'].replace('@', '')
            elif metadata.get('host'):
                host = metadata['host'].replace('@', '').replace('#', '')
                if host and host != 'Unknown Host':
                    host_handle = host
            
            if not host_handle:
                logger.info("No host handle found, using placeholder")
                return None
            
            # Download profile picture from unavatar.io
            unavatar_url = f"https://unavatar.io/twitter/{host_handle}"
            filename = f"profile_{job_id}.jpg"
            
            return self._download_image(unavatar_url, filename)
            
        except Exception as e:
            logger.warning(f"Failed to get host profile picture: {e}")
            return None
    
    def _clean_for_json(self, obj):
        """Clean an object to make it JSON serializable."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: self._clean_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._clean_for_json(item) for item in obj]
        elif hasattr(obj, '__dict__'):
            return self._clean_for_json(obj.__dict__)
        else:
            return obj
    
    def cleanup_job(self, job_id: str) -> bool:
        """
        Clean up job files (optional).
        
        Args:
            job_id (str): Job ID
            
        Returns:
            bool: Success flag
        """
        try:
            job_file = os.path.join(self.jobs_dir, f"{job_id}_video.json")
            if os.path.exists(job_file):
                os.remove(job_file)
                logger.info(f"Cleaned up job file for {job_id}")
            return True
        except Exception as e:
            logger.error(f"Error cleaning up job {job_id}: {e}")
            return False

# Example usage
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Test video generation
    generator = VideoGenerator()
    
    # This would be called by the API
    # job_id = generator.create_video_job("test_space", "test_audio.mp3", {"title": "Test Space"})
    # status = generator.get_job_status(job_id)
    # print(f"Job status: {status}")