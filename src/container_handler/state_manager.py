import os
import json
import fcntl
from datetime import datetime
from typing import Dict, Optional, Tuple, List
from src.utils.logging import logger
from src.utils.constants import STATE_DIR

class ContainerStateManager:
    """Manages container state in a persistent and atomic way.
    
    This class is process-safe using file locking (fcntl) to handle concurrent access
    from multiple processes. Each container's state is stored in a separate JSON file
    to allow independent access and better concurrency.
    """
    
    STATE_VERSION = '1.0'
    REQUIRED_FIELDS = {'version', 'skip_start', 'skip_resume', 'exit_code', 'last_updated'}
    
    def __init__(self, state_dir: str = STATE_DIR):
        """
        Initialize the state manager.
        
        Args:
            state_dir: Directory to store state files
        """
        self.state_dir = state_dir
        os.makedirs(state_dir, mode=0o755, exist_ok=True)
        
    def _get_state_file(self, namespace: str, container_id: str) -> str:
        """Get the path to the state file for a container."""
        return os.path.join(self.state_dir, f"{namespace}_{container_id}.json")
        
    def _validate_state(self, state: Dict) -> bool:
        """
        Validate state structure.
        
        Args:
            state: State dictionary to validate
            
        Returns:
            bool: True if state is valid, False otherwise
        """
        return all(field in state for field in self.REQUIRED_FIELDS)
        
    def _create_initial_state(self) -> Dict:
        """
        Create initial state structure.
        
        Returns:
            Dict: Initial state with all required fields
        """
        return {
            'version': self.STATE_VERSION,
            'skip_start': False,
            'skip_resume': False,
            'exit_code': None,
            'last_updated': datetime.now().isoformat()
        }
        
    def _read_state(self, state_file: str) -> Dict:
        """Read container state from file with file locking.
        
        Uses fcntl.LOCK_SH for shared (read) access, allowing multiple processes
        to read simultaneously while preventing writes.
        
        Raises:
            ValueError: If state structure is invalid
            IOError: If file operations fail
        """
        try:
            with open(state_file, 'r') as f:
                # Acquire shared lock for reading
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    state = json.load(f)
                    if not self._validate_state(state):
                        raise ValueError(f"Invalid state structure in {state_file}")
                    return state
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to read state file {state_file}: {e}")
            raise
            
    def _write_state(self, state_file: str, state: Dict) -> None:
        """Write container state to file with file locking.
        
        Uses fcntl.LOCK_EX for exclusive access, ensuring only one process
        can write at a time while preventing any reads.
        
        Raises:
            ValueError: If state structure is invalid
            IOError: If file operations fail
        """
        if not self._validate_state(state):
            raise ValueError(f"Invalid state structure for {state_file}")
            
        try:
            with open(state_file, 'w') as f:
                # Acquire exclusive lock for writing
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(state, f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except (IOError, OSError) as e:
            logger.error(f"Failed to write state file {state_file}: {e}")
            raise

    def has_state(self, namespace: str, container_id: str) -> bool:
        """
        Check if state exists for a container.
        
        Args:
            namespace: Container namespace
            container_id: Container ID
            
        Returns:
            bool: True if state exists, False otherwise
        """
        state_file = self._get_state_file(namespace, container_id)
        return os.path.exists(state_file)

    def list_containers(self) -> List[Tuple[str, str]]:
        """
        List all containers that have state files.
        
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

    def create_state(self, namespace: str, container_id: str) -> None:
        """
        Create initial state file for a container.
        Called by RuncHandler during container create if container is Tardis-enabled.
        
        Args:
            namespace: Container namespace
            container_id: Container ID
            
        Raises:
            ValueError: If state already exists
            IOError: If file operations fail
        """
        if self.has_state(namespace, container_id):
            raise ValueError(f"State already exists for container {container_id} in namespace {namespace}")
            
        state_file = self._get_state_file(namespace, container_id)
        initial_state = self._create_initial_state()
        self._write_state(state_file, initial_state)
        logger.info(f"Created state file for container {container_id} in namespace {namespace}")
                
    def set_skip_start(self, namespace: str, container_id: str, value: bool) -> None:
        """
        Set the skip_start flag for a container.
        
        Args:
            namespace: Container namespace
            container_id: Container ID
            value: True to skip start, False otherwise
            
        Raises:
            ValueError: If state doesn't exist
            IOError: If file operations fail
        """
        if not self.has_state(namespace, container_id):
            raise ValueError(f"Cannot set skip_start: no state exists for container {container_id}")
            
        state_file = self._get_state_file(namespace, container_id)
        state = self._read_state(state_file)
        state['skip_start'] = value
        state['last_updated'] = datetime.now().isoformat()
        self._write_state(state_file, state)
        logger.info(f"Set skip_start={value} for container {container_id} in namespace {namespace}")
        
    def get_skip_start(self, namespace: str, container_id: str) -> bool:
        """
        Get the skip_start flag for a container.
        
        Args:
            namespace: Container namespace
            container_id: Container ID
            
        Returns:
            bool: True if start should be skipped, False otherwise
            
        Raises:
            IOError: If file operations fail
        """
        state_file = self._get_state_file(namespace, container_id)
        state = self._read_state(state_file)
        return state.get('skip_start', False)
        
    def set_skip_resume(self, namespace: str, container_id: str, value: bool) -> None:
        """
        Set the skip_resume flag for a container.
        
        Args:
            namespace: Container namespace
            container_id: Container ID
            value: True to skip resume, False otherwise
            
        Raises:
            ValueError: If state doesn't exist
            IOError: If file operations fail
        """
        if not self.has_state(namespace, container_id):
            raise ValueError(f"Cannot set skip_resume: no state exists for container {container_id}")
            
        state_file = self._get_state_file(namespace, container_id)
        state = self._read_state(state_file)
        state['skip_resume'] = value
        state['last_updated'] = datetime.now().isoformat()
        self._write_state(state_file, state)
        logger.info(f"Set skip_resume={value} for container {container_id} in namespace {namespace}")
        
    def get_skip_resume(self, namespace: str, container_id: str) -> bool:
        """
        Get the skip_resume flag for a container.
        
        Args:
            namespace: Container namespace
            container_id: Container ID
            
        Returns:
            bool: True if resume should be skipped, False otherwise
            
        Raises:
            IOError: If file operations fail
        """
        state_file = self._get_state_file(namespace, container_id)
        state = self._read_state(state_file)
        return state.get('skip_resume', False)
        
    def set_exit_code(self, namespace: str, container_id: str, exit_code: int) -> None:
        """
        Set the exit code for a container.
        
        Args:
            namespace: Container namespace
            container_id: Container ID
            exit_code: Container exit code
            
        Raises:
            ValueError: If state doesn't exist
            IOError: If file operations fail
        """
        if not self.has_state(namespace, container_id):
            raise ValueError(f"Cannot set exit_code: no state exists for container {container_id}")
            
        state_file = self._get_state_file(namespace, container_id)
        state = self._read_state(state_file)
        state['exit_code'] = exit_code
        state['last_updated'] = datetime.now().isoformat()
        self._write_state(state_file, state)
        logger.info(f"Set exit_code={exit_code} for container {container_id} in namespace {namespace}")
        
    def get_exit_code(self, namespace: str, container_id: str) -> Optional[int]:
        """
        Get the exit code for a container.
        
        Args:
            namespace: Container namespace
            container_id: Container ID
            
        Returns:
            Optional[int]: Container exit code if set, None otherwise
            
        Raises:
            IOError: If file operations fail
        """
        state_file = self._get_state_file(namespace, container_id)
        state = self._read_state(state_file)
        return state.get('exit_code')
        
    def clear_state(self, namespace: str, container_id: str) -> None:
        """
        Clear all state for a container by deleting its state file.
        
        Args:
            namespace: Container namespace
            container_id: Container ID
            
        Raises:
            IOError: If file operations fail
        """
        state_file = self._get_state_file(namespace, container_id)
        try:
            os.remove(state_file)
            logger.info(f"Cleared state for container {container_id} in namespace {namespace}")
        except FileNotFoundError:
            pass
