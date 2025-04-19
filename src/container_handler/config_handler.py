import os
import json
import shutil
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
            logger.debug(f"Checking path: {path}")
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
    
    def _ensure_directory(self, path: str) -> bool:
        """
        Create directory if it doesn't exist.
        
        Args:
            path: Directory path to create
            
        Returns:
            bool: True if directory exists or was created, False on error
        """
        try:
            os.makedirs(path, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Failed to create directory {path}: {e}")
            return False
    
    def is_arch_enabled(self, container_id: str, namespace: str) -> bool:
        """
        Check if a container is ARCH-enabled.
        
        Args:
            container_id: Container ID
            namespace: Container namespace
            
        Returns:
            bool: True if ARCH is enabled, False otherwise
        """
        is_enabled = self._get_env_var_value(container_id, namespace, "ARCH_ENABLE") == "1"
        logger.info(f"Container {container_id} is ARCH-enabled" if is_enabled else f"Container {container_id} is not ARCH-enabled")
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
            # Check sharedfs path first
            sharedfs_path = self._get_env_var_value(container_id, namespace, "ARCH_SHAREDFS_HOST_PATH", default=None)
            if sharedfs_path:
                return os.path.join(sharedfs_path, "checkpoint", namespace, container_id)
            
            # Then checkpoint host path
            checkpoint_path = self._get_env_var_value(container_id, namespace, "ARCH_CHECKPOINT_HOST_PATH", default=None)
            if checkpoint_path:
                return os.path.join(checkpoint_path, namespace, container_id)
            
            # Finally default path
            return os.path.join(DEFAULT_CHECKPOINT_PATH, namespace, container_id)
            
        except Exception as e:
            logger.error(f"Error getting checkpoint path for container {container_id}: {str(e)}")
            return None

    def add_bind_mount(self, container_id: str, namespace: str) -> bool:
        """
        Add bind mount to container config if ARCH_SHAREDFS_HOST_PATH is set.
        Uses ARCH_WORKDIR_CONTAINER_PATH as destination, defaults to /tmp if not set.
        Also sets the working directory to the destination path.
        
        Args:
            container_id: Container ID
            namespace: Container namespace
            
        Returns:
            bool: True if bind mount added successfully, False otherwise
        """
        sharedfs_path = self._get_env_var_value(container_id, namespace, "ARCH_SHAREDFS_HOST_PATH", default=None)
        if not sharedfs_path:
            return True  # No sharedfs path, nothing to do
            
        # Get destination path from ARCH_WORKDIR_CONTAINER_PATH, default to /tmp
        dest_path = self._get_env_path(container_id, namespace, "ARCH_WORKDIR_CONTAINER_PATH", default="/tmp")
        
        # Build source path under work directory
        source_path = os.path.join(sharedfs_path, "work", namespace, container_id)
        
        # Create work directory
        if not self._ensure_directory(source_path):
            logger.warning(f"Failed to create work directory {source_path}")
            return False
            
        # Get config path and runtime directory
        config_path = self._find_config_path(namespace, container_id)
        if not config_path:
            return False
            
        # Get runtime directory (parent of config.json)
        runtime_dir = os.path.dirname(config_path)
        
        # Find rootfs directory in runtime directory
        rootfs_path = os.path.join(runtime_dir, "rootfs")
        if not os.path.exists(rootfs_path):
            logger.warning(f"Rootfs directory not found at {rootfs_path}")
            return False
            
        # Check if destination exists in container rootfs
        dest_in_rootfs = os.path.join(rootfs_path, dest_path.lstrip('/'))
        if not os.path.exists(dest_in_rootfs):
            logger.warning(f"Destination path {dest_path} does not exist in container rootfs at {dest_in_rootfs}")
            return False
            
        # Get config
        config = self._read_config(config_path)
        if not config:
            return False
            
        # Initialize mounts array if not exists
        if 'mounts' not in config:
            config['mounts'] = []
            
        # Check if destination is already mounted
        for mount in config['mounts']:
            if mount.get('destination') == dest_path:
                logger.warning(f"Destination path {dest_path} is already mounted to {mount.get('source')}")
                return False
            
        # Check if source path is already mounted
        for mount in config['mounts']:
            if mount.get('type') == 'bind' and mount.get('source') == source_path:
                logger.warning(f"Source path {source_path} is already mounted to {mount.get('destination')}")
                return False
            
        # Add new bind mount
        config['mounts'].append({
            'type': 'bind',
            'source': source_path,
            'destination': dest_path,
            'options': ['rbind', 'rw']
        })
        
        # Set working directory
        if 'process' not in config:
            config['process'] = {}
            
        if 'cwd' in config['process']:
            logger.warning(f"Working directory already set to {config['process']['cwd']}, updating to {dest_path}")
            
        config['process']['cwd'] = dest_path
        
        # Write updated config
        try:
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to update config.json: {e}")
            return False

    def delete_work_directory(self, container_id: str, namespace: str) -> bool:
        """
        Delete the work directory for a container if it exists.
        
        Args:
            container_id: Container ID
            namespace: Container namespace
            
        Returns:
            bool: True if directory deleted or doesn't exist, False on error
        """
        # Get sharedfs path
        sharedfs_path = self._get_env_var_value(container_id, namespace, "ARCH_SHAREDFS_HOST_PATH", default=None)
        if not sharedfs_path:
            return True  # No sharedfs path, nothing to do
            
        # Build work directory path
        work_dir = os.path.join(sharedfs_path, "work", namespace, container_id)
        
        # Delete work directory if it exists
        try:
            if os.path.exists(work_dir):
                shutil.rmtree(work_dir)
                logger.info(f"Deleted work directory {work_dir}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete work directory {work_dir}: {e}")
            return False

    def has_bind_mount(self, container_id: str, namespace: str) -> bool:
        """
        Check if a container has a bind mount by checking if ARCH_SHAREDFS_HOST_PATH is set.
        
        Args:
            container_id: Container ID
            namespace: Container namespace
            
        Returns:
            bool: True if container has bind mount, False otherwise
        """
        sharedfs_path = self._get_env_var_value(container_id, namespace, "ARCH_SHAREDFS_HOST_PATH", default=None)
        return sharedfs_path is not None

