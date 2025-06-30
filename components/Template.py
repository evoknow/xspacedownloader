import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, TemplateSyntaxError, meta
import glob
import re

class Template:
    def __init__(self, base_path="/var/www/production/xspacedownload.com/website/xspacedownloader"):
        self.base_path = base_path
        self.templates_dir = os.path.join(base_path, "templates")
        self.backups_dir = os.path.join(self.templates_dir, "backups")
        self.max_backups = 3
        
        # Create backups directory if it doesn't exist
        os.makedirs(self.backups_dir, exist_ok=True)
        
        # Initialize Jinja2 environment for validation
        self.env = Environment()
    
    def list_templates(self):
        """List all template files in the templates directory"""
        templates = []
        
        # Get all .html files in templates directory (excluding backups)
        for file_path in glob.glob(os.path.join(self.templates_dir, "*.html")):
            filename = os.path.basename(file_path)
            
            # Get file stats
            stats = os.stat(file_path)
            
            # Get backup count for this template
            backup_pattern = os.path.join(self.backups_dir, f"{filename[:-5]}-*.html")
            backups = sorted(glob.glob(backup_pattern), reverse=True)
            
            templates.append({
                'name': filename,
                'path': file_path,
                'size': stats.st_size,
                'modified': datetime.fromtimestamp(stats.st_mtime).isoformat(),
                'backup_count': len(backups),
                'latest_backup': os.path.basename(backups[0]) if backups else None
            })
        
        return sorted(templates, key=lambda x: x['name'])
    
    def get_template_content(self, template_name):
        """Get the content of a specific template"""
        if not self._is_safe_filename(template_name):
            raise ValueError("Invalid template name")
        
        file_path = os.path.join(self.templates_dir, template_name)
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Template {template_name} not found")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Get backup history
        backup_pattern = os.path.join(self.backups_dir, f"{template_name[:-5]}-*.html")
        backups = sorted(glob.glob(backup_pattern), reverse=True)
        
        backup_history = []
        for backup in backups[:10]:  # Show last 10 backups
            backup_name = os.path.basename(backup)
            # Extract timestamp from filename
            timestamp_str = backup_name[len(template_name[:-5])+1:-5]
            try:
                timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                backup_history.append({
                    'filename': backup_name,
                    'timestamp': timestamp.isoformat(),
                    'size': os.path.getsize(backup)
                })
            except:
                pass
        
        return {
            'name': template_name,
            'content': content,
            'backups': backup_history
        }
    
    def validate_template(self, content):
        """Validate template syntax and extract variables used"""
        errors = []
        warnings = []
        variables = set()
        
        try:
            # Parse the template
            ast = self.env.parse(content)
            
            # Extract all variables used in the template
            variables = meta.find_undeclared_variables(ast)
            
            # Check for common template patterns that might be problematic
            if '{% raw %}' in content or '{% endraw %}' in content:
                warnings.append("Template contains raw blocks - ensure they are properly closed")
            
            # Check for unclosed blocks
            block_pattern = r'{%\s*(block|for|if|macro|call|filter|set)\s+'
            endblock_pattern = r'{%\s*end(block|for|if|macro|call|filter|set)\s*%}'
            
            blocks = len(re.findall(block_pattern, content))
            endblocks = len(re.findall(endblock_pattern, content))
            
            if blocks != endblocks:
                errors.append(f"Unclosed template blocks detected: {blocks} opening blocks, {endblocks} closing blocks")
            
            # Check for common Jinja2 variables we expect
            expected_vars = {'request', 'session', 'g', 'url_for', 'get_flashed_messages'}
            missing_expected = expected_vars - variables
            if missing_expected:
                warnings.append(f"Template might be missing expected variables: {', '.join(missing_expected)}")
            
        except TemplateSyntaxError as e:
            errors.append(f"Template syntax error at line {e.lineno}: {str(e)}")
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'variables': list(variables)
        }
    
    def save_template(self, template_name, content):
        """Save template with validation and backup"""
        if not self._is_safe_filename(template_name):
            raise ValueError("Invalid template name")
        
        file_path = os.path.join(self.templates_dir, template_name)
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Template {template_name} not found")
        
        # Validate the new content
        validation = self.validate_template(content)
        if not validation['valid']:
            raise ValueError(f"Template validation failed: {'; '.join(validation['errors'])}")
        
        # Create backup of current version
        self._create_backup(template_name)
        
        # Save the new content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Clear template cache
        self._clear_template_cache()
        
        return {
            'success': True,
            'message': f"Template {template_name} saved successfully",
            'validation': validation
        }
    
    def restore_backup(self, template_name, backup_filename):
        """Restore a template from a specific backup"""
        if not self._is_safe_filename(template_name) or not self._is_safe_filename(backup_filename):
            raise ValueError("Invalid filename")
        
        backup_path = os.path.join(self.backups_dir, backup_filename)
        template_path = os.path.join(self.templates_dir, template_name)
        
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"Backup {backup_filename} not found")
        
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Template {template_name} not found")
        
        # Create a backup of current version before restoring
        self._create_backup(template_name)
        
        # Copy backup to template
        shutil.copy2(backup_path, template_path)
        
        # Clear template cache
        self._clear_template_cache()
        
        return {
            'success': True,
            'message': f"Template {template_name} restored from backup {backup_filename}"
        }
    
    def _create_backup(self, template_name):
        """Create a backup of the current template"""
        source_path = os.path.join(self.templates_dir, template_name)
        
        if not os.path.exists(source_path):
            return
        
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{template_name[:-5]}-{timestamp}.html"
        backup_path = os.path.join(self.backups_dir, backup_filename)
        
        # Copy the file
        shutil.copy2(source_path, backup_path)
        
        # Clean up old backups
        self._cleanup_old_backups(template_name)
    
    def _cleanup_old_backups(self, template_name):
        """Keep only the latest N backups for a template"""
        backup_pattern = os.path.join(self.backups_dir, f"{template_name[:-5]}-*.html")
        backups = sorted(glob.glob(backup_pattern), reverse=True)
        
        # Delete old backups beyond max_backups
        for backup in backups[self.max_backups:]:
            try:
                os.unlink(backup)
            except:
                pass
    
    def _clear_template_cache(self):
        """Clear Flask template cache"""
        # Flask caches compiled templates, we need to clear them
        # In production, this might require restarting the app
        cache_patterns = [
            os.path.join(self.base_path, "__pycache__"),
            os.path.join(self.templates_dir, "__pycache__"),
            "/tmp/jinja2_cache_*"
        ]
        
        for pattern in cache_patterns:
            for path in glob.glob(pattern):
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.unlink(path)
                except:
                    pass
    
    def _is_safe_filename(self, filename):
        """Check if filename is safe (no path traversal)"""
        return (
            filename and
            '..' not in filename and
            '/' not in filename and
            '\\' not in filename and
            filename.endswith('.html')
        )
    
    def get_template_info(self):
        """Get general information about templates"""
        templates = self.list_templates()
        
        total_size = sum(t['size'] for t in templates)
        total_backups = sum(t['backup_count'] for t in templates)
        
        # Get backup directory size
        backup_size = 0
        for backup in glob.glob(os.path.join(self.backups_dir, "*.html")):
            backup_size += os.path.getsize(backup)
        
        return {
            'template_count': len(templates),
            'total_size': total_size,
            'total_backups': total_backups,
            'backup_size': backup_size,
            'templates_dir': self.templates_dir,
            'backups_dir': self.backups_dir
        }