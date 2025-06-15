#!/bin/bash

# Quick fix for HTTP/2 audio streaming errors

echo "Step 1: Checking current Nginx config..."
sudo nginx -t

echo -e "\nStep 2: Adding /audio/ location to your Nginx config..."
echo "Add this to your server block in /etc/nginx/sites-available/xspacedownload.com.conf"
echo "======================================================================"
cat << 'EOF'

    # ADD THIS BLOCK before your location / block:
    location ^~ /audio/ {
        alias /var/www/production/xspacedownload.com/website/htdocs/downloads/;
        
        sendfile on;
        tcp_nopush on;
        tcp_nodelay on;
        gzip off;
        
        add_header Accept-Ranges bytes always;
        
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

EOF
echo "======================================================================"

echo -e "\nStep 3: CRITICAL - Change your listen directive:"
echo "Find this line:"
echo "    listen 443 ssl;"
echo "Change it to:"
echo "    listen 443 ssl http2 off;"

echo -e "\nStep 4: After making changes, run:"
echo "sudo nginx -t && sudo systemctl reload nginx"

echo -e "\nStep 5: Test the audio endpoint:"
echo "curl -I https://xspacedownload.com/audio/1lDxLnrWjwkGm.mp3"

echo -e "\nStep 6: Check if HTTP/1.1 is being used:"
echo "curl -I -v https://xspacedownload.com/audio/1lDxLnrWjwkGm.mp3 2>&1 | grep 'HTTP/'"