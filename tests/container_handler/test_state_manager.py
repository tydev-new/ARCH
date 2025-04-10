import os
import json
import pytest
import tempfile
from datetime import datetime
from src.container_handler.state_manager import ContainerStateManager

@pytest.fixture
def state_manager():
    """Create a state manager with a temporary directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        manager = ContainerStateManager(state_dir=temp_dir)
        yield manager

def test_create_state(state_manager):
    """Test creating state for a container."""
    namespace = "test"
    container_id = "container1"
    
    # Create state
    state_manager.create_state(namespace, container_id)
    assert state_manager.has_state(namespace, container_id)
    
    # Verify state structure
    state_file = state_manager._get_state_file(namespace, container_id)
    with open(state_file, 'r') as f:
        state = json.load(f)
        assert state['version'] == '1.0'
        assert state['skip_start'] is False
        assert state['skip_resume'] is False
        assert state['exit_code'] is None
        assert 'last_updated' in state

def test_create_state_duplicate(state_manager):
    """Test creating state for same container twice."""
    namespace = "test"
    container_id = "container1"
    
    state_manager.create_state(namespace, container_id)
    with pytest.raises(ValueError):
        state_manager.create_state(namespace, container_id)

def test_skip_start(state_manager):
    """Test skip_start flag operations."""
    namespace = "test"
    container_id = "container1"
    
    # Create state first
    state_manager.create_state(namespace, container_id)
    
    # Set and get skip_start
    state_manager.set_skip_start(namespace, container_id, True)
    assert state_manager.get_skip_start(namespace, container_id) is True
    
    state_manager.set_skip_start(namespace, container_id, False)
    assert state_manager.get_skip_start(namespace, container_id) is False

def test_skip_resume(state_manager):
    """Test skip_resume flag operations."""
    namespace = "test"
    container_id = "container1"
    
    # Create state first
    state_manager.create_state(namespace, container_id)
    
    # Set and get skip_resume
    state_manager.set_skip_resume(namespace, container_id, True)
    assert state_manager.get_skip_resume(namespace, container_id) is True
    
    state_manager.set_skip_resume(namespace, container_id, False)
    assert state_manager.get_skip_resume(namespace, container_id) is False

def test_exit_code(state_manager):
    """Test exit_code operations."""
    namespace = "test"
    container_id = "container1"
    
    # Create state first
    state_manager.create_state(namespace, container_id)
    
    # Set and get exit_code
    state_manager.set_exit_code(namespace, container_id, 1)
    assert state_manager.get_exit_code(namespace, container_id) == 1
    
    state_manager.set_exit_code(namespace, container_id, 0)
    assert state_manager.get_exit_code(namespace, container_id) == 0

def test_clear_state(state_manager):
    """Test clearing container state."""
    namespace = "test"
    container_id = "container1"
    
    # Create and verify state exists
    state_manager.create_state(namespace, container_id)
    assert state_manager.has_state(namespace, container_id)
    
    # Clear state and verify it's gone
    state_manager.clear_state(namespace, container_id)
    assert not state_manager.has_state(namespace, container_id)

def test_list_containers(state_manager):
    """Test listing containers with state."""
    # Create states for multiple containers
    containers = [
        ("ns1", "container1"),
        ("ns1", "container2"),
        ("ns2", "container1")
    ]
    
    for namespace, container_id in containers:
        state_manager.create_state(namespace, container_id)
    
    # List and verify
    listed = state_manager.list_containers()
    assert len(listed) == len(containers)
    for container in containers:
        assert container in listed

def test_invalid_state_file(state_manager):
    """Test handling of invalid state file."""
    namespace = "test"
    container_id = "container1"
    
    # Create state first
    state_manager.create_state(namespace, container_id)
    
    # Corrupt the state file
    state_file = state_manager._get_state_file(namespace, container_id)
    with open(state_file, 'w') as f:
        f.write("invalid json")
    
    # Operations should fail with ValueError due to invalid state structure
    with pytest.raises(ValueError):
        state_manager.get_skip_start(namespace, container_id)

def test_missing_state_operations(state_manager):
    """Test operations on non-existent state."""
    namespace = "test"
    container_id = "container1"
    
    # Set operations should fail with ValueError
    with pytest.raises(ValueError):
        state_manager.set_skip_start(namespace, container_id, True)
    
    with pytest.raises(ValueError):
        state_manager.set_skip_resume(namespace, container_id, True)
    
    with pytest.raises(ValueError):
        state_manager.set_exit_code(namespace, container_id, 1)
    
    # Get operations should fail with FileNotFoundError
    with pytest.raises(FileNotFoundError):
        state_manager.get_skip_start(namespace, container_id)
    
    with pytest.raises(FileNotFoundError):
        state_manager.get_skip_resume(namespace, container_id)
    
    with pytest.raises(FileNotFoundError):
        state_manager.get_exit_code(namespace, container_id) 