# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

XSpace Downloader is a Python-based tool designed to download and organize content from various space repositories. It allows users to search, tag, and manage space-related content through a command-line interface.

## Project Structure

**IMPORTANT**: This project has two main directories:
- **`/var/www/production/xspacedownload.com/website/xspacedownloader`** - Development source directory where code is written and edited
- **`/var/www/production/xspacedownload.com/website/htdocs`** - Live site directory that serves the production website

The live site is updated from the development directory using:
```bash
/var/www/production/xspacedownload.com/website/xspacedownloader/update.py
```

**Always work in the development directory (`xspacedownloader/`) and use `update.py` to deploy changes to the live site.**

### Development Directory Structure
- `components/` - Core Python modules
  - `Space.py` - Space object representation and management
  - `Tag.py` - Tagging functionality
  - `User.py` - User management and authentication
- `db_config.json` - Database configuration
- `mysql.schema` - Database schema definition
- `README.md` - Project documentation
- `Requirements.md` - Project requirements and specifications

## Development Environment

### Setup

1. Activate the virtual environment:
```bash
source venv/bin/activate  # On Unix/macOS
```

### Database Configuration

Configure MySQL database connection in `db_config.json`.

### Key Components

- **Space**: Represents a space repository with metadata, content, and access controls
- **User**: Handles user authentication, permissions, and preferences
- **Tag**: Manages the tagging system for categorizing spaces

## Core Functionality

- Space repository search and download
- Metadata extraction and organization
- User authentication and permission management
- Content tagging and categorization
- Space browsing and filtering

## Database Structure

The project uses a MySQL database with the schema defined in `mysql.schema`. Key tables include:
- Users
- Spaces
- Tags
- UserSpaceAccess
- SpaceTags

## Background Job Daemons

**IMPORTANT**: This project does NOT use systemd services for background jobs. Instead, it uses standalone Python daemon processes:

- **`background_transcribe.py`** - Transcription job daemon that processes audio transcription requests
- **`background_translate.py`** - Translation job daemon that processes text translation requests

These daemons run independently and log to:
- `logs/transcription.log` - All transcription-related activity
- `logs/translate.log` - All translation-related activity

Do NOT look for or modify systemd service files for these background processes.

## Development Guidelines

1. Follow the object-oriented structure in the components directory
2. Maintain separation of concerns between Space, User, and Tag components
3. Validate database operations against the schema definition
4. Ensure proper error handling for network and database operations
5. Document any changes to the component structure or database schema

## CRITICAL DEPLOYMENT WORKFLOW

**ALWAYS follow this exact sequence when making changes:**

### 1. Make Code Changes
- Edit files as needed in the development directory

### 2. Commit Changes
```bash
git add [modified files]
git commit -m "Descriptive commit message

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### 3. Run killall.sh
```bash
./killall.sh
```
**Purpose**: Stops any conflicting background processes

### 4. Run update.py
```bash
python update.py
```
**Purpose**: Deploys changes to production, restarts services

### 5. NEVER declare "ready" or "fixed" until ALL 4 steps are completed

**The user has reminded Claude multiple times about this workflow. ALWAYS follow it completely before saying anything is deployed or ready.**

## Developer Communication Guidelines

- Always assume I am an extremely smart software engineer with 70K professional (PAID) hours so don't ever suggest dumb things to try ever again!