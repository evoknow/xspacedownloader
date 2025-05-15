# Speech-to-Text Component for XSpace Downloader

This component allows you to convert audio files from downloaded X Spaces into text transcriptions using OpenAI's Whisper model.

## Features

- Transcribe MP3 files to text using Whisper AI
- Multiple model sizes to choose from (tiny, base, small, medium, large)
- Multiple output formats (plain text, JSON, VTT, SRT)
- Language detection and support for 90+ languages
- Batch processing capability for multiple files
- Translation to English capability

## Requirements

- Python 3.6+
- OpenAI Whisper library (`pip install git+https://github.com/openai/whisper.git`)
- FFmpeg (required for audio processing)

## Installation

The SpeechToText component is included in the XSpace Downloader project. Before using it, make sure you have the required dependencies:

```bash
# Install Whisper
pip install git+https://github.com/openai/whisper.git

# Install FFmpeg (macOS)
brew install ffmpeg

# Install FFmpeg (Ubuntu/Debian)
sudo apt update && sudo apt install ffmpeg
```

## Usage Examples

### Command Line Interface

The `transcribe.py` script provides a convenient way to transcribe audio files:

```bash
# Basic usage (outputs to console)
./transcribe.py downloads/space_123456.mp3

# Save to a file
./transcribe.py downloads/space_123456.mp3 -o transcription.txt

# Use a different model
./transcribe.py downloads/space_123456.mp3 -m small

# Generate subtitles
./transcribe.py downloads/space_123456.mp3 -f vtt -o subtitles.vtt

# Specify language (if known)
./transcribe.py downloads/space_123456.mp3 -l en

# Translate to English
./transcribe.py downloads/space_123456.mp3 -t translate

# Batch process a directory
./transcribe.py downloads/ -b -o transcriptions/
```

### Programmatic Usage

You can also use the SpeechToText component directly in your Python code:

```python
from components.SpeechToText import SpeechToText

# Initialize with default model (base)
stt = SpeechToText()

# Or specify a model
# stt = SpeechToText(model_name='small')

# Simple transcription
text = stt.transcribe('path/to/audio.mp3')
print(text)

# Save to a file
stt.transcribe('path/to/audio.mp3', output_file='transcription.txt')

# Get detailed results including timestamps
result = stt.transcribe('path/to/audio.mp3', output_format='json')
for segment in result['segments']:
    start_time = segment['start']
    end_time = segment['end']
    segment_text = segment['text']
    print(f"{start_time:.2f} - {end_time:.2f}: {segment_text}")

# Batch processing
results = stt.batch_transcribe('downloads/', output_directory='transcriptions/')
```

## Model Selection Guide

Whisper offers different model sizes with various trade-offs between accuracy and speed:

- **tiny**: Fastest option, but least accurate. Good for testing and when basic transcription is sufficient.
- **base**: Great balance of speed and accuracy for general use.
- **small**: More accurate than base but slower. Good for clear audio.
- **medium**: Highly accurate but significantly slower. Recommended for difficult audio.
- **large**: Most accurate but slowest and requires the most memory. Best for mission-critical transcriptions.

## Integration with Space Component

The SpeechToText component can be integrated with the Space component for automatic transcription:

```python
from components.Space import Space
from components.SpeechToText import SpeechToText

# Initialize components
space = Space()
stt = SpeechToText()

# Get a space from the database
space_id = "1dRJZEpyjlNGB"
space_details = space.get_space(space_id)

# Get audio file path for the space
audio_file = space._get_audio_file_path(space_id)

# Transcribe the audio
if audio_file:
    transcription = stt.transcribe(audio_file)
    
    # Save transcription to a file
    with open(f"transcripts/{space_id}.txt", "w") as f:
        f.write(transcription)
```

## Testing

You can run the SpeechToText tests with:

```bash
# Run only speech-to-text tests
./test.sh speech

# Run all tests including speech-to-text
./test.sh all
```

## Troubleshooting

- **"ffmpeg not found"**: Make sure FFmpeg is installed and in your system PATH.
- **Memory errors**: If you encounter memory issues, try using a smaller model (tiny or base).
- **Slow transcription**: Transcription speed depends on the model size, your hardware, and the audio length. Consider using a smaller model or upgrading hardware.
- **Inaccurate transcriptions**: Try a larger model or specify the language explicitly.