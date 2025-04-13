import os
import sys
import pytest
from unittest.mock import patch, MagicMock, mock_open, Mock, ANY
import json

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Mock logger at module level
mock_logger = MagicMock()
patch('src.utils.logging.logger', mock_logger).start()

from src.runc_handler import RuncHandler
from src.utils.constants import ENV_REAL_RUNC_CMD, CONFIG_PATH, INTERCEPTABLE_COMMANDS

@pytest.fixture(autouse=True)
def setup_and_teardown():
    """Reset mocks before and after each test."""
    mock_logger.reset_mock()
    yield
    mock_logger.reset_mock()

@pytest.fixture
def mock_config_handler():
    """Mock for ContainerConfigHandler."""
    return Mock()

@pytest.fixture
def mock_state_manager():
    return Mock()

@pytest.fixture
def mock_checkpoint_handler():
    return Mock()

@pytest.fixture
def mock_filesystem_handler():
    return Mock()

@pytest.fixture
def mock_parser():
    parser = Mock()
    parser.parse_command = Mock()
    return parser

@pytest.fixture
def runc_handler(mock_config_handler, mock_state_manager, mock_checkpoint_handler, mock_filesystem_handler, mock_parser):
    with patch('src.runc_handler.ContainerConfigHandler', return_value=mock_config_handler), \
         patch('src.runc_handler.ContainerStateManager', return_value=mock_state_manager), \
         patch('src.runc_handler.CheckpointHandler', return_value=mock_checkpoint_handler), \
         patch('src.runc_handler.ContainerFilesystemHandler', return_value=mock_filesystem_handler), \
         patch('src.runc_handler.RuncCommandParser', return_value=mock_parser), \
         patch('src.runc_handler.os.path.exists', return_value=True), \
         patch('src.runc_handler.os.access', return_value=True), \
         patch('src.runc_handler.os.environ.get', return_value='/usr/bin/runc'):
        handler = RuncHandler()
        return handler

def test_init_env_var():
    with patch('src.runc_handler.RuncCommandParser'), \
         patch('src.runc_handler.ContainerConfigHandler'), \
         patch('src.runc_handler.ContainerStateManager'), \
         patch('os.makedirs'), \
         patch('os.environ.get', return_value="/usr/bin/runc.real"), \
         patch('os.path.exists', return_value=True), \
         patch('os.access', return_value=True):
        handler = RuncHandler()
        assert handler.original_runc_cmd == "/usr/bin/runc.real"

def test_init_config_file():
    with patch('src.runc_handler.RuncCommandParser'), \
         patch('src.runc_handler.ContainerConfigHandler'), \
         patch('src.runc_handler.ContainerStateManager'), \
         patch('os.makedirs'), \
         patch('os.environ.get', return_value=None), \
         patch('os.path.exists', return_value=True), \
         patch('os.access', return_value=True), \
         patch('builtins.open', mock_open(read_data=f'{ENV_REAL_RUNC_CMD}=/usr/local/bin/runc.real\n')):
        handler = RuncHandler()
        assert handler.original_runc_cmd == "/usr/local/bin/runc.real"

def test_init_config_file_error():
    with patch('src.runc_handler.RuncCommandParser'), \
         patch('os.environ.get', return_value=None), \
         patch('os.path.exists', return_value=True), \
         patch('os.access', return_value=True), \
         patch('builtins.open', side_effect=Exception("File error")), \
         pytest.raises(SystemExit) as exc_info:
        RuncHandler()
    assert exc_info.value.code == 1
    mock_logger.error.assert_any_call(f"Error reading {CONFIG_PATH}: File error")
    mock_logger.error.assert_any_call("Could not find runc binary")

def test_init_no_runc_found():
    with patch('src.runc_handler.RuncCommandParser'), \
         patch('os.environ.get', return_value=None), \
         patch('os.path.exists', return_value=False), \
         pytest.raises(SystemExit) as exc_info:
        RuncHandler()
    assert exc_info.value.code == 1
    mock_logger.error.assert_called_with("Could not find runc binary")

def test_intercept_command_skip_non_interceptable(runc_handler):
    # Setup
    args = ["runc", "list"]
    runc_handler.parser.parse_command.return_value = ("list", {}, {}, None, None)
    
    # Execute
    result = runc_handler.intercept_command(args)
    
    # Verify
    assert result == 1  # Because exec failed
    runc_handler.config_handler.is_tardis_enabled.assert_not_called()
    runc_handler.state_manager.create_state.assert_not_called()
    runc_handler.state_manager.clear_state.assert_not_called()

def test_intercept_command_skip_non_tardis_container(runc_handler):
    # Setup
    args = ["runc", "create", "container1"]
    runc_handler.parser.parse_command.return_value = ("create", {}, {}, "container1", "default")
    runc_handler.config_handler.is_tardis_enabled.return_value = False
    
    # Execute
    result = runc_handler.intercept_command(args)
    
    # Verify
    assert result == 1  # Because exec failed
    runc_handler.state_manager.create_state.assert_not_called()
    runc_handler.state_manager.clear_state.assert_not_called()

def test_intercept_command_create_state(runc_handler):
    # Setup
    args = ["runc", "create", "container1"]
    runc_handler.parser.parse_command.return_value = ("create", {}, {}, "container1", "default")
    runc_handler.config_handler.is_tardis_enabled.return_value = True
    runc_handler.state_manager.has_state.return_value = False
    
    # Execute
    result = runc_handler.intercept_command(args)
    
    # Verify
    assert result == 1  # Because exec failed
    runc_handler.state_manager.create_state.assert_called_once_with("default", "container1")

def test_intercept_command_clear_state(runc_handler):
    # Setup
    args = ["runc", "delete", "container1"]
    runc_handler.parser.parse_command.return_value = ("delete", {}, {}, "container1", "default")
    runc_handler.config_handler.is_tardis_enabled.return_value = True
    runc_handler.state_manager.has_state.return_value = True
    
    # Execute
    result = runc_handler.intercept_command(args)
    
    # Verify
    assert result == 1  # Because exec failed
    runc_handler.state_manager.clear_state.assert_called_once_with("default", "container1")

def test_intercept_command_error_handling(runc_handler):
    # Setup
    args = ["runc", "create", "container1"]
    runc_handler.parser.parse_command.side_effect = Exception("Test error")
    
    # Execute
    result = runc_handler.intercept_command(args)
    
    # Verify
    assert result == 1

def test_execute_original_command_exec_success(runc_handler):
    with patch('os.execvp') as mock_exec:
        mock_exec.side_effect = Exception("Exec would have replaced process")
        result = runc_handler._execute_original_command(["runc", "run", "container1"])
        assert result == 1  # Because exec failed
        mock_exec.assert_called_once_with(
            runc_handler.original_runc_cmd, 
            [runc_handler.original_runc_cmd, "run", "container1"]
        )

def test_execute_original_command_exec_error(runc_handler):
    mock_logger.reset_mock()
    with patch('os.execvp', side_effect=OSError("Exec failed")):
        result = runc_handler._execute_original_command(["runc", "run", "container1"])
        assert result == 1
        mock_logger.error.assert_called_with("Error executing original command: Exec failed")

def test_intercept_command_with_tardis_enabled(runc_handler):
    # Setup
    args = ['runc', 'create', '--bundle', '/path/to/bundle', 'container1']
    runc_handler.parser.parse_command.return_value = ("create", {}, {}, "container1", "default")
    runc_handler.config_handler.is_tardis_enabled.return_value = True
    runc_handler.checkpoint_handler.get_checkpoint_path.return_value = "/path/to/checkpoint"
    runc_handler.state_manager.has_state.return_value = False
    
    # Execute
    result = runc_handler.intercept_command(args)
    
    # Verify
    assert result == 1  # Because exec failed
    runc_handler.config_handler.is_tardis_enabled.assert_called_with('container1', 'default')
    runc_handler.checkpoint_handler.get_checkpoint_path.assert_called_with('container1', 'default')
    runc_handler.state_manager.create_state.assert_called_once_with('default', 'container1')

def test_intercept_command_with_tardis_disabled(runc_handler):
    # Setup
    args = ['runc', 'create', '--bundle', '/path/to/bundle', 'container1']
    runc_handler.parser.parse_command.return_value = ("create", {}, {}, "container1", "default")
    runc_handler.config_handler.is_tardis_enabled.return_value = False
    
    # Execute
    result = runc_handler.intercept_command(args)
    
    # Verify
    assert result == 1  # Because exec failed
    runc_handler.config_handler.is_tardis_enabled.assert_called_with('container1', 'default')
    runc_handler.state_manager.create_state.assert_not_called()

def test_intercept_command_without_container_id(runc_handler, mock_config_handler):
    # Setup
    args = ['runc', 'list']
    with patch.object(runc_handler.parser, 'parse_command') as mock_parse:
        mock_parse.return_value = ("list", {}, [], None, None)
        
        # Execute
        with patch('os.execvp') as mock_exec:
            mock_exec.side_effect = Exception("Exec would have replaced process")
            result = runc_handler.intercept_command(args)
    
    # Verify
    assert result == 1  # Because exec failed
    mock_config_handler.return_value.is_tardis_enabled.assert_not_called()
    mock_config_handler.return_value.get_checkpoint_path.assert_not_called()

def test_modify_command_checkpoint(runc_handler):
    """Test command modification for checkpoint operation."""
    # Setup
    args = ["runc", "checkpoint", "--work-path", "/tmp/work", "--leave-running", "container1"]
    checkpoint_path = "/path/to/checkpoint"
    
    # Execute
    modified_args = runc_handler._modify_command(args, "checkpoint", checkpoint_path)
    
    # Verify
    assert "--work-path" not in modified_args
    assert "--leave-running" not in modified_args
    assert f"--image-path={checkpoint_path}" in modified_args

def test_modify_command_restore(runc_handler):
    """Test command modification for restore operation."""
    # Setup
    args = ["runc", "restore", "--bundle", "/path/to/bundle", "container1"]
    checkpoint_path = "/path/to/checkpoint"
    
    # Execute
    modified_args = runc_handler._modify_command(args, "restore", checkpoint_path)
    
    # Verify
    assert "--detach" in modified_args
    assert f"--image-path={checkpoint_path}" in modified_args

def test_handle_error(runc_handler):
    """Test error handling with logging and command execution."""
    # Setup
    error_msg = "Test error"
    container_id = "container1"
    namespace = "default"
    runc_handler.current_args = ["runc", "create", "container1"]
    
    # Execute
    result = runc_handler._handle_error(error_msg, container_id, namespace)
    
    # Verify
    assert result == 1  # Because exec failed
    mock_logger.error.assert_any_call(f"{error_msg} for container {container_id} in namespace {namespace}")

def test_intercept_command_checkpoint(runc_handler):
    """Test checkpoint command interception and processing."""
    # Setup
    args = ["runc", "checkpoint", "--work-path", "/tmp/work", "container1"]
    runc_handler.parser.parse_command.return_value = ("checkpoint", {}, {"--work-path": "/tmp/work"}, "container1", "default")
    runc_handler.config_handler.is_tardis_enabled.return_value = True
    runc_handler.checkpoint_handler.get_checkpoint_path.return_value = "/path/to/checkpoint"
    runc_handler.checkpoint_handler.copy_container_files.return_value = (True, None)
    
    # Execute
    result = runc_handler.intercept_command(args)
    
    # Verify
    assert result == 1  # Because exec failed
    runc_handler.checkpoint_handler.copy_container_files.assert_called_once_with("/tmp/work", "/path/to/checkpoint")

def test_intercept_command_checkpoint_copy_failure(runc_handler):
    """Test checkpoint command when file copying fails."""
    # Setup
    args = ["runc", "checkpoint", "--work-path", "/tmp/work", "container1"]
    runc_handler.parser.parse_command.return_value = ("checkpoint", {}, {"--work-path": "/tmp/work"}, "container1", "default")
    runc_handler.config_handler.is_tardis_enabled.return_value = True
    runc_handler.checkpoint_handler.get_checkpoint_path.return_value = "/path/to/checkpoint"
    runc_handler.checkpoint_handler.copy_container_files.return_value = (False, "Copy failed")
    
    # Execute
    result = runc_handler.intercept_command(args)
    
    # Verify
    assert result == 1  # Because exec failed
    mock_logger.error.assert_called_with("Failed to copy container files: Copy failed for container container1 in namespace default")

def test_intercept_command_restore(runc_handler):
    """Test restore command interception and processing."""
    # Setup
    args = ["runc", "restore", "--bundle", "/path/to/bundle", "container1"]
    runc_handler.parser.parse_command.return_value = ("restore", {}, {"--bundle": "/path/to/bundle"}, "container1", "default")
    runc_handler.config_handler.is_tardis_enabled.return_value = True
    runc_handler.checkpoint_handler.get_checkpoint_path.return_value = "/path/to/checkpoint"
    runc_handler.checkpoint_handler.validate_checkpoint.return_value = (True, None)
    
    # Execute
    result = runc_handler.intercept_command(args)
    
    # Verify
    assert result == 1  # Because exec failed
    runc_handler.checkpoint_handler.validate_checkpoint.assert_called_once_with("/path/to/checkpoint")

def test_intercept_command_restore_invalid_checkpoint(runc_handler):
    """Test restore command with invalid checkpoint."""
    # Setup
    args = ["runc", "restore", "--bundle", "/path/to/bundle", "container1"]
    runc_handler.parser.parse_command.return_value = ("restore", {}, {"--bundle": "/path/to/bundle"}, "container1", "default")
    runc_handler.config_handler.is_tardis_enabled.return_value = True
    runc_handler.checkpoint_handler.get_checkpoint_path.return_value = "/path/to/checkpoint"
    runc_handler.checkpoint_handler.validate_checkpoint.return_value = (False, "Invalid checkpoint")
    
    # Execute
    result = runc_handler.intercept_command(args)
    
    # Verify
    assert result == 1  # Because exec failed
    mock_logger.error.assert_called_with("Invalid checkpoint: Invalid checkpoint for container container1 in namespace default")

def test_intercept_command_invalid_checkpoint_path(runc_handler):
    """Test command interception with invalid checkpoint path."""
    # Setup
    args = ["runc", "checkpoint", "container1"]
    runc_handler.parser.parse_command.return_value = ("checkpoint", {}, {}, "container1", "default")
    runc_handler.config_handler.is_tardis_enabled.return_value = True
    runc_handler.checkpoint_handler.get_checkpoint_path.return_value = None
    
    # Execute
    result = runc_handler.intercept_command(args)
    
    # Verify
    assert result == 1  # Because exec failed
    mock_logger.error.assert_called_with("Could not determine checkpoint path for container container1 in namespace default")

def test_intercept_command_file_permission_error(runc_handler):
    """Test command interception with file permission error."""
    # Setup
    args = ["runc", "checkpoint", "container1"]
    runc_handler.parser.parse_command.return_value = ("checkpoint", {}, {}, "container1", "default")
    runc_handler.config_handler.is_tardis_enabled.return_value = True
    runc_handler.checkpoint_handler.get_checkpoint_path.return_value = "/path/to/checkpoint"
    runc_handler.checkpoint_handler.copy_container_files.side_effect = PermissionError("Permission denied")
    
    # Execute
    result = runc_handler.intercept_command(args)
    
    # Verify
    assert result == 1  # Because exec failed
    mock_logger.error.assert_called_with("Error handling checkpoint: Permission denied for container container1 in namespace default")

def test_intercept_command_invalid_command_format(runc_handler):
    """Test command interception with invalid command format."""
    # Setup
    args = ["runc"]  # Missing subcommand and container_id
    
    # Execute
    result = runc_handler.intercept_command(args)
    
    # Verify
    assert result == 1  # Because exec failed
    runc_handler.parser.parse_command.assert_called_once_with(args)

def test_intercept_command_corrupted_config(runc_handler):
    """Test command interception with corrupted container config."""
    # Setup
    args = ["runc", "create", "container1"]
    runc_handler.parser.parse_command.return_value = ("create", {}, {}, "container1", "default")
    runc_handler.config_handler.is_tardis_enabled.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
    
    # Execute
    result = runc_handler.intercept_command(args)
    
    # Verify
    assert result == 1  # Because exec failed
    mock_logger.error.assert_any_call("Error intercepting command: Invalid JSON: line 1 column 1 (char 0)")

def test_get_real_runc_cmd_from_env(runc_handler):
    assert runc_handler.original_runc_cmd == '/usr/bin/runc'

def test_get_real_runc_cmd_from_file():
    def debug_exists(x):
        result = x in ['/path/to/tardis.env', '/usr/local/bin/runc', '/path/to/checkpoints']
        print(f"os.path.exists({x}) = {result}")
        return result

    def debug_access(x, mode):
        result = x == '/usr/local/bin/runc' and mode == os.X_OK
        print(f"os.access({x}, {mode}) = {result}")
        return result

    mock_file_content = f'{ENV_REAL_RUNC_CMD}=/usr/local/bin/runc\n'
    mock_file = Mock()
    mock_file.__enter__ = Mock(return_value=mock_file)
    mock_file.__exit__ = Mock()
    mock_file.__iter__ = Mock(return_value=iter([mock_file_content]))

    with patch('src.runc_handler.os.path.exists', side_effect=debug_exists), \
         patch('src.runc_handler.os.access', side_effect=debug_access), \
         patch('src.runc_handler.os.environ.get', return_value=None), \
         patch('src.checkpoint_handler.os.path.exists', side_effect=debug_exists), \
         patch('src.runc_handler.os.makedirs') as mock_makedirs, \
         patch('src.runc_handler.open', return_value=mock_file), \
         patch('src.runc_handler.CONFIG_PATH', '/path/to/tardis.env'), \
         patch('src.runc_handler.ContainerConfigHandler') as mock_config_handler_class, \
         patch('src.runc_handler.sys.exit') as mock_exit:
        mock_config_handler = mock_config_handler_class.return_value
        mock_config_handler.get_checkpoint_base_path.return_value = '/path/to/checkpoints'
        handler = RuncHandler()
        assert handler.original_runc_cmd == '/usr/local/bin/runc'
        mock_exit.assert_not_called()

def test_intercept_command_not_tardis_enabled(runc_handler, mock_config_handler):
    mock_config_handler.is_tardis_enabled.return_value = False
    args = ['runc', 'create', '--bundle', '/path/to/bundle', 'container-id']
    result = runc_handler.intercept_command(args)
    assert result == 1  # Error code since we're not executing original command

def test_intercept_command_create(runc_handler, mock_config_handler, mock_state_manager):
    mock_config_handler.is_tardis_enabled.return_value = True
    mock_state_manager.has_state.return_value = False
    args = ['runc', 'create', '--bundle', '/path/to/bundle', 'container-id']
    result = runc_handler.intercept_command(args)
    mock_state_manager.create_state.assert_called_once()
    assert result == 1  # Error code since we're not executing original command

def test_intercept_command_delete(runc_handler, mock_config_handler, mock_state_manager):
    mock_config_handler.is_tardis_enabled.return_value = True
    mock_state_manager.has_state.return_value = True
    args = ['runc', 'delete', 'container-id']
    result = runc_handler.intercept_command(args)
    mock_state_manager.clear_state.assert_called_once()
    assert result == 1  # Error code since we're not executing original command

def test_intercept_command_checkpoint_error(runc_handler, mock_config_handler, mock_checkpoint_handler):
    mock_config_handler.is_tardis_enabled.return_value = True
    mock_checkpoint_handler.get_checkpoint_path.return_value = None
    args = ['runc', 'checkpoint', 'container-id']
    result = runc_handler.intercept_command(args)
    assert result == 1  # Error code for checkpoint path error

def test_intercept_command_restore_error(runc_handler, mock_config_handler, mock_checkpoint_handler):
    mock_config_handler.is_tardis_enabled.return_value = True
    mock_checkpoint_handler.get_checkpoint_path.return_value = '/path/to/checkpoint'
    mock_checkpoint_handler.validate_checkpoint.return_value = (False, "Invalid checkpoint")
    args = ['runc', 'restore', 'container-id']
    result = runc_handler.intercept_command(args)
    assert result == 1  # Error code for invalid checkpoint

def test_init_runc_handler(runc_handler):
    assert runc_handler.original_runc_cmd == '/usr/bin/runc'
    assert runc_handler.config_handler is not None
    assert runc_handler.state_manager is not None
    assert runc_handler.checkpoint_handler is not None
    assert runc_handler.filesystem_handler is not None

def test_handle_create_command_success(runc_handler, mock_config_handler, mock_filesystem_handler):
    args = ['runc', 'create', '--bundle', '/path/to/bundle', 'container1']
    mock_config_handler.is_tardis_enabled.return_value = True
    mock_filesystem_handler.get_upperdir.return_value = '/path/to/upperdir'
    
    with patch('subprocess.run', return_value=MagicMock(returncode=0)):
        result = runc_handler._handle_create_command(args, 'container1', 'default', {})
        assert result == 0

def test_handle_checkpoint_command_success(runc_handler, mock_config_handler, mock_filesystem_handler, mock_checkpoint_handler):
    args = ['runc', 'checkpoint', '--work-path', '/tmp/work', 'container1']
    mock_config_handler.get_checkpoint_path.return_value = '/path/to/checkpoint'
    mock_filesystem_handler.get_upperdir.return_value = '/path/to/upperdir'
    mock_checkpoint_handler.save_checkpoint.return_value = True
    
    with patch('subprocess.run', return_value=MagicMock(returncode=0)):
        result = runc_handler._handle_checkpoint_command(args, 'container1', 'default', {'--work-path': '/tmp/work'})
        assert result == 0

def test_handle_checkpoint_command_no_path(runc_handler, mock_config_handler):
    args = ['runc', 'checkpoint', 'container1']
    mock_config_handler.get_checkpoint_path.return_value = None
    
    result = runc_handler._handle_checkpoint_command(args, 'container1', 'default', {})
    assert result == 1

def test_handle_checkpoint_command_no_upperdir(runc_handler, mock_config_handler, mock_filesystem_handler):
    args = ['runc', 'checkpoint', 'container1']
    mock_config_handler.get_checkpoint_path.return_value = '/path/to/checkpoint'
    mock_filesystem_handler.get_upperdir.return_value = None
    
    result = runc_handler._handle_checkpoint_command(args, 'container1', 'default', {})
    assert result == 1

def test_handle_checkpoint_command_save_failure(runc_handler, mock_config_handler, mock_filesystem_handler, mock_checkpoint_handler):
    args = ['runc', 'checkpoint', 'container1']
    mock_config_handler.get_checkpoint_path.return_value = '/path/to/checkpoint'
    mock_filesystem_handler.get_upperdir.return_value = '/path/to/upperdir'
    mock_checkpoint_handler.save_checkpoint.return_value = False
    
    with patch('subprocess.run', return_value=MagicMock(returncode=0)):
        result = runc_handler._handle_checkpoint_command(args, 'container1', 'default', {})
        assert result == 1

def test_execute_command_success(runc_handler):
    args = ['runc', 'create', 'container1']
    with patch('subprocess.run', return_value=MagicMock(returncode=0)):
        result = runc_handler._execute_command(args)
        assert result == 0

def test_execute_command_failure(runc_handler):
    args = ['runc', 'create', 'container1']
    with patch('subprocess.run', return_value=MagicMock(returncode=1)):
        result = runc_handler._execute_command(args)
        assert result == 1 