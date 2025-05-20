# XSpace Downloader

A tool for downloading and managing X (formerly Twitter) Spaces audio content.

## Components

### Space Component
Handles CRUD operations for spaces using space_id as unique identifier.

### Email Component
Handles email operations using configurable email providers (SendGrid, Mailgun, SMTP).

### DownloadSpace Component
Handles downloading X space audio using yt-dlp with progress tracking.

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

# Download as WAV
job_id = downloader.download("https://x.com/i/spaces/1dRJZEpyjlNGB", file_type="wav")

# Check download status
status = downloader.get_download_status(job_id)

# Cancel download
downloader.cancel_download(job_id)

# List all downloads
jobs = downloader.list_downloads()
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