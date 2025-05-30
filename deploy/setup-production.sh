#!/bin/bash
# Quick setup script for production deployment

set -e

echo "XSpace Downloader - Production Setup Script"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
   echo "Please run as root (use sudo)"
   exit 1
fi

# Get domain name
read -p "Enter your domain name (or press Enter to skip): " DOMAIN
if [ -z "$DOMAIN" ]; then
    DOMAIN="your-domain.com"
    echo "Using placeholder domain: $DOMAIN"
fi

# Install system dependencies
echo "Installing system dependencies..."
apt update
apt install -y python3-pip python3-venv python3-dev \
    mysql-server nginx git ffmpeg \
    build-essential libssl-dev libffi-dev \
    python3-setuptools

# Create application directory
echo "Setting up application directory..."
mkdir -p /var/www/xspacedownloader
chown -R www-data:www-data /var/www/xspacedownloader

# Copy application files
echo "Copying application files..."
cp -r . /var/www/xspacedownloader/
chown -R www-data:www-data /var/www/xspacedownloader

# Setup Python environment
echo "Setting up Python virtual environment..."
cd /var/www/xspacedownloader
sudo -u www-data python3 -m venv venv
sudo -u www-data venv/bin/pip install --upgrade pip
sudo -u www-data venv/bin/pip install -r requirements.txt
sudo -u www-data venv/bin/pip install gunicorn

# Create necessary directories
sudo -u www-data mkdir -p logs downloads transcript_jobs

# Setup nginx
echo "Configuring nginx..."
cp deploy/nginx/xspacedownloader.conf /etc/nginx/sites-available/
sed -i "s/your-domain.com/$DOMAIN/g" /etc/nginx/sites-available/xspacedownloader.conf
ln -sf /etc/nginx/sites-available/xspacedownloader.conf /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# Setup systemd services
echo "Installing systemd services..."
cp deploy/systemd/*.service /etc/systemd/system/
systemctl daemon-reload

# Database setup reminder
echo ""
echo "IMPORTANT: Database Setup Required!"
echo "==================================="
echo "1. Create MySQL database and user:"
echo "   sudo mysql -u root -p"
echo "   CREATE DATABASE xspacedownloader CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
echo "   CREATE USER 'xspace'@'localhost' IDENTIFIED BY 'your_password';"
echo "   GRANT ALL PRIVILEGES ON xspacedownloader.* TO 'xspace'@'localhost';"
echo "   FLUSH PRIVILEGES;"
echo ""
echo "2. Update /var/www/xspacedownloader/db_config.json with your database credentials"
echo ""
echo "3. Copy and edit .env file:"
echo "   cp /var/www/xspacedownloader/.env.example /var/www/xspacedownloader/.env"
echo "   nano /var/www/xspacedownloader/.env"
echo ""
echo "4. Initialize database:"
echo "   cd /var/www/xspacedownloader"
echo "   sudo -u www-data venv/bin/python db_setup.py"
echo ""
echo "5. Start services:"
echo "   systemctl enable --now xspacedownloader-gunicorn"
echo "   systemctl enable --now xspacedownloader-bg"
echo "   systemctl enable --now xspacedownloader-transcribe"
echo ""
echo "6. (Optional) Setup SSL with certbot:"
echo "   apt install certbot python3-certbot-nginx"
echo "   certbot --nginx -d $DOMAIN -d www.$DOMAIN"
echo ""
echo "Setup script complete! Follow the steps above to finish configuration."