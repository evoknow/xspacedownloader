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
    
    def get_disk_usage(self) -> Dict[str, Any]:
        """Get disk usage for key directories."""
        disk_info = {}
        
        try:
            # Get usage for main directories
            directories = {
                'root': '/',
                'downloads': self.current_dir / 'downloads',
                'logs': self.current_dir / 'logs',
                'transcripts': self.current_dir / 'transcript_jobs'
            }
            
            for name, path in directories.items():
                try:
                    if Path(path).exists():
                        usage = psutil.disk_usage(str(path))
                        disk_info[name] = {
                            'total_gb': round(usage.total / (1024**3), 2),
                            'used_gb': round(usage.used / (1024**3), 2),
                            'free_gb': round(usage.free / (1024**3), 2),
                            'percent_used': round((usage.used / usage.total) * 100, 1)
                        }
                except Exception as e:
                    disk_info[name] = {'error': str(e)}
                    
        except Exception as e:
            print(f"Error getting disk usage: {e}")
        
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
                conn = mysql.connector.connect(
                    host=config.get('host', 'localhost'),
                    port=config.get('port', 3306),
                    user=config['user'],
                    password=config['password'],
                    database=config['database'],
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
                    'host': config.get('host', 'localhost'),
                    'port': config.get('port', 3306),
                    'database': config.get('database', 'unknown'),
                    'message': f"Connected to {config.get('host', 'localhost')}:{config.get('port', 3306)}"
                }
                
            except mysql.connector.Error as e:
                return {
                    'active': False,
                    'status': 'error',
                    'enabled': True,
                    'host': config.get('host', 'localhost'),
                    'port': config.get('port', 3306),
                    'database': config.get('database', 'unknown'),
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
                'xspacedownloader-bg': self.get_systemd_service_status('xspacedownloader-bg'),
                'xspacedownloader-transcribe': self.get_systemd_service_status('xspacedownloader-transcribe'),
                'nginx': self.get_systemd_service_status('nginx')
            },
            'mysql_status': self.check_mysql_connection(),
            'port_info': self.get_port_info(),
            'disk_usage': self.get_disk_usage()
        }

# Global instance
system_status = SystemStatus()