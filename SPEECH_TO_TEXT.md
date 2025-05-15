# Speech-to-Text Component for XSpace Downloader

The SpeechToText component allows users to convert audio recordings from X Spaces into accurate, searchable text transcriptions. This document covers the features, requirements, usage examples, and technical details of the SpeechToText component.

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
  - [Command-Line Usage](#command-line-usage)
  - [Programmatic Usage](#programmatic-usage)
- [Model Selection](#model-selection)
- [Output Formats](#output-formats)
- [Advanced Options](#advanced-options)
- [Batch Processing](#batch-processing)
- [Integration with Space Component](#integration-with-space-component)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

## Overview

The SpeechToText component uses OpenAI's Whisper automatic speech recognition (ASR) system to provide high-accuracy transcription for X Space recordings. It integrates seamlessly with the XSpace Downloader system and can be used either programmatically through the Python API or via the included command-line utility.

## Features

- **High-Quality Speech Recognition**: Uses state-of-the-art Whisper ASR models
- **Multiple Languages**: Supports 99+ languages with automatic language detection
- **Model Options**: 5 model sizes (tiny to large) to balance speed vs. accuracy
- **Multiple Output Formats**:
  - Plain text (TXT)
  - JSON with timestamps and metadata
  - WebVTT and SRT subtitles with timestamps
- **Batch Processing**: Transcribe multiple audio files in a directory
- **Quiet Mode**: Suppress verbose output for automation and scripting
- **Error Handling**: Robust error management and recovery
- **Progress Display**: Visual feedback during processing
- **Comprehensive Logging**: Detailed logs for troubleshooting

## Requirements

- Python 3.8 or higher
- FFmpeg (required for audio processing)
- PyTorch (automatically installed as a dependency)
- Internet connection (for initial model download)
- Sufficient disk space for models (~1GB for the large model)
- Sufficient RAM (4GB minimum, 8GB+ recommended for larger models)

## Installation

The SpeechToText component is installed as part of the XSpace Downloader system. If you need to install it specifically:

1. Ensure FFmpeg is installed on your system:
   - On macOS: `brew install ffmpeg`
   - On Ubuntu: `sudo apt-get install ffmpeg`
   - On Windows: Download from [ffmpeg.org](https://ffmpeg.org/download.html)

2. Install the required Python packages:
   ```bash
   pip install openai-whisper torch
   ```

## Usage

### Command-Line Usage

The `transcribe.py` script provides an easy-to-use command-line interface:

```bash
# Basic usage
./transcribe.py path/to/audio.mp3

# Specify output file and format
./transcribe.py path/to/audio.mp3 -o transcription.txt -f txt

# Use a specific model size
./transcribe.py path/to/audio.mp3 -m medium

# Specify language (instead of auto-detection)
./transcribe.py path/to/audio.mp3 -l en

# Create subtitles
./transcribe.py path/to/audio.mp3 -o subtitles.vtt -f vtt

# Batch process a directory
./transcribe.py path/to/audio_directory/ -b -o output_directory/

# Suppress all output (quiet mode)
./transcribe.py path/to/audio.mp3 -o transcription.txt --quiet

# Show verbose output
./transcribe.py path/to/audio.mp3 -v
```

### Full Command-Line Options

```
usage: transcribe.py [-h] [--output OUTPUT] [--format {txt,json,vtt,srt}]
                      [--model {tiny,base,small,medium,large}]
                      [--language LANGUAGE] [--task {transcribe,translate}]
                      [--verbose] [--quiet] [--batch]
                      audio_file

Transcribe an audio file to text using Whisper AI

positional arguments:
  audio_file            Path to the audio file to transcribe

optional arguments:
  -h, --help            show this help message and exit
  --output OUTPUT, -o OUTPUT
                        Path to save the transcription output
  --format {txt,json,vtt,srt}, -f {txt,json,vtt,srt}
                        Output format (txt, json, vtt, srt) (default: txt)
  --model {tiny,base,small,medium,large}, -m {tiny,base,small,medium,large}
                        Whisper model to use (default: base)
  --language LANGUAGE, -l LANGUAGE
                        Language code (e.g., 'en', 'fr'). Auto-detected if not
                        specified.
  --task {transcribe,translate}, -t {transcribe,translate}
                        Task to perform (transcribe or translate to English)
                        (default: transcribe)
  --verbose, -v         Print verbose output
  --quiet, -q           Suppress all non-essential output
  --batch, -b           Treat audio_file as a directory and transcribe all
                        audio files
```

### Programmatic Usage

You can also use the SpeechToText component in your Python code:

```python
from components.SpeechToText import SpeechToText

# Initialize the component (optionally specifying model size)
stt = SpeechToText(model_name="base")  # Options: tiny, base, small, medium, large

# Simple transcription
result = stt.transcribe("path/to/audio.mp3")
print(result)

# Transcribe with specific options
result = stt.transcribe(
    audio_file="path/to/audio.mp3",
    language="en",  # Optional: specify language code
    task="transcribe",  # Options: transcribe, translate
    verbose=False,
    output_file="transcription.txt",
    output_format="txt"  # Options: txt, json, vtt, srt
)

# Batch processing
results = stt.batch_transcribe(
    audio_directory="path/to/audio_directory",
    output_directory="path/to/output_directory",
    language=None,  # Auto-detect language
    file_extensions=[".mp3", ".wav", ".m4a"],
    recursive=True  # Process subdirectories
)
```

## Model Selection

Whisper offers multiple model sizes, each with different accuracy and speed characteristics:

| Model | Parameters | Required VRAM | Relative Speed | Accuracy |
|-------|------------|---------------|----------------|----------|
| tiny  | 39M        | ~1GB          | ~32x           | Lowest   |
| base  | 74M        | ~1GB          | ~16x           | Low      |
| small | 244M       | ~2GB          | ~6x            | Medium   |
| medium| 769M       | ~5GB          | ~2x            | High     |
| large | 1550M      | ~10GB         | 1x             | Highest  |

Guidelines for choosing a model:
- **tiny**: Quick tests, very short clips, non-critical applications
- **base**: Default, good balance of speed and accuracy for most purposes
- **small**: Better quality when accuracy matters more than speed
- **medium**: High quality for important content
- **large**: Best quality for critical content where accuracy is paramount

## Output Formats

The SpeechToText component supports multiple output formats:

### Plain Text (txt)
The simplest format with just the transcribed text.

### JSON
Contains the full transcription data including:
- Complete text
- Detected language
- Segments with timestamps
- Confidence scores

Example:
```json
{
  "text": "This is the transcribed text of the entire audio.",
  "language": "en",
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 5.2,
      "text": "This is the first segment.",
      "tokens": [50364, 800, 338, 329, 1459, 13, 50564],
      "temperature": 0.0,
      "avg_logprob": -0.458,
      "compression_ratio": 1.375,
      "no_speech_prob": 0.019
    },
    {
      "id": 1,
      "start": 5.2,
      "end": 10.4,
      "text": "This is the second segment.",
      "tokens": [50364, 800, 338, 329, 1017, 1459, 13, 50564],
      "temperature": 0.0,
      "avg_logprob": -0.384,
      "compression_ratio": 1.25,
      "no_speech_prob": 0.031
    }
  ]
}
```

### WebVTT
Web Video Text Tracks format for subtitles:
```
WEBVTT

00:00:00.000 --> 00:00:05.200
This is the first segment.

00:00:05.200 --> 00:00:10.400
This is the second segment.
```

### SRT
SubRip Text format for subtitles:
```
1
00:00:00,000 --> 00:00:05,200
This is the first segment.

2
00:00:05,200 --> 00:00:10,400
This is the second segment.
```

## Advanced Options

### Language Specification
By default, Whisper automatically detects the language. However, you can specify a language code to improve accuracy:

```bash
./transcribe.py audio.mp3 --language en  # English
./transcribe.py audio.mp3 --language fr  # French
./transcribe.py audio.mp3 --language de  # German
```

### Translation
Whisper can translate non-English speech directly to English:

```bash
./transcribe.py foreign_language.mp3 --task translate
```

## Batch Processing

You can transcribe multiple audio files in a directory:

```bash
./transcribe.py /path/to/audio/directory --batch --output /path/to/output/directory
```

This will:
1. Scan the directory for audio files (mp3, wav, m4a, flac, ogg)
2. Process each file and save transcriptions to the output directory
3. Maintain directory structure if using the recursive option

## Integration with Space Component

The SpeechToText component can be integrated with the Space component for automatic transcription:

```python
from components.Space import Space
from components.SpeechToText import SpeechToText

# Initialize components
space = Space(db_connection)
stt = SpeechToText()

# Get a space from the database
space_id = "1dRJZEpyjlNGB"
space_details = space.get_space(space_id)

# Get audio file path for the space
audio_file = space.get_file_path(space_id)

# Transcribe the audio
if audio_file:
    transcription = stt.transcribe(audio_file)
    
    # Save transcription to a file
    transcript_path = f"transcripts/{space_id}.txt"
    with open(transcript_path, "w") as f:
        f.write(transcription)
        
    # Optionally, update the space record with transcript info
    space.update_space_metadata(space_id, {
        "has_transcript": True,
        "transcript_path": transcript_path,
        "transcript_date": datetime.now().isoformat()
    })
```

## Testing

You can run the SpeechToText tests with:

```bash
# Run only speech-to-text tests
./test.sh speech

# Run all tests including speech-to-text
./test.sh all
```

The speech test mode:
1. Tests the SpeechToText component initialization
2. Tests model loading
3. Transcribes a test audio file
4. Tests the transcribe.py script
5. Verifies the quiet mode functionality
6. Saves a transcript to speech_test_transcript.txt for inspection

## Troubleshooting

### Common Issues

**Installation Problems:**
- Ensure FFmpeg is installed and in your PATH
- Make sure PyTorch is installed correctly for your system

**Performance Issues:**
- If transcription is too slow, try a smaller model
- For GPU acceleration, ensure PyTorch is installed with CUDA support

**Accuracy Issues:**
- Try specifying the language instead of auto-detection
- Use a larger model for better accuracy
- Ensure audio quality is reasonable (noise, multiple speakers, and background music can reduce accuracy)

**Memory Issues:**
- If you encounter "out of memory" errors, try a smaller model
- Close other memory-intensive applications

**Model Download Issues:**
- Ensure you have a stable internet connection for the initial model download
- Check you have sufficient disk space for the models

### Logging

The SpeechToText component uses Python's logging module. You can see more detailed logs by setting the logging level:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

In the command-line tool, use the `--verbose` flag for more information.

### Quiet Mode

When automation or scripting is needed, use the `--quiet` flag to suppress all non-essential output:

```bash
./transcribe.py audio.mp3 -o transcription.txt --quiet
```

This is particularly useful for background processes or when integrating with other systems.