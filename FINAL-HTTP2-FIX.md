# FINAL HTTP/2 Fix - Complete Solution

## Step 1: Check Global Nginx HTTP/2 Settings

```bash
# Check your main nginx.conf for global HTTP/2 settings
grep -r "http2" /etc/nginx/

# If you find http2_max_field_size, http2_max_header_size, etc. in nginx.conf, comment them out
```

## Step 2: Force HTTP/1.1 in Your Site Config

Replace your entire `/etc/nginx/sites-available/xspacedownload.com.conf` with this:

```nginx
server {
    server_name xspacedownload.com;

    # Explicitly disable HTTP/2 (this overrides any global settings)
    listen 443 ssl http2 off;  # Force HTTP/1.1
    
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;

    root /var/www/production/xspacedownload.com/website/htdocs;

    access_log /var/www/production/logs/nginx/xspacedownload.com.log;
    error_log /var/www/production/logs/nginx/xspacedownload.com.log;
    include /etc/nginx/security.conf;

    error_page 404 /404;
    error_page 403 /404;

    # Direct audio serving - NO HTTP/2, NO proxy
    location ^~ /audio/ {
        alias /var/www/production/xspacedownload.com/website/htdocs/downloads/;
        
        # Force HTTP/1.1 for this location
        http2 off;
        
        sendfile on;
        tcp_nopush on;
        tcp_nodelay on;
        gzip off;
        
        # Range request support
        add_header Accept-Ranges bytes always;
        
        # MIME types
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

    # Downloads (Flask with auth)
    location ^~ /download/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_set_header Upgrade "";
        proxy_set_header Connection "close";
        
        proxy_buffering off;
        proxy_request_buffering off;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
        
        proxy_redirect off;
    }

    # Main Flask app
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;

        proxy_connect_timeout 600;
        proxy_send_timeout 600;
        proxy_read_timeout 600;
        send_timeout 600;
    }

    # Static files
    location /static {
        alias /var/www/production/xspacedownload.com/website/htdocs/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    client_max_body_size 500M;

    # SSL configuration
    ssl_certificate /etc/letsencrypt/live/xspacedownload.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/xspacedownload.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}

server {
    if ($host = xspacedownload.com) {
        return 301 https://$host$request_uri;
    }

    server_name xspacedownload.com;
    listen 80;
    return 404;
}
```

## Step 3: Alternative - Disable HTTP/2 Globally

If the above doesn't work, disable HTTP/2 globally:

```bash
# Edit main nginx config
sudo nano /etc/nginx/nginx.conf

# Add this in the http block:
http {
    # Disable HTTP/2 globally
    http2 off;
    
    # ... rest of your config
}
```

## Step 4: Check File Permissions

Make sure Nginx can access the files:

```bash
# Check permissions
ls -la /var/www/production/xspacedownload.com/website/htdocs/downloads/

# Fix if needed
sudo chown -R www-data:www-data /var/www/production/xspacedownload.com/website/htdocs/downloads/
sudo chmod -R 644 /var/www/production/xspacedownload.com/website/htdocs/downloads/*.mp3
```

## Step 5: Test Configuration

```bash
# Test config
sudo nginx -t

# Reload
sudo systemctl reload nginx

# Check if the /audio/ endpoint works
curl -I https://xspacedownload.com/audio/1lDxLnrWjwkGm.mp3
```

## Step 6: Verify No HTTP/2

```bash
# Check what protocol is being used
curl -I -v https://xspacedownload.com/audio/1lDxLnrWjwkGm.mp3 2>&1 | grep -i "HTTP/"
```

You should see `HTTP/1.1` not `HTTP/2`.

## Nuclear Option: Recompile Nginx Without HTTP/2

If nothing works, the nuclear option is to use a version of Nginx compiled without HTTP/2 support entirely.

```bash
# Check if your nginx was compiled with HTTP/2
nginx -V 2>&1 | grep -o with-http_v2_module

# If it shows "with-http_v2_module", HTTP/2 is compiled in
```