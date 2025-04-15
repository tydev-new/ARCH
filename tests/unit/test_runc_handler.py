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

# Mock logger at module level
mock_logger = MagicMock()
patch('src.utils.logging.logger', mock_logger).start()

from src.runc_handler import RuncHandler
from src.utils.constants import ENV_REAL_RUNC_CMD, CONFIG_PATH, INTERCEPTABLE_COMMANDS
from src.runc_command_parser import RuncCommandParser
from src.container_handler.state_manager import ContainerStateManager

@pytest.fixture(autouse=True)
def setup_and_teardown(temp_dir):
    """Reset mocks and clean state directory before and after each test."""
    mock_logger.reset_mock()
    state_dir = temp_dir / "state"
    if state_dir.exists():
        shutil.rmtree(state_dir)
    state_dir.mkdir(parents=True)
    yield
    mock_logger.reset_mock()
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

@pytest.fixture
def runc_handler(temp_dir):
    """Create RuncHandler with minimal mocking."""
    state_dir = temp_dir / "state"
    state_dir.mkdir(exist_ok=True)
    
    def get_state_file(self, namespace, container_id):
        return os.path.join(str(state_dir), f"{namespace}_{container_id}.json")
    
    with patch('src.runc_handler.os.environ.get', return_value='/usr/bin/runc'), \
         patch.dict(os.environ, {
             'TARDIS_STATE_DIR': str(state_dir),
             'TARDIS_CHECKPOINT_DIR': str(temp_dir / "checkpoints"),
             'TARDIS_WORK_DIR': str(temp_dir / "work")
         }), \
         patch('src.container_handler.state_manager.ContainerStateManager._get_state_file', new=get_state_file):
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
    with patch('src.runc_handler.os.path.exists', return_value=False), \
         pytest.raises(SystemExit) as exc_info:
        RuncHandler()
    assert exc_info.value.code == 1
    mock_logger.error.assert_called_with("Could not find runc binary")

# Test main public method - intercept_command
def test_intercept_command_non_interceptable(runc_handler):
    """Test handling of non-interceptable commands."""
    args = ["runc", "list"]
    with patch.object(runc_handler.parser, 'parse_command', return_value=("list", {}, {}, None, None)), \
         patch('os.execvp') as mock_exec:
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed

def test_intercept_command_not_tardis_enabled(runc_handler):
    """Test handling of commands for non-Tardis containers."""
    args = ["runc", "create", "container1"]
    with patch.object(runc_handler.parser, 'parse_command', return_value=("create", {}, {}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=False), \
         patch('os.execvp') as mock_exec:
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed

def test_intercept_command_create(runc_handler):
    """Test create command interception."""
    args = ["runc", "create", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("create", {}, {}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
         patch.object(runc_handler.config_handler, 'get_checkpoint_path', return_value=None), \
         patch('os.execvp') as mock_exec:
        
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed
        assert runc_handler.state_manager.has_state("default", "container1")

def test_intercept_command_checkpoint(runc_handler):
    """Test checkpoint command interception."""
    args = ["runc", "checkpoint", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("checkpoint", {}, {}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
         patch.object(runc_handler.config_handler, 'get_checkpoint_path', return_value="/path/to/checkpoint"), \
         patch.object(runc_handler.filesystem_handler, 'get_upperdir', return_value="/path/to/upperdir"), \
         patch.object(runc_handler.checkpoint_handler, 'save_checkpoint', return_value=True), \
         patch('os.execvp') as mock_exec:
        
        mock_exec.side_effect = Exception("Exec would have replaced process")
        runc_handler.state_manager.create_state("default", "container1")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed
        assert runc_handler.state_manager.get_skip_resume("default", "container1")

def test_intercept_command_start(runc_handler):
    """Test start command interception."""
    args = ["runc", "start", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("start", {}, {}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
         patch('os.execvp') as mock_exec:
        
        runc_handler.state_manager.create_state("default", "container1")
        runc_handler.state_manager.set_skip_start("default", "container1", True)
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 0  # Skip start flag is set
        assert not runc_handler.state_manager.get_skip_start("default", "container1")

def test_intercept_command_resume(runc_handler):
    """Test resume command interception."""
    args = ["runc", "resume", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("resume", {}, {}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
         patch('os.execvp') as mock_exec:
        
        runc_handler.state_manager.create_state("default", "container1")
        runc_handler.state_manager.set_skip_resume("default", "container1", True)
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 0  # Skip resume flag is set
        assert not runc_handler.state_manager.get_skip_resume("default", "container1")

def test_intercept_command_delete(runc_handler):
    """Test delete command interception."""
    args = ["runc", "delete", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("delete", {}, {}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
         patch.object(runc_handler.state_manager, 'get_exit_code', return_value=0), \
         patch.object(runc_handler.config_handler, 'get_checkpoint_path', return_value="/path/to/checkpoint"), \
         patch.object(runc_handler.checkpoint_handler, 'cleanup_checkpoint', return_value=True), \
         patch.object(runc_handler.config_handler, 'delete_work_directory', return_value=True), \
         patch('os.execvp') as mock_exec:
        
        runc_handler.state_manager.create_state("default", "container1")
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed
        assert not runc_handler.state_manager.has_state("default", "container1")

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
         patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
         patch.object(runc_handler.config_handler, 'get_checkpoint_path', return_value=None), \
         patch('os.execvp') as mock_exec:
        
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed
        assert runc_handler.state_manager.has_state("default", "container1")

def test_intercept_command_checkpoint_with_options(runc_handler):
    """Test checkpoint command with work path and global options."""
    args = ["runc", "--root", "/var/run/runc", "--log-level", "debug",
            "checkpoint", "--work-path", "/tmp/work", "--leave-running", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("checkpoint", {}, {"--work-path": "/tmp/work", "--leave-running": ""}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
         patch.object(runc_handler.config_handler, 'get_checkpoint_path', return_value="/path/to/checkpoint"), \
         patch.object(runc_handler.filesystem_handler, 'get_upperdir', return_value="/path/to/upperdir"), \
         patch.object(runc_handler.checkpoint_handler, 'save_checkpoint', return_value=True), \
         patch('os.execvp') as mock_exec:
        
        mock_exec.side_effect = Exception("Exec would have replaced process")
        runc_handler.state_manager.create_state("default", "container1")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed
        assert runc_handler.state_manager.get_skip_resume("default", "container1")

def test_intercept_command_start_with_options(runc_handler):
    """Test start command with detach and global options."""
    args = ["runc", "--root", "/var/run/runc", "--systemd-cgroup",
            "start", "--detach", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("start", {}, {"--detach": ""}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
         patch('os.execvp') as mock_exec:
        
        runc_handler.state_manager.create_state("default", "container1")
        runc_handler.state_manager.set_skip_start("default", "container1", True)
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 0  # Skip start flag is set
        assert not runc_handler.state_manager.get_skip_start("default", "container1")

def test_intercept_command_resume_with_options(runc_handler):
    """Test resume command with bundle path and global options."""
    args = ["runc", "--root", "/var/run/runc", "--log", "/var/log/runc.log",
            "resume", "--bundle", "/path/to/bundle", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("resume", {}, {"--bundle": "/path/to/bundle"}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
         patch('os.execvp') as mock_exec:
        
        runc_handler.state_manager.create_state("default", "container1")
        runc_handler.state_manager.set_skip_resume("default", "container1", True)
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 0  # Skip resume flag is set
        assert not runc_handler.state_manager.get_skip_resume("default", "container1")

def test_intercept_command_delete_with_options(runc_handler):
    """Test delete command with force and global options."""
    args = ["runc", "--root", "/var/run/runc", "--log-level", "debug",
            "delete", "--force", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("delete", {}, {"--force": ""}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
         patch.object(runc_handler.state_manager, 'get_exit_code', return_value=0), \
         patch.object(runc_handler.config_handler, 'get_checkpoint_path', return_value="/path/to/checkpoint"), \
         patch.object(runc_handler.checkpoint_handler, 'cleanup_checkpoint', return_value=True), \
         patch.object(runc_handler.config_handler, 'delete_work_directory', return_value=True), \
         patch('os.execvp') as mock_exec:
        
        runc_handler.state_manager.create_state("default", "container1")
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed
        assert not runc_handler.state_manager.has_state("default", "container1")

def test_intercept_command_create_failed_restore(runc_handler):
    """Test create command when checkpoint restore fails."""
    args = ["runc", "create", "container1"]
    
    with patch.object(runc_handler.parser, 'parse_command', return_value=("create", {}, {}, "container1", "default")), \
         patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
         patch.object(runc_handler.config_handler, 'add_bind_mount', return_value=True), \
         patch.object(runc_handler.config_handler, 'get_checkpoint_path', return_value="/path/to/checkpoint"), \
         patch.object(runc_handler.checkpoint_handler, 'validate_checkpoint', return_value=True), \
         patch.object(runc_handler.filesystem_handler, 'get_upperdir', return_value="/path/to/upperdir"), \
         patch.object(runc_handler.checkpoint_handler, 'restore_checkpoint', return_value=True), \
         patch.object(runc_handler.checkpoint_handler, 'rollback_restore'), \
         patch('subprocess.run') as mock_run, \
         patch('os.execvp') as mock_exec:
        
        mock_run.return_value = Mock(returncode=1)  # Properly set up the mock with returncode=1
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler.intercept_command(args)
        assert result == 1  # Because exec failed
        assert runc_handler.state_manager.has_state("default", "container1")
        runc_handler.checkpoint_handler.rollback_restore.assert_called_once_with("/path/to/upperdir")

class TestRuncHandler:
    """Test RuncHandler focusing on public methods and real components where possible."""
    
    def test_intercept_non_tardis_command(self, runc_handler):
        """Test handling of commands for non-Tardis containers."""
        args = ["runc", "create", "container1"]
        with patch.object(runc_handler.parser, 'parse_command', return_value=("create", {}, {}, "container1", "default")), \
             patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=False), \
             patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec called")
            result = runc_handler.intercept_command(args)
            assert result == 1
            mock_exec.assert_called_once()

    def test_intercept_create_with_checkpoint(self, runc_handler, temp_dir):
        """Test create command with existing checkpoint."""
        container_id = "test-container"
        namespace = "default"
        
        # Setup checkpoint
        checkpoint_dir = temp_dir / "checkpoints" / namespace / container_id
        checkpoint_dir.mkdir(parents=True)
        (checkpoint_dir / "checkpoint.tar").touch()
        
        # Create test bundle
        bundle_dir = temp_dir / "bundles" / container_id
        bundle_dir.mkdir(parents=True)
        
        args = ["runc", "create", 
                "--bundle", str(bundle_dir),
                container_id]
        
        with patch.object(runc_handler.parser, 'parse_command', 
                         return_value=("create", {}, {"--bundle": str(bundle_dir)}, container_id, namespace)), \
             patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
             patch.object(runc_handler.config_handler, 'get_checkpoint_path', 
                         return_value=str(checkpoint_dir / "checkpoint.tar")), \
             patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec called")
            result = runc_handler.intercept_command(args)
            assert result == 1
            assert runc_handler.state_manager.has_state(namespace, container_id)

    def test_intercept_checkpoint_success(self, runc_handler, temp_dir):
        """Test successful checkpoint creation."""
        container_id = "test-container"
        namespace = "default"
        
        # Setup container state
        runc_handler.state_manager.create_state(namespace, container_id)
        
        args = ["runc", "checkpoint", container_id]
        
        with patch.object(runc_handler.parser, 'parse_command',
                         return_value=("checkpoint", {}, {}, container_id, namespace)), \
             patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
             patch.object(runc_handler.config_handler, 'get_checkpoint_path',
                         return_value=str(temp_dir / "checkpoints" / namespace / container_id)), \
             patch.object(runc_handler.filesystem_handler, 'get_upperdir', return_value="/path/to/upperdir"), \
             patch.object(runc_handler.checkpoint_handler, 'save_checkpoint', return_value=True), \
             patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec called")
            result = runc_handler.intercept_command(args)
            assert result == 1
            assert runc_handler.state_manager.get_skip_resume(namespace, container_id)

    def test_intercept_delete_with_cleanup(self, runc_handler, temp_dir):
        """Test delete command with state cleanup."""
        container_id = "test-container"
        namespace = "default"
        
        # Setup container state and checkpoint
        runc_handler.state_manager.create_state(namespace, container_id)
        checkpoint_dir = temp_dir / "checkpoints" / namespace / container_id
        checkpoint_dir.mkdir(parents=True)
        
        args = ["runc", "delete", container_id]
        
        with patch.object(runc_handler.parser, 'parse_command',
                         return_value=("delete", {}, {}, container_id, namespace)), \
             patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
             patch.object(runc_handler.state_manager, 'get_exit_code', return_value=0), \
             patch.object(runc_handler.config_handler, 'get_checkpoint_path',
                         return_value=str(checkpoint_dir)), \
             patch.object(runc_handler.checkpoint_handler, 'cleanup_checkpoint', return_value=True), \
             patch.object(runc_handler.config_handler, 'delete_work_directory', return_value=True), \
             patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec called")
            result = runc_handler.intercept_command(args)
            assert result == 1
            assert not runc_handler.state_manager.has_state(namespace, container_id)

    def test_intercept_start_skip_flag(self, runc_handler):
        """Test start command with skip flag set."""
        container_id = "test-container"
        namespace = "default"
        
        # Setup state with skip flag
        runc_handler.state_manager.create_state(namespace, container_id)
        runc_handler.state_manager.set_skip_start(namespace, container_id, True)
        
        args = ["runc", "start", container_id]
        
        with patch.object(runc_handler.parser, 'parse_command',
                         return_value=("start", {}, {}, container_id, namespace)), \
             patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
             patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec called")
            result = runc_handler.intercept_command(args)
            assert result == 0
            assert not runc_handler.state_manager.get_skip_start(namespace, container_id)

    def test_intercept_resume_skip_flag(self, runc_handler):
        """Test resume command with skip flag set."""
        container_id = "test-container"
        namespace = "default"
        
        # Setup state with skip flag
        runc_handler.state_manager.create_state(namespace, container_id)
        runc_handler.state_manager.set_skip_resume(namespace, container_id, True)
        
        args = ["runc", "resume", container_id]
        
        with patch.object(runc_handler.parser, 'parse_command',
                         return_value=("resume", {}, {}, container_id, namespace)), \
             patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
             patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec called")
            result = runc_handler.intercept_command(args)
            assert result == 0
            assert not runc_handler.state_manager.get_skip_resume(namespace, container_id)

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
             patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
             patch.object(runc_handler.config_handler, 'add_bind_mount', return_value=False), \
             patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec called")
            result = runc_handler.intercept_command(args)
            assert result == 1
            assert runc_handler.state_manager.has_state(namespace, container_id)

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
             patch.object(runc_handler.config_handler, 'is_tardis_enabled', return_value=True), \
             patch.object(runc_handler.config_handler, 'get_checkpoint_path',
                         return_value=str(checkpoint_path)), \
             patch.object(runc_handler.checkpoint_handler, 'validate_checkpoint', return_value=True), \
             patch.object(runc_handler.filesystem_handler, 'get_upperdir',
                         return_value="/path/to/upperdir"), \
             patch.object(runc_handler.checkpoint_handler, 'restore_checkpoint', return_value=True), \
             patch('subprocess.run') as mock_run, \
             patch.object(runc_handler.checkpoint_handler, 'rollback_restore') as mock_rollback, \
             patch('os.execvp') as mock_exec:
            
            # Make restore fail
            mock_run.return_value = Mock(returncode=1)
            mock_exec.side_effect = Exception("Exec called")
            
            result = runc_handler.intercept_command(args)
            
            # Verify behavior
            assert result == 1  # Final execvp failed
            assert runc_handler.state_manager.has_state(namespace, container_id)  # State was created
            mock_rollback.assert_called_once_with("/path/to/upperdir")  # Rollback was called
            # Check that execvp was called with the original command
            assert mock_exec.call_args[0][0] == runc_handler.original_runc_cmd  # First arg is the binary path
            assert mock_exec.call_args[0][1][1:] == args[1:]  # Rest of args should match (excluding 'runc') 