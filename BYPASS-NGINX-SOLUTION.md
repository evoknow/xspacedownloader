# Bypass Nginx for Audio Downloads - Ultimate Fix

Since HTTP/2 errors persist even with HTTP/1.1 configuration, let's bypass Nginx entirely for audio downloads.

## Solution: Direct Flask Serving on Different Port

### 1. Create a second Flask instance for downloads only

Add this to your Flask app startup (app.py):

```python
# Add this to the end of app.py
if __name__ == '__main__':
    import threading
    
    # Create a simple download-only server on port 8081
    from flask import Flask as DownloadFlask
    download_app = DownloadFlask(__name__)
    
    # Copy only the download route to the download app
    @download_app.route('/download/<space_id>')
    def download_only(space_id):
        # Same logic as your main download route
        return download_space(space_id)
    
    # Start download server in a separate thread
    def run_download_server():
        download_app.run(host='127.0.0.1', port=8081, debug=False)
    
    download_thread = threading.Thread(target=run_download_server)
    download_thread.daemon = True
    download_thread.start()
    
    # Run main app on 8080
    app.run(host='127.0.0.1', port=8080, debug=True)
```

### 2. Update Nginx to bypass downloads entirely

```nginx
server {
    server_name xspacedownload.com;
    
    # ... your existing configuration ...
    
    # Direct pass downloads to Flask on port 8081 (bypass all proxy processing)
    location ^~ /download/ {
        proxy_pass http://127.0.0.1:8081;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_max_temp_file_size 0;
    }
    
    # Everything else goes to main Flask app on 8080
    location / {
        proxy_pass http://127.0.0.1:8080;
        # ... your existing configuration ...
    }
}
```

## Alternative: Serve Downloads Directly from Nginx

If the above is too complex, serve files directly from Nginx:

### 1. Move audio files to web-accessible directory

```bash
# Create symlinks or move files to a web directory
mkdir -p /var/www/production/xspacedowoad.com/website/htdocs/audio
ln -s /path/to/your/downloads/* /var/www/production/xspacedowoad.com/website/htdocs/audio/
```

### 2. Update Nginx to serve files directly

```nginx
# Add this location block
location ^~ /audio/ {
    alias /var/www/production/xspacedowoad.com/website/htdocs/audio/;
    
    # Perfect for media streaming
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    
    # Range request support
    add_header Accept-Ranges bytes;
    
    # MIME types
    location ~* \.(mp3)$ { add_header Content-Type audio/mpeg; }
    location ~* \.(m4a)$ { add_header Content-Type audio/mp4; }
    location ~* \.(wav)$ { add_header Content-Type audio/wav; }
    location ~* \.(mp4)$ { add_header Content-Type video/mp4; }
    
    # Cache headers
    expires 1h;
    add_header Cache-Control "public, immutable";
}
```

### 3. Update your template to point to direct files

In space.html, change:
```html
<source src="/download/{{ space.space_id }}" type="{{ content_type|default('audio/mpeg') }}">
```

To:
```html
<source src="/audio/{{ space.space_id }}.mp3" type="audio/mpeg">
```

## Recommended Approach

Try the **Direct Nginx serving** approach first - it's simpler and guarantees no HTTP/2 issues since Nginx handles everything natively.

The dual Flask server approach is more complex but maintains your authentication/authorization logic.

## Why This Works

- **No proxy involved**: Direct file serving from Nginx or direct Flask
- **No HTTP/2**: Even if HTTP/2 is enabled, range requests work better with direct serving
- **Native range support**: Nginx's built-in range handling is bulletproof
- **Better performance**: No Python in the data path for large file transfers