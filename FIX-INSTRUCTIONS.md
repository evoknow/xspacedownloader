# IMMEDIATE FIX INSTRUCTIONS

## The Error
`nginx: [emerg] invalid parameter "off"` means your Nginx version doesn't support `http2 off`.

## The Solution

### 1. Keep your listen line as is:
```nginx
listen 443 ssl; # NO 'http2' and NO 'http2 off'
```

### 2. Add the /audio/ location block to your config:

Edit `/etc/nginx/sites-available/xspacedownload.com.conf` and add this **BEFORE** your `location /` block:

```nginx
# Direct audio serving - bypasses all proxy/HTTP2 issues
location ^~ /audio/ {
    alias /var/www/production/xspacedownload.com/website/htdocs/downloads/;
    
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    gzip off;
    
    # Enable range requests
    add_header Accept-Ranges bytes always;
    
    # Set MIME types
    location ~* \.mp3$ { 
        add_header Content-Type audio/mpeg always;
        add_header Accept-Ranges bytes always;
    }
    location ~* \.m4a$ { 
        add_header Content-Type audio/mp4 always; 
        add_header Accept-Ranges bytes always;
    }
    location ~* \.wav$ { 
        add_header Content-Type audio/wav always;
        add_header Accept-Ranges bytes always;
    }
    location ~* \.mp4$ { 
        add_header Content-Type video/mp4 always;
        add_header Accept-Ranges bytes always;
    }
    
    expires 1h;
    add_header Cache-Control "public, max-age=3600" always;
}
```

### 3. Test and reload:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 4. Verify the /audio/ endpoint works:
```bash
# Test if the file is accessible
curl -I https://xspacedownload.com/audio/1lDxLnrWjwkGm.mp3

# You should see:
# HTTP/1.1 200 OK
# Accept-Ranges: bytes
# Content-Type: audio/mpeg
```

## Why This Works

- The `/audio/` location serves files **directly from disk**
- No Flask proxy involved = No HTTP/2 protocol issues
- Nginx's native file serving handles range requests perfectly
- Even if HTTP/2 is enabled globally, direct file serving works fine

## If You Still Get HTTP/2 Errors

Check if you have HTTP/2 enabled globally:

```bash
# Check main nginx config
grep -i "http2" /etc/nginx/nginx.conf

# Check if any other includes have http2
grep -r "http2" /etc/nginx/
```

If you find global HTTP/2 settings, you may need to comment them out or consider using a different approach like serving audio from a subdomain without HTTP/2.