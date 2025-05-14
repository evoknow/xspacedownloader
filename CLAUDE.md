# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

XSpace Downloader is a Python-based tool designed to download and organize content from various space repositories. It allows users to search, tag, and manage space-related content through a command-line interface.

## Project Structure

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

## Development Guidelines

1. Follow the object-oriented structure in the components directory
2. Maintain separation of concerns between Space, User, and Tag components
3. Validate database operations against the schema definition
4. Ensure proper error handling for network and database operations
5. Document any changes to the component structure or database schema