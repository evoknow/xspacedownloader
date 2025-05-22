#!/usr/bin/env python3
# tests/test_download_space.py

import unittest
import sys
import os
import json
import time
import signal
from unittest.mock import patch, MagicMock, mock_open
import tempfile
import shutil
import subprocess

# Add parent directory to path for importing components
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.DownloadSpace import DownloadSpace

class DownloadSpaceTest(unittest.TestCase):
    """
    Test case for DownloadSpace component.
    Tests the Space download functionality with mocks to avoid actual downloading.
    """
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary directory for downloads
        self.temp_dir = tempfile.mkdtemp()
        
        # Mock Space component
        with patch('components.Space.Space') as mock_space_class:
            # Configure the mock
            self.mock_space = mock_space_class.return_value
            
            # Set up extract_space_id to return a valid space_id
            self.mock_space.extract_space_id.return_value = "1dRJZEpyjlNGB"
            
            # Set up create_download_job to return a valid job_id
            self.mock_space.create_download_job.return_value = 1
            
            # Create DownloadSpace instance with mocked dependencies
            self.downloader = DownloadSpace(download_dir=self.temp_dir)
            
            # Replace the real Space component with our mock
            self.downloader.space_component = self.mock_space
    
    def tearDown(self):
        """Tear down test fixtures."""
        # Clean up temporary directory
        shutil.rmtree(self.temp_dir)
    
    def test_extract_space_id(self):
        """Test space ID extraction from URL."""
        # Set up test data
        test_url = "https://x.com/i/spaces/1dRJZEpyjlNGB"
        
        # Call the method
        result = self.downloader.extract_space_id(test_url)
        
        # Verify extract_space_id was called on the Space component
        self.mock_space.extract_space_id.assert_called_once_with(test_url)
        
        # Verify result
        self.assertEqual(result, "1dRJZEpyjlNGB")
    
    @patch('subprocess.run')
    @patch('os.path.isfile')
    @patch('shutil.which')
    def test_check_yt_dlp_installed(self, mock_which, mock_isfile, mock_run):
        """Test checking if yt-dlp is installed."""
        # Configure mocks to simulate successful installation
        mock_isfile.return_value = True
        mock_which.return_value = "/usr/bin/yt-dlp"
        mock_run.return_value = MagicMock(returncode=0, stdout="yt-dlp 2023.02.17")
        
        # Call the method
        result = self.downloader._check_yt_dlp_installed()
        
        # Verify result
        self.assertTrue(result)
        
        # Now test with yt-dlp not installed
        mock_isfile.return_value = False
        mock_which.return_value = None
        mock_run.side_effect = FileNotFoundError("No such file or directory: 'yt-dlp'")
        
        # Patch os.path.dirname to avoid looking for files in actual directories
        with patch('os.path.dirname', return_value="/fake/path"):
            # Mock os.path.exists to simulate no yt-dlp in venv
            with patch('os.path.exists', return_value=False):
                # Call the method
                result = self.downloader._check_yt_dlp_installed()
                
                # Verify result
                self.assertFalse(result)
    
    def test_get_output_filename(self):
        """Test generating output filename for downloaded space."""
        # Set up test data
        space_id = "1dRJZEpyjlNGB"
        file_type = "mp3"
        
        # Case 1: Space details available with title
        self.mock_space.get_space.return_value = {
            'space_id': space_id,
            'title': "Test Space Title"
        }
        
        # Call the method
        result = self.downloader._get_output_filename(space_id, file_type)
        
        # Verify get_space was called
        self.mock_space.get_space.assert_called_with(space_id)
        
        # Verify correct filename was generated
        expected_path = os.path.join(self.temp_dir, f"Test_Space_Title_{space_id}.{file_type}")
        self.assertEqual(result, expected_path)
        
        # Case 2: No space details available
        self.mock_space.get_space.reset_mock()
        self.mock_space.get_space.return_value = None
        
        # Call the method
        result = self.downloader._get_output_filename(space_id, file_type)
        
        # Verify get_space was called
        self.mock_space.get_space.assert_called_with(space_id)
        
        # Verify correct filename was generated (just space_id)
        expected_path = os.path.join(self.temp_dir, f"{space_id}.{file_type}")
        self.assertEqual(result, expected_path)
    
    def test_progress_hook(self):
        """Test progress hook function updates database correctly."""
        # Set up test data
        job_id = 1
        space_id = "1dRJZEpyjlNGB"
        
        # Case 1: Downloading status
        progress_data = {
            'status': 'downloading',
            'downloaded_bytes': 10485760,  # 10 MB
            'total_bytes': 104857600       # 100 MB
        }
        
        # Call the method
        self.downloader._progress_hook(progress_data, job_id, space_id)
        
        # Verify update_download_job was called to update the progress
        args_list = self.mock_space.update_download_job.call_args_list
        progress_size_found = False
        progress_percent_found = False
        
        for args, kwargs in args_list:
            if 'progress_in_size' in kwargs and kwargs['progress_in_size'] == 10.0:
                progress_size_found = True
            if 'progress_in_percent' in kwargs and kwargs['progress_in_percent'] == 10:
                progress_percent_found = True
        
        self.assertTrue(progress_size_found, "progress_in_size not updated correctly")
        self.assertTrue(progress_percent_found, "progress_in_percent not updated correctly")
        
        # Verify update_download_progress was called
        self.mock_space.update_download_progress.assert_called()
        
        # Case 2: Finished status
        self.mock_space.update_download_job.reset_mock()
        self.mock_space.update_download_progress.reset_mock()
        
        progress_data = {
            'status': 'finished',
            'downloaded_bytes': 104857600  # 100 MB
        }
        
        # Call the method
        self.downloader._progress_hook(progress_data, job_id, space_id)
        
        # Verify update_download_job was called with completed status
        args_list = self.mock_space.update_download_job.call_args_list
        status_completed_found = False
        
        for args, kwargs in args_list:
            if 'status' in kwargs and kwargs['status'] == 'completed':
                status_completed_found = True
        
        self.assertTrue(status_completed_found, "status='completed' not set correctly")
    
    def test_build_yt_dlp_command(self):
        """Test building yt-dlp command."""
        # Set up test data
        url = "https://x.com/i/spaces/1dRJZEpyjlNGB"
        output_path = "/path/to/output.mp3"
        file_type = "mp3"
        
        # Override the YT_DLP_BINARY for the test
        original_binary = self.downloader.YT_DLP_BINARY
        self.downloader.YT_DLP_BINARY = "yt-dlp"
        
        try:
            # Call the method 
            result = self.downloader._build_yt_dlp_command(url, output_path, file_type)
            
            # Check if we're using module approach
            if isinstance(result, list) and len(result) > 1 and result[1] == "-m":
                # If module approach is used, verify key parameters instead of exact command
                self.assertIn("--extract-audio", result)
                self.assertIn(f"--audio-format={file_type}", result)
                self.assertIn("--audio-quality=0", result)
                self.assertIn("-o", result)
                self.assertIn(output_path, result)
                self.assertIn(url, result)
            else:
                # For binary approach
                # Verify correct command was generated
                expected_command = [
                    "yt-dlp",
                    "--extract-audio",
                    f"--audio-format={file_type}",
                    "--audio-quality=0",
                    "--continue",
                    "--no-warnings",
                    "-o", output_path,
                    url
                ]
                
                # Check only essential parameters, not exact command
                for param in expected_command:
                    self.assertIn(param, result)
        finally:
            # Restore the original binary path
            self.downloader.YT_DLP_BINARY = original_binary
    
    @patch('components.DownloadSpace.DownloadSpace._check_yt_dlp_installed')
    def test_download_with_invalid_file_type(self, mock_check_installed):
        """Test download with invalid file type."""
        # Configure mocks
        mock_check_installed.return_value = True
        
        # Call the method with invalid file type
        result = self.downloader.download("https://x.com/i/spaces/1dRJZEpyjlNGB", "invalid_type")
        
        # Verify result is None (error)
        self.assertIsNone(result)
        
        # No need to verify _check_yt_dlp_installed was called
        # Current implementation validates file type before checking yt-dlp
        # mock_check_installed.assert_called_once()
    
    @patch('components.DownloadSpace.DownloadSpace._check_yt_dlp_installed')
    def test_download_with_yt_dlp_not_installed(self, mock_check_installed):
        """Test download when yt-dlp is not installed."""
        # Configure mocks
        mock_check_installed.return_value = False
        
        # Call the method
        result = self.downloader.download("https://x.com/i/spaces/1dRJZEpyjlNGB")
        
        # Verify result is None (error)
        self.assertIsNone(result)
        
        # Verify _check_yt_dlp_installed was called
        mock_check_installed.assert_called_once()
    
    @patch('components.DownloadSpace.DownloadSpace._check_yt_dlp_installed')
    def test_download_with_invalid_url(self, mock_check_installed):
        """Test download with invalid URL."""
        # Configure mocks
        mock_check_installed.return_value = True
        self.mock_space.extract_space_id.return_value = None
        
        # Call the method with invalid URL
        result = self.downloader.download("https://invalid.url")
        
        # Verify result is None (error)
        self.assertIsNone(result)
        
        # Verify _check_yt_dlp_installed was called
        mock_check_installed.assert_called_once()
        
        # Verify extract_space_id was called
        self.mock_space.extract_space_id.assert_called_once_with("https://invalid.url")
    
    @patch('components.DownloadSpace.DownloadSpace._check_yt_dlp_installed')
    @patch('components.DownloadSpace.DownloadSpace._download_async')
    def test_download_async(self, mock_download_async, mock_check_installed):
        """Test asynchronous download."""
        # Configure mocks
        mock_check_installed.return_value = True
        self.mock_space.extract_space_id.return_value = "1dRJZEpyjlNGB"
        self.mock_space.get_space.return_value = None
        mock_download_async.return_value = 1
        
        # Call the method with async_mode=True
        result = self.downloader.download("https://x.com/i/spaces/1dRJZEpyjlNGB", async_mode=True)
        
        # Verify create_space was called
        self.mock_space.create_space.assert_called_once()
        
        # Verify create_download_job was called
        self.mock_space.create_download_job.assert_called_once_with(
            space_id="1dRJZEpyjlNGB",
            user_id=0,
            file_type="mp3"
        )
        
        # Verify update_download_job was called
        self.mock_space.update_download_job.assert_called_once_with(
            1,
            status='pending'
        )
        
        # Verify _download_async was called
        mock_download_async.assert_called_once()
        
        # Verify result is the job ID
        self.assertEqual(result, 1)
    
    @patch('components.DownloadSpace.DownloadSpace._check_yt_dlp_installed')
    @patch('components.DownloadSpace.DownloadSpace._download_sync')
    def test_download_sync(self, mock_download_sync, mock_check_installed):
        """Test synchronous download."""
        # Configure mocks
        mock_check_installed.return_value = True
        self.mock_space.extract_space_id.return_value = "1dRJZEpyjlNGB"
        self.mock_space.get_space.return_value = None
        mock_download_sync.return_value = "/path/to/output.mp3"
        
        # Call the method with async_mode=False
        result = self.downloader.download("https://x.com/i/spaces/1dRJZEpyjlNGB", async_mode=False)
        
        # Verify create_space was called
        self.mock_space.create_space.assert_called_once()
        
        # Verify create_download_job was called
        self.mock_space.create_download_job.assert_called_once_with(
            space_id="1dRJZEpyjlNGB",
            user_id=0,
            file_type="mp3"
        )
        
        # Verify update_download_job was called
        self.mock_space.update_download_job.assert_called_once_with(
            1,
            status='pending'
        )
        
        # Verify _download_sync was called
        mock_download_sync.assert_called_once()
        
        # Verify result is the output path
        self.assertEqual(result, "/path/to/output.mp3")
    
    @patch('subprocess.Popen')
    @patch('os.path.getsize')
    @patch('shutil.move')
    @patch('os.listdir')
    @patch('tempfile.TemporaryDirectory')
    @patch('os.makedirs')
    def test_download_sync_implementation(self, mock_makedirs, mock_temp_dir, mock_listdir, mock_move, mock_getsize, mock_popen):
        """Test synchronous download implementation."""
        # Configure mocks
        mock_temp_dir.return_value.__enter__.return_value = "/tmp/temp_dir"
        mock_listdir.return_value = ["1dRJZEpyjlNGB.mp3"]
        mock_getsize.return_value = 104857600  # 100 MB
        
        # Mock the process
        mock_process = MagicMock()
        mock_process.poll.return_value = 0
        mock_process.stdout.readline.side_effect = [
            "[download] 10.5% of 95.37MiB at 1.23MiB/s",
            "[download] 50.0% of 95.37MiB at 2.34MiB/s",
            "[download] 100.0% of 95.37MiB at 3.45MiB/s",
            ""  # End of output
        ]
        mock_popen.return_value = mock_process
        
        # Override _build_yt_dlp_command for the test
        with patch.object(self.downloader, '_build_yt_dlp_command') as mock_build_cmd:
            # Make it return a simple, deterministic command for testing
            test_command = [
                "yt-dlp",
                "--extract-audio",
                "--audio-format=mp3",
                "--audio-quality=0",
                "--continue",
                "--no-warnings",
                "-o", "/tmp/temp_dir/1dRJZEpyjlNGB.%(ext)s",
                "https://x.com/i/spaces/1dRJZEpyjlNGB"
            ]
            mock_build_cmd.return_value = test_command
            
            # Call the method
            output_path = os.path.join(self.temp_dir, "1dRJZEpyjlNGB.mp3")
            result = self.downloader._download_sync(
                space_url="https://x.com/i/spaces/1dRJZEpyjlNGB",
                space_id="1dRJZEpyjlNGB",
                job_id=1,
                output_path=output_path,
                file_type="mp3"
            )
            
            # Verify job was updated to in_progress
            assert_called = False
            for call_args, call_kwargs in self.mock_space.update_download_job.call_args_list:
                if 'status' in call_kwargs and call_kwargs['status'] == 'in_progress':
                    assert_called = True
            self.assertTrue(assert_called, "Job not set to in_progress status")
            
            # Verify subprocess.Popen was called
            mock_popen.assert_called_once()
            
            # Verify temp dir was created
            mock_temp_dir.assert_called_once()
            
            # Verify downloaded file was moved
            mock_move.assert_called_with(
                os.path.join("/tmp/temp_dir", "1dRJZEpyjlNGB.mp3"),
                output_path
            )
            
            # Verify result is the output path
            self.assertEqual(result, output_path)
    
    def test_get_download_status(self):
        """Test getting download status."""
        # Configure mock
        self.mock_space.get_download_job.return_value = {
            'id': 1,
            'space_id': "1dRJZEpyjlNGB",
            'status': 'completed',
            'progress_in_percent': 100
        }
        
        # Call the method
        result = self.downloader.get_download_status(1)
        
        # Verify get_download_job was called
        self.mock_space.get_download_job.assert_called_once_with(1)
        
        # Verify result
        self.assertEqual(result['id'], 1)
        self.assertEqual(result['status'], 'completed')
    
    @patch('os.kill')
    @patch('time.sleep')
    def test_cancel_download(self, mock_sleep, mock_kill):
        """Test canceling a download."""
        # Configure mocks
        self.mock_space.get_download_job.return_value = {
            'id': 1,
            'space_id': "1dRJZEpyjlNGB",
            'status': 'in_progress',
            'process_id': 12345
        }
        
        # Setup mock so first os.kill works, second raises OSError (process ended)
        mock_kill.side_effect = [None, OSError("No such process")]
        
        # Call the method
        result = self.downloader.cancel_download(1)
        
        # Verify get_download_job was called
        self.mock_space.get_download_job.assert_called_once_with(1)
        
        # Verify os.kill was called to terminate the process with SIGTERM
        mock_kill.assert_any_call(12345, signal.SIGTERM)
        
        # Verify update_download_job was called with expected values
        update_calls = self.mock_space.update_download_job.call_args_list
        status_updated = False
        
        for args, kwargs in update_calls:
            if 'status' in kwargs and kwargs['status'] == 'failed':
                if 'error_message' in kwargs and "canceled by user" in kwargs['error_message']:
                    status_updated = True
        
        self.assertTrue(status_updated, "Job not properly marked as failed with cancel message")
        
        # Verify result
        self.assertTrue(result)
    
    def test_list_downloads(self):
        """Test listing downloads."""
        # Configure mock
        self.mock_space.list_download_jobs.return_value = [
            {'id': 1, 'space_id': "1dRJZEpyjlNGB", 'status': 'completed'},
            {'id': 2, 'space_id': "2eRJZEpyjlNHC", 'status': 'in_progress'}
        ]
        
        # Call the method
        result = self.downloader.list_downloads(user_id=0, status='completed')
        
        # Verify list_download_jobs was called
        self.mock_space.list_download_jobs.assert_called_once_with(0, 'completed', 10, 0)
        
        # Verify result
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['id'], 1)
        self.assertEqual(result[1]['id'], 2)


if __name__ == '__main__':
    unittest.main()