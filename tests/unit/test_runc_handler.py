import os
import sys
import pytest
from unittest.mock import patch, MagicMock, mock_open, Mock, ANY

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Mock logger at module level
mock_logger = MagicMock()
patch('src.utils.logging.logger', mock_logger).start()

from src.runc_handler import RuncHandler
from src.utils.constants import ENV_REAL_RUNC_CMD, CONFIG_PATH, INTERCEPTABLE_COMMANDS

@pytest.fixture(autouse=True)
def setup_and_teardown():
    # Reset mock before each test
    mock_logger.reset_mock()
    yield
    # Clean up after each test
    mock_logger.reset_mock()

@pytest.fixture
def mock_config_handler():
    with patch('src.container_handler.config_handler.ContainerConfigHandler') as mock:
        yield mock

@pytest.fixture
def runc_handler():
    with patch('src.runc_handler.RuncCommandParser') as mock_parser, \
         patch('src.runc_handler.ContainerConfigHandler') as mock_config, \
         patch('src.runc_handler.ContainerStateManager') as mock_state, \
         patch('os.makedirs') as mock_makedirs, \
         patch('os.execvp') as mock_exec:
        handler = RuncHandler()
        handler.parser = mock_parser.return_value
        handler.config_handler = mock_config.return_value
        handler.state_manager = mock_state.return_value
        handler.original_runc_cmd = "/usr/local/bin/runc"
        mock_exec.side_effect = Exception("Exec would have replaced process")
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
    runc_handler.config_handler.get_checkpoint_path.return_value = "/path/to/checkpoint"
    runc_handler.state_manager.has_state.return_value = False
    
    # Execute
    result = runc_handler.intercept_command(args)
    
    # Verify
    assert result == 1  # Because exec failed
    runc_handler.config_handler.is_tardis_enabled.assert_called_with('container1', 'default')
    runc_handler.config_handler.get_checkpoint_path.assert_called_with('container1', 'default')
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