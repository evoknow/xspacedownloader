#!/usr/bin/env python3
"""
System Status Component for XSpace Downloader
Monitors background processes, system resources, and application health.
"""

import os
import psutil
import subprocess
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

class SystemStatus:
    """Provides comprehensive system status monitoring."""
    
    def __init__(self):
        self.current_dir = Path(__file__).parent.parent.absolute()
        
    def get_process_info(self, process_name: str) -> List[Dict[str, Any]]:
        """Get information about running processes matching the name."""
        processes = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time', 'memory_info', 'cpu_percent']):
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if process_name in cmdline:
                        processes.append({
                            'pid': proc.info['pid'],
                            'name': proc.info['name'],
                            'cmdline': cmdline,
                            'started': datetime.fromtimestamp(proc.info['create_time']).strftime('%Y-%m-%d %H:%M:%S'),
                            'uptime': self._format_uptime(time.time() - proc.info['create_time']),
                            'memory_mb': round(proc.info['memory_info'].rss / 1024 / 1024, 1),
                            'cpu_percent': proc.info['cpu_percent']
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            print(f"Error getting process info for {process_name}: {e}")
        
        return processes
    
    def _format_uptime(self, seconds: float) -> str:
        """Format uptime in human-readable format."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        elif seconds < 86400:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
        else:
            days = int(seconds // 86400)
            hours = int((seconds % 86400) // 3600)
            return f"{days}d {hours}h"
    
    def get_background_processes(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get information about background processes."""
        processes = {
            'bg_downloader': self.get_process_info('bg_downloader.py'),
            'background_transcribe': self.get_process_info('background_transcribe.py'),
            'bg_progress_watcher': self.get_process_info('bg_progress_watcher.py'),
        }
        
        return processes
    
    def get_gunicorn_status(self) -> Dict[str, Any]:
        """Get Gunicorn process information."""
        gunicorn_processes = self.get_process_info('gunicorn')
        
        if not gunicorn_processes:
            return {
                'status': 'stopped',
                'master_pid': None,
                'worker_count': 0,
                'workers': []
            }
        
        # Find master process (usually has 'master' in cmdline or is parent)
        master = None
        workers = []
        
        for proc in gunicorn_processes:
            if 'master' in proc['cmdline'].lower() or 'app:app' in proc['cmdline']:
                master = proc
            else:
                workers.append(proc)
        
        return {
            'status': 'running' if master else 'unknown',
            'master_pid': master['pid'] if master else None,
            'master_uptime': master['uptime'] if master else None,
            'worker_count': len(workers),
            'workers': workers,
            'total_memory_mb': sum(p['memory_mb'] for p in gunicorn_processes)
        }
    
    def get_systemd_service_status(self, service_name: str) -> Dict[str, Any]:
        """Get systemd service status."""
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', service_name],
                capture_output=True, text=True, timeout=5
            )
            is_active = result.stdout.strip() == 'active'
            
            # Get detailed status
            status_result = subprocess.run(
                ['systemctl', 'status', service_name, '--no-pager', '--lines=0'],
                capture_output=True, text=True, timeout=5
            )
            
            status_info = {
                'active': is_active,
                'status': result.stdout.strip(),
                'enabled': False,
                'main_pid': None,
                'memory': None,
                'uptime': None
            }
            
            # Parse status output for additional info
            if status_result.returncode == 0:
                lines = status_result.stdout.split('\n')
                for line in lines:
                    line = line.strip()
                    if 'Main PID:' in line:
                        try:
                            status_info['main_pid'] = int(line.split('Main PID:')[1].split()[0])
                        except (ValueError, IndexError):
                            pass
                    elif 'Memory:' in line:
                        try:
                            status_info['memory'] = line.split('Memory:')[1].strip()
                        except IndexError:
                            pass
            
            # Check if enabled
            enabled_result = subprocess.run(
                ['systemctl', 'is-enabled', service_name],
                capture_output=True, text=True, timeout=5
            )
            status_info['enabled'] = enabled_result.stdout.strip() == 'enabled'
            
            return status_info
            
        except subprocess.TimeoutExpired:
            return {'active': False, 'status': 'timeout', 'enabled': False}
        except Exception as e:
            return {'active': False, 'status': f'error: {e}', 'enabled': False}
    
    def get_port_info(self) -> Dict[str, Any]:
        """Get information about listening ports."""
        port_info = {
            'main_app': None,
            'listening_ports': []
        }
        
        try:
            # Get listening connections
            connections = psutil.net_connections(kind='inet')
            listening_ports = []
            
            for conn in connections:
                if conn.status == 'LISTEN' and conn.laddr:
                    port_details = {
                        'port': conn.laddr.port,
                        'address': conn.laddr.ip,
                        'pid': conn.pid,
                        'process_name': None
                    }
                    
                    # Get process name if PID is available
                    if conn.pid:
                        try:
                            process = psutil.Process(conn.pid)
                            port_details['process_name'] = process.name()
                            
                            # Check if this is our main app
                            if 'gunicorn' in process.name() or 'python' in process.name():
                                cmdline = ' '.join(process.cmdline())
                                if 'app.py' in cmdline or 'app:app' in cmdline:
                                    port_info['main_app'] = port_details
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    
                    listening_ports.append(port_details)
            
            # Sort by port number
            port_info['listening_ports'] = sorted(listening_ports, key=lambda x: x['port'])
            
        except Exception as e:
            print(f"Error getting port info: {e}")
        
        return port_info
    
    def get_directory_size(self, path: Path) -> int:
        """Get total size of a directory in bytes."""
        total_size = 0
        try:
            if path.exists():
                if path.is_file():
                    return path.stat().st_size
                for item in path.rglob('*'):
                    if item.is_file():
                        try:
                            total_size += item.stat().st_size
                        except (OSError, IOError):
                            pass
        except Exception:
            pass
        return total_size
    
    def get_disk_usage(self) -> Dict[str, Any]:
        """Get disk usage for key directories and overall disk info."""
        disk_info = {
            'directories': {},
            'disk_total': {},
            'app_total_gb': 0
        }
        
        try:
            # Get overall disk usage (where the app is installed)
            disk_usage = psutil.disk_usage(str(self.current_dir))
            disk_info['disk_total'] = {
                'total_gb': round(disk_usage.total / (1024**3), 2),
                'used_gb': round(disk_usage.used / (1024**3), 2),
                'free_gb': round(disk_usage.free / (1024**3), 2),
                'percent_used': round((disk_usage.used / disk_usage.total) * 100, 1)
            }
            
            # Get usage for app directories
            directories = {
                'downloads': self.current_dir / 'downloads',
                'logs': self.current_dir / 'logs',
                'transcripts': self.current_dir / 'transcript_jobs',
                'temp': self.current_dir / 'temp'
            }
            
            total_app_size = 0
            
            for name, path in directories.items():
                try:
                    if Path(path).exists():
                        dir_size = self.get_directory_size(Path(path))
                        total_app_size += dir_size
                        size_gb = round(dir_size / (1024**3), 2)
                        
                        disk_info['directories'][name] = {
                            'size_gb': size_gb,
                            'size_mb': round(dir_size / (1024**2), 2)
                        }
                    else:
                        disk_info['directories'][name] = {
                            'size_gb': 0,
                            'size_mb': 0,
                            'exists': False
                        }
                except Exception as e:
                    disk_info['directories'][name] = {'error': str(e)}
            
            # Calculate total app size and percentages
            disk_info['app_total_gb'] = round(total_app_size / (1024**3), 2)
            
            # Calculate percentage of app size each directory uses
            for name, info in disk_info['directories'].items():
                if 'size_gb' in info and total_app_size > 0:
                    info['percent_of_app'] = round((info['size_gb'] / disk_info['app_total_gb']) * 100, 1)
                else:
                    info['percent_of_app'] = 0
                    
        except Exception as e:
            print(f"Error getting disk usage: {e}")
            disk_info['error'] = str(e)
        
        return disk_info
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get general system information."""
        try:
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime_seconds = time.time() - psutil.boot_time()
            
            return {
                'hostname': os.uname().nodename,
                'platform': f"{os.uname().sysname} {os.uname().release}",
                'architecture': os.uname().machine,
                'boot_time': boot_time.strftime('%Y-%m-%d %H:%M:%S'),
                'uptime': self._format_uptime(uptime_seconds),
                'cpu_count': psutil.cpu_count(),
                'cpu_count_logical': psutil.cpu_count(logical=True),
                'load_average': os.getloadavg() if hasattr(os, 'getloadavg') else None,
                'python_version': f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}"
            }
        except Exception as e:
            return {'error': str(e)}
    
    def check_mysql_connection(self) -> Dict[str, Any]:
        """Check MySQL database connectivity using db_config.json."""
        try:
            db_config_path = self.current_dir / 'db_config.json'
            if not db_config_path.exists():
                return {
                    'active': False,
                    'status': 'error',
                    'message': 'db_config.json not found',
                    'enabled': False
                }
            
            with open(db_config_path, 'r') as f:
                config = json.load(f)
            
            # Check if using MySQL
            if config.get('type') != 'mysql' or 'mysql' not in config:
                return {
                    'active': False,
                    'status': 'info',
                    'message': 'Not using MySQL database (SQLite or other)',
                    'enabled': False
                }
            
            # Try to import mysql.connector
            try:
                import mysql.connector
            except ImportError:
                return {
                    'active': False,
                    'status': 'error',
                    'message': 'mysql-connector-python not installed',
                    'enabled': False
                }
            
            # Test the connection
            try:
                # Get MySQL config section
                mysql_config = config.get('mysql', {})
                
                # Handle different config formats
                db_user = mysql_config.get('user') or mysql_config.get('username') or mysql_config.get('db_user')
                db_password = mysql_config.get('password') or mysql_config.get('db_password')
                db_name = mysql_config.get('database') or mysql_config.get('db_name') or mysql_config.get('name')
                db_host = mysql_config.get('host', 'localhost')
                db_port = mysql_config.get('port', 3306)
                
                if not db_user or not db_password or not db_name:
                    return {
                        'active': False,
                        'status': 'error',
                        'message': 'Missing database credentials in mysql config section',
                        'enabled': False
                    }
                
                conn = mysql.connector.connect(
                    host=db_host,
                    port=db_port,
                    user=db_user,
                    password=db_password,
                    database=db_name,
                    connect_timeout=5
                )
                
                # Execute a simple query to verify connection
                cursor = conn.cursor()
                cursor.execute('SELECT 1')
                cursor.fetchone()
                cursor.close()
                conn.close()
                
                return {
                    'active': True,
                    'status': 'active',
                    'enabled': True,
                    'host': db_host,
                    'port': db_port,
                    'database': db_name,
                    'message': f"Connected to {db_host}:{db_port}"
                }
                
            except mysql.connector.Error as e:
                return {
                    'active': False,
                    'status': 'error',
                    'enabled': True,
                    'host': db_host,
                    'port': db_port,
                    'database': db_name,
                    'message': f"Connection failed: {str(e)}"
                }
                
        except Exception as e:
            return {
                'active': False,
                'status': 'error',
                'enabled': False,
                'message': f"Error checking MySQL: {str(e)}"
            }
    
    def get_comprehensive_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        return {
            'timestamp': datetime.now().isoformat(),
            'system_info': self.get_system_info(),
            'background_processes': self.get_background_processes(),
            'gunicorn_status': self.get_gunicorn_status(),
            'systemd_services': {
                'xspacedownloader-gunicorn': self.get_systemd_service_status('xspacedownloader-gunicorn'),
                'nginx': self.get_systemd_service_status('nginx')
            },
            'mysql_status': self.check_mysql_connection(),
            'port_info': self.get_port_info(),
            'disk_usage': self.get_disk_usage()
        }

# Global instance
system_status = SystemStatus()