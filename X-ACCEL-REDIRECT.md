# X-Accel-Redirect Implementation for Audio Streaming

## Overview

This implementation uses Nginx's X-Accel-Redirect feature to handle audio/video streaming, which solves HTTP/2 protocol errors when seeking in media files.

## How It Works

1. **Client Request**: Browser/Plyr requests `/download/<space_id>`
2. **Flask Processing**: Flask validates the request and locates the file
3. **X-Accel-Redirect**: Flask returns headers telling Nginx to serve the file
4. **Nginx Serving**: Nginx handles the actual file serving with proper byte-range support

## Benefits

- ✅ Eliminates `net::ERR_HTTP2_PROTOCOL_ERROR` when seeking
- ✅ Nginx handles all byte-range requests natively
- ✅ Better performance (no Python in the data path)
- ✅ Proper HTTP/2 framing
- ✅ Instant seeking in large files

## Configuration Steps

### 1. Update Nginx Configuration

Add the internal location block from `nginx-xaccel-config.conf` to your server block:

```nginx
server {
    listen 443 ssl http2;
    server_name xspacedownload.com;
    
    # ... existing configuration ...
    
    # Add this internal location
    location /downloads/ {
        internal;
        alias /var/www/production/xspacedownload.com/website/htdocs/downloads/;
        # ... see nginx-xaccel-config.conf for full configuration
    }
    
    # Keep your existing Flask proxy
    location / {
        proxy_pass http://127.0.0.1:8080;
        # ... existing proxy configuration ...
    }
}
```

### 2. Remove Conflicting Configuration

Remove any existing `/download/` location blocks that proxy to Flask:

```nginx
# REMOVE THIS if it exists:
# location /download/ {
#     proxy_pass http://127.0.0.1:8080;
#     ...
# }
```

### 3. Reload Nginx

```bash
sudo nginx -t  # Test configuration
sudo systemctl reload nginx  # or: sudo service nginx reload
```

### 4. Restart Flask Application

The Flask app now uses X-Accel-Redirect headers instead of streaming files directly.

## How Flask Uses X-Accel-Redirect

```python
# Instead of send_file(), Flask returns:
response = Response()
response.headers['X-Accel-Redirect'] = '/downloads/filename.mp3'
response.headers['Content-Type'] = 'audio/mpeg'
response.headers['Content-Disposition'] = 'inline; filename="filename.mp3"'
return response
```

## Troubleshooting

1. **404 Errors**: Check that the alias path in Nginx matches your actual downloads directory
2. **403 Forbidden**: Ensure Nginx has read permissions on the downloads directory
3. **Still Getting Protocol Errors**: Make sure old `/download/` proxy blocks are removed
4. **Files Download Instead of Stream**: Check Content-Disposition header is set to 'inline'

## Security Notes

- The `/downloads/` location is marked as `internal` - it cannot be accessed directly
- Only accessible via X-Accel-Redirect from your Flask app
- Flask still controls authentication and authorization before serving files