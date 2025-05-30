# Background Progress Watcher

The Background Progress Watcher is a separate service that monitors download progress by watching `.part` files and updating the database with file sizes.

## Overview

The progress watcher runs independently from the main application and bg_downloader. Its sole purpose is to:
- Monitor the downloads directory for `.part` files
- Track file size changes
- Update the `progress_in_size` field in the `space_download_scheduler` table every 10 seconds

## Why a Separate Watcher?

- **Decoupled Architecture**: Keeps progress tracking separate from download logic
- **Reliability**: Continues tracking even if bg_downloader restarts
- **Performance**: Lightweight process with minimal resource usage
- **Flexibility**: Can monitor downloads from multiple sources

## Supported File Formats

The watcher monitors for these part file patterns:
- `*.part` - Generic part files
- `*.m4a.part` - Audio downloads (common for Twitter/X spaces)
- `*.mp4.part` - Video downloads
- `*.mp3.part` - MP3 conversions
- `*.webm.part` - WebM format

## Usage

### Starting the Watcher

```bash
./run_progress_watcher.sh
```

### Stopping the Watcher

```bash
./stop_progress_watcher.sh
```

### Checking Status

```bash
# Check if running
ps aux | grep bg_progress_watcher

# View logs
tail -f logs/bg_progress_watcher.log
```

## Integration

The progress watcher is automatically started when you run:
- `./run.sh` - Starts all services including the watcher
- `./restart.sh` - Restarts all services including the watcher

## Database Updates

The watcher updates the `space_download_scheduler` table:
- Only updates jobs with status: `pending`, `in_progress`, or `downloading`
- Updates `progress_in_size` field with current file size in bytes
- Updates `updated_at` timestamp

## Configuration

The watcher reads configuration from:
- `db_config.json` - Database connection settings
- `mainconfig.json` - Download directory location (optional)

Default settings:
- Update interval: 10 seconds
- Download directory: `downloads/`
- Log file: `logs/bg_progress_watcher.log`

## Systemd Service (Optional)

For production deployments, you can run as a systemd service:

1. Copy and edit the service file:
```bash
sudo cp bg_progress_watcher.service /etc/systemd/system/
sudo nano /etc/systemd/system/bg_progress_watcher.service
```

2. Update paths and user in the service file

3. Enable and start:
```bash
sudo systemctl enable bg_progress_watcher
sudo systemctl start bg_progress_watcher
```

## Troubleshooting

### Watcher Not Starting
- Check if already running: `cat logs/bg_progress_watcher.pid`
- Check logs: `tail logs/bg_progress_watcher.err`
- Verify database connection in `db_config.json`

### Not Updating Progress
- Verify `.part` files exist in downloads directory
- Check if jobs have correct status in database
- Look for errors in `logs/bg_progress_watcher.log`

### High CPU Usage
- Normal operation uses minimal CPU (<1%)
- If high, check log file size and rotate if needed
- Verify no infinite loops in error conditions

## Technical Details

- Written in Python 3
- Uses mysql.connector for database operations
- Implements graceful shutdown on SIGTERM/SIGINT
- PID file prevents multiple instances
- Automatically reconnects on database errors