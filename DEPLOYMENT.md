# XSpace Downloader - Production Deployment Guide

This guide will help you deploy XSpace Downloader on a production server running Ubuntu/Debian with nginx.

## Quick Deploy

Use the automated deployment script for quick setup:

```bash
sudo python3 deploy.py --nginx-user=www-data \
                      --production-dir=/var/www/xspacedownloader \
                      --nginx-etc-dir=/etc/nginx \
                      --domain=your-domain.com
```

For different server configurations:
- **CentOS/RHEL**: Use `--nginx-user=nginx`
- **Custom paths**: Adjust `--production-dir` and `--nginx-etc-dir` as needed
- **Dry run**: Add `--dry-run` to see what would be done

## Prerequisites

- Ubuntu 20.04+ or Debian 10+ server
- Root or sudo access
- Domain name pointed to your server (optional but recommended)
- MySQL 5.7+ or MariaDB 10.3+
- Python 3.8+
- nginx
- Git

## Step 1: Initial Server Setup

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install required system packages
sudo apt install -y python3-pip python3-venv python3-dev \
    mysql-server nginx git ffmpeg \
    build-essential libssl-dev libffi-dev \
    python3-setuptools

# Create application user
sudo useradd -m -s /bin/bash xspace
```

## Step 2: Setup MySQL Database

```bash
# Secure MySQL installation
sudo mysql_secure_installation

# Login to MySQL
sudo mysql -u root -p

# Create database and user
CREATE DATABASE xspacedownloader CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'xspace'@'localhost' IDENTIFIED BY 'your_secure_password';
GRANT ALL PRIVILEGES ON xspacedownloader.* TO 'xspace'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

## Step 3: Clone and Setup Application

```bash
# Create application directory
sudo mkdir -p /var/www/xspacedownloader
sudo chown -R www-data:www-data /var/www/xspacedownloader

# Switch to www-data user
sudo -u www-data bash

# Clone the repository
cd /var/www
git clone https://github.com/evoknow/xspacedownloader.git

# Navigate to project directory
cd xspacedownloader

# Create Python virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install requirements
pip install -r requirements.txt

# Install additional production dependencies
pip install gunicorn

# Create necessary directories
mkdir -p logs downloads transcript_jobs

# Exit from www-data user
exit
```

## Step 4: Configure Application

```bash
# Copy environment example
sudo -u www-data cp /var/www/xspacedownloader/.env.example /var/www/xspacedownloader/.env

# Edit environment file
sudo nano /var/www/xspacedownloader/.env
```

Add your configuration:
```env
# SendGrid API Key (if using email features)
SENDGRID_API_KEY=your_actual_sendgrid_api_key

# OpenAI API Key (for AI features)
OPENAI_API_KEY=your_openai_api_key

# Anthropic API Key (optional)
ANTHROPIC_API_KEY=your_anthropic_api_key
```

Update database configuration:
```bash
sudo nano /var/www/xspacedownloader/db_config.json
```

Update with your database credentials:
```json
{
    "type": "mysql",
    "mysql": {
        "host": "localhost",
        "user": "xspace",
        "password": "your_secure_password",
        "database": "xspacedownloader",
        "charset": "utf8mb4",
        "use_unicode": true
    }
}
```

## Step 5: Initialize Database

```bash
# Run database setup
cd /var/www/xspacedownloader
sudo -u www-data venv/bin/python db_setup.py

# Import schema if needed
sudo -u www-data mysql -u xspace -p xspacedownloader < mysql.schema
```

## Step 6: Setup Nginx

```bash
# Copy nginx configuration
sudo cp /var/www/xspacedownloader/deploy/nginx/xspacedownloader.conf /etc/nginx/sites-available/

# Update domain name in nginx config
sudo nano /etc/nginx/sites-available/xspacedownloader.conf
# Replace your-domain.com with your actual domain

# Enable the site
sudo ln -s /etc/nginx/sites-available/xspacedownloader.conf /etc/nginx/sites-enabled/

# Test nginx configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

## Step 7: Setup Systemd Services

```bash
# Copy systemd service files
sudo cp /var/www/xspacedownloader/deploy/systemd/*.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable xspacedownloader.service
sudo systemctl enable xspacedownloader-bg.service
sudo systemctl enable xspacedownloader-transcribe.service

# Start services
sudo systemctl start xspacedownloader.service
sudo systemctl start xspacedownloader-bg.service
sudo systemctl start xspacedownloader-transcribe.service

# Check service status
sudo systemctl status xspacedownloader.service
sudo systemctl status xspacedownloader-bg.service
sudo systemctl status xspacedownloader-transcribe.service
```

## Step 8: Setup SSL Certificate (Recommended)

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain SSL certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# The certificate will auto-renew, but you can test renewal with:
sudo certbot renew --dry-run
```

## Step 9: Configure Firewall

```bash
# Allow SSH (if using UFW)
sudo ufw allow ssh

# Allow HTTP and HTTPS
sudo ufw allow 'Nginx Full'

# Enable firewall
sudo ufw enable
```

## Step 10: Setup Log Rotation

Create `/etc/logrotate.d/xspacedownloader`:
```bash
sudo nano /etc/logrotate.d/xspacedownloader
```

Add:
```
/var/www/xspacedownloader/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data www-data
    sharedscripts
    postrotate
        systemctl reload xspacedownloader >/dev/null 2>&1 || true
    endscript
}
```

## Monitoring and Maintenance

### View Logs
```bash
# Application logs
sudo journalctl -u xspacedownloader -f
sudo tail -f /var/www/xspacedownloader/logs/app.log

# Background downloader logs
sudo journalctl -u xspacedownloader-bg -f
sudo tail -f /var/www/xspacedownloader/logs/bg-downloader.log

# Transcriber logs
sudo journalctl -u xspacedownloader-transcribe -f
sudo tail -f /var/www/xspacedownloader/logs/transcribe.log
```

### Restart Services
```bash
sudo systemctl restart xspacedownloader
sudo systemctl restart xspacedownloader-bg
sudo systemctl restart xspacedownloader-transcribe
```

### Update Application
```bash
cd /var/www/xspacedownloader
sudo -u www-data git pull
sudo -u www-data venv/bin/pip install -r requirements.txt
sudo systemctl restart xspacedownloader xspacedownloader-bg xspacedownloader-transcribe
```

## Performance Tuning

### Nginx Optimization
Edit `/etc/nginx/nginx.conf`:
```nginx
worker_processes auto;
worker_connections 1024;
client_max_body_size 500M;  # For large audio files
```

### MySQL Optimization
Edit `/etc/mysql/mysql.conf.d/mysqld.cnf`:
```ini
[mysqld]
# Increase buffer pool for better performance
innodb_buffer_pool_size = 1G
innodb_log_file_size = 256M
max_connections = 200
```

### System Limits
Edit `/etc/security/limits.conf`:
```
www-data soft nofile 65536
www-data hard nofile 65536
```

## Troubleshooting

### Service Won't Start
```bash
# Check service logs
sudo journalctl -u xspacedownloader -n 50

# Check permissions
sudo chown -R www-data:www-data /var/www/xspacedownloader

# Check Python path
/var/www/xspacedownloader/venv/bin/python --version
```

### Database Connection Issues
```bash
# Test database connection
mysql -u xspace -p -h localhost xspacedownloader

# Check MySQL service
sudo systemctl status mysql
```

### Permission Errors
```bash
# Fix permissions
sudo chown -R www-data:www-data /var/www/xspacedownloader
sudo chmod -R 755 /var/www/xspacedownloader
sudo chmod -R 775 /var/www/xspacedownloader/downloads
sudo chmod -R 775 /var/www/xspacedownloader/logs
sudo chmod -R 775 /var/www/xspacedownloader/transcript_jobs
```

## Security Recommendations

1. **Use strong passwords** for MySQL and admin accounts
2. **Enable firewall** and only allow necessary ports
3. **Keep system updated** with security patches
4. **Use SSL certificates** for HTTPS
5. **Regularly backup** your database and downloads
6. **Monitor logs** for suspicious activity
7. **Set up fail2ban** to prevent brute force attacks

## Backup Strategy

Create a backup script at `/usr/local/bin/backup-xspace.sh`:
```bash
#!/bin/bash
BACKUP_DIR="/backup/xspacedownloader"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup database
mysqldump -u xspace -p xspacedownloader | gzip > $BACKUP_DIR/db_$DATE.sql.gz

# Backup downloads (optional, can be large)
tar -czf $BACKUP_DIR/downloads_$DATE.tar.gz /var/www/xspacedownloader/downloads/

# Keep only last 7 days of backups
find $BACKUP_DIR -name "*.gz" -mtime +7 -delete
```

Make it executable and add to cron:
```bash
sudo chmod +x /usr/local/bin/backup-xspace.sh
sudo crontab -e
# Add: 0 2 * * * /usr/local/bin/backup-xspace.sh
```

## Support

For issues and support:
- Check logs in `/var/www/xspacedownloader/logs/`
- Review system logs with `journalctl`
- Report issues at: https://github.com/evoknow/xspacedownloader/issues