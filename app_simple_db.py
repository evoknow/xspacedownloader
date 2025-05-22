#!/usr/bin/env python3
# Simple database connection fix for app.py
# This approach creates a new Space component for each request to avoid memory corruption

def get_space_component():
    """Get a Space component instance with a fresh DB connection."""
    try:
        # Always create a new Space component to avoid threading issues
        # This prevents memory corruption from shared database connections
        from components.Space import Space
        space_component = Space()
        logger.info("Created new Space component instance")
        return space_component
        
    except Exception as e:
        logger.error(f"Error getting Space component: {e}")
        return None