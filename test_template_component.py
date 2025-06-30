#!/usr/bin/env python3
"""Test Template component functionality."""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from components.Template import Template

try:
    print("Testing Template component...")
    
    # Create Template instance
    template = Template()
    print(f"Templates directory: {template.templates_dir}")
    print(f"Backups directory: {template.backups_dir}")
    
    # List templates
    print("\nListing templates:")
    templates = template.list_templates()
    print(f"Found {len(templates)} templates")
    
    for t in templates:
        print(f"  - {t['name']} ({t['size']} bytes, {t['backup_count']} backups)")
    
    # Get template info
    print("\nTemplate info:")
    info = template.get_template_info()
    print(f"  Total templates: {info['template_count']}")
    print(f"  Total size: {info['total_size']} bytes")
    print(f"  Total backups: {info['total_backups']}")
    print(f"  Backup size: {info['backup_size']} bytes")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()