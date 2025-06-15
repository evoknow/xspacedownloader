# Flask Service Restart Issue - Debug & Fix

## The Issue
The update script is working (code synced successfully), but `systemctl restart xspacedownloader-gunicorn` is failing.

## Debug Steps

### 1. Check Service Status
```bash
systemctl status xspacedownloader-gunicorn.service
```

### 2. Check Service Logs
```bash
journalctl -xeu xspacedownloader-gunicorn.service --no-pager -n 50
```

### 3. Check What's Running on Port 8080
```bash
lsof -i :8080
netstat -tulpn | grep :8080
```

### 4. Try Manual Start
```bash
# Stop the service
systemctl stop xspacedownloader-gunicorn

# Try starting manually to see errors
sudo -u nginx python3 /var/www/production/xspacedownload.com/website/htdocs/app.py
```

## Common Fixes

### Fix 1: Kill Existing Process
```bash
# Find and kill any existing Python processes
pkill -f "python.*app.py"
pkill -f gunicorn

# Then restart
systemctl start xspacedownloader-gunicorn
```

### Fix 2: Check Service Configuration
```bash
# Check if service file exists and is correct
cat /etc/systemd/system/xspacedownloader-gunicorn.service

# Reload systemd if service file was changed
systemctl daemon-reload
systemctl restart xspacedownloader-gunicorn
```

### Fix 3: Check File Permissions
```bash
# Ensure nginx user can access all files
chown -R nginx:nginx /var/www/production/xspacedownload.com/
chmod +x /var/www/production/xspacedownload.com/website/htdocs/app.py
```

### Fix 4: Check Python Environment
```bash
# Test if app.py can be imported
sudo -u nginx python3 -c "import sys; sys.path.insert(0, '/var/www/production/xspacedownload.com/website/htdocs'); import app; print('App imported successfully')"
```

## Quick Fix Commands

Run these in order:

```bash
# 1. Stop everything
systemctl stop xspacedownloader-gunicorn
pkill -f "python.*app.py"
pkill -f gunicorn

# 2. Check what's using port 8080
lsof -i :8080

# 3. Force kill if needed
kill -9 $(lsof -t -i :8080)

# 4. Fix permissions
chown -R nginx:nginx /var/www/production/xspacedownload.com/

# 5. Reload systemd and restart
systemctl daemon-reload
systemctl start xspacedownloader-gunicorn
systemctl status xspacedownloader-gunicorn
```

## Test the Audio Fix Meanwhile

Even with the Flask service issue, you can test if the Chrome audio fix is working:

1. **Test direct audio URL:** https://xspacedownload.com/audio/1lDxLnrWjwkGm.mp3
2. **Add Connection: close to Nginx** (if not already done):

```bash
# Edit Nginx config
sudo nano /etc/nginx/sites-available/xspacedownload.com.conf

# In the /audio/ location, add:
add_header Connection "close" always;
keepalive_timeout 0;

# Reload Nginx
sudo nginx -t && sudo systemctl reload nginx
```

The audio streaming fix is independent of the Flask service restart issue!