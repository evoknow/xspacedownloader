#!/usr/bin/env python3
# components/VideoGenerator.py
"""Video generation component for creating MP4 files with audio visualization."""

import os
import json
import uuid
import subprocess
import logging
import requests
import platform
from typing import Dict, Optional, Tuple, List
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Setup video generation specific logger
video_logger = logging.getLogger('video_generation')
video_logger.setLevel(logging.DEBUG)

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Create file handler for video.log
video_handler = logging.FileHandler('logs/video.log')
video_handler.setLevel(logging.DEBUG)

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
video_handler.setFormatter(formatter)

# Add handler if not already added
if not any(isinstance(h, logging.FileHandler) and h.baseFilename.endswith('video.log') for h in video_logger.handlers):
    video_logger.addHandler(video_handler)

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
        
        # Detect hardware acceleration support
        self._hardware_accel = self._detect_hardware_acceleration()
        
        # Detect CPU cores for multi-threading
        self._cpu_cores = self._detect_cpu_cores()
        
        logger.info(f"VideoGenerator initialized (hardware acceleration: {self._hardware_accel or 'none'}, CPU cores: {self._cpu_cores})")
    
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
            
            # Handle relative paths - convert to absolute if needed
            if not os.path.isabs(audio_path):
                # If it's a relative path like ./downloads/file.mp3, make it absolute
                if audio_path.startswith('./'):
                    audio_path = audio_path[2:]  # Remove ./
                audio_path = os.path.abspath(audio_path)
            
            # Verify the audio file exists
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
            logger.info(f"Processing audio file: {audio_path}")
            
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
    
    def _detect_hardware_acceleration(self) -> Optional[str]:
        """
        Detect available hardware acceleration for video encoding.
        
        Returns:
            Optional[str]: Hardware acceleration codec name or None
        """
        try:
            # Check if we're on macOS
            if platform.system() != 'Darwin':
                return None
            
            # Check available hardware accelerations
            result = subprocess.run(
                ['ffmpeg', '-hwaccels'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return None
            
            # Check if videotoolbox is available
            if 'videotoolbox' not in result.stdout:
                return None
            
            # Verify h264_videotoolbox encoder is available
            result = subprocess.run(
                ['ffmpeg', '-encoders'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and 'h264_videotoolbox' in result.stdout:
                logger.info("Detected VideoToolbox hardware acceleration support")
                return 'h264_videotoolbox'
            
            return None
            
        except Exception as e:
            logger.debug(f"Error detecting hardware acceleration: {e}")
            return None
    
    def _detect_cpu_cores(self) -> int:
        """
        Detect number of CPU cores for multi-threading.
        
        Returns:
            int: Number of CPU cores to use for encoding
        """
        try:
            import multiprocessing
            cores = multiprocessing.cpu_count()
            # Use most cores but leave 1-2 for system
            optimal_cores = max(1, cores - 1 if cores > 2 else cores)
            logger.info(f"Detected {cores} CPU cores, will use {optimal_cores} for encoding")
            return optimal_cores
        except Exception as e:
            logger.debug(f"Error detecting CPU cores: {e}")
            return 1
    
    def _get_encoding_params(self) -> List[str]:
        """
        Get optimal encoding parameters based on available hardware and CPU.
        
        Returns:
            List[str]: List of ffmpeg parameters for video encoding
        """
        params = []
        
        # Video codec
        if self._hardware_accel:
            params.extend(['-c:v', self._hardware_accel])
            # For hardware acceleration, limit threads as they can interfere
            optimal_threads = min(8, self._cpu_cores)
            params.extend(['-threads', str(optimal_threads)])
            # Add VideoToolbox optimizations
            if 'videotoolbox' in self._hardware_accel:
                params.extend(['-b:v', '2M'])  # Set bitrate for better quality/speed balance
                params.extend(['-allow_sw', '1'])  # Allow software fallback if needed
            logger.info(f"Using hardware acceleration: {self._hardware_accel} with {optimal_threads} threads")
        else:
            params.extend(['-c:v', 'libx264'])
            # Add preset for software encoding
            params.extend(['-preset', 'veryfast'])
            # For software encoding, use more threads
            if self._cpu_cores > 1:
                params.extend(['-threads', str(self._cpu_cores)])
                logger.debug(f"Using software encoding with {self._cpu_cores} threads")
            logger.info("Using software encoding with veryfast preset")
        
        return params
    
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
        video_logger.info("=" * 80)
        video_logger.info(f"Starting video generation for job: {job_data.get('job_id')}")
        video_logger.info(f"Audio path: {audio_path}")
        video_logger.info(f"Video path: {video_path}")
        video_logger.info(f"Audio file exists: {os.path.exists(audio_path)}")
        video_logger.info(f"Audio file size: {os.path.getsize(audio_path) if os.path.exists(audio_path) else 'N/A'} bytes")
        
        try:
            # Update progress
            job_data['progress'] = 25
            with open(job_file, 'w') as f:
                json.dump(job_data, f, indent=2)
            
            # Process audio to remove leading silence
            video_logger.info("Processing audio to remove leading silence...")
            processed_audio_path = self._remove_leading_silence(audio_path, job_data.get('job_id'))
            video_logger.info(f"Processed audio path: {processed_audio_path}")
            
            # Extract space information
            space_data = job_data.get('space_data', {})
            title = space_data.get('title', 'Audio Space')
            host = space_data.get('metadata', {}).get('host', 'Unknown Host')
            job_id = job_data.get('job_id')
            
            video_logger.info(f"Space title: {title}")
            video_logger.info(f"Host: {host}")
            video_logger.info(f"Job ID: {job_id}")
            
            # Get branding configuration
            brand_config = self._get_brand_config()
            brand_name = brand_config['brand_name']
            brand_color = brand_config['brand_color']
            brand_logo_url = brand_config['brand_logo_url']
            video_title_branding = brand_config['video_title_branding']
            video_watermark_text = brand_config['video_watermark_text']
            branding_enabled = brand_config['branding_enabled']
            background_color = brand_config['background_color']
            
            # Convert hex colors to ffmpeg format (remove # and ensure 6 digits)
            bg_color_hex = background_color.replace('#', '') if background_color else '808080'
            brand_color_hex = brand_color.replace('#', '') if brand_color else 'FF6B35'
            
            # Download brand logo if URL provided
            logo_path = None
            if branding_enabled and brand_logo_url:
                logo_filename = f"brand_logo_{job_id}.png"
                logo_path = self._download_image(brand_logo_url, logo_filename)
                if logo_path:
                    logger.info(f"Downloaded brand logo: {logo_path}")
            
            # Download host profile picture
            profile_pic_path = self._get_host_profile_picture(space_data, job_id)
            
            # Get optimal encoding parameters
            encoding_params = self._get_encoding_params()
            
            # Clean text for ffmpeg (escape special characters)
            clean_title = self._escape_ffmpeg_text(title)
            clean_host = self._escape_ffmpeg_text(host)
            clean_brand = self._escape_ffmpeg_text(brand_name)
            clean_video_title_branding = self._escape_ffmpeg_text(video_title_branding)
            clean_watermark = self._escape_ffmpeg_text(video_watermark_text)
            
            # Build filter complex with profile picture and configurable branding
            if profile_pic_path and os.path.exists(profile_pic_path):
                # Use downloaded profile picture
                # Build filter complex conditionally based on branding settings
                if branding_enabled:
                    # Start with custom background color
                    filter_complex = f"""
                        color=c=0x{bg_color_hex}:s=1920x1080:d=1[bg_base];
                        [bg_base]drawbox=x=0:y=0:w=1920:h=1080:
                        color=0x{bg_color_hex}@0.1:thickness=fill[bg_gradient];"""
                    
                    # Add logo if available, otherwise use text branding
                    if logo_path and os.path.exists(logo_path):
                        # Calculate index for logo input (2 if profile pic exists, 1 if not)
                        logo_input_idx = 2
                        filter_complex += f"""
                        
                        [{logo_input_idx}:v]scale=200:-1:force_original_aspect_ratio=1[logo_scaled];
                        [bg_gradient][logo_scaled]overlay=50:50[bg_with_logo];"""
                        current_bg = "bg_with_logo"
                    else:
                        filter_complex += f"""
                        
                        [bg_gradient]drawtext=text='{clean_video_title_branding}':
                        fontsize=32:fontcolor=white:x=50:y=50:
                        box=1:boxcolor=0x{brand_color_hex}@0.8:boxborderw=10[bg_with_logo];"""
                        current_bg = "bg_with_logo"
                    
                    filter_complex += f"""
                        
                        [{current_bg}]drawtext=text='{clean_title}':
                        fontsize=48:fontcolor=white:x=(w-text_w)/2:y=200:
                        shadowcolor=black@0.5:shadowx=3:shadowy=3[bg_title];
                        
                        [bg_title]drawtext=text='Host\\: {clean_host}':
                        fontsize=36:fontcolor=0xF0F0F0:x=(w-text_w)/2:y=300[bg_host];
                        
                        [1:v]scale=400:400:force_original_aspect_ratio=1,
                        pad=400:400:(ow-iw)/2:(oh-ih)/2:black[profile_scaled];
                        
                        [bg_host][profile_scaled]overlay=760:400[bg_with_profile];"""
                    
                    # Add watermark if specified
                    if clean_watermark:
                        filter_complex += f"""
                        
                        [bg_with_profile]drawtext=text='{clean_watermark}':
                        fontsize=24:fontcolor=white@0.7:x=w-text_w-20:y=h-text_h-150:
                        shadowcolor=black@0.8:shadowx=2:shadowy=2[bg_watermarked];"""
                        last_filter = "bg_watermarked"
                    else:
                        last_filter = "bg_with_profile"
                        
                    filter_complex += f"""
                        
                        [0:a]aformat=channel_layouts=mono,
                        showwaves=s=1920x200:mode=p2p:colors=white:
                        scale=sqrt:split_channels=1:
                        draw=scale[waveform_base];
                        
                        [waveform_base]crop=1920:150:0:25[waveform];
                        
                        [{last_filter}][waveform]overlay=0:880[v]
                    """
                else:
                    # Minimal branding when disabled
                    filter_complex = f"""
                        color=c=0x{bg_color_hex}:s=1920x1080:d=1[bg_base];
                        
                        [bg_base]drawtext=text='{clean_title}':
                        fontsize=48:fontcolor=white:x=(w-text_w)/2:y=200:
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
                
                # Build command with inputs
                cmd = [
                    'ffmpeg',
                    '-i', processed_audio_path,  # Input 0: audio (with silence removed)
                    '-i', profile_pic_path,  # Input 1: profile picture
                ]
                
                # Add logo as input if available
                if branding_enabled and logo_path and os.path.exists(logo_path):
                    cmd.extend(['-i', logo_path])  # Input 2: logo
                
                cmd.extend([
                    '-filter_complex', filter_complex,
                    '-map', '[v]',     # Video from complex filter
                    '-map', '0:a',     # Audio from first input
                ] + encoding_params + [
                    '-c:a', 'aac',     # Audio codec
                    '-shortest',       # Stop when shortest stream ends
                    '-r', '30',        # 30 FPS
                    '-y',              # Overwrite output file
                    video_path
                ])
            else:
                # Fallback without profile picture
                if branding_enabled:
                    # Start with custom background color
                    filter_complex = f"""
                        color=c=0x{bg_color_hex}:s=1920x1080:d=1[bg_base];
                        [bg_base]drawbox=x=0:y=0:w=1920:h=1080:
                        color=0x{bg_color_hex}@0.1:thickness=fill[bg_gradient];"""
                    
                    # Add logo if available, otherwise use text branding
                    if logo_path and os.path.exists(logo_path):
                        # Calculate index for logo input (1 without profile pic)
                        logo_input_idx = 1
                        filter_complex += f"""
                        
                        [{logo_input_idx}:v]scale=200:-1:force_original_aspect_ratio=1[logo_scaled];
                        [bg_gradient][logo_scaled]overlay=50:50[bg_with_logo];"""
                        current_bg = "bg_with_logo"
                    else:
                        filter_complex += f"""
                        
                        [bg_gradient]drawtext=text='{clean_video_title_branding}':
                        fontsize=32:fontcolor=white:x=50:y=50:
                        box=1:boxcolor=0x{brand_color_hex}@0.8:boxborderw=10[bg_with_logo];"""
                        current_bg = "bg_with_logo"
                    
                    filter_complex += f"""
                        
                        [{current_bg}]drawtext=text='{clean_title}':
                        fontsize=48:fontcolor=white:x=(w-text_w)/2:y=200:
                        shadowcolor=black@0.5:shadowx=3:shadowy=3[bg_title];
                        
                        [bg_title]drawtext=text='Host\\: {clean_host}':
                        fontsize=36:fontcolor=0xF0F0F0:x=(w-text_w)/2:y=300[bg_host];
                        
                        [bg_host]drawbox=x=710:y=400:w=500:h=400:
                        color=white@0.9:thickness=fill[bg_placeholder_bg];
                        [bg_placeholder_bg]drawbox=x=710:y=400:w=500:h=400:
                        color=0x2C3E50:thickness=8[bg_placeholder];
                        
                        [bg_placeholder]drawtext=text='🎤':fontsize=150:
                        fontcolor=0x34495E:x=960-75:y=600-75[bg_with_placeholder];"""
                    
                    # Add watermark if specified
                    if clean_watermark:
                        filter_complex += f"""
                        
                        [bg_with_placeholder]drawtext=text='{clean_watermark}':
                        fontsize=24:fontcolor=white@0.7:x=w-text_w-20:y=h-text_h-150:
                        shadowcolor=black@0.8:shadowx=2:shadowy=2[bg_watermarked];"""
                        last_filter = "bg_watermarked"
                    else:
                        last_filter = "bg_with_placeholder"
                        
                    filter_complex += f"""
                        
                        [0:a]aformat=channel_layouts=mono,
                        showwaves=s=1920x200:mode=p2p:colors=white:
                        scale=sqrt:split_channels=1:
                        draw=scale[waveform_base];
                        
                        [waveform_base]crop=1920:150:0:25[waveform];
                        
                        [{last_filter}][waveform]overlay=0:880[v]
                    """
                else:
                    # Minimal branding when disabled
                    filter_complex = f"""
                        color=c=0x{bg_color_hex}:s=1920x1080:d=1[bg_base];
                        
                        [bg_base]drawtext=text='{clean_title}':
                        fontsize=48:fontcolor=white:x=(w-text_w)/2:y=200:
                        shadowcolor=black@0.5:shadowx=3:shadowy=3[bg_title];
                        
                        [bg_title]drawtext=text='Host\\: {clean_host}':
                        fontsize=36:fontcolor=0xF0F0F0:x=(w-text_w)/2:y=300[bg_host];
                        
                        [bg_host]drawbox=x=710:y=400:w=500:h=400:
                        color=gray@0.5:thickness=fill[bg_placeholder_bg];
                        [bg_placeholder_bg]drawbox=x=710:y=400:w=500:h=400:
                        color=0x606060:thickness=4[bg_placeholder];
                        
                        [bg_placeholder]drawtext=text='🎤':fontsize=150:
                        fontcolor=0x808080:x=960-75:y=600-75[bg_with_placeholder];
                        
                        [0:a]aformat=channel_layouts=mono,
                        showwaves=s=1920x200:mode=p2p:colors=white:
                        scale=sqrt:split_channels=1:
                        draw=scale[waveform_base];
                        
                        [waveform_base]crop=1920:150:0:25[waveform];
                        
                        [bg_with_placeholder][waveform]overlay=0:880[v]
                    """
                # Build command with inputs
                cmd = [
                    'ffmpeg',
                    '-i', processed_audio_path,  # Input 0: audio (with silence removed)
                ]
                
                # Add logo as input if available
                if branding_enabled and logo_path and os.path.exists(logo_path):
                    cmd.extend(['-i', logo_path])  # Input 1: logo
                
                cmd.extend([
                    '-filter_complex', filter_complex,
                    '-map', '[v]',     # Video from complex filter
                    '-map', '0:a',     # Audio from first input
                ] + encoding_params + [
                    '-c:a', 'aac',     # Audio codec
                    '-shortest',       # Stop when shortest stream ends
                    '-r', '30',        # 30 FPS
                    '-y',              # Overwrite output file
                    video_path
                ])
            
            logger.info(f"Creating styled video cover for: {title}")
            logger.info(f"Running ffmpeg command: {' '.join(cmd)}")
            
            # Log detailed command for debugging
            video_logger.info("=" * 60)
            video_logger.info("FFMPEG COMMAND DETAILS:")
            video_logger.info("Command parts:")
            for i, part in enumerate(cmd):
                video_logger.info(f"  [{i}]: {part}")
            video_logger.info("Full command:")
            video_logger.info(' '.join(cmd))
            video_logger.info("=" * 60)
            
            # Check FFmpeg availability
            ffmpeg_check = self._check_ffmpeg()
            video_logger.info(f"FFmpeg available: {ffmpeg_check}")
            
            # Update progress
            job_data['progress'] = 50
            with open(job_file, 'w') as f:
                json.dump(job_data, f, indent=2)
            
            # Run ffmpeg
            video_logger.info("Starting FFmpeg execution...")
            start_time = datetime.now()
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout for complex operations
            )
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            video_logger.info(f"FFmpeg execution completed in {duration:.2f} seconds")
            
            if result.returncode == 0:
                logger.info(f"Video created successfully: {video_path}")
                video_logger.info(f"FFmpeg success! Return code: 0")
                video_logger.info(f"Output video path: {video_path}")
                
                # Track compute cost for MP4 video generation
                try:
                    from .DatabaseManager import DatabaseManager
                    
                    user_id = job_data.get('user_id')
                    space_id = job_data.get('space_id')
                    
                    if user_id and space_id:
                        db = DatabaseManager()
                        with db.get_connection() as conn:
                            cursor = conn.cursor()
                            
                            # Get compute cost per second from config (fallback to 0.001)
                            try:
                                cursor.execute("""
                                    SELECT setting_value FROM app_settings 
                                    WHERE setting_name = 'compute_cost_per_second'
                                """)
                                cost_result = cursor.fetchone()
                                cost_per_second = float(cost_result[0]) if cost_result else 0.001
                            except:
                                cost_per_second = 0.001  # Default fallback
                                
                            total_cost = max(1, round(duration * cost_per_second))
                            
                            # Get user balance
                            cursor.execute("SELECT credits FROM users WHERE id = %s", (user_id,))
                            balance_result = cursor.fetchone()
                            balance_before = float(balance_result[0]) if balance_result else 0.0
                            
                            # Check if user has sufficient credits
                            if balance_before >= total_cost:
                                # Deduct credits
                                balance_after = balance_before - total_cost
                                cursor.execute("""
                                    UPDATE users 
                                    SET credits = %s 
                                    WHERE id = %s
                                """, (balance_after, user_id))
                                
                                # Record compute transaction
                                cursor.execute("""
                                    INSERT INTO computes 
                                    (user_id, cookie_id, space_id, action, compute_time_seconds, 
                                     cost_per_second, total_cost, balance_before, balance_after)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                                """, (user_id, None, space_id, "mp4_generation", duration,
                                      cost_per_second, total_cost, balance_before, balance_after))
                                
                                conn.commit()
                                video_logger.info(f"COST TRACKING: mp4_generation cost tracked - ${total_cost:.6f} for {duration:.2f}s (User {user_id}: ${balance_before:.2f} -> ${balance_after:.2f})")
                            else:
                                video_logger.warning(f"COST TRACKING: Insufficient credits for user {user_id} - required ${total_cost:.6f}, available ${balance_before:.2f}")
                            
                            cursor.close()
                    else:
                        video_logger.info(f"COST TRACKING: Video generation by visitor - ${duration * 0.001:.6f} for {duration:.2f}s (not charged)")
                
                except Exception as cost_err:
                    video_logger.error(f"Error tracking video generation cost: {cost_err}")
                    # Don't fail video generation if cost tracking fails
                
                # Update progress
                job_data['progress'] = 90
                with open(job_file, 'w') as f:
                    json.dump(job_data, f, indent=2)
                
                # Clean up temporary files
                if processed_audio_path != audio_path and os.path.exists(processed_audio_path):
                    try:
                        os.remove(processed_audio_path)
                        logger.debug(f"Cleaned up temporary audio file: {processed_audio_path}")
                    except Exception as e:
                        logger.warning(f"Failed to clean up temporary audio: {e}")
                
                # Clean up downloaded logo if it was created
                if logo_path and os.path.exists(logo_path):
                    try:
                        os.remove(logo_path)
                        logger.debug(f"Cleaned up temporary logo file: {logo_path}")
                    except Exception as e:
                        logger.warning(f"Failed to clean up temporary logo: {e}")
                
                # Verify file was created and has reasonable size
                if os.path.exists(video_path):
                    file_size = os.path.getsize(video_path)
                    video_logger.info(f"Video file created: {video_path}")
                    video_logger.info(f"Video file size: {file_size} bytes ({file_size / (1024*1024):.2f} MB)")
                    
                    if file_size > 1024:
                        video_logger.info("Video generation SUCCESSFUL!")
                        return True
                    else:
                        video_logger.error(f"Video file too small: {file_size} bytes")
                        return False
                else:
                    video_logger.error(f"Video file not created at: {video_path}")
                    return False
            else:
                logger.error(f"FFmpeg failed with return code {result.returncode}")
                logger.error(f"FFmpeg stderr: {result.stderr}")
                
                # Log detailed error information
                video_logger.error("=" * 60)
                video_logger.error(f"FFMPEG FAILED! Return code: {result.returncode}")
                video_logger.error("STDOUT:")
                video_logger.error(result.stdout)
                video_logger.error("STDERR:")
                video_logger.error(result.stderr)
                video_logger.error("=" * 60)
                
                # Clean up temporary files on failure too
                if processed_audio_path != audio_path and os.path.exists(processed_audio_path):
                    try:
                        os.remove(processed_audio_path)
                    except:
                        pass
                
                if logo_path and os.path.exists(logo_path):
                    try:
                        os.remove(logo_path)
                    except:
                        pass
                        
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg command timed out")
            video_logger.error("FFMPEG TIMEOUT ERROR!")
            video_logger.error(f"FFmpeg timed out after 600 seconds (10 minutes)")
            
            # Clean up temporary files on timeout
            if 'processed_audio_path' in locals() and processed_audio_path != audio_path and os.path.exists(processed_audio_path):
                try:
                    os.remove(processed_audio_path)
                except:
                    pass
            
            if 'logo_path' in locals() and logo_path and os.path.exists(logo_path):
                try:
                    os.remove(logo_path)
                except:
                    pass
            return False
            
        except Exception as e:
            logger.error(f"Error creating video: {e}")
            video_logger.error("=" * 60)
            video_logger.error("EXCEPTION IN VIDEO GENERATION!")
            video_logger.error(f"Exception type: {type(e).__name__}")
            video_logger.error(f"Exception message: {str(e)}")
            video_logger.error("Full traceback:")
            import traceback
            video_logger.error(traceback.format_exc())
            video_logger.error("=" * 60)
            # Clean up temporary files on error
            if 'processed_audio_path' in locals() and processed_audio_path != audio_path and os.path.exists(processed_audio_path):
                try:
                    os.remove(processed_audio_path)
                except:
                    pass
            
            if 'logo_path' in locals() and logo_path and os.path.exists(logo_path):
                try:
                    os.remove(logo_path)
                except:
                    pass
            return False
    
    def _remove_leading_silence(self, audio_path: str, job_id: str) -> str:
        """
        Remove leading silence from audio file using ffmpeg.
        
        Args:
            audio_path (str): Input audio file path
            job_id (str): Job ID for naming temporary file
            
        Returns:
            str: Path to processed audio file
        """
        try:
            # Create output path for processed audio
            base_name = os.path.basename(audio_path)
            name, ext = os.path.splitext(base_name)
            
            # Determine output codec and extension based on input format
            # Keep MP3 as MP3, convert others to AAC
            if ext.lower() == '.mp3':
                output_codec = 'libmp3lame'
                output_ext = '.mp3'
            else:
                output_codec = 'aac'
                output_ext = '.m4a'  # Use proper extension for AAC
            
            processed_path = os.path.join("temp", f"{name}_trimmed_{job_id}{output_ext}")
            
            # First, detect where the actual audio starts using silencedetect
            # Use very aggressive settings to catch any low-level noise
            detect_cmd = [
                'ffmpeg',
                '-i', audio_path,
                '-af', 'silencedetect=noise=-60dB:d=0.01',  # Very sensitive: -60dB, 10ms
                '-f', 'null',
                '-'
            ]
            
            logger.info(f"Detecting silence in audio: {audio_path}")
            detect_result = subprocess.run(
                detect_cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Parse the output to find silence_end (where audio starts)
            start_time = 0
            if detect_result.returncode == 0:
                import re
                # Log the full stderr for debugging
                logger.debug(f"Silence detection output: {detect_result.stderr}")
                
                # Look for first silence_end in stderr (ffmpeg outputs to stderr)
                silence_end_match = re.search(r'silence_end: ([\d.]+)', detect_result.stderr)
                if silence_end_match:
                    start_time = float(silence_end_match.group(1))
                    # Don't add buffer - we want to cut right where audio starts
                    logger.info(f"Detected audio starts at {start_time} seconds")
                    # Store the silence offset for transcription timecode correction
                    self._store_silence_offset(job_id, start_time)
                else:
                    logger.info("No silence_end found, checking for continuous silence")
                    # If no silence_end found, audio might start immediately or have very short silence
            
            # Now trim the audio from the detected start point
            if start_time > 0:
                trim_cmd = [
                    'ffmpeg',
                    '-i', audio_path,
                    '-ss', str(start_time),  # Start from detected point
                    '-acodec', output_codec,
                    '-y',
                    processed_path
                ]
            else:
                # Fallback to very aggressive silenceremove if no silence detected
                logger.info("Using aggressive silenceremove filter as fallback")
                trim_cmd = [
                    'ffmpeg',
                    '-i', audio_path,
                    '-af', 'silenceremove=start_periods=1:start_duration=0.01:start_threshold=-60dB:detection=peak',
                    '-acodec', output_codec,
                    '-y',
                    processed_path
                ]
            
            logger.info(f"Trimming audio with command: {' '.join(trim_cmd)}")
            
            result = subprocess.run(
                trim_cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0 and os.path.exists(processed_path):
                # Verify the processed file is not empty
                original_size = os.path.getsize(audio_path)
                processed_size = os.path.getsize(processed_path)
                
                if processed_size > 1024:  # At least 1KB
                    logger.info(f"Successfully removed leading silence: {processed_path}")
                    logger.info(f"Original size: {original_size} bytes, Processed size: {processed_size} bytes")
                    logger.info(f"Size reduction: {original_size - processed_size} bytes ({((original_size - processed_size) / original_size * 100):.1f}%)")
                    
                    # Log duration comparison if possible
                    try:
                        # Get durations for comparison
                        dur_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1']
                        orig_dur = subprocess.run(dur_cmd + [audio_path], capture_output=True, text=True, timeout=5)
                        proc_dur = subprocess.run(dur_cmd + [processed_path], capture_output=True, text=True, timeout=5)
                        
                        if orig_dur.returncode == 0 and proc_dur.returncode == 0:
                            orig_duration = float(orig_dur.stdout.strip())
                            proc_duration = float(proc_dur.stdout.strip())
                            logger.info(f"Duration - Original: {orig_duration:.2f}s, Processed: {proc_duration:.2f}s, Trimmed: {orig_duration - proc_duration:.2f}s")
                    except:
                        pass
                    
                    return processed_path
                else:
                    logger.warning(f"Processed file too small ({processed_size} bytes), using original")
                    return audio_path
            else:
                logger.warning(f"Failed to remove silence, using original audio. Return code: {result.returncode}")
                logger.warning(f"FFmpeg stderr: {result.stderr}")
                return audio_path
                
        except Exception as e:
            logger.warning(f"Error removing leading silence: {e}, using original audio")
            return audio_path
    
    def _store_silence_offset(self, job_id: str, offset_seconds: float):
        """
        Store the silence offset in the job file for timecode correction.
        
        Args:
            job_id (str): Video generation job ID
            offset_seconds (float): Seconds of silence removed from the beginning
        """
        try:
            job_file = os.path.join("transcript_jobs", f"{job_id}_video.json")
            
            # Read existing job data
            job_data = {}
            if os.path.exists(job_file):
                with open(job_file, 'r') as f:
                    job_data = json.load(f)
            
            # Add silence offset to job data
            job_data['silence_offset'] = offset_seconds
            
            # Write back to file
            with open(job_file, 'w') as f:
                json.dump(job_data, f, indent=2)
            
            logger.info(f"Stored silence offset of {offset_seconds}s for job {job_id}")
            
        except Exception as e:
            logger.warning(f"Failed to store silence offset for job {job_id}: {e}")
    
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
        # Default configuration
        default_config = {
            'brand_name': 'XSpace',
            'brand_color': '#FF6B35',
            'brand_logo_url': None,
            'video_title_branding': 'XSpace Downloader',
            'video_watermark_text': '',
            'font_family': 'Arial',
            'branding_enabled': True,
            'background_color': '#808080'
        }
        
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    
                    # Extract all branding-related settings
                    brand_config = {
                        'brand_name': config.get('brand_name', default_config['brand_name']),
                        'brand_color': config.get('brand_color', default_config['brand_color']),
                        'brand_logo_url': config.get('brand_logo_url', default_config['brand_logo_url']),
                        'video_title_branding': config.get('video_title_branding', default_config['video_title_branding']),
                        'video_watermark_text': config.get('video_watermark_text', default_config['video_watermark_text']),
                        'font_family': config.get('font_family', default_config['font_family']),
                        'branding_enabled': config.get('branding_enabled', default_config['branding_enabled']),
                        'background_color': config.get('background_color', default_config['background_color'])
                    }
                    
                    logger.debug(f"Loaded brand config: {brand_config}")
                    return brand_config
                    
        except Exception as e:
            logger.warning(f"Could not load brand config: {e}")
        
        # Return default fallback
        logger.debug(f"Using default brand config: {default_config}")
        return default_config
    
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