import json
import subprocess
import os
from typing import Optional, Tuple
from src.utils.logging import logger
from src.utils.constants import ENV_REAL_RUNC_CMD, CONFIG_PATH

class ContainerRuntimeState:
    """Handles container runtime state operations."""
    
    def __init__(self, runc_cmd: Optional[str] = None):
        """
        Initialize ContainerRuntimeState.
        
        Args:
            runc_cmd: Optional path to the runc binary. If not provided, will try to find it.
        """
        self.runc_cmd = runc_cmd or self._get_real_runc_cmd()
        
    def _get_real_runc_cmd(self) -> str:
        """Get the path to the real Runc binary from environment variable or env file"""
        # Try environment variable first
        env_cmd = os.environ.get(ENV_REAL_RUNC_CMD)
        if env_cmd and os.path.exists(env_cmd) and os.access(env_cmd, os.X_OK):
            logger.info("Using real runc from environment variable: %s", env_cmd)
            return env_cmd
            
        # Try reading from tardis.env file
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r') as f:
                    for line in f:
                        if line.startswith(f'{ENV_REAL_RUNC_CMD}='):
                            path = line.split('=', 1)[1].strip()
                            if os.path.exists(path) and os.access(path, os.X_OK):
                                logger.info("Using real runc from config file: %s", path)
                                return path
            except Exception as e:
                logger.error("Error reading %s: %s", CONFIG_PATH, str(e))
                
        logger.error("Could not find runc binary")
        raise RuntimeError("Could not find runc binary")
        
    def get_container_state(self, container_id: str, namespace: str) -> Tuple[Optional[str], Optional[int]]:
        """
        Get container state and exit code.
        
        Args:
            container_id: Container ID
            namespace: Container namespace
            
        Returns:
            Tuple[Optional[str], Optional[int]]: Container state and exit code
        """
        try:
            # Convert namespace to global options with correct containerd runtime path
            global_options = {'--root': f'/run/containerd/runc/{namespace}'}
            
            # Build state command
            cmd = ['sudo', self.runc_cmd]
            for opt, value in global_options.items():
                cmd.extend([opt, value])
            cmd.extend(['state', container_id])
            
            # Log the exact command
            logger.info("Running command: %s", ' '.join(cmd))
            
            # Execute command
            result = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if result.returncode != 0:
                logger.warning("Failed to get state for container %s: %s", container_id, result.stderr)
                return None, None
                
            # Parse output
            try:
                state_data = json.loads(result.stdout)
                return state_data.get('status'), state_data.get('exitCode')
            except json.JSONDecodeError as e:
                logger.error("Failed to parse state output for container %s: %s", container_id, str(e))
                return None, None
                
        except Exception as e:
            logger.error("Error getting state for container %s: %s", container_id, str(e))
            return None, None 