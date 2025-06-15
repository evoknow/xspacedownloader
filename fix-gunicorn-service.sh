#!/bin/bash

echo "=== Fixing Gunicorn Service Issue ==="

echo "1. Check if gunicorn exists in venv:"
echo "ls -la /var/www/production/xspacedownload.com/website/htdocs/venv/bin/gunicorn"

echo -e "\n2. Check if venv directory exists:"
echo "ls -la /var/www/production/xspacedownload.com/website/htdocs/venv/"

echo -e "\n3. Find where gunicorn is actually installed:"
echo "which gunicorn"
echo "find /var/www/production/xspacedownload.com/ -name gunicorn -type f 2>/dev/null"

echo -e "\n4. Check the service file:"
echo "cat /etc/systemd/system/xspacedownloader-gunicorn.service"

echo -e "\n=== Possible Fixes ==="

echo -e "\nFix A: If venv doesn't exist, create it:"
echo "cd /var/www/production/xspacedownload.com/website/htdocs"
echo "python3 -m venv venv"
echo "source venv/bin/activate"
echo "pip install gunicorn flask"

echo -e "\nFix B: If gunicorn is in system python, update service file:"
echo "Use: ExecStart=/usr/local/bin/gunicorn app:app -c gunicorn.conf.py"
echo "Or: ExecStart=/usr/bin/python3 -m gunicorn app:app -c gunicorn.conf.py"

echo -e "\nFix C: Use system python temporarily:"
echo "ExecStart=/usr/bin/python3 /var/www/production/xspacedownload.com/website/htdocs/app.py"