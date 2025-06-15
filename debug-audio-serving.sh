#!/bin/bash

echo "=== Debugging Audio Serving Issues ==="

echo -e "\n1. Check if the audio files exist:"
echo "Run: ls -la /var/www/production/xspacedownload.com/website/htdocs/downloads/*.mp3"

echo -e "\n2. Check file permissions:"
echo "Run: ls -la /var/www/production/xspacedownload.com/website/htdocs/downloads/1lDxLnrWjwkGm.mp3"

echo -e "\n3. Test if Nginx can access the file:"
echo "Run: sudo -u www-data stat /var/www/production/xspacedownload.com/website/htdocs/downloads/1lDxLnrWjwkGm.mp3"

echo -e "\n4. Check Nginx error logs:"
echo "Run: sudo tail -50 /var/www/production/logs/nginx/xspacedownload.com.log"
echo "Or: sudo tail -50 /var/log/nginx/error.log"

echo -e "\n5. Test the /audio/ endpoint directly:"
echo "Run: curl -I https://xspacedownload.com/audio/1lDxLnrWjwkGm.mp3"

echo -e "\n6. Check if the /audio/ location is being matched:"
echo "Add this to your /audio/ location block temporarily:"
cat << 'EOF'
location ^~ /audio/ {
    # Add this for debugging:
    add_header X-Debug-Audio "Audio location matched" always;
    
    alias /var/www/production/xspacedownload.com/website/htdocs/downloads/;
    # ... rest of your config
}
EOF

echo -e "\n7. Alternative - try a simpler configuration first:"
cat << 'EOF'
location ^~ /audio/ {
    alias /var/www/production/xspacedownload.com/website/htdocs/downloads/;
    try_files $uri =404;
}
EOF

echo -e "\n8. Verify the full path is correct:"
echo "The request /audio/1lDxLnrWjwkGm.mp3"
echo "Should map to: /var/www/production/xspacedownload.com/website/htdocs/downloads/1lDxLnrWjwkGm.mp3"
echo "Make sure there's no typo in 'xspacedownload.com' (missing 'nl'?)"