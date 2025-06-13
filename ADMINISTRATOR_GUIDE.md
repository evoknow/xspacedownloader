# XSpace Downloader - Administrator's Guide

## Table of Contents
1. [Overview](#overview)
2. [Initial Setup](#initial-setup)
3. [Admin Dashboard](#admin-dashboard)
4. [Service Management](#service-management)
5. [User Management](#user-management)
6. [Content Management](#content-management)
7. [System Monitoring](#system-monitoring)
8. [Queue Management](#queue-management)
9. [Database Operations](#database-operations)
10. [Troubleshooting](#troubleshooting)
11. [Maintenance Tasks](#maintenance-tasks)
12. [Security Considerations](#security-considerations)

---

## Overview

XSpace Downloader is a comprehensive platform for downloading, transcribing, and managing X (Twitter) Spaces. As an administrator, you have full control over the system through the web interface and command-line tools.

### Key Features
- **Space Downloads**: Automated downloading and conversion to MP3
- **AI Transcription**: Speech-to-text with OpenAI Whisper or Anthropic Claude
- **Translation**: Multi-language content translation
- **Video Generation**: MP4 creation with waveform visualization
- **User Management**: Account creation, permissions, and activity tracking
- **Content Moderation**: Space management, tagging, and reviews
- **System Monitoring**: Real-time status, logs, and performance metrics

---

## Initial Setup

### 1. First-Time Configuration
Access the setup wizard at `/setup` when first installing the application:

1. **Database Configuration**: Configure MySQL connection
2. **Admin Account**: Create your first administrator account
3. **Email Provider**: Set up SendGrid or Mailgun for notifications
4. **AI Services**: Configure OpenAI or Anthropic API keys
5. **Test Configuration**: Verify all services are working

### 2. Environment Variables
Set these in your `.env` file or environment:
```bash
# Database
MYSQL_HOST=localhost
MYSQL_USER=your_user
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=xspacedownloader

# Email (choose one)
SENDGRID_API_KEY=your_sendgrid_key
MAILGUN_API_KEY=your_mailgun_key
MAILGUN_DOMAIN=your_domain

# AI Services (choose one)
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
```

### 3. Service Management Scripts
Use these scripts to manage background services:

```bash
# Start all background services
./start.sh

# Stop all background services
./stop.sh

# Check status
./run.sh  # For development

# Reset system (WARNING: Clears all data)
./reset.sh
```

---

## Admin Dashboard

Access the admin dashboard by clicking **Admin** in the navigation menu (only visible to admin users).

### Dashboard Sections

#### 1. **Overview Tab**
- **System Statistics**: Total users, spaces, downloads
- **Recent Activity**: Latest downloads and user registrations
- **Quick Actions**: Common administrative tasks

#### 2. **Users Tab**
- **User List**: View all registered users with search and filtering
- **User Actions**: 
  - Grant/revoke admin privileges
  - Suspend/activate accounts
  - View user activity and statistics
- **User Statistics**: Registration trends and activity patterns

#### 3. **Spaces Tab**
- **Space Management**: View all downloaded spaces
- **Content Moderation**: Remove inappropriate content
- **Bulk Operations**: Mass delete or update spaces
- **Space Analytics**: Download and play statistics

#### 4. **Queue Tab**
- **Active Jobs**: Monitor current downloads, transcriptions, translations
- **Job Details**: Click info buttons for detailed job information
- **Queue Control**: Pause, resume, or cancel jobs
- **Priority Management**: Adjust job processing order

#### 5. **System Status Tab**
- **Process Monitoring**: Background service status and PIDs
- **Resource Usage**: CPU, memory, and disk utilization
- **Service Health**: MySQL, Nginx, and application services
- **Disk Usage**: Storage breakdown by component

#### 6. **SQL Tab**
- **Query Logging**: Monitor database performance
- **Execution Times**: Track slow queries
- **Log Management**: Enable/disable logging, clear logs
- **Copy Functionality**: Export logs for analysis

#### 7. **Settings Tab**
- **Transcription**: Configure AI providers and models
- **Email**: Set up notification preferences
- **Branding**: Customize logos, colors, and site appearance
- **Rate Limiting**: Control API usage and abuse prevention
- **Cache Management**: Clear system caches

---

## Service Management

### Background Services

XSpace Downloader runs several background processes:

1. **Background Downloader** (`bg_downloader.py`)
   - Downloads spaces from X
   - Converts audio to MP3
   - Updates job status

2. **Transcription Worker** (`background_transcribe.py`)
   - Processes audio files for speech-to-text
   - Handles translation requests
   - Manages AI API calls

3. **Progress Watcher** (`bg_progress_watcher.py`)
   - Monitors download progress
   - Updates file sizes in real-time
   - Tracks completion status

### Service Commands

```bash
# Start Services
./start.sh
# - Activates virtual environment
# - Starts all background processes
# - Provides status report

# Stop Services
./stop.sh
# - Gracefully stops all processes
# - Cleans up PID files
# - Verifies shutdown

# Service Status
ps aux | grep -E "(bg_downloader|background_transcribe|bg_progress_watcher)"

# View Logs
tail -f logs/bg_downloader.log
tail -f logs/bg_transcribe.log
tail -f logs/bg_progress_watcher.log
```

### Deployment Management

```bash
# Production Deployment
sudo python3 deploy.py --domain=yoursite.com

# Zero-Downtime Updates
sudo ./update.py

# Auto-Update Setup (optional)
sudo ./setup_auto_update.sh
```

---

## User Management

### User Roles

1. **Admin Users**
   - Full system access
   - User management capabilities
   - Content moderation powers
   - System configuration access

2. **Regular Users**
   - Download spaces
   - Personal notes and favorites
   - Space ratings and reviews
   - Account management

### User Administration

#### Creating Admin Users
1. Navigate to **Admin > Users**
2. Find the user in the list
3. Click the toggle switch under **Admin** column
4. Confirm the action

#### User Suspension
1. Go to **Admin > Users**
2. Click the **Suspend** button next to the user
3. User account will be deactivated
4. To reactivate, click **Activate**

#### User Analytics
- **Login Activity**: Track user engagement
- **Download History**: Monitor usage patterns
- **Geographic Data**: See user distribution
- **Activity Trends**: Analyze growth and retention

### Important Notes
- Cannot delete or suspend the last admin user (system protection)
- Cannot delete your own admin account
- User suspensions are reversible
- Admin privileges can be granted/revoked at any time

---

## Content Management

### Space Management

#### Viewing Spaces
- **Admin > Spaces**: Lists all downloaded spaces
- **Search & Filter**: Find specific content
- **Bulk Select**: Perform mass operations
- **Export Data**: Download space lists

#### Content Moderation
```bash
# Remove inappropriate content
1. Go to Admin > Spaces
2. Find the space in question
3. Click "Delete" to remove permanently
4. Content is immediately removed from public view
```

#### Tag Management
- **Auto-Tagging**: AI generates tags automatically
- **Manual Tags**: Add custom tags via admin interface
- **Tag Cleanup**: Remove inappropriate or duplicate tags
- **Bulk Operations**: Apply tags to multiple spaces

#### Reviews and Ratings
- **Review Moderation**: Flag and remove inappropriate reviews
- **Rating Analytics**: Track content quality metrics
- **User Feedback**: Monitor community engagement

---

## System Monitoring

### Real-Time Monitoring

#### System Status Dashboard
```
✅ Background Downloader: Running (PID: 12345)
✅ Transcription Worker: Running (2 processes)
✅ Progress Watcher: Running (PID: 12347)
✅ MySQL Database: Connected
✅ Nginx: Running
```

#### Resource Monitoring
- **CPU Usage**: Process-level monitoring
- **Memory Usage**: Per-service memory consumption
- **Disk Usage**: Storage breakdown by component
- **Network**: API request rates and response times

#### Log Monitoring
```bash
# Application Logs
tail -f logs/webapp.log

# Service Logs
tail -f logs/bg_downloader.log
tail -f logs/bg_transcribe.log
tail -f logs/bg_progress_watcher.log

# Error Logs
grep ERROR logs/*.log
```

### SQL Query Monitoring

The SQL tab provides comprehensive database monitoring:

1. **Enable Logging**: Toggle SQL query logging
2. **Performance Metrics**: Execution times and slow queries
3. **Component Tracking**: See which parts of the app generate queries
4. **Error Monitoring**: Database connection and query errors
5. **Log Export**: Copy logs for external analysis

### Performance Optimization

#### Common Issues
1. **Slow Downloads**: Check network connectivity and X API status
2. **High Memory Usage**: Monitor transcription processes
3. **Disk Space**: Regularly clean old downloads and logs
4. **Database Performance**: Monitor slow queries and optimize

#### Optimization Tips
```bash
# Clear old logs (older than 30 days)
find logs/ -name "*.log" -mtime +30 -delete

# Clean temporary files
rm -rf temp/*

# Database optimization
mysql -u root -p -e "OPTIMIZE TABLE spaces, space_download_scheduler, space_transcripts;"
```

---

## Queue Management

### Understanding Queues

The system maintains several processing queues:

1. **Download Queue**: Space downloading and audio conversion
2. **Transcription Queue**: Speech-to-text processing
3. **Translation Queue**: Multi-language content translation
4. **Video Generation Queue**: MP4 creation with visualization

### Queue Operations

#### Monitoring Active Jobs
- **Admin > Queue**: View all active processing jobs
- **Real-time Updates**: Status updates every 5 seconds
- **Progress Tracking**: Visual progress bars and ETAs
- **Job Details**: Click info buttons for comprehensive job information

#### Job Management
```bash
# Cancel a job (via admin interface)
1. Go to Admin > Queue
2. Find the job in the list
3. Click "Cancel" button
4. Job will be stopped and marked as cancelled

# Retry failed jobs (via admin interface)
1. Navigate to failed jobs section
2. Click "Retry" on specific jobs
3. Job will be re-queued for processing
```

#### Priority Management
- **High Priority**: Critical downloads (admin-initiated)
- **Normal Priority**: Regular user downloads
- **Low Priority**: Bulk processing jobs

---

## Database Operations

### Database Maintenance

#### Backup Operations
```bash
# Full database backup
mysqldump -u root -p xspacedownloader > backup_$(date +%Y%m%d).sql

# Backup specific tables
mysqldump -u root -p xspacedownloader spaces space_transcripts > content_backup.sql

# Restore from backup
mysql -u root -p xspacedownloader < backup_20241206.sql
```

#### Schema Management
```bash
# View current schema
mysql -u root -p xspacedownloader -e "SHOW TABLES;"

# Check table sizes
mysql -u root -p xspacedownloader -e "
SELECT 
    table_name AS 'Table',
    ROUND(((data_length + index_length) / 1024 / 1024), 2) AS 'Size (MB)'
FROM information_schema.tables 
WHERE table_schema = 'xspacedownloader'
ORDER BY (data_length + index_length) DESC;
"
```

#### Data Cleanup
```bash
# Remove old failed jobs (older than 7 days)
mysql -u root -p xspacedownloader -e "
DELETE FROM space_download_scheduler 
WHERE status = 'failed' AND created_at < DATE_SUB(NOW(), INTERVAL 7 DAY);
"

# Clean orphaned records
mysql -u root -p xspacedownloader -e "
DELETE FROM space_metadata WHERE space_id NOT IN (SELECT space_id FROM spaces);
DELETE FROM space_tags WHERE space_id NOT IN (SELECT space_id FROM spaces);
"
```

### Database Configuration

#### Connection Settings
Located in `db_config.json`:
```json
{
  "mysql": {
    "host": "localhost",
    "user": "xspace_user",
    "password": "your_password",
    "database": "xspacedownloader",
    "charset": "utf8mb4",
    "autocommit": true
  }
}
```

#### Performance Tuning
```sql
-- Optimize for read-heavy workloads
SET GLOBAL innodb_buffer_pool_size = 1073741824; -- 1GB
SET GLOBAL query_cache_size = 67108864; -- 64MB
SET GLOBAL query_cache_type = 1;

-- Index optimization
ANALYZE TABLE spaces, space_download_scheduler, space_transcripts;
```

---

## Troubleshooting

### Common Issues

#### 1. Services Not Starting
```bash
# Check logs for errors
tail -f logs/*.log

# Verify virtual environment
source venv/bin/activate
python3 -c "import mysql.connector; print('MySQL connector OK')"

# Check database connection
mysql -u root -p -e "SELECT 1;"

# Restart services
./stop.sh && ./start.sh
```

#### 2. Download Failures
```bash
# Check X API connectivity
curl -I "https://api.twitter.com/2/users/by"

# Verify yt-dlp installation
yt-dlp --version

# Test download manually
python3 direct_download.py "https://x.com/i/spaces/SPACE_ID"
```

#### 3. Transcription Issues
```bash
# Check API keys
python3 test_api_key.py

# Verify audio files
ffprobe downloads/SPACE_ID.mp3

# Test transcription
python3 test_speech_to_text.py
```

#### 4. Database Problems
```bash
# Check MySQL status
systemctl status mysql

# Test connection
mysql -u root -p -e "SHOW PROCESSLIST;"

# Check table integrity
mysql -u root -p xspacedownloader -e "CHECK TABLE spaces;"

# Repair tables if needed
mysql -u root -p xspacedownloader -e "REPAIR TABLE spaces;"
```

### Log Analysis

#### Error Patterns
```bash
# Find common errors
grep -i error logs/*.log | sort | uniq -c | sort -nr

# Check for memory issues
grep -i "memory\|oom" logs/*.log

# Database connection problems
grep -i "connection\|mysql" logs/*.log

# API rate limiting
grep -i "rate\|limit\|quota" logs/*.log
```

#### Performance Issues
```bash
# Slow queries
grep -i "slow\|timeout" logs/*.log

# High CPU usage
top -p $(pgrep -f "bg_downloader\|background_transcribe\|bg_progress_watcher")

# Disk space issues
df -h
du -sh downloads/ logs/ temp/
```

### Emergency Procedures

#### System Recovery
```bash
# Emergency stop all services
pkill -f "bg_downloader\|background_transcribe\|bg_progress_watcher"

# Clear stuck jobs
mysql -u root -p xspacedownloader -e "
UPDATE space_download_scheduler 
SET status = 'failed' 
WHERE status IN ('in_progress', 'downloading') 
AND updated_at < DATE_SUB(NOW(), INTERVAL 1 HOUR);
"

# Restart system
./stop.sh
./start.sh
```

#### Data Recovery
```bash
# Recover from backup
mysql -u root -p xspacedownloader < latest_backup.sql

# Rebuild indexes
mysql -u root -p xspacedownloader -e "
ALTER TABLE spaces ENGINE=InnoDB;
ALTER TABLE space_download_scheduler ENGINE=InnoDB;
"

# Fix file permissions
chmod -R 755 downloads/
chmod -R 755 logs/
chown -R www-data:www-data downloads/ logs/
```

---

## Maintenance Tasks

### Daily Tasks

#### 1. System Health Check
```bash
# Run automated health check
./check_system_health.sh

# Verify all services running
./start.sh  # Will show status of all services

# Check disk space
df -h
```

#### 2. Log Review
```bash
# Check for errors in last 24 hours
find logs/ -name "*.log" -mtime -1 -exec grep -l "ERROR\|CRITICAL" {} \;

# Review failed jobs
mysql -u root -p xspacedownloader -e "
SELECT space_id, error_message, created_at 
FROM space_download_scheduler 
WHERE status = 'failed' AND created_at > DATE_SUB(NOW(), INTERVAL 1 DAY);
"
```

### Weekly Tasks

#### 1. Database Maintenance
```bash
# Backup database
mysqldump -u root -p xspacedownloader > weekly_backup_$(date +%Y%m%d).sql

# Optimize tables
mysql -u root -p xspacedownloader -e "
OPTIMIZE TABLE spaces, space_download_scheduler, space_transcripts;
"

# Update statistics
mysql -u root -p xspacedownloader -e "
ANALYZE TABLE spaces, space_download_scheduler, space_transcripts;
"
```

#### 2. Storage Cleanup
```bash
# Clean old logs (older than 30 days)
find logs/ -name "*.log" -mtime +30 -delete

# Remove temporary files
rm -rf temp/*

# Clean old failed download files
find downloads/ -name "*.part" -mtime +7 -delete
```

### Monthly Tasks

#### 1. Security Updates
```bash
# Update system packages
sudo apt update && sudo apt upgrade

# Update Python packages
pip install --upgrade -r requirements.txt

# Review user access
# Use Admin > Users to review active accounts
```

#### 2. Performance Review
```bash
# Generate performance report
mysql -u root -p xspacedownloader -e "
SELECT 
    DATE(created_at) as date,
    COUNT(*) as total_jobs,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
    AVG(TIMESTAMPDIFF(SECOND, created_at, updated_at)) as avg_duration
FROM space_download_scheduler 
WHERE created_at > DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY DATE(created_at)
ORDER BY date;
"

# Review disk usage trends
du -sh downloads/ logs/ temp/ | tee monthly_usage_$(date +%Y%m).txt
```

### Quarterly Tasks

#### 1. Full System Backup
```bash
# Create complete backup
tar -czf full_backup_$(date +%Y%m%d).tar.gz \
    db_config.json mainconfig.json \
    downloads/ logs/ \
    --exclude='*.part' --exclude='temp/*'

# Backup database separately
mysqldump -u root -p xspacedownloader | gzip > database_backup_$(date +%Y%m%d).sql.gz
```

#### 2. Capacity Planning
- Review storage growth trends
- Analyze user growth patterns
- Plan infrastructure scaling
- Update resource allocations

---

## Security Considerations

### Access Control

#### Admin Account Security
1. **Strong Passwords**: Use complex, unique passwords
2. **Two-Factor Authentication**: Consider implementing 2FA
3. **Regular Access Review**: Audit admin privileges quarterly
4. **Session Management**: Monitor active admin sessions

#### API Security
```bash
# Monitor API usage
grep "API" logs/*.log | tail -100

# Check for suspicious activity
grep -i "error\|fail\|unauthorized" logs/*.log

# Review rate limiting
mysql -u root -p xspacedownloader -e "
SELECT user_id, COUNT(*) as request_count, DATE(created_at) as date
FROM space_download_scheduler 
WHERE created_at > DATE_SUB(NOW(), INTERVAL 1 DAY)
GROUP BY user_id, DATE(created_at)
HAVING request_count > 50
ORDER BY request_count DESC;
"
```

### Data Protection

#### Privacy Compliance
1. **User Data**: Minimize personal data collection
2. **Content Moderation**: Remove inappropriate or illegal content
3. **Data Retention**: Implement retention policies
4. **Export/Deletion**: Provide user data export and deletion

#### Backup Security
```bash
# Encrypt backups
gpg --symmetric --cipher-algo AES256 backup_$(date +%Y%m%d).sql

# Secure backup storage
chmod 600 *.sql.gz
chown root:root *.sql.gz
```

### Network Security

#### Firewall Configuration
```bash
# Allow only necessary ports
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw allow 22/tcp    # SSH (admin only)
ufw deny 3306/tcp   # MySQL (internal only)
```

#### SSL/TLS
- Use Let's Encrypt for HTTPS certificates
- Implement HSTS headers
- Regular certificate renewal
- Strong cipher suites

### Monitoring and Alerting

#### Security Monitoring
```bash
# Monitor failed login attempts
grep -i "failed\|unauthorized" logs/*.log

# Check for unusual activity
mysql -u root -p xspacedownloader -e "
SELECT user_id, COUNT(*) as activity_count
FROM space_download_scheduler 
WHERE created_at > DATE_SUB(NOW(), INTERVAL 1 HOUR)
GROUP BY user_id
HAVING activity_count > 10;
"
```

#### Incident Response
1. **Detection**: Monitor logs and alerts
2. **Assessment**: Evaluate threat severity
3. **Containment**: Isolate affected systems
4. **Recovery**: Restore normal operations
5. **Documentation**: Record incidents and responses

---

## Support and Resources

### Getting Help

#### Documentation
- **Setup Guide**: `/setup` - Initial configuration wizard
- **FAQ**: `/faq` - Common questions and answers
- **API Documentation**: Available in admin dashboard
- **GitHub Issues**: Report bugs and feature requests

#### Log Files
All system logs are stored in the `logs/` directory:
- `webapp.log` - Main application logs
- `bg_downloader.log` - Download service logs
- `bg_transcribe.log` - Transcription service logs
- `bg_progress_watcher.log` - Progress monitoring logs

#### Useful Commands
```bash
# Quick status check
./start.sh | grep -E "(✅|❌)"

# Service restart
./stop.sh && ./start.sh

# Database status
mysql -u root -p -e "SHOW PROCESSLIST;"

# Disk usage summary
du -sh downloads/ logs/ temp/

# Recent errors
grep -i error logs/*.log | tail -20
```

### Community and Support

#### Reporting Issues
1. **GitHub Issues**: Technical bugs and feature requests
2. **Documentation**: Contribute to guides and FAQs
3. **Community Forum**: User discussions and best practices

#### Contributing
- **Bug Reports**: Detailed reproduction steps
- **Feature Requests**: Clear use cases and benefits
- **Code Contributions**: Follow coding standards
- **Documentation**: Help improve guides and tutorials

---

## Conclusion

This guide covers the essential aspects of administering XSpace Downloader. Regular monitoring, maintenance, and security practices will ensure reliable operation and optimal performance.

For additional support or questions not covered in this guide, please:
1. Check the FAQ section
2. Review system logs for error messages
3. Submit detailed bug reports on GitHub
4. Engage with the community for best practices

Remember to keep regular backups and maintain security best practices to protect your installation and user data.

---

*This guide is regularly updated. Last updated: {{ current_date }}*