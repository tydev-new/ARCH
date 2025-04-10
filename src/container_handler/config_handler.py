import os
import json
from typing import Dict, Optional, Tuple
from src.utils.logging import logger

class ContainerConfigHandler:
    """Handler for container configuration validation and management."""
    
    def __init__(self):
        self.possible_config_paths = [
            "/run/containerd/io.containerd.runtime.v2.task/{namespace}/{container_id}/config.json",
            "/run/containerd/runc/{namespace}/{container_id}/config.json",
            "/run/runc/{namespace}/{container_id}/config.json"
        ]
    
    def _find_config_path(self, namespace: str, container_id: str) -> Optional[str]:
        """
        Find the container's config.json file.
        
        Args:
            namespace: Container namespace
            container_id: Container ID
            
        Returns:
            str: Path to config.json if found, None otherwise
        """
        for path_template in self.possible_config_paths:
            path = path_template.format(
                namespace=namespace,
                container_id=container_id
            )
            if os.path.exists(path):
                logger.debug(f"Found config.json at: {path}")
                return path
                
        logger.error(f"Could not find config.json for container {container_id} in namespace {namespace}")
        return None
    
    def _read_config(self, config_path: str) -> Optional[Dict]:
        """
        Read and parse the container's config.json file.
        
        Args:
            config_path: Path to config.json
            
        Returns:
            Dict: Parsed config if successful, None otherwise
        """
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                logger.debug(f"Successfully read config.json from {config_path}")
                return config
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to read config.json from {config_path}: {str(e)}")
            return None

    def _validate_config(self, config: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validate container config structure and extract environment variables.
        
        Args:
            config: Container configuration dictionary
            
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        if 'process' not in config:
            return False, "'process'"
        return True, None

    def _get_env_vars(self, config: Dict) -> list:
        """
        Extract environment variables from config.
        
        Args:
            config: Container configuration dictionary
            
        Returns:
            list: Environment variables
        """
        return config['process'].get('env', [])
    
    def is_tardis_enabled(self, container_id: str, namespace: str) -> bool:
        """
        Check if a container is Tardis-enabled.
        
        Args:
            container_id: Container ID
            namespace: Container namespace
            
        Returns:
            bool: True if Tardis is enabled, False otherwise
        """
        if not container_id or not namespace:
            logger.error(f"Invalid container_id or namespace: id={container_id}, namespace={namespace}")
            return False
            
        try:
            # Find and read config
            config_path = self._find_config_path(namespace, container_id)
            if not config_path:
                return False
                
            config = self._read_config(config_path)
            if not config:
                return False
            
            # Validate config structure
            is_valid, error = self._validate_config(config)
            if not is_valid:
                logger.error(f"Error checking Tardis enable status: {error}")
                return False
            
            # Check for Tardis enable flag
            env = self._get_env_vars(config)
            is_enabled = 'TARDIS_ENABLE=1' in env
            logger.info(f"Container {container_id} is Tardis-enabled" if is_enabled else f"Container {container_id} is not Tardis-enabled")
            return is_enabled
            
        except Exception as e:
            logger.error(f"Error checking Tardis status for container {container_id}: {str(e)}")
            return False
    
    def get_checkpoint_path(self, container_id: str, namespace: str) -> Optional[str]:
        """
        Get the checkpoint path from container config.
        
        Args:
            container_id: Container ID
            namespace: Container namespace
            
        Returns:
            str: Checkpoint path if specified, None otherwise
        """
        if not container_id or not namespace:
            logger.error(f"Invalid container_id or namespace: id={container_id}, namespace={namespace}")
            return None
            
        try:
            # Find and read config
            config_path = self._find_config_path(namespace, container_id)
            if not config_path:
                return None
                
            config = self._read_config(config_path)
            if not config:
                return None
            
            # Validate config structure
            is_valid, error = self._validate_config(config)
            if not is_valid:
                logger.error(f"Error getting checkpoint path: {error}")
                return None
            
            # Look for checkpoint path
            env = self._get_env_vars(config)
            for var in env:
                if var.startswith('TARDIS_CHECKPOINT_HOST_PATH='):
                    path = var.split('=', 1)[1]
                    logger.debug(f"Found checkpoint path: {path}")
                    return path
                    
            logger.debug("No checkpoint path specified in config")
            return None
        except Exception as e:
            logger.error(f"Error getting checkpoint path: {str(e)}")
            return None

