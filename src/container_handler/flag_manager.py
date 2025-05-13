import os
import json
import fcntl
from datetime import datetime
from typing import Dict, Optional, Tuple, List
from src.utils.logging import logger
from src.utils.constants import STATE_PATH

class ContainerFlagManager:
    """Manages container state in a persistent and atomic way.
    
    This class is process-safe using file locking (fcntl) to handle concurrent access
    from multiple processes. Each container's state is stored in a separate JSON file
    to allow independent access and better concurrency.
    """
    
    STATE_VERSION = '1.0'
    REQUIRED_FIELDS = {'version', 'skip_start', 'skip_resume', 'keep_resources', 'exit_code', 'last_updated'}
    
    def __init__(self, state_dir: str = STATE_PATH):
        """
        Initialize the state manager.
        
        Args:
            state_dir: Directory to store state files
        """
        self.state_dir = state_dir
        os.makedirs(state_dir, mode=0o755, exist_ok=True)
        
    def _get_flag_file(self, namespace: str, container_id: str) -> str:
        """Get the path to the flag file for a container."""
        return os.path.join(self.state_dir, f"{namespace}_{container_id}.json")
        
    def _validate_flag(self, flag_data: Dict) -> bool:
        """
        Validate flag structure.
        
        Args:
            flag_data: Flag dictionary to validate
            
        Returns:
            bool: True if flag data is valid, False otherwise
        """
        return all(field in flag_data for field in self.REQUIRED_FIELDS)
        
    def _create_initial_flag(self) -> Dict:
        """
        Create initial flag structure.
        
        Returns:
            Dict: Initial flag data with all required fields
        """
        return {
            'version': self.STATE_VERSION,
            'skip_start': False,
            'skip_resume': False,
            'keep_resources': False,
            'exit_code': None,
            'last_updated': datetime.now().isoformat()
        }
        
    def _read_flag(self, flag_file: str) -> Optional[Dict]:
        """Read container flag from file with file locking.
        
        Uses fcntl.LOCK_SH for shared (read) access, allowing multiple processes
        to read simultaneously while preventing writes.
        
        Returns:
            Optional[Dict]: Flag dictionary if valid, None if file not found or invalid
        """
        try:
            with open(flag_file, 'r') as f:
                try:
                    # Acquire shared lock for reading
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                    flag_data = json.load(f)
                    if not self._validate_flag(flag_data):
                        logger.warning(f"Invalid flag structure in {flag_file}")
                        return None
                    return flag_data
                except IOError as e:
                    logger.warning(f"Failed to lock flag file {flag_file}: {e}")
                    return None
                finally:
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    except IOError:
                        pass
        except (FileNotFoundError, json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to read flag file {flag_file}: {e}")
            return None
            
    def _write_flag(self, flag_file: str, flag_data: Dict) -> None:
        """Write container flag to file with file locking.
        
        Uses fcntl.LOCK_EX for exclusive access, ensuring only one process
        can write at a time while preventing any reads.
        
        Raises:
            ValueError: If flag structure is invalid
            IOError: If file operations fail
        """
        if not self._validate_flag(flag_data):
            raise ValueError(f"Invalid flag structure for {flag_file}")
            
        try:
            with open(flag_file, 'w') as f:
                try:
                    # Acquire exclusive lock for writing
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    json.dump(flag_data, f)
                except IOError as e:
                    logger.error(f"Failed to lock flag file {flag_file}: {e}")
                    raise
                finally:
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    except IOError:
                        pass
        except (IOError, OSError) as e:
            logger.error(f"Failed to write flag file {flag_file}: {e}")
            raise

    def has_flag(self, namespace: str, container_id: str) -> bool:
        """
        Check if flag exists for a container.
        
        Args:
            namespace: Container namespace
            container_id: Container ID
            
        Returns:
            bool: True if flag exists, False otherwise
        """
        flag_file = self._get_flag_file(namespace, container_id)
        return os.path.exists(flag_file)

    def list_containers(self) -> List[Tuple[str, str]]:
        """
        List all containers that have flag files.
        
        Returns:
            List[Tuple[str, str]]: List of (namespace, container_id) tuples
        """
        containers = []
        try:
            for filename in os.listdir(self.state_dir):
                if filename.endswith('.json'):
                    # Extract namespace and container_id from filename
                    parts = filename[:-5].split('_', 1)  # Remove .json and split
                    if len(parts) == 2:
                        namespace, container_id = parts
                        containers.append((namespace, container_id))
        except OSError as e:
            logger.error(f"Failed to list containers: {e}")
        return containers

    def create_flag(self, namespace: str, container_id: str) -> None:
        """
        Create initial flag file for a container.
        Called by RuncHandler during container create if container is Tardis-enabled.
        If flag already exists, it will be overwritten with fresh flag data.
        
        Args:
            namespace: Container namespace
            container_id: Container ID
            
        Raises:
            IOError: If file operations fail
        """
        flag_file = self._get_flag_file(namespace, container_id)
        initial_flag = self._create_initial_flag()
        self._write_flag(flag_file, initial_flag)
        logger.info(f"Created flag file for container {container_id} in namespace {namespace}")
                
    def set_skip_start(self, namespace: str, container_id: str, value: bool) -> None:
        """Set the skip_start flag for a container."""
        self._set_flag(namespace, container_id, 'skip_start', value)
        
    def get_skip_start(self, namespace: str, container_id: str) -> bool:
        """Get the skip_start flag for a container."""
        return self._get_flag(namespace, container_id, 'skip_start', False)
        
    def set_skip_resume(self, namespace: str, container_id: str, value: bool) -> None:
        """Set the skip_resume flag for a container."""
        self._set_flag(namespace, container_id, 'skip_resume', value)
        
    def get_skip_resume(self, namespace: str, container_id: str) -> bool:
        """Get the skip_resume flag for a container."""
        return self._get_flag(namespace, container_id, 'skip_resume', False)
        
    def set_exit_code(self, namespace: str, container_id: str, exit_code: int) -> None:
        """Set the exit code for a container."""
        self._set_flag(namespace, container_id, 'exit_code', exit_code)
        
    def get_exit_code(self, namespace: str, container_id: str) -> Optional[int]:
        """Get the exit code for a container."""
        return self._get_flag(namespace, container_id, 'exit_code', None)
        
    def clear_flag(self, namespace: str, container_id: str) -> None:
        """
        Clear all flag data for a container by deleting its flag file.
        
        Args:
            namespace: Container namespace
            container_id: Container ID
            
        Raises:
            IOError: If file operations fail
        """
        flag_file = self._get_flag_file(namespace, container_id)
        try:
            os.remove(flag_file)
            logger.info(f"Cleared flag for container {container_id} in namespace {namespace}")
        except FileNotFoundError:
            pass

    def set_keep_resources(self, namespace: str, container_id: str, value: bool) -> None:
        """Set the keep_resources flag for a container."""
        self._set_flag(namespace, container_id, 'keep_resources', value)
        
    def get_keep_resources(self, namespace: str, container_id: str) -> bool:
        """Get the keep_resources flag for a container."""
        return self._get_flag(namespace, container_id, 'keep_resources', False)

    def _get_flag(self, namespace: str, container_id: str, flag_name: str, default_value: any = False) -> any:
        """
        Generic method to get a flag value from container flag.
        
        Args:
            namespace: Container namespace
            container_id: Container ID
            flag_name: Name of the flag to get
            default_value: Default value to return if flag doesn't exist or is invalid
            
        Returns:
            any: Value of the flag or default value
        """
        flag_file = self._get_flag_file(namespace, container_id)
        try:
            flag_data = self._read_flag(flag_file)
            return flag_data.get(flag_name, default_value) if flag_data else default_value
        except (FileNotFoundError, json.JSONDecodeError):
            logger.warning(f"Cannot get {flag_name}: no flag file found for container {container_id} in namespace {namespace}")
            return default_value

    def _set_flag(self, namespace: str, container_id: str, flag_name: str, value: any) -> None:
        """
        Generic method to set a flag value in container flag.
        
        Args:
            namespace: Container namespace
            container_id: Container ID
            flag_name: Name of the flag to set
            value: Value to set for the flag
        """
        if not self.has_flag(namespace, container_id):
            logger.warning(f"Cannot set {flag_name}: no flag exists for container {container_id}")
            return
            
        flag_file = self._get_flag_file(namespace, container_id)
        try:
            flag_data = self._read_flag(flag_file)
            if flag_data is None:
                logger.warning(f"Cannot set {flag_name}: failed to read flag for container {container_id}")
                return
            flag_data[flag_name] = value
            flag_data['last_updated'] = datetime.now().isoformat()
            self._write_flag(flag_file, flag_data)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.warning(f"Cannot set {flag_name}: no flag file found for container {container_id} in namespace {namespace}")
