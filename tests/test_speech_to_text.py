#!/usr/bin/env python3
# tests/test_speech_to_text.py

import unittest
import os
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

# Add parent directory to path to import components
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from components.SpeechToText import SpeechToText

class TestSpeechToText(unittest.TestCase):
    """Test case for the SpeechToText component."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary directory for test outputs
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = self.temp_dir.name
        
        # Path to test audio file - you'll need a real audio file for integration tests
        self.test_audio_dir = Path("downloads")
        self.test_audio_files = list(self.test_audio_dir.glob("*.mp3"))
        
        # Initialize SpeechToText with 'tiny' model for faster tests
        self.speech_to_text = SpeechToText(model_name='tiny')
    
    def tearDown(self):
        """Tear down test fixtures."""
        # Clean up temporary directory
        self.temp_dir.cleanup()
    
    @patch('whisper.load_model')
    def test_load_model(self, mock_load_model):
        """Test loading a Whisper model."""
        # Mock the whisper.load_model function
        mock_model = MagicMock()
        mock_load_model.return_value = mock_model
        
        # Test loading the model
        result = self.speech_to_text.load_model()
        
        # Verify the model was loaded
        self.assertTrue(result)
        mock_load_model.assert_called_once_with('tiny', device=None)
        self.assertEqual(self.speech_to_text.model, mock_model)
    
    @patch('whisper.load_model')
    def test_load_model_error(self, mock_load_model):
        """Test handling errors when loading a model."""
        # Mock an error when loading the model
        mock_load_model.side_effect = Exception("Test error")
        
        # Test loading the model
        result = self.speech_to_text.load_model()
        
        # Verify the error was handled
        self.assertFalse(result)
        self.assertIsNone(self.speech_to_text.model)
    
    @patch('components.SpeechToText.SpeechToText.load_model')
    @patch('whisper.load_model')
    def test_transcribe_file_not_found(self, mock_load_model, mock_load_model_method):
        """Test transcribing a non-existent file."""
        # Mock successful model loading
        mock_load_model_method.return_value = True
        
        # Test transcribing a non-existent file
        result = self.speech_to_text.transcribe("non_existent_file.mp3")
        
        # Verify the error was handled
        self.assertIsNone(result)
    
    @unittest.skipIf(not os.path.exists("downloads") or not any(Path("downloads").glob("*.mp3")), 
                    "No test audio files available")
    def test_transcribe_integration(self):
        """Integration test for transcribing a real audio file."""
        # Skip this test if there are no audio files in the test directory
        if not self.test_audio_files:
            self.skipTest("No test audio files available")
        
        # Get the first test audio file
        test_audio = str(self.test_audio_files[0])
        output_file = os.path.join(self.output_dir, "test_transcription.txt")
        
        # Transcribe the test audio file
        result = self.speech_to_text.transcribe(
            test_audio,
            output_file=output_file,
            verbose=True
        )
        
        # Verify a result was returned and the output file was created
        self.assertIsNotNone(result)
        self.assertTrue(os.path.exists(output_file))
        with open(output_file, 'r', encoding='utf-8') as f:
            file_content = f.read()
        self.assertEqual(result, file_content)
        
    @patch('components.SpeechToText.SpeechToText.transcribe')
    @patch('components.SpeechToText.SpeechToText.load_model')
    def test_batch_transcribe(self, mock_load_model, mock_transcribe):
        """Test batch transcription of multiple audio files."""
        # Mock successful model loading
        mock_load_model.return_value = True
        
        # Mock the transcribe method to return a test string
        mock_transcribe.return_value = "Test transcription"
        
        # Create test audio files
        test_dir = os.path.join(self.output_dir, "test_audio")
        os.makedirs(test_dir, exist_ok=True)
        test_files = [
            os.path.join(test_dir, f"test{i}.mp3") for i in range(3)
        ]
        
        # Create empty files
        for file_path in test_files:
            with open(file_path, 'w') as f:
                pass
        
        # Test batch transcription
        results = self.speech_to_text.batch_transcribe(
            test_dir,
            output_directory=os.path.join(self.output_dir, "test_output")
        )
        
        # Verify the results
        self.assertEqual(len(results), 3)
        for file_path in test_files:
            self.assertEqual(results[file_path], "Test transcription")
        
        # Verify the transcribe method was called for each file
        self.assertEqual(mock_transcribe.call_count, 3)
    
    def test_format_timestamp(self):
        """Test formatting timestamps for VTT and SRT formats."""
        # Test VTT format
        vtt_timestamp = self.speech_to_text._format_timestamp(3661.5, vtt=True)
        self.assertEqual(vtt_timestamp, "01:01:01.500")
        
        # Test SRT format
        srt_timestamp = self.speech_to_text._format_timestamp(3661.5, vtt=False)
        self.assertEqual(srt_timestamp, "01:01:01,500")
    
    @patch('components.SpeechToText.SpeechToText.load_model')
    @patch('components.SpeechToText.SpeechToText._save_output')
    def test_save_output_formats(self, mock_save_output, mock_load_model):
        """Test saving output in different formats."""
        # Mock successful model loading
        mock_load_model.return_value = True
        
        # Create a mock transcription result
        mock_result = {
            "text": "This is a test transcription.",
            "segments": [
                {"start": 0.0, "end": 2.0, "text": "This is a test"},
                {"start": 2.0, "end": 4.0, "text": "transcription."}
            ],
            "language": "en"
        }
        
        # Test saving as text
        self.speech_to_text._save_output(
            mock_result, 
            os.path.join(self.output_dir, "test.txt"),
            "txt"
        )
        
        # Test saving as JSON
        self.speech_to_text._save_output(
            mock_result, 
            os.path.join(self.output_dir, "test.json"),
            "json"
        )
        
        # Check that files were created
        self.assertTrue(os.path.exists(os.path.join(self.output_dir, "test.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.output_dir, "test.json")))
        
        # Verify content of text file
        with open(os.path.join(self.output_dir, "test.txt"), 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertEqual(content, "This is a test transcription.")
        
        # Verify content of JSON file
        with open(os.path.join(self.output_dir, "test.json"), 'r', encoding='utf-8') as f:
            content = json.load(f)
            self.assertEqual(content["text"], "This is a test transcription.")
            self.assertEqual(len(content["segments"]), 2)

if __name__ == '__main__':
    unittest.main()