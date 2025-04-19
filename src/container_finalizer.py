#!/usr/bin/env python3
import sys
import subprocess
from typing import List, Dict
from src.utils.logging import logger
from src.container_handler.flag_manager import ContainerFlagManager
from src.container_handler.runtime_state import ContainerRuntimeState

def get_tardis_containers() -> List[Dict[str, str]]:
    """Get list of tardis-enabled containers."""
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
    """Main function to finalize all tardis-enabled containers."""
    containers = get_tardis_containers()
    if not containers:
        logger.info("No tardis-enabled containers found")
        return 0
        
    logger.info("Found %d tardis-enabled containers to finalize", len(containers))
    
    success = True
    for container in containers:
        if not finalize_container(container['id'], container['namespace']):
            success = False
            
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main()) 