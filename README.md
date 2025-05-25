# XSpace Downloader

A tool for downloading and managing X (formerly Twitter) Spaces audio content.

## Components

### Space Component
Handles CRUD operations for spaces using space_id as unique identifier.

### Email Component
Handles email operations using configurable email providers (SendGrid, Mailgun, SMTP).

### DownloadSpace Component
Handles downloading X space audio using yt-dlp with progress tracking.

### SpeechToText Component
Handles transcription of audio files using Whisper with progress tracking.

### Translate Component
Handles translation of text between languages using AI providers (OpenAI or Claude).

## Installation

1. Clone this repository
2. Run the setup script:
   ```bash
   ./setup.sh
   ```
   This will:
   - Create a virtual environment
   - Install dependencies
   - Create necessary directories
   - Create a sample db_config.json file
   - Make scripts executable

3. Configure the database (see Database Configuration below)

## Database Configuration

Create a `db_config.json` file with your MySQL connection details:

```json
{
    "type": "mysql",
    "mysql": {
        "host": "your-mysql-host",
        "port": 3306,
        "database": "xspacedownloader",
        "user": "your-mysql-user",
        "password": "your-mysql-password",
        "use_ssl": false
    }
}
```

## Translation Configuration

Translation uses the same AI provider configuration as transcription. Configure in `mainconfig.json`:

```json
{
    "translate": {
        "enable": true,
        "provider": "openai",  // or "claude"
        "openai": {
            "api_key": "your-openai-api-key",
            "model": "gpt-4o"
        },
        "claude": {
            "api_key": "your-anthropic-api-key",
            "model": "claude-3-sonnet-20240229"
        }
    }
}
```

You can use either:

1. **OpenAI**:
   - Get an API key from [OpenAI Platform](https://platform.openai.com/)
   - Add the API key to the `openai.api_key` field

2. **Claude**:
   - Get an API key from [Anthropic Console](https://console.anthropic.com/)
   - Add the API key to the `claude.api_key` field

## Usage

### Web Interface

The XSpace Downloader now includes a web interface that allows users to submit space URLs for download through a simple form. The downloads are processed by the background downloader daemon.

To run the web interface and background downloader:

```bash
./run.sh
```

This will start:
1. The Flask web app on http://127.0.0.1:5000
2. The background downloader daemon in foreground mode

You can then access the web interface by opening http://127.0.0.1:5000 in your browser.

### Downloaded File Format

**IMPORTANT**: All downloaded files are automatically converted to MP3 format, regardless of the original format from the source. This ensures compatibility with most audio players and standardizes the output format. Even if you specify a different format when downloading, the system will ensure the final output is converted to MP3.

### Command-Line Tools

The following command-line tools are available for easy use:

1. Download an X Space:
   ```bash
   ./test_download.py https://x.com/i/spaces/1dRJZEpyjlNGB [mp3|wav]
   ```

2. Monitor download progress for a specific job or space:
   ```bash
   ./monitor_download.py 1              # Monitor job ID 1
   ./monitor_download.py 1dRJZEpyjlNGB  # Monitor latest job for space ID
   ```

3. List all download jobs:
   ```bash
   ./list_downloads.py
   ```

4. Fix stuck download jobs:
   ```bash
   ./fix_jobs.py
   ```

5. Test direct synchronous download:
   ```bash
   ./test_sync_download.py https://x.com/i/spaces/1dRJZEpyjlNGB
   ```

### API Usage

#### Downloading X Spaces

```python
from components.DownloadSpace import DownloadSpace

# Create downloader instance
downloader = DownloadSpace()

# Asynchronous download (default)
job_id = downloader.download("https://x.com/i/spaces/1dRJZEpyjlNGB")

# Synchronous download
file_path = downloader.download("https://x.com/i/spaces/1dRJZEpyjlNGB", async_mode=False)

# Note: Even if you specify a different file type, the final output will always be MP3
# The file_type parameter is mainly for compatibility with older code
job_id = downloader.download("https://x.com/i/spaces/1dRJZEpyjlNGB", file_type="wav")

# Check download status
status = downloader.get_download_status(job_id)

# Cancel download
downloader.cancel_download(job_id)

# List all downloads
jobs = downloader.list_downloads()
```

#### Speech-to-Text Transcription

```python
from components.SpeechToText import SpeechToText

# Create transcriber instance
transcriber = SpeechToText()

# Transcribe audio file
job_id = transcriber.transcribe("/path/to/audio.mp3")

# Check transcription status
status = transcriber.get_transcription_status(job_id)

# Get transcript
success, transcript = transcriber.get_transcript(job_id)
```

#### Translation

```python
from components.Translate import Translate

# Create translator instance
translator = Translate()

# Get available languages
languages = translator.get_languages()
print(languages)  # [{"code": "en", "name": "English"}, ...]

# Translate text
success, result = translator.translate(
    text="Hello, how are you?",
    source_lang="en",
    target_lang="es"
)

if success:
    print(f"Translation: {result}")
else:
    print(f"Error: {result['error']}")

# Detect language
success, lang_code = translator.detect_language("Bonjour, comment allez-vous?")
if success:
    print(f"Detected language: {lang_code}")  # "fr"
```

#### Sending Emails

```python
from components.Email import Email

# Create email instance
email = Email()

# Send a test email to configured testers
email.test()

# Send email to specific recipient
email.send(
    to="user@example.com",
    subject="Hello from XSpace",
    body="<h1>Welcome</h1><p>This is an HTML email</p>"
)
```

## Web Interface

The web interface provides a simple way to submit space URLs for download. Features include:

- Submit X space URL for background download
- Check download status and progress
- View queue status (active and pending downloads)
- Real-time status updates
- Speech-to-text transcription and viewing
- Translate transcripts between multiple languages
- Multi-language support for transcriptions

## Testing

Run the automated tests:

```bash
./test.sh
```

Run tests including real email sending:

```bash
./test_with_emails.sh
```

Test the download component:

```bash
./test_download.py https://x.com/i/spaces/1dRJZEpyjlNGB
```

## Database Schema

### spaces
Table to store space metadata and download status.

### space_download_scheduler
Table to track Space audio download progress:

- `id`: Primary key
- `space_id`: Space ID extracted from the URL
- `user_id`: User ID who initiated the download
- `start_time`: Time when download started
- `end_time`: Time when download completed (NULL if in progress)
- `file_type`: Output file type (mp3, wav, etc)
- `progress_in_size`: Download progress in MB
- `progress_in_percent`: Download progress as percentage (0-100)
- `process_id`: Process ID of the forked process
- `status`: Current status of the download (pending, in_progress, completed, failed)
- `error_message`: Error message if download failed

### email_config
Table to store email provider configuration:

- `id`: Primary key
- `provider`: Email provider name (sendgrid, mailgun, default-smtp)
- `api_key`: API key for SendGrid or Mailgun
- `from_email`: From email address
- `from_name`: From name
- `server`: SMTP server (for default-smtp)
- `port`: SMTP port (for default-smtp)
- `username`: SMTP username (for default-smtp)
- `password`: SMTP password (for default-smtp)
- `use_tls`: Whether to use TLS for SMTP
- `status`: Status (0=disabled, 1=enabled)
- `templates`: JSON field for email templates
- `testers`: JSON field for email testers

## File Format Conversion

The system now ensures all downloaded files are in MP3 format. If you have existing non-MP3 files (like .m4a or .wav) that need to be converted, use the `convert_to_mp3.py` script:

```bash
./convert_to_mp3.py
```

This script will:
1. Scan the downloads directory for any non-MP3 audio files (m4a, wav)
2. Convert each file to MP3 format using FFmpeg
3. Remove the original non-MP3 file after successful conversion
4. Update database records to reflect the new MP3 file

Example output:
```
2025-05-20 14:10:55,123 - convert_to_mp3 - INFO - Starting conversion of all non-MP3 files to MP3 format
2025-05-20 14:10:55,124 - convert_to_mp3 - INFO - Scanning directory: /path/to/downloads
2025-05-20 14:10:55,125 - convert_to_mp3 - INFO - Found 3 non-MP3 files to convert: 2 m4a, 1 wav
2025-05-20 14:10:55,126 - convert_to_mp3 - INFO - Converting /path/to/downloads/1YpKkgVgMQAKj.m4a to MP3...
2025-05-20 14:10:55,127 - convert_to_mp3 - INFO - Running: ffmpeg -y -i /path/to/downloads/1YpKkgVgMQAKj.m4a -acodec libmp3lame -q:a 2 /path/to/downloads/1YpKkgVgMQAKj.mp3
2025-05-20 14:11:05,128 - convert_to_mp3 - INFO - Successfully converted to MP3: /path/to/downloads/1YpKkgVgMQAKj.mp3 (64574123 bytes)
2025-05-20 14:11:05,129 - convert_to_mp3 - INFO - Removing original file: /path/to/downloads/1YpKkgVgMQAKj.m4a
2025-05-20 14:11:06,130 - convert_to_mp3 - INFO - Conversion complete.
```

## Troubleshooting

### yt-dlp Missing
If you see an error like "No such file or directory: 'yt-dlp'", the yt-dlp utility is missing. Fix it by:

1. Install yt-dlp:
   ```bash
   pip install yt-dlp
   ```

2. Reset the failed job(s):
   ```bash
   ./fix_jobs.py
   ```
   
3. Restart the background downloader:
   ```bash
   ./run.sh
   ```

Alternatively, use the setup script to check and install all dependencies:
```bash
./setup.sh
```

### Empty Log File
If the download job completes but the log file is empty, it might be due to a permissions issue with the downloads directory or the forked process not being able to write to the log file. Try running `fix_jobs.py` to fix stuck jobs.

### Process Not Updating Database
If the download process completes but the database isn't updated, use `monitor_download.py` to check the job status and fix it if needed.

### Multiple Download Attempts
If you have multiple downloaded files with the same space_id, check the job status with `list_downloads.py` to see which job is associated with which file.

### Web Interface Issues
If the web interface shows "Failed to schedule the download", check:
1. The database connection settings in `db_config.json`
2. The logs in `webapp.log` for error details
3. Ensure the URL follows the correct format (https://x.com/i/spaces/ID)