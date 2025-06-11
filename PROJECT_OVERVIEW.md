# X Space Downloader

## Project Overview

X Space Downloader is a comprehensive web application and API platform designed to capture, process, and manage audio content from X (formerly Twitter) Spaces. This open-source tool provides content creators, researchers, journalists, and organizations with powerful capabilities to archive, transcribe, and analyze live audio conversations from the X platform.

## Table of Contents

- [Features](#features)
- [Use Cases](#use-cases)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Core Components](#core-components)
- [API Capabilities](#api-capabilities)
- [Installation](#installation)
- [Configuration](#configuration)
- [Contributing](#contributing)
- [License](#license)

## Features

### 🎵 Audio Processing
- **High-Quality Downloads**: Capture X Spaces audio in multiple formats (MP3, M4A, WAV)
- **Automatic Silence Removal**: Intelligent preprocessing to remove leading silence and noise
- **Format Conversion**: Convert between various audio formats
- **Audio Trimming**: Precise start/end time controls for content editing

### 🎥 Video Generation
- **Professional MP4 Creation**: Generate branded video content with audio waveforms
- **Custom Branding**: Configurable logos, colors, backgrounds, and watermarks
- **Host Profile Integration**: Automatic inclusion of speaker profile pictures
- **Hardware Acceleration**: Optimized for macOS VideoToolbox and multi-threading

### 📝 Advanced Transcription
- **Multi-Model Support**: OpenAI Whisper integration with multiple model sizes
- **Corrective AI Filtering**: GPT-powered post-processing for improved accuracy
- **Timecode Support**: Precise timestamp mapping for navigation
- **Language Detection**: Automatic language identification and processing
- **Batch Processing**: Efficient handling of multiple transcription jobs

### 🏷️ Intelligent Tagging
- **AI-Powered Categorization**: Automatic content classification using GPT models
- **Custom Tag Management**: Manual and automated tag assignment
- **Search & Discovery**: Advanced filtering and search capabilities
- **Tag Analytics**: Content organization and trend analysis

### 👥 User Management
- **Multi-User Support**: Individual user accounts and preferences
- **Admin Dashboard**: Comprehensive management interface
- **Permission Controls**: Granular access control and user roles
- **Usage Analytics**: Detailed user activity tracking

### 📊 Analytics & Reporting
- **Download Statistics**: Comprehensive usage metrics
- **Performance Monitoring**: System health and processing analytics
- **Content Insights**: Trending topics and engagement metrics
- **Export Capabilities**: Data export in multiple formats

### 🔧 Admin Controls
- **Centralized Management**: Complete system administration interface
- **Content Moderation**: Tools for managing and organizing content
- **System Configuration**: Flexible settings for all components
- **Bulk Operations**: Efficient management of large content libraries

## Use Cases

### 📚 Content Creators & Podcasters
- **Archive Live Discussions**: Preserve valuable conversations for future reference
- **Create Podcast Content**: Convert Spaces to podcast episodes with professional branding
- **Generate Clips**: Extract highlights and key moments for social media
- **Transcription Services**: Create searchable text content from audio discussions

### 📰 Journalists & Media Organizations
- **Interview Documentation**: Preserve important interviews and press conferences
- **Quote Extraction**: Accurate transcriptions for reporting and fact-checking
- **Source Material**: Maintain archives of newsworthy discussions
- **Research Tools**: Search and analyze conversations by topic or speaker

### 🎓 Researchers & Academics
- **Data Collection**: Gather social media conversation data for analysis
- **Linguistic Studies**: Analyze speech patterns and language usage
- **Social Research**: Study public discourse and opinion trends
- **Educational Content**: Create learning materials from expert discussions

### 🏢 Enterprise & Organizations
- **Brand Monitoring**: Track mentions and discussions about products/services
- **Competitive Intelligence**: Monitor industry conversations and trends
- **Community Management**: Engage with and understand audience discussions
- **Internal Training**: Convert public discussions into training materials

### 💼 Legal & Compliance
- **Evidence Preservation**: Maintain legal records of public statements
- **Compliance Monitoring**: Track regulatory discussions and announcements
- **Documentation**: Create official records of public communications
- **Audit Trails**: Maintain comprehensive logs of content access and usage

## Architecture

### System Design
X Space Downloader follows a modular architecture with clear separation of concerns:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Frontend  │    │   API Gateway   │    │  Admin Panel    │
│                 │    │                 │    │                 │
│ - User Interface│    │ - Rate Limiting │    │ - Management UI │
│ - Authentication│    │ - Request Routing│    │ - Analytics     │
│ - Real-time UI  │    │ - Response Cache│    │ - Configuration │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                        │                        │
         └────────────────────────┼────────────────────────┘
                                  │
                    ┌─────────────────┐
                    │  Core Engine    │
                    │                 │
                    │ - Space Scraper │
                    │ - Download Mgr  │
                    │ - Job Scheduler │
                    │ - User Manager  │
                    └─────────────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         │                       │                        │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Processing Layer│    │  Storage Layer  │    │ External APIs   │
│                 │    │                 │    │                 │
│ - Video Gen     │    │ - MySQL Database│    │ - OpenAI        │
│ - Transcription │    │ - File Storage  │    │ - Twitter/X     │
│ - AI Tagging    │    │ - Cache Layer   │    │ - Cloud Storage │
│ - Audio Proc    │    │ - Job Queue     │    │ - Email Service │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Component Architecture
Each major component is designed as an independent module:

- **Space Component**: Handles X Spaces metadata and content management
- **SpeechToText Component**: Manages transcription workflows and AI processing
- **VideoGenerator Component**: Creates professional video content with branding
- **User Component**: Manages authentication, preferences, and permissions
- **Tag Component**: Handles content categorization and search functionality
- **Email Component**: Manages notifications and user communications

## Technology Stack

### Backend Technologies
- **Framework**: Flask (Python 3.8+)
- **Database**: MySQL with connection pooling
- **Task Queue**: Background job processing
- **Audio Processing**: FFmpeg, Whisper
- **Video Generation**: FFmpeg with hardware acceleration
- **AI Integration**: OpenAI GPT and Whisper APIs

### Frontend Technologies
- **UI Framework**: Bootstrap 5 with custom CSS
- **JavaScript**: Modern ES6+ with fetch API
- **Real-time Updates**: WebSocket connections for live progress
- **Responsive Design**: Mobile-first responsive interface
- **Icons**: Bootstrap Icons library

### Infrastructure & DevOps
- **Deployment**: Systemd services with auto-restart
- **Web Server**: Nginx reverse proxy with SSL
- **Process Management**: Gunicorn WSGI server
- **Monitoring**: Comprehensive logging with rotation
- **Backup**: Automated database and file system backups

### External Integrations
- **OpenAI**: GPT-4 for content analysis and Whisper for transcription
- **Email Services**: SendGrid and SMTP support for notifications
- **Cloud Storage**: Configurable cloud storage backends
- **X Platform**: Direct integration with X Spaces API

## Core Components

### Space Management System
- **Metadata Extraction**: Comprehensive space information parsing
- **Content Discovery**: Advanced search and filtering capabilities
- **Status Tracking**: Real-time download and processing status
- **Quality Control**: Validation and error handling for all operations

### Transcription Engine
- **Multi-Provider Support**: OpenAI Whisper with local fallback options
- **Model Selection**: Choice of speed vs. accuracy trade-offs
- **Language Support**: Automatic detection and multi-language processing
- **Quality Enhancement**: AI-powered post-processing for improved accuracy

### Video Production Pipeline
- **Template System**: Customizable video templates and branding
- **Asset Management**: Profile pictures, logos, and media assets
- **Rendering Engine**: High-performance video generation with hardware acceleration
- **Format Support**: Multiple output formats and quality settings

### Administrative Interface
- **Dashboard Analytics**: Real-time system metrics and usage statistics
- **User Management**: Complete user lifecycle management
- **Content Moderation**: Tools for organizing and managing content
- **System Configuration**: Centralized settings management

## API Capabilities

### RESTful API Endpoints
- **Space Operations**: CRUD operations for space management
- **User Management**: Authentication and user data management
- **Transcription Jobs**: Asynchronous transcription processing
- **Video Generation**: On-demand video creation
- **Analytics**: Usage statistics and reporting data

### Rate Limiting & Security
- **Configurable Limits**: Per-user and per-endpoint rate limiting
- **Authentication**: Session-based authentication with secure tokens
- **Permission Controls**: Role-based access control system
- **Audit Logging**: Comprehensive activity logging for security

### Integration Support
- **Webhook Support**: Real-time notifications for external systems
- **Export APIs**: Data export in JSON, CSV, and other formats
- **Import Tools**: Bulk import capabilities for migration
- **Third-party Integration**: APIs for external tool integration

## Installation

### Prerequisites
- Python 3.8 or higher
- MySQL 5.7 or higher
- FFmpeg with appropriate codecs
- Node.js (for build tools)
- Git for version control

### Quick Start
```bash
# Clone the repository
git clone https://github.com/evoknow/xspacedownloader.git
cd xspacedownloader

# Set up virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure database
cp db_config.json.example db_config.json
# Edit db_config.json with your database settings

# Initialize database
python db_setup.py

# Configure main settings
cp mainconfig.json.example mainconfig.json
# Edit mainconfig.json with your settings

# Start the application
python app.py
```

### Docker Deployment
```bash
# Using Docker Compose
docker-compose up -d

# Using individual containers
docker build -t xspacedownloader .
docker run -d -p 5000:5000 xspacedownloader
```

## Configuration

### Environment Configuration
- **Database Settings**: MySQL connection parameters
- **API Keys**: OpenAI, email service, and other third-party API keys
- **Storage Configuration**: Local and cloud storage settings
- **Security Settings**: Authentication and session management

### Feature Configuration
- **Transcription Settings**: Model selection and processing options
- **Video Generation**: Branding, quality, and format settings
- **User Management**: Registration, permissions, and limits
- **Content Policies**: Moderation and content management rules

### Performance Tuning
- **Resource Limits**: CPU, memory, and storage allocation
- **Concurrency Settings**: Parallel processing configuration
- **Cache Configuration**: Redis and application-level caching
- **Monitoring**: Logging levels and performance metrics

## Contributing

We welcome contributions from the community! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details on:

- Code of Conduct
- Development workflow
- Testing requirements
- Documentation standards
- Pull request process

### Development Setup
1. Fork the repository
2. Create a feature branch
3. Set up development environment
4. Make your changes
5. Add tests and documentation
6. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support & Community

- **Documentation**: [Full documentation](https://docs.xspacedownloader.com)
- **Issues**: [GitHub Issues](https://github.com/evoknow/xspacedownloader/issues)
- **Discussions**: [GitHub Discussions](https://github.com/evoknow/xspacedownloader/discussions)
- **Security**: [Security Policy](SECURITY.md)

---

**Developed by EVOKNOW, Inc.**  
**Open Source Software under MIT License**  
**© 2025 EVOKNOW, Inc. All rights reserved.**