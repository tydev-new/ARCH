import os
import json
import pytest
from datetime import datetime
from src.container_handler.flag_manager import ContainerFlagManager

@pytest.fixture
def flag_manager(tmp_path):
    """Create a FlagManager instance with a temporary directory."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return ContainerFlagManager(str(state_dir))

def test_create_flag(flag_manager):
    """Test creating flag file."""
    namespace = "test"
    container_id = "container1"
    
    flag_manager.create_flag(namespace, container_id)
    assert flag_manager.has_flag(namespace, container_id)
    
    flag_file = flag_manager._get_flag_file(namespace, container_id)
    with open(flag_file, 'r') as f:
        flag_data = json.load(f)
        assert flag_data['version'] == flag_manager.STATE_VERSION
        assert flag_data['skip_start'] is False
        assert flag_data['skip_resume'] is False
        assert flag_data['exit_code'] is None
        assert 'last_updated' in flag_data

def test_create_flag_duplicate(flag_manager):
    """Test creating flag file when it already exists."""
    namespace = "test"
    container_id = "container1"
    
    # Create initial flag
    flag_manager.create_flag(namespace, container_id)
    first_flag_file = flag_manager._get_flag_file(namespace, container_id)
    with open(first_flag_file, 'r') as f:
        first_flag = json.load(f)
    
    # Create duplicate flag
    flag_manager.create_flag(namespace, container_id)
    second_flag_file = flag_manager._get_flag_file(namespace, container_id)
    with open(second_flag_file, 'r') as f:
        second_flag = json.load(f)
    
    # Verify both flags are valid
    assert flag_manager._validate_flag(first_flag)
    assert flag_manager._validate_flag(second_flag)
    
    # Verify second flag has newer timestamp
    first_time = datetime.fromisoformat(first_flag['last_updated'])
    second_time = datetime.fromisoformat(second_flag['last_updated'])
    assert second_time >= first_time

def test_skip_start(flag_manager):
    """Test skip_start flag operations."""
    namespace = "test"
    container_id = "container1"
    
    # Create flag first
    flag_manager.create_flag(namespace, container_id)
    
    # Set and get skip_start
    flag_manager.set_skip_start(namespace, container_id, True)
    assert flag_manager.get_skip_start(namespace, container_id) is True
    
    flag_manager.set_skip_start(namespace, container_id, False)
    assert flag_manager.get_skip_start(namespace, container_id) is False

def test_skip_resume(flag_manager):
    """Test skip_resume flag operations."""
    namespace = "test"
    container_id = "container1"
    
    # Create flag first
    flag_manager.create_flag(namespace, container_id)
    
    # Set and get skip_resume
    flag_manager.set_skip_resume(namespace, container_id, True)
    assert flag_manager.get_skip_resume(namespace, container_id) is True
    
    flag_manager.set_skip_resume(namespace, container_id, False)
    assert flag_manager.get_skip_resume(namespace, container_id) is False

def test_exit_code(flag_manager):
    """Test exit_code operations."""
    namespace = "test"
    container_id = "container1"
    
    # Create flag first
    flag_manager.create_flag(namespace, container_id)
    
    # Set and get exit_code
    flag_manager.set_exit_code(namespace, container_id, 1)
    assert flag_manager.get_exit_code(namespace, container_id) == 1
    
    flag_manager.set_exit_code(namespace, container_id, 0)
    assert flag_manager.get_exit_code(namespace, container_id) == 0

def test_clear_flag(flag_manager):
    """Test clearing flag file."""
    namespace = "test"
    container_id = "container1"
    
    # Create flag
    flag_manager.create_flag(namespace, container_id)
    assert flag_manager.has_flag(namespace, container_id)
    
    # Clear flag
    flag_manager.clear_flag(namespace, container_id)
    assert not flag_manager.has_flag(namespace, container_id)
    
    # Verify file is deleted
    flag_file = flag_manager._get_flag_file(namespace, container_id)
    assert not os.path.exists(flag_file)

def test_list_containers(flag_manager):
    """Test listing containers with flags."""
    # Create flags for multiple containers
    containers = [
        ("ns1", "container1"),
        ("ns1", "container2"),
        ("ns2", "container1")
    ]
    
    for namespace, container_id in containers:
        flag_manager.create_flag(namespace, container_id)
    
    # List containers
    listed_containers = flag_manager.list_containers()
    assert len(listed_containers) == 3
    assert all((ns, cid) in listed_containers for ns, cid in containers)

def test_invalid_flag_file(flag_manager):
    """Test handling of invalid flag file."""
    namespace = "test"
    container_id = "container1"
    
    # Create flag first
    flag_manager.create_flag(namespace, container_id)
    
    # Corrupt the flag file
    flag_file = flag_manager._get_flag_file(namespace, container_id)
    with open(flag_file, 'w') as f:
        f.write("invalid json")
    
    # Operations should return default values for invalid flag
    assert flag_manager.get_skip_start(namespace, container_id) is False
    assert flag_manager.get_skip_resume(namespace, container_id) is False
    assert flag_manager.get_exit_code(namespace, container_id) is None

def test_file_locking_errors(flag_manager, monkeypatch):
    """Test handling of file locking errors."""
    namespace = "test"
    container_id = "container1"
    
    def mock_flock(*args, **kwargs):
        raise IOError("Lock error")
    
    # Create flag first
    flag_manager.create_flag(namespace, container_id)
    
    # Mock flock to simulate locking error
    monkeypatch.setattr("fcntl.flock", mock_flock)
    
    # Operations should handle locking errors gracefully
    assert flag_manager.get_skip_start(namespace, container_id) is False
    assert flag_manager.get_skip_resume(namespace, container_id) is False
    assert flag_manager.get_exit_code(namespace, container_id) is None

def test_write_flag_validation(flag_manager):
    """Test flag validation during write operations."""
    namespace = "test"
    container_id = "container1"
    
    # Create invalid flag
    invalid_flag = {
        'version': '1.0',
        'skip_start': False,
        # Missing required fields
    }
    
    # Attempt to write invalid flag should raise ValueError
    with pytest.raises(ValueError):
        flag_manager._write_flag(
            flag_manager._get_flag_file(namespace, container_id),
            invalid_flag
        )

def test_write_flag_io_error(flag_manager, monkeypatch):
    """Test handling of IO errors during flag write."""
    namespace = "test"
    container_id = "container1"
    
    def mock_open(*args, **kwargs):
        raise IOError("Write error")
    
    # Create flag first
    flag_manager.create_flag(namespace, container_id)
    
    # Mock open to simulate IO error
    monkeypatch.setattr("builtins.open", mock_open)
    
    # Operations should handle IO errors gracefully
    with pytest.raises(IOError):
        flag_manager._write_flag(
            flag_manager._get_flag_file(namespace, container_id),
            flag_manager._create_initial_flag()
        )

def test_keep_resources(flag_manager):
    """Test keep_resources flag operations."""
    namespace = "test"
    container_id = "container1"
    
    # Create flag first
    flag_manager.create_flag(namespace, container_id)
    
    # Set and get keep_resources
    flag_manager.set_keep_resources(namespace, container_id, True)
    assert flag_manager.get_keep_resources(namespace, container_id) is True
    
    flag_manager.set_keep_resources(namespace, container_id, False)
    assert flag_manager.get_keep_resources(namespace, container_id) is False 