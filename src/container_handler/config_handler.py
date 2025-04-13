import os
import json
from typing import Dict, Optional, List
from src.utils.logging import logger
from src.utils.constants import CONFIG_PATH, DEFAULT_CHECKPOINT_PATH, CONTAINER_CONFIG_PATHS

class ContainerConfigHandler:
    """Handler for container configuration validation and management."""
    
    def __init__(self):
        self.possible_config_paths = CONTAINER_CONFIG_PATHS
    
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

    def _get_env_var_value(self, container_id: str, namespace: str, var_name: str, default: Optional[str] = "0") -> Optional[str]:
        """
        Get value of a specific environment variable from container config.
        
        Args:
            container_id: Container ID
            namespace: Container namespace
            var_name: Name of the environment variable
            default: Default value if variable not found, None for path variables
            
        Returns:
            Optional[str]: Value of the environment variable or default
        """
        if not container_id or not namespace:
            logger.error(f"Invalid container_id or namespace: id={container_id}, namespace={namespace}")
            return default
            
        try:
            config_path = self._find_config_path(namespace, container_id)
            if not config_path:
                return default
                
            config = self._read_config(config_path)
            if not config or 'process' not in config:
                return default
                
            env_vars = config['process'].get('env', [])
            for var in env_vars:
                if var.startswith(f"{var_name}="):
                    return var.split('=', 1)[1]
            return default
            
        except Exception as e:
            logger.error(f"Error reading config for container {container_id}: {str(e)}")
            return default
    
    def is_tardis_enabled(self, container_id: str, namespace: str) -> bool:
        """
        Check if a container is Tardis-enabled.
        
        Args:
            container_id: Container ID
            namespace: Container namespace
            
        Returns:
            bool: True if Tardis is enabled, False otherwise
        """
        is_enabled = self._get_env_var_value(container_id, namespace, "TARDIS_ENABLE") == "1"
        logger.info(f"Container {container_id} is Tardis-enabled" if is_enabled else f"Container {container_id} is not Tardis-enabled")
        return is_enabled

    def get_checkpoint_path(self, container_id: str, namespace: str) -> Optional[str]:
        """
        Get checkpoint path following priority rules.
        
        Args:
            container_id: Container ID
            namespace: Container namespace
            
        Returns:
            Optional[str]: Checkpoint path if found, None otherwise
        """
        try:
            # Check networkfs path first
            networkfs_path = self._get_env_var_value(container_id, namespace, "TARDIS_NETWORKFS_HOST_PATH", default=None)
            if networkfs_path:
                return os.path.join(networkfs_path, "checkpoint", namespace, container_id)
            
            # Then checkpoint host path
            checkpoint_path = self._get_env_var_value(container_id, namespace, "TARDIS_CHECKPOINT_HOST_PATH", default=None)
            if checkpoint_path:
                return os.path.join(checkpoint_path, namespace, container_id)
            
            # Finally default path
            return os.path.join(DEFAULT_CHECKPOINT_PATH, namespace, container_id)
            
        except Exception as e:
            logger.error(f"Error getting checkpoint path for container {container_id}: {str(e)}")
            return None

