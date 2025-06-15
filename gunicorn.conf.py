# Gunicorn configuration for production deployment

import multiprocessing
import os

# Server socket
bind = "127.0.0.1:8080"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 600  # 10 minutes for long-running downloads
keepalive = 2

# Restart workers after this many requests, to help prevent memory leaks
max_requests = 1000
max_requests_jitter = 100

# Logging
accesslog = "/var/www/production/xspacedownload.com/website/htdocs/logs/gunicorn-access.log"
errorlog = "/var/www/production/xspacedownload.com/website/htdocs/logs/gunicorn-error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'xspacedownloader'

# Server mechanics
daemon = False
pidfile = "/var/www/production/xspacedownload.com/website/htdocs/gunicorn.pid"
user = "nginx"
group = "nginx"
tmp_upload_dir = None

# SSL (if not using nginx for SSL termination)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

# Environment variables
raw_env = [
    "PYTHONPATH=/var/www/production/xspacedownload.com/website/htdocs",
]

# Preload application for better memory usage
preload_app = True

# Enable automatic worker restarts if memory usage exceeds limit
# Requires python-prctl package
# limit_request_line = 4094
# limit_request_fields = 100
# limit_request_field_size = 8190