#!/bin/bash

echo "=== Debugging Flask Service Restart Issue ==="

echo -e "\n1. Check service status:"
echo "systemctl status xspacedownloader-gunicorn"

echo -e "\n2. Check detailed logs:"
echo "journalctl -xeu xspacedownloader-gunicorn.service --no-pager -n 50"

echo -e "\n3. Check if there are any Python errors:"
echo "journalctl -u xspacedownloader-gunicorn.service --no-pager -n 20 | grep -i error"

echo -e "\n4. Try starting manually to see errors:"
echo "sudo -u nginx python3 /var/www/production/xspacedownload.com/website/htdocs/app.py"

echo -e "\n5. Check if there are any file permission issues:"
echo "ls -la /var/www/production/xspacedownload.com/website/htdocs/app.py"

echo -e "\n6. Restart the service and check immediately:"
echo "systemctl restart xspacedownloader-gunicorn && systemctl status xspacedownloader-gunicorn"

echo -e "\n=== Common Issues and Fixes ==="

echo -e "\nIssue 1: Python import errors"
echo "Solution: Check if all required packages are installed"
echo "Command: pip3 list | grep flask"

echo -e "\nIssue 2: Permission errors"
echo "Solution: Ensure nginx user can read all files"
echo "Command: chown -R nginx:nginx /var/www/production/xspacedownload.com/"

echo -e "\nIssue 3: Port already in use"
echo "Solution: Check if another process is using the port"
echo "Command: lsof -i :8080"

echo -e "\nIssue 4: Configuration file errors"
echo "Solution: Check gunicorn config syntax"
echo "Command: python3 -c \"import gunicorn.conf; print('Config OK')\""