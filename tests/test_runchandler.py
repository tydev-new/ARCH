import pytest
from unittest.mock import Mock, patch
from src.runc_handler import RuncHandler
from src.runc_command_parser import RuncCommandParser

@pytest.fixture
def runc_handler():
    with patch('os.path.exists') as mock_exists, \
         patch('os.access') as mock_access, \
         patch('os.execvp') as mock_execvp:
        mock_exists.return_value = True
        mock_access.return_value = True
        mock_execvp.side_effect = Exception("execvp called")
        
        handler = RuncHandler()
        # Use real parser
        handler.parser = RuncCommandParser()
        # Mock other dependencies
        handler.config_handler.is_arch_enabled = Mock(return_value=True)
        handler.checkpoint_handler.validate_checkpoint = Mock(return_value=False)
        handler.checkpoint_handler.restore_checkpoint_file = Mock(return_value=True)
        handler.flag_manager.get_skip_start = Mock(return_value=False)
        handler.flag_manager.get_skip_resume = Mock(return_value=False)
        handler.flag_manager.get_keep_resources = Mock(return_value=False)
        
        return handler

def test_init_with_env_var():
    with patch.dict('os.environ', {'RUNC_BINARY_PATH': '/usr/bin/runc'}):
        handler = RuncHandler()
        assert handler.original_runc_cmd == '/usr/bin/runc'

def test_init_with_config_file():
    with patch('os.path.exists') as mock_exists, \
         patch('builtins.open', mock_open(read_data='RUNC_BINARY_PATH=/usr/local/bin/runc\n')):
        mock_exists.return_value = True
        handler = RuncHandler()
        assert handler.original_runc_cmd == '/usr/local/bin/runc'

def test_init_no_runc_found():
    with patch('os.path.exists') as mock_exists:
        mock_exists.return_value = False
        with pytest.raises(SystemExit) as exc_info:
            RuncHandler()
        assert exc_info.value.code == 1

def test_intercept_command_create(runc_handler):
    result = runc_handler.intercept_command(["runc", "create", "container1"])
    assert result == 1
    runc_handler.config_handler.is_arch_enabled.assert_called_once()

def test_intercept_command_invalid(runc_handler):
    result = runc_handler.intercept_command(["runc", "invalid", "command"])
    assert result == 1

def test_intercept_command_create_with_bundle(runc_handler):
    result = runc_handler.intercept_command(["runc", "--root", "/var/run/runc", "create", "--bundle", "/path/to/bundle", "container1"])
    assert result == 1
    runc_handler.config_handler.is_arch_enabled.assert_called_once()

def test_intercept_command_checkpoint_with_work_path(runc_handler):
    runc_handler.checkpoint_handler.validate_checkpoint.return_value = True
    result = runc_handler.intercept_command(["runc", "checkpoint", "--work-path", "/tmp/work", "--leave-running", "--image-path", "/old/path", "container1"])
    assert result == 1
    runc_handler.config_handler.is_arch_enabled.assert_called_once()
    runc_handler.flag_manager.set_skip_resume.assert_called_once()
    runc_handler.flag_manager.set_keep_resources.assert_called_once()

def test_intercept_command_create_with_flag(runc_handler):
    result = runc_handler.intercept_command(["runc", "create", "--arch-create", "container1"])
    assert result == 1
    runc_handler.config_handler.is_arch_enabled.assert_called_once()

def test_intercept_command_start_with_skip(runc_handler):
    runc_handler.flag_manager.get_skip_start.return_value = True
    result = runc_handler.intercept_command(["runc", "start", "container1"])
    assert result == 0
    runc_handler.flag_manager.set_skip_start.assert_called_once_with("default", "container1", False)

def test_intercept_command_resume_with_skip(runc_handler):
    runc_handler.flag_manager.get_skip_resume.return_value = True
    result = runc_handler.intercept_command(["runc", "resume", "container1"])
    assert result == 0
    runc_handler.flag_manager.set_skip_resume.assert_called_once_with("default", "container1", False)

def test_intercept_command_delete_with_keep_resources(runc_handler):
    runc_handler.flag_manager.get_keep_resources.return_value = True
    result = runc_handler.intercept_command(["runc", "delete", "container1"])
    assert result == 1
    runc_handler.flag_manager.clear_flag.assert_called_once_with("default", "container1") 