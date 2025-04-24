import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open, Mock
import json

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Create mock logger
mock_logger = MagicMock()

@pytest.fixture(autouse=True)
def mock_logger_fixture():
    """Mock logger for all tests."""
    with patch('src.runc_handler.logger', mock_logger):
        yield mock_logger

from src.runc_handler import RuncHandler
from src.utils.constants import ENV_REAL_RUNC_CMD, CONFIG_PATH, INTERCEPTABLE_COMMANDS
from src.runc_command_parser import RuncCommandParser
from src.container_handler.flag_manager import ContainerFlagManager
from src.container_handler.config_handler import ContainerConfigHandler
from src.container_handler.filesystem_handler import ContainerFilesystemHandler
from src.checkpoint_handler import CheckpointHandler

@pytest.fixture(autouse=True)
def setup_and_teardown(temp_dir):
    """Reset mocks and clean state directory before and after each test."""
    state_dir = temp_dir / "state"
    if state_dir.exists():
        shutil.rmtree(state_dir)
    state_dir.mkdir(parents=True)
    yield
    if state_dir.exists():
        shutil.rmtree(state_dir)

@pytest.fixture
def temp_dir():
    """Create temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # Create all required directories with proper permissions
        (tmp_path / "state").mkdir(parents=True, exist_ok=True)
        (tmp_path / "checkpoints").mkdir(parents=True, exist_ok=True)
        (tmp_path / "work").mkdir(parents=True, exist_ok=True)
        yield tmp_path

def get_state_file(namespace, container_id):
    return f"/tmp/arch/state/{namespace}_{container_id}.json"

@pytest.fixture
def runc_handler():
    """Create a RuncHandler instance with mocked dependencies."""
    handler = RuncHandler()
    yield handler

# Test initialization
def test_init_with_env_var():
    """Test initialization with environment variable."""
    with patch('src.runc_handler.os.path.exists', return_value=True), \
         patch('os.environ.get', return_value="/usr/bin/runc.real"), \
         patch('os.access', return_value=True):
        handler = RuncHandler()
        assert handler.original_runc_cmd == "/usr/bin/runc.real"

def test_init_with_config_file():
    """Test initialization with config file."""
    with patch('src.runc_handler.os.path.exists', return_value=True), \
         patch('os.environ.get', return_value=None), \
         patch('os.access', return_value=True), \
         patch('builtins.open', mock_open(read_data=f'{ENV_REAL_RUNC_CMD}=/usr/local/bin/runc.real\n')):
        handler = RuncHandler()
        assert handler.original_runc_cmd == "/usr/local/bin/runc.real"

def test_init_no_runc_found():
    """Test initialization failure when no runc found."""
    mock_env = patch('src.runc_handler.os.environ.get', return_value=None)
    mock_exists = patch('src.runc_handler.os.path.exists', return_value=False)
    mock_access = patch('src.runc_handler.os.access', return_value=False)
    mock_file = patch('builtins.open', mock_open(read_data=''))

    # Start all mocks
    mock_env.start()
    mock_exists.start()
    mock_access.start()
    mock_file.start()

    try:
        with pytest.raises(SystemExit) as exc_info:
            RuncHandler()
        assert exc_info.value.code == 1
    finally:
        # Stop all mocks
        mock_env.stop()
        mock_exists.stop()
        mock_access.stop()
        mock_file.stop()

# Test main public method - intercept_command
def test_intercept_command_non_interceptable(runc_handler):
    """Test handling of non-interceptable commands."""
    args = ["runc", "list"]
    with patch.object(runc_handler.parser, 'parse_command', return_value=("list", {}, {}, None, None)), \
         patch('os.execvp') as mock_exec:
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed

def test_intercept_command_not_arch_enabled(runc_handler):
    """Test handling of commands for non-ARCH containers."""
    args = ["runc", "create", "container1"]
    with patch.object(runc_handler.parser, 'parse_command', return_value=("create", {}, {}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=False), \
         patch('os.execvp') as mock_exec:
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed

def test_intercept_command_create(runc_handler, temp_dir):
    """Test create command interception creates a real flag file."""
    # Set up state directory for flag manager
    state_dir = temp_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    runc_handler.flag_manager.state_dir = str(state_dir)
    
    # Create bundle directory
    bundle_dir = temp_dir / "bundles" / "container1"
    bundle_dir.mkdir(parents=True)
    
    # Use real command with actual arguments
    args = ["runc", "create", "--bundle", str(bundle_dir), "container1"]
    
    with patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
         patch.object(runc_handler, '_get_container_paths', return_value=(None, None)), \
         patch('os.execvp') as mock_exec:
        mock_exec.side_effect = Exception("Exec called")
        
        # Execute command
        result = runc_handler.intercept_command(args)
        
        # Check logs to understand what happened
        for call in mock_logger.mock_calls:
            print(f"Log call: {call}")
            
        assert result == 1  # Because exec failed
        
        # Verify flag file was created
        flag_file = state_dir / "default_container1.json"
        assert flag_file.exists()
        
        # Verify flag file contents
        with open(flag_file) as f:
            flag_data = json.load(f)
            assert isinstance(flag_data, dict)
            assert flag_data['version'] == ContainerFlagManager.STATE_VERSION
            assert not flag_data['skip_start']
            assert not flag_data['skip_resume']
            assert not flag_data['keep_resources']
            assert flag_data['exit_code'] is None
        
        # Verify command execution
        mock_exec.assert_called_once_with(runc_handler.original_runc_cmd, 
                                        [runc_handler.original_runc_cmd] + args[1:])

def test_intercept_command_checkpoint(runc_handler):
    """Test checkpoint command interception."""
    args = ["runc", "checkpoint", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("checkpoint", {}, {}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
         patch('os.execvp') as mock_exec:
        mock_exec.side_effect = Exception("Exec called")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed
        mock_exec.assert_called_once_with(runc_handler.original_runc_cmd, [runc_handler.original_runc_cmd] + args[1:])

def test_intercept_command_start(runc_handler, temp_dir):
    """Test start command interception."""
    # Set up state directory for flag manager
    state_dir = temp_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    runc_handler.flag_manager.state_dir = str(state_dir)
    
    args = ["runc", "start", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("start", {}, {}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
         patch('os.execvp') as mock_exec:
        
        # Create flag and set skip_start flag
        runc_handler.flag_manager.create_flag("default", "container1")
        runc_handler.flag_manager.set_skip_start("default", "container1", True)
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 0  # Skip start flag is set
        assert not runc_handler.flag_manager.get_skip_start("default", "container1")

def test_intercept_command_resume(runc_handler):
    """Test resume command interception."""
    args = ["runc", "resume", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("resume", {}, {}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
         patch('os.execvp') as mock_exec:
        mock_exec.side_effect = Exception("Exec called")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed
        mock_exec.assert_called_once_with(runc_handler.original_runc_cmd, [runc_handler.original_runc_cmd] + args[1:])

def test_intercept_command_delete(runc_handler, temp_dir):
    """Test delete command interception."""
    # Set up state directory for flag manager
    state_dir = temp_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    runc_handler.flag_manager.state_dir = str(state_dir)
    
    args = ["runc", "delete", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("delete", {}, {}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
         patch.object(runc_handler.runtime_state, 'get_container_state', return_value="stopped"), \
         patch('os.execvp') as mock_exec:
        
        # Create flag file
        runc_handler.flag_manager.create_flag("default", "container1")
        mock_exec.side_effect = Exception("Exec called")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed
        assert not runc_handler.flag_manager.has_flag("default", "container1")

def test_intercept_command_error_handling(runc_handler):
    """Test error handling in intercept_command."""
    args = ["runc", "invalid", "command"]
    with patch.object(runc_handler.parser, 'parse_command', side_effect=Exception("Invalid command: invalid")):
        result = runc_handler.intercept_command(args)
        assert result == 1
        mock_logger.error.assert_called_with("Error intercepting command: %s", "Invalid command: invalid")

def test_intercept_command_create_with_options(runc_handler):
    """Test create command with bundle path and global options."""
    args = ["runc", "--root", "/var/run/runc", "--log", "/var/log/runc.log",
            "create", "--bundle", "/path/to/bundle", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("create", {}, {"--bundle": "/path/to/bundle"}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
         patch.object(runc_handler.config_handler, 'get_checkpoint_path', return_value=None), \
         patch('os.execvp') as mock_exec:
        
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed
        assert runc_handler.flag_manager.has_flag("default", "container1")

def test_intercept_command_checkpoint_with_options(runc_handler):
    """Test checkpoint command with work path and global options."""
    args = ["runc", "--root", "/var/run/runc", "--log-level", "debug",
            "checkpoint", "--work-path", "/tmp/work", "--leave-running", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("checkpoint", {}, {"--work-path": "/tmp/work", "--leave-running": ""}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
         patch.object(runc_handler.config_handler, 'get_checkpoint_path', return_value="/path/to/checkpoint"), \
         patch.object(runc_handler.filesystem_handler, 'get_upperdir', return_value="/path/to/upperdir"), \
         patch.object(runc_handler.checkpoint_handler, 'save_checkpoint_file', return_value=True), \
         patch('os.execvp') as mock_exec:
        
        mock_exec.side_effect = Exception("Exec would have replaced process")
        runc_handler.flag_manager.create_flag("default", "container1")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed
        assert runc_handler.flag_manager.get_skip_resume("default", "container1")

def test_intercept_command_start_with_options(runc_handler):
    """Test start command with detach and global options."""
    args = ["runc", "--root", "/var/run/runc", "--systemd-cgroup",
            "start", "--detach", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("start", {}, {"--detach": ""}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
         patch('os.execvp') as mock_exec:
        
        runc_handler.flag_manager.create_flag("default", "container1")
        runc_handler.flag_manager.set_skip_start("default", "container1", True)
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 0  # Skip start flag is set
        assert not runc_handler.flag_manager.get_skip_start("default", "container1")

def test_intercept_command_resume_with_options(runc_handler):
    """Test resume command with bundle path and global options."""
    args = ["runc", "--root", "/var/run/runc", "--log", "/var/log/runc.log",
            "resume", "--bundle", "/path/to/bundle", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("resume", {}, {"--bundle": "/path/to/bundle"}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
         patch('os.execvp') as mock_exec:
        
        runc_handler.flag_manager.create_flag("default", "container1")
        runc_handler.flag_manager.set_skip_resume("default", "container1", True)
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 0  # Skip resume flag is set
        assert not runc_handler.flag_manager.get_skip_resume("default", "container1")

def test_intercept_command_delete_with_options(runc_handler):
    """Test delete command with force and global options."""
    args = ["runc", "--root", "/var/run/runc", "--log-level", "debug",
            "delete", "--force", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("delete", {}, {"--force": ""}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
         patch.object(runc_handler.flag_manager, 'get_exit_code', return_value=0), \
         patch.object(runc_handler.config_handler, 'get_checkpoint_path', return_value="/path/to/checkpoint"), \
         patch.object(runc_handler.checkpoint_handler, 'cleanup_checkpoint', return_value=True), \
         patch.object(runc_handler.config_handler, 'delete_work_directory', return_value=True), \
         patch('os.execvp') as mock_exec:
        
        runc_handler.flag_manager.create_flag("default", "container1")
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed
        assert not runc_handler.flag_manager.has_flag("default", "container1")

def test_intercept_command_create_failed_restore(runc_handler):
    """Test create command when checkpoint restore fails."""
    args = ["runc", "create", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("create", {}, {}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
         patch.object(runc_handler.config_handler, 'add_bind_mount', return_value=True), \
         patch.object(runc_handler.config_handler, 'get_checkpoint_path', return_value="/path/to/checkpoint"), \
         patch.object(runc_handler.checkpoint_handler, 'validate_checkpoint', return_value=True), \
         patch.object(runc_handler.filesystem_handler, 'get_upperdir', return_value="/path/to/upperdir"), \
         patch.object(runc_handler.checkpoint_handler, 'restore_checkpoint_file', return_value=False), \
         patch('subprocess.run') as mock_run, \
         patch('os.execvp') as mock_exec:
        
        mock_run.return_value = Mock(returncode=1)  # Properly set up the mock with returncode=1
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed
        assert runc_handler.flag_manager.has_flag("default", "container1")
        runc_handler.checkpoint_handler.rollback_restore_file.assert_called_once_with("/path/to/upperdir")

class TestRuncHandler:
    """Test RuncHandler focusing on public methods and real components where possible."""
    
    def test_intercept_non_arch_command(self, runc_handler):
        """Test handling of commands for non-ARCH containers."""
        args = ["runc", "create", "container1"]
        with patch.object(runc_handler.parser, 'parse_command', return_value=("create", {}, {}, "container1", "default")), \
             patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=False), \
             patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec called")
            result = runc_handler.intercept_command(args)
            assert result == 1
            mock_exec.assert_called_once()

    def test_intercept_create_with_checkpoint(self, runc_handler, temp_dir):
        """Test create command with existing checkpoint."""
        container_id = "test-container"
        namespace = "default"
        bundle_dir = temp_dir / "bundles" / namespace / container_id
        bundle_dir.mkdir(parents=True)
        
        args = ["runc", "create", "--bundle", str(bundle_dir), container_id]
        
        with patch.object(runc_handler.parser, 'parse_command',
                         return_value=("create", {"bundle": str(bundle_dir)}, {}, container_id, namespace)), \
             patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
             patch.object(runc_handler.checkpoint_handler, 'validate_checkpoint', return_value=True), \
             patch.object(runc_handler.checkpoint_handler, 'restore_checkpoint_file', return_value=True), \
             patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec called")
            result = runc_handler.intercept_command(args)
            assert result == 0
            assert runc_handler.flag_manager.has_flag(namespace, container_id)

    def test_intercept_create_with_invalid_checkpoint(self, runc_handler, temp_dir):
        """Test create command with invalid checkpoint."""
        container_id = "test-container"
        namespace = "default"
        bundle_dir = temp_dir / "bundles" / namespace / container_id
        bundle_dir.mkdir(parents=True)
        
        args = ["runc", "create", "--bundle", str(bundle_dir), container_id]
        
        with patch.object(runc_handler.parser, 'parse_command',
                         return_value=("create", {"bundle": str(bundle_dir)}, {}, container_id, namespace)), \
             patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
             patch.object(runc_handler.checkpoint_handler, 'validate_checkpoint', return_value=False), \
             patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec called")
            result = runc_handler.intercept_command(args)
            assert result == 0
            assert runc_handler.flag_manager.has_flag(namespace, container_id)

    def test_intercept_create_with_restore_failure(self, runc_handler, temp_dir):
        """Test create command when checkpoint restore fails."""
        container_id = "test-container"
        namespace = "default"
        bundle_dir = temp_dir / "bundles" / namespace / container_id
        bundle_dir.mkdir(parents=True)
        
        args = ["runc", "create", "--bundle", str(bundle_dir), container_id]
        
        with patch.object(runc_handler.parser, 'parse_command',
                         return_value=("create", {"bundle": str(bundle_dir)}, {}, container_id, namespace)), \
             patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
             patch.object(runc_handler.checkpoint_handler, 'validate_checkpoint', return_value=True), \
             patch.object(runc_handler.checkpoint_handler, 'restore_checkpoint_file', return_value=False), \
             patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec called")
            result = runc_handler.intercept_command(args)
            assert result == 0
            assert runc_handler.flag_manager.has_flag(namespace, container_id)

    def test_intercept_checkpoint_success(self, runc_handler, temp_dir):
        """Test successful checkpoint creation."""
        container_id = "test-container"
        namespace = "default"
        
        # Setup container state
        runc_handler.flag_manager.create_flag(namespace, container_id)
        
        args = ["runc", "checkpoint", container_id]
        
        with patch.object(runc_handler.parser, 'parse_command',
                         return_value=("checkpoint", {}, {}, container_id, namespace)), \
             patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
             patch.object(runc_handler.config_handler, 'get_checkpoint_path',
                         return_value=str(temp_dir / "checkpoints" / namespace / container_id)), \
             patch.object(runc_handler.filesystem_handler, 'get_upperdir', return_value="/path/to/upperdir"), \
             patch.object(runc_handler.checkpoint_handler, 'save_checkpoint_file', return_value=True), \
             patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec called")
            result = runc_handler.intercept_command(args)
            assert result == 1
            assert runc_handler.flag_manager.get_skip_resume(namespace, container_id)

    def test_intercept_delete_with_cleanup(self, runc_handler, temp_dir):
        """Test delete command with state cleanup."""
        container_id = "test-container"
        namespace = "default"
        
        # Setup container state and checkpoint
        runc_handler.flag_manager.create_flag(namespace, container_id)
        checkpoint_dir = temp_dir / "checkpoints" / namespace / container_id
        checkpoint_dir.mkdir(parents=True)
        
        args = ["runc", "delete", container_id]
        
        with patch.object(runc_handler.parser, 'parse_command',
                         return_value=("delete", {}, {}, container_id, namespace)), \
             patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
             patch.object(runc_handler.flag_manager, 'get_exit_code', return_value=0), \
             patch.object(runc_handler, '_get_container_runtime_state', return_value="stopped"), \
             patch.object(runc_handler.config_handler, 'get_checkpoint_path',
                         return_value=str(checkpoint_dir)), \
             patch.object(runc_handler.checkpoint_handler, 'cleanup_checkpoint', return_value=True), \
             patch.object(runc_handler.config_handler, 'delete_work_directory', return_value=True), \
             patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec called")
            result = runc_handler.intercept_command(args)
            assert result == 1
            assert not runc_handler.flag_manager.has_flag(namespace, container_id)

    def test_intercept_start_skip_flag(self, runc_handler):
        """Test start command with skip flag set."""
        container_id = "test-container"
        namespace = "default"
        
        # Setup state with skip flag
        runc_handler.flag_manager.create_flag(namespace, container_id)
        runc_handler.flag_manager.set_skip_start(namespace, container_id, True)
        
        args = ["runc", "start", container_id]
        
        with patch.object(runc_handler.parser, 'parse_command',
                         return_value=("start", {}, {}, container_id, namespace)), \
             patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
             patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec called")
            result = runc_handler.intercept_command(args)
            assert result == 0
            assert not runc_handler.flag_manager.get_skip_start(namespace, container_id)

    def test_intercept_resume_skip_flag(self, runc_handler):
        """Test resume command with skip flag set."""
        container_id = "test-container"
        namespace = "default"
        
        # Setup state with skip flag
        runc_handler.flag_manager.create_flag(namespace, container_id)
        runc_handler.flag_manager.set_skip_resume(namespace, container_id, True)
        
        args = ["runc", "resume", container_id]
        
        with patch.object(runc_handler.parser, 'parse_command',
                         return_value=("resume", {}, {}, container_id, namespace)), \
             patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
             patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec called")
            result = runc_handler.intercept_command(args)
            assert result == 0
            assert not runc_handler.flag_manager.get_skip_resume(namespace, container_id)

    def test_intercept_invalid_command(self, runc_handler):
        """Test handling of invalid commands."""
        args = ["runc", "invalid"]
        with patch.object(runc_handler.parser, 'parse_command', side_effect=Exception("Invalid command")):
            result = runc_handler.intercept_command(args)
            assert result == 1

    def test_intercept_create_network_mount_failure(self, runc_handler):
        """Test create command with network mount failure."""
        container_id = "test-container"
        namespace = "default"
        args = ["runc", "create", container_id]
        
        with patch.object(runc_handler.parser, 'parse_command',
                         return_value=("create", {}, {}, container_id, namespace)), \
             patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
             patch.object(runc_handler.config_handler, 'add_bind_mount', return_value=False), \
             patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec called")
            result = runc_handler.intercept_command(args)
            assert result == 1
            assert runc_handler.flag_manager.has_flag(namespace, container_id)

    def test_intercept_create_restore_failure(self, runc_handler, temp_dir):
        """Test create command when restore fails and falls back to create."""
        container_id = "test-container"
        namespace = "default"
        
        # Setup checkpoint and bundle
        checkpoint_dir = temp_dir / "checkpoints" / namespace / container_id
        checkpoint_dir.mkdir(parents=True)
        checkpoint_path = checkpoint_dir / "checkpoint.tar"
        checkpoint_path.touch()
        
        bundle_dir = temp_dir / "bundles" / container_id
        bundle_dir.mkdir(parents=True)
        
        args = ["runc", "create", "--bundle", str(bundle_dir), container_id]
        
        with patch.object(runc_handler.parser, 'parse_command',
                         return_value=("create", {}, {"--bundle": str(bundle_dir)}, container_id, namespace)), \
             patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
             patch.object(runc_handler.config_handler, 'get_checkpoint_path',
                         return_value=str(checkpoint_path)), \
             patch.object(runc_handler.checkpoint_handler, 'validate_checkpoint', return_value=True), \
             patch.object(runc_handler.filesystem_handler, 'get_upperdir',
                         return_value="/path/to/upperdir"), \
             patch.object(runc_handler.checkpoint_handler, 'restore_checkpoint_file', return_value=True), \
             patch('subprocess.run') as mock_run, \
             patch.object(runc_handler.checkpoint_handler, 'rollback_restore_file') as mock_rollback, \
             patch('os.execvp') as mock_exec:
            
            # Make restore fail
            mock_run.return_value = Mock(returncode=1)
            mock_exec.side_effect = Exception("Exec called")
            
            result = runc_handler.intercept_command(args)
            
            # Verify behavior
            assert result == 1  # Final execvp failed
            assert runc_handler.flag_manager.has_flag(namespace, container_id)  # State was created
            mock_rollback.assert_called_once_with("/path/to/upperdir")  # Rollback was called
            # Check that execvp was called with the original command
            assert mock_exec.call_args[0][0] == runc_handler.original_runc_cmd  # First arg is the binary path
            assert mock_exec.call_args[0][1][1:] == args[1:]  # Rest of args should match (excluding 'runc')

    def test_intercept_create_without_checkpoint(self, runc_handler, temp_dir):
        """Test create command without checkpoint."""
        container_id = "test-container"
        namespace = "default"
        bundle_dir = temp_dir / "bundles" / namespace / container_id
        bundle_dir.mkdir(parents=True)
        
        args = ["runc", "create", "--bundle", str(bundle_dir), container_id]
        
        with patch.object(runc_handler.parser, 'parse_command',
                         return_value=("create", {"bundle": str(bundle_dir)}, {}, container_id, namespace)), \
             patch.object(runc_handler, '_get_container_paths',
                         return_value={"bundle": str(bundle_dir), "checkpoint": None}), \
             patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec called")
            result = runc_handler.intercept_command(args)
            assert result == 0
            assert runc_handler.state_manager.has_state(namespace, container_id)

    def test_intercept_create_flag(self, runc_handler):
        """Test create command with flag."""
        container_id = "test-container"
        namespace = "default"
        
        # Create flag using the real flag manager
        runc_handler.flag_manager.create_flag(namespace, container_id)
        
        # Verify flag file exists in the default location
        flag_file = f"/var/lib/arch/state/{namespace}_{container_id}.json"
        assert os.path.exists(flag_file)
        
        # Clean up
        os.remove(flag_file)

    def test_intercept_delete_flag(self, runc_handler):
        """Test delete command with flag."""
        container_id = "test-container"
        namespace = "default"
        with patch('src.container_handler.flag_manager.ContainerFlagManager._get_flag_file', new=get_flag_file):
            runc_handler.state_manager.create_flag(namespace, container_id)
            runc_handler.state_manager.create_flag(namespace, container_id)
            assert runc_handler.state_manager.has_flag(namespace, container_id)
            runc_handler.state_manager.delete_flag(namespace, container_id)
            assert not runc_handler.state_manager.has_flag(namespace, container_id)

    def test_intercept_create_flag_with_options(self, runc_handler):
        """Test create command with flag and options."""
        container_id = "test-container"
        namespace = "default"
        with patch('src.container_handler.flag_manager.ContainerFlagManager._get_flag_file', new=get_flag_file):
            args = ["runc", "--root", "/var/run/runc", "--log", "/var/log/runc.log",
                    "create", "--bundle", "/path/to/bundle", "--flag", "flag1", container_id]
            
            with patch.object(runc_handler.parser, 'parse_command', return_value=("create", {}, {"--bundle": "/path/to/bundle", "--flag": "flag1"}, container_id, namespace)), \
                 patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
                 patch.object(runc_handler.config_handler, 'get_checkpoint_path', return_value=None), \
                 patch('os.execvp') as mock_exec:
                
                mock_exec.side_effect = Exception("Exec called")
                result = runc_handler.intercept_command(args)
                assert result == 1  # Because exec failed
                assert runc_handler.state_manager.has_state(namespace, container_id)
                assert runc_handler.state_manager.has_flag(namespace, container_id)

    def test_intercept_delete_flag_with_options(self, runc_handler):
        """Test delete command with flag and options."""
        container_id = "test-container"
        namespace = "default"
        with patch('src.container_handler.flag_manager.ContainerFlagManager._get_flag_file', new=get_flag_file):
            args = ["runc", "--root", "/var/run/runc", "--log-level", "debug",
                    "delete", "--force", "--flag", "flag1", container_id]
            
            with patch.object(runc_handler.parser, 'parse_command', return_value=("delete", {}, {"--force": "", "--flag": "flag1"}, container_id, namespace)), \
                 patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
                 patch.object(runc_handler.state_manager, 'get_exit_code', return_value=0), \
                 patch.object(runc_handler.config_handler, 'get_checkpoint_path', return_value="/path/to/checkpoint"), \
                 patch.object(runc_handler.checkpoint_handler, 'cleanup_checkpoint', return_value=True), \
                 patch.object(runc_handler.config_handler, 'delete_work_directory', return_value=True), \
                 patch('os.execvp') as mock_exec:
                
                runc_handler.state_manager.create_state(namespace, container_id)
                mock_exec.side_effect = Exception("Exec called")
                result = runc_handler.intercept_command(args)
                assert result == 1  # Because exec failed
                assert not runc_handler.state_manager.has_state(namespace, container_id)
                assert not runc_handler.state_manager.has_flag(namespace, container_id)

    def test_intercept_create_flag_with_invalid_options(self, runc_handler):
        """Test create command with invalid flag options."""
        container_id = "test-container"
        namespace = "default"
        with patch('src.container_handler.flag_manager.ContainerFlagManager._get_flag_file', new=get_flag_file):
            args = ["runc", "--root", "/var/run/runc", "--log", "/var/log/runc.log",
                    "create", "--bundle", "/path/to/bundle", "--flag", "invalidflag", container_id]
            
            with patch.object(runc_handler.parser, 'parse_command', side_effect=Exception("Invalid flag: invalidflag")), \
                 patch('os.execvp') as mock_exec:
                
                result = runc_handler.intercept_command(args)
                assert result == 1
                assert not runc_handler.state_manager.has_state(namespace, container_id)
                assert not runc_handler.state_manager.has_flag(namespace, container_id)

    def test_intercept_delete_flag_with_invalid_options(self, runc_handler):
        """Test delete command with invalid flag options."""
        container_id = "test-container"
        namespace = "default"
        with patch('src.container_handler.flag_manager.ContainerFlagManager._get_flag_file', new=get_flag_file):
            args = ["runc", "--root", "/var/run/runc", "--log-level", "debug",
                    "delete", "--force", "--flag", "invalidflag", container_id]
            
            with patch.object(runc_handler.parser, 'parse_command', side_effect=Exception("Invalid flag: invalidflag")), \
                 patch('os.execvp') as mock_exec:
                
                result = runc_handler.intercept_command(args)
                assert result == 1
                assert not runc_handler.state_manager.has_state(namespace, container_id)
                assert not runc_handler.state_manager.has_flag(namespace, container_id)

    def test_intercept_create_flag_with_invalid_flag(self, runc_handler):
        """Test create command with invalid flag."""
        container_id = "test-container"
        namespace = "default"
        with patch('src.container_handler.flag_manager.ContainerFlagManager._get_flag_file', new=get_flag_file):
            args = ["runc", "--root", "/var/run/runc", "--log", "/var/log/runc.log",
                    "create", "--bundle", "/path/to/bundle", "--flag", "invalidflag", container_id]
            
            with patch.object(runc_handler.parser, 'parse_command', side_effect=Exception("Invalid flag: invalidflag")), \
                 patch('os.execvp') as mock_exec:
                
                result = runc_handler.intercept_command(args)
                assert result == 1
                assert not runc_handler.state_manager.has_state(namespace, container_id)
                assert not runc_handler.state_manager.has_flag(namespace, container_id)

    def test_intercept_delete_flag_with_invalid_flag(self, runc_handler):
        """Test delete command with invalid flag."""
        container_id = "test-container"
        namespace = "default"
        with patch('src.container_handler.flag_manager.ContainerFlagManager._get_flag_file', new=get_flag_file):
            args = ["runc", "--root", "/var/run/runc", "--log-level", "debug",
                    "delete", "--force", "--flag", "invalidflag", container_id]
            
            with patch.object(runc_handler.parser, 'parse_command', side_effect=Exception("Invalid flag: invalidflag")), \
                 patch('os.execvp') as mock_exec:
                
                result = runc_handler.intercept_command(args)
                assert result == 1
                assert not runc_handler.state_manager.has_state(namespace, container_id)
                assert not runc_handler.state_manager.has_flag(namespace, container_id)

    def test_intercept_create_flag_with_empty_flag(self, runc_handler):
        """Test create command with empty flag."""
        container_id = "test-container"
        namespace = "default"
        with patch('src.container_handler.flag_manager.ContainerFlagManager._get_flag_file', new=get_flag_file):
            args = ["runc", "--root", "/var/run/runc", "--log", "/var/log/runc.log",
                    "create", "--bundle", "/path/to/bundle", "--flag", "", container_id]
            
            with patch.object(runc_handler.parser, 'parse_command', return_value=("create", {}, {"--bundle": "/path/to/bundle", "--flag": ""}, container_id, namespace)), \
                 patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
                 patch.object(runc_handler.config_handler, 'get_checkpoint_path', return_value=None), \
                 patch('os.execvp') as mock_exec:
                
                mock_exec.side_effect = Exception("Exec called")
                result = runc_handler.intercept_command(args)
                assert result == 1  # Because exec failed
                assert runc_handler.state_manager.has_state(namespace, container_id)
                assert runc_handler.state_manager.has_flag(namespace, container_id)

    def test_intercept_delete_flag_with_empty_flag(self, runc_handler):
        """Test delete command with empty flag."""
        container_id = "test-container"
        namespace = "default"
        with patch('src.container_handler.flag_manager.ContainerFlagManager._get_flag_file', new=get_flag_file):
            args = ["runc", "--root", "/var/run/runc", "--log-level", "debug",
                    "delete", "--force", "--flag", "", container_id]
            
            with patch.object(runc_handler.parser, 'parse_command', return_value=("delete", {}, {"--force": "", "--flag": ""}, container_id, namespace)), \
                 patch.object(runc_handler.config_handler, 'is_arch_enabled', return_value=True), \
                 patch.object(runc_handler.state_manager, 'get_exit_code', return_value=0), \
                 patch.object(runc_handler.config_handler, 'get_checkpoint_path', return_value="/path/to/checkpoint"), \
                 patch.object(runc_handler.checkpoint_handler, 'cleanup_checkpoint', return_value=True), \
                 patch.object(runc_handler.config_handler, 'delete_work_directory', return_value=True), \
                 patch('os.execvp') as mock_exec:
                
                runc_handler.state_manager.create_state(namespace, container_id)
                mock_exec.side_effect = Exception("Exec called")
                result = runc_handler.intercept_command(args)
                assert result == 1  # Because exec failed
                assert not runc_handler.state_manager.has_state(namespace, container_id)
                assert not runc_handler.state_manager.has_flag(namespace, container_id) 