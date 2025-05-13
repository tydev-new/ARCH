#!/usr/bin/env python3
import sys
import subprocess
import argparse
import os
from typing import List, Dict
from src.utils.logging import logger, setup_logger
from src.container_handler.flag_manager import ContainerFlagManager
from src.container_handler.runtime_state import ContainerRuntimeState
from src.utils.constants import CONFIG_PATH, LOG_FILE, USER_CONFIG_PATH

HELP_TEXT = '''ARCH CLI - Container Management Tool

Commands:
  container finalize    Finalize all ARCH containers
  log                  Configure logging settings

Logging Configuration:
  --level LEVEL        Set log level
                       DEBUG: Detailed debugging information
                       INFO: General operational information
                       WARNING: Warning messages
                       ERROR: Error messages only

  --file FILE          Set log file path
                       Examples:
                       - /var/log/arch.log
                       - ./logs/arch.log

Examples:
  # Finalize all ARCH containers
  arch-cli container finalize

  # Configure logging
  arch-cli log --level DEBUG --file /var/log/arch.log
'''

def parse_args(args=None):
    """Parse command line arguments.
    
    Args:
        args: Optional list of arguments. If None, uses sys.argv[1:].
    """
    parser = argparse.ArgumentParser(
        description=HELP_TEXT,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command')
    
    # Container finalize command
    container_parser = subparsers.add_parser('container')
    container_subparsers = container_parser.add_subparsers(dest='container_command')
    container_subparsers.add_parser('finalize')
    
    # Logging configuration command
    log_parser = subparsers.add_parser('log')
    log_parser.add_argument('--level', 
                          choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])
    log_parser.add_argument('--file')
    
    return parser.parse_args(args)

def configure_logging(args):
    """Configure logging based on command line arguments."""
    global logger
    
    if args.command == 'log':
        # Read existing config
        config = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and '=' in line:
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
        
        # Update config with new values
        if args.level:
            config['ARCH_LOG_LEVEL'] = args.level
        if args.file:
            # Convert relative path to absolute if needed
            log_path = os.path.abspath(args.file)
            config['ARCH_LOG_FILE'] = log_path
            
        # Create user config directory if needed
        try:
            os.makedirs(USER_CONFIG_PATH, mode=0o777, exist_ok=True)
        except PermissionError:
            logger.error("Permission denied: Cannot create config directory. Try running with sudo.")
            return False
            
        # Write updated config
        try:
            with open(CONFIG_PATH, 'w') as f:
                for key, value in sorted(config.items()):
                    f.write(f"{key}={value}\n")
            # Try to set permissions, but don't fail if we can't
            #try:
            #    os.chmod(CONFIG_PATH, 0o666)  # rw-rw-rw-
            #except PermissionError:
            #    logger.warning("Could not set config file permissions. Some features may be limited.")
        except PermissionError:
            logger.error("Permission denied: Cannot write to config file. Try running with sudo.")
            return False
        
        # Update the logger with new config
        logger = setup_logger('arch')
                
        logger.info("Logging configured - level: %s, file: %s", 
                   config.get('ARCH_LOG_LEVEL', 'not changed'),
                   config.get('ARCH_LOG_FILE', 'not changed'))
        return True
    return False

def get_arch_containers() -> List[Dict[str, str]]:
    """Get list of arch-enabled containers."""
    flag_manager = ContainerFlagManager()
    containers = []
    
    # Get all containers with flag files
    for namespace, container_id in flag_manager.list_containers():
        containers.append({
            'id': container_id,
            'namespace': namespace
        })
    
    return containers

def finalize_container(container_id: str, namespace: str) -> bool:
    """Finalize a single container by checkpointing and exiting it."""
    try:
        # Check container state
        runtime_state = ContainerRuntimeState()
        container_state, _ = runtime_state.get_container_state(container_id, namespace)
        
        if container_state != 'running':
            logger.warning("Container %s is not running (state: %s), skipping", container_id, container_state)
            return False
            
        # Build checkpoint command using ctr
        cmd = ['sudo', 'ctr', '--namespace', namespace, 'containers', 'checkpoint', '--task', container_id, f'checkpoint/{container_id}']
        
        # Log the exact command
        logger.info("Executing checkpoint command: %s", ' '.join(cmd))
        
        # Execute checkpoint
        logger.info("Checkpointing container %s in namespace %s", container_id, namespace)
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning("Failed to checkpoint container %s: %s, %s", container_id,result.returncode, result.stderr)
            
        # Kill the task
        cmd = ['sudo', 'ctr', '--namespace', namespace, 'task', 'kill', container_id]
        logger.info("Killing task for container %s", container_id)
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning("Failed to kill task for container %s: %s, %s", container_id, result.returncode, result.stderr)
            
        # Remove the task
        cmd = ['sudo', 'ctr', '--namespace', namespace, 'task', 'rm', container_id]
        logger.info("Removing task for container %s", container_id)
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning("Failed to remove task for container %s: %s, %s", container_id, result.returncode, result.stderr)
            
        # Remove the container
        cmd = ['sudo', 'ctr', '--namespace', namespace, 'container', 'rm', container_id]
        logger.info("Removing container %s", container_id)
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning("Failed to remove container %s: %s, %s", container_id, result.returncode, result.stderr)
            
        return True
        
    except Exception as e:
        logger.error("Error finalizing container %s: %s", container_id, str(e))
        return False

def main():
    """Main function to handle ARCH CLI commands."""
    args = parse_args()
    
    if args.command == 'log':
        configure_logging(args)
        return 0
        
    if args.command != 'container' or args.container_command != 'finalize':
        logger.error("Invalid command. Use 'arch-cli container finalize' or 'arch-cli log --level LEVEL --file FILE'")
        return 1
        
    containers = get_arch_containers()
    if not containers:
        logger.info("No arch-enabled containers found")
        return 0
        
    logger.info("Found %d arch-enabled containers to finalize", len(containers))
    
    success = True
    for container in containers:
        if not finalize_container(container['id'], container['namespace']):
            success = False
            
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main()) 