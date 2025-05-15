# XSpace Downloader Components

This document provides detailed information about the key components of the XSpace Downloader application. Each component is designed with specific responsibilities and features to ensure a modular, maintainable codebase.

## Table of Contents
- [Space Component](#space-component)
- [Tag Component](#tag-component)
- [User Component](#user-component)
- [Email Component](#email-component)
- [DownloadSpace Component](#downloadspace-component)
- [SpeechToText Component](#speechtotext-component)

## Space Component

**File:** `components/Space.py`

### Purpose
The Space component is responsible for managing X Space audio data in the system. It handles the creation, retrieval, and management of space metadata, including their associated tags and user relationships.

### Features
- **Space Management**: Create, retrieve, update, and delete spaces
- **Metadata Handling**: Store and manage space metadata like title, description, and URL
- **File Management**: Track associated audio files and their locations
- **Status Tracking**: Monitor download and processing status
- **User Association**: Link spaces to specific users
- **List Functionality**: Query spaces with various filters (by user, tag, status)
- **Batch Operations**: Process multiple spaces efficiently

### Usage Example
```python
from components.Space import Space

# Initialize with database connection
space = Space(db_connection)

# Create a new space
space_id = space.create_space(
    url="https://x.com/i/spaces/1dRJZEpyjlNGB",
    title="Example X Space",
    notes="Important discussion",
    user_id=1
)

# Retrieve space information
space_info = space.get_space(space_id)

# List spaces by user
user_spaces = space.list_spaces(user_id=1)

# Update space status
space.update_space_status(space_id, "completed")
```

## Tag Component

**File:** `components/Tag.py`

### Purpose
The Tag component manages the tagging system for spaces, allowing users to categorize and organize their downloaded content. It handles tag creation, assignment, and retrieval.

### Features
- **Tag Management**: Create, retrieve, update, and delete tags
- **Space Tagging**: Assign tags to spaces and remove tags from spaces
- **Tag Queries**: Search for tags and retrieve spaces by tag
- **Popularity Tracking**: Monitor tag usage frequency
- **Validation**: Ensure tag names meet system requirements
- **Bulk Operations**: Add or remove multiple tags efficiently

### Usage Example
```python
from components.Tag import Tag

# Initialize with database connection
tag = Tag(db_connection)

# Create a new tag
tag_id = tag.create_tag("interview")

# Assign tag to a space
tag.add_tag_to_space(tag_id, space_id)

# Get spaces with a specific tag
tagged_spaces = tag.get_spaces_by_tag("interview")

# Get all tags for a space
space_tags = tag.get_tags_for_space(space_id)
```

## User Component

**File:** `components/User.py`

### Purpose
The User component handles user authentication, authorization, and profile management. It provides functionality for user registration, authentication, and managing user-specific settings and permissions.

### Features
- **User Management**: Create, retrieve, update, and delete user accounts
- **Authentication**: Validate user credentials and manage sessions
- **Profile Management**: Store and update user profile information
- **Permission Control**: Manage access rights and roles
- **Password Security**: Handle secure password storage and validation
- **User Verification**: Email verification and account activation flows
- **Quota Management**: Track and enforce usage limits

### Usage Example
```python
from components.User import User

# Initialize with database connection
user = User(db_connection)

# Create a new user
user_id = user.create_user(
    email="user@example.com",
    password="secure_password",
    username="username",
    visitor_id=None
)

# Authenticate a user
is_valid = user.validate_credentials("user@example.com", "secure_password")

# Get user information
user_info = user.get_user(user_id=user_id)

# Update user profile
user.update_user(user_id, email="new_email@example.com")
```

## Email Component

**File:** `components/Email.py`

### Purpose
The Email component handles all email communication from the application to users, including notifications, alerts, verification emails, and reports.

### Features
- **Email Sending**: Send emails using configurable email providers (SendGrid, SMTP)
- **Template Support**: Use HTML email templates for consistent messaging
- **Attachments**: Support for file attachments in emails
- **Queue Management**: Handle email sending queue for reliability
- **Delivery Tracking**: Monitor email delivery status
- **Configuration**: Flexible email provider configuration
- **Testing Mode**: Support for testing without sending actual emails

### Usage Example
```python
from components.Email import Email

# Initialize email component
email = Email()

# Send a simple email
email.send(
    to="user@example.com",
    subject="Your Space Download is Complete",
    body="Your requested X Space has been downloaded successfully."
)

# Send an email with attachment
email.send_with_attachment(
    to="user@example.com",
    subject="Your Transcription",
    body="Here is the transcription you requested.",
    attachment_path="/path/to/transcription.txt"
)

# Test email configuration
email.test()
```

## DownloadSpace Component

**File:** `components/DownloadSpace.py`

### Purpose
The DownloadSpace component is responsible for downloading X Space audio content from X (formerly Twitter). It handles the extraction of space information, downloading the audio stream, and saving it to the filesystem.

### Features
- **URL Validation**: Verify and parse X Space URLs
- **Space Info Extraction**: Extract metadata like title, host, participants
- **Audio Download**: Download audio content from X Spaces
- **Progress Tracking**: Monitor and report download progress
- **Error Handling**: Robust handling of download failures and retries
- **Format Conversion**: Support for different audio formats
- **Bandwidth Management**: Optimize download speeds and resource usage
- **Metadata Storage**: Save space metadata alongside audio files

### Usage Example
```python
from components.DownloadSpace import DownloadSpace

# Initialize the component
downloader = DownloadSpace()

# Download a space
result = downloader.download(
    space_url="https://x.com/i/spaces/1dRJZEpyjlNGB",
    output_dir="/downloads",
    filename="space_recording.mp3"
)

# Check download status
if result['success']:
    print(f"Downloaded to: {result['file_path']}")
    print(f"Space title: {result['metadata']['title']}")
else:
    print(f"Download failed: {result['error']}")
```

## SpeechToText Component

**File:** `components/SpeechToText.py`

### Purpose
The SpeechToText component converts audio recordings of X Spaces to text, providing transcriptions that can be searched, analyzed, and shared. It uses OpenAI's Whisper model for high-quality speech recognition.

### Features
- **Audio Transcription**: Convert speech in audio files to text
- **Multiple Model Support**: Choose from different Whisper model sizes (tiny, base, small, medium, large)
- **Language Detection**: Automatically detect the spoken language
- **Multiple Output Formats**: Generate transcripts in various formats (txt, json, vtt, srt)
- **Timestamp Support**: Include timestamps in transcriptions
- **Batch Processing**: Process multiple audio files efficiently
- **Subtitle Generation**: Create subtitle files for videos
- **Error Handling**: Robust error management and logging
- **Quiet Mode**: Option to suppress verbose output during processing

### Usage Example
```python
from components.SpeechToText import SpeechToText

# Initialize with desired model
stt = SpeechToText(model_name="base")

# Transcribe an audio file
transcript = stt.transcribe(
    audio_file="/downloads/space_recording.mp3",
    output_file="transcription.txt",
    output_format="txt"
)

# Generate subtitles
stt.transcribe(
    audio_file="/downloads/space_recording.mp3",
    output_file="subtitles.vtt",
    output_format="vtt"
)

# Batch processing
results = stt.batch_transcribe(
    audio_directory="/downloads/",
    output_directory="/transcripts/",
    recursive=True
)
```

## Command-Line Utilities

### transcribe.py

**File:** `transcribe.py`

#### Purpose
A command-line utility that leverages the SpeechToText component to provide an easy-to-use interface for transcribing audio files from the command line.

#### Features
- **Simple CLI Interface**: Easy command-line usage
- **Model Selection**: Choose from different Whisper model sizes
- **Format Options**: Output in various formats (txt, json, vtt, srt)
- **Batch Processing**: Process multiple files at once
- **Language Options**: Specify language or use auto-detection
- **Quiet Mode**: Suppress all non-essential output
- **Verbose Mode**: Get detailed processing information

#### Usage Example
```bash
# Basic usage
./transcribe.py path/to/audio.mp3 -o transcription.txt

# With model selection and format
./transcribe.py path/to/audio.mp3 -m medium -f vtt -o subtitles.vtt

# Batch processing
./transcribe.py path/to/audio/directory -b -o output/directory

# Quiet mode (suppress output)
./transcribe.py path/to/audio.mp3 -o transcription.txt --quiet
```

## Testing Framework

### test.sh

**File:** `test.sh`

#### Purpose
A comprehensive testing script that validates the functionality of all system components, ensuring they work correctly both individually and together.

#### Features
- **Modular Testing**: Test specific components or all components
- **Database Testing**: Verify database connectivity and schema
- **Component Tests**: Individual tests for each component
- **API Testing**: Verify API endpoints and functionality
- **Daemon Testing**: Test background processing daemon
- **Audio Processing Tests**: Validate audio manipulation features
- **Speech-to-Text Tests**: Test transcription functionality
- **Email Testing**: Verify email sending capabilities
- **Detailed Reporting**: Clear success/failure reporting
- **Test Artifacts**: Generate test outputs for verification

#### Usage Example
```bash
# Run all tests
./test.sh

# Test specific components
./test.sh api        # Test API controller
./test.sh email      # Test email sending
./test.sh core       # Test core components (Space, User, Tag)
./test.sh daemon     # Test background downloader
./test.sh audio      # Test audio processing
./test.sh speech     # Test speech-to-text conversion
```