import os
import sys
import json
import pytest
from unittest.mock import patch, mock_open, MagicMock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Mock the logger
mock_logger = patch('src.utils.logging.logger').start()

from src.container_handler.config_handler import ContainerConfigHandler

# Load actual config file
CONFIG_PATH = "/home/ec2-user/new-tardis/tests/resource/sample_container_run_directory/config.json"
with open(CONFIG_PATH, 'r') as f:
    SAMPLE_CONFIG = json.load(f)

@pytest.fixture(autouse=True)
def setup_and_teardown():
    # Reset mock before each test
    mock_logger.reset_mock()
    yield
    # Clean up after each test
    mock_logger.reset_mock()

@pytest.fixture
def config_handler():
    return ContainerConfigHandler()

@pytest.fixture
def sample_config_path():
    return "/run/containerd/io.containerd.runtime.v2.task/default/container1/config.json"

def test_find_config_path_success(config_handler):
    with patch('os.path.exists', return_value=True):
        path = config_handler._find_config_path("default", "container1")
        assert path == "/run/containerd/io.containerd.runtime.v2.task/default/container1/config.json"
        mock_logger.debug.assert_called_with(
            "Found config.json at: /run/containerd/io.containerd.runtime.v2.task/default/container1/config.json"
        )

def test_find_config_path_not_found(config_handler):
    with patch('os.path.exists', return_value=False):
        path = config_handler._find_config_path("default", "container1")
        assert path is None
        mock_logger.error.assert_called_with(
            "Could not find config.json for container container1 in namespace default"
        )

def test_read_config_success(config_handler, sample_config_path):
    mock_file = mock_open(read_data=json.dumps(SAMPLE_CONFIG))
    with patch('builtins.open', mock_file):
        config = config_handler._read_config(sample_config_path)
        assert config == SAMPLE_CONFIG
        mock_logger.debug.assert_called_with(
            f"Successfully read config.json from {sample_config_path}"
        )

def test_read_config_json_error(config_handler, sample_config_path):
    mock_file = mock_open(read_data="invalid json")
    with patch('builtins.open', mock_file):
        config = config_handler._read_config(sample_config_path)
        assert config is None
        mock_logger.error.assert_called_with(
            f"Failed to read config.json from {sample_config_path}: Expecting value: line 1 column 1 (char 0)"
        )

def test_read_config_io_error(config_handler, sample_config_path):
    with patch('builtins.open', side_effect=IOError("File not found")):
        config = config_handler._read_config(sample_config_path)
        assert config is None
        mock_logger.error.assert_called_with(
            f"Failed to read config.json from {sample_config_path}: File not found"
        )

def test_is_tardis_enabled_success(config_handler):
    with patch('os.path.exists', return_value=True), \
         patch('builtins.open', mock_open(read_data=json.dumps(SAMPLE_CONFIG))):
        is_enabled = config_handler.is_tardis_enabled("container1", "default")
        assert is_enabled is True
        mock_logger.info.assert_called_with("Container container1 is Tardis-enabled")

def test_is_tardis_enabled_not_found(config_handler):
    with patch('os.path.exists', return_value=False):
        is_enabled = config_handler.is_tardis_enabled("container1", "default")
        assert is_enabled is False

def test_is_tardis_enabled_invalid_input(config_handler):
    is_enabled = config_handler.is_tardis_enabled("", "default")
    assert is_enabled is False
    mock_logger.error.assert_called_with("Invalid container_id or namespace: id=, namespace=default")

def test_is_tardis_enabled_read_error(config_handler):
    with patch('os.path.exists', return_value=True), \
         patch('builtins.open', mock_open(read_data="invalid json")):
        is_enabled = config_handler.is_tardis_enabled("container1", "default")
        assert is_enabled is False

def test_get_checkpoint_path_success(config_handler):
    with patch('os.path.exists', return_value=True), \
         patch('builtins.open', mock_open(read_data=json.dumps(SAMPLE_CONFIG))):
        path = config_handler.get_checkpoint_path("container1", "default")
        assert path == "/home/ec2-user/Tardis2/data"
        mock_logger.debug.assert_called_with("Found checkpoint path: /home/ec2-user/Tardis2/data")

def test_get_checkpoint_path_not_found(config_handler):
    with patch('os.path.exists', return_value=False):
        path = config_handler.get_checkpoint_path("container1", "default")
        assert path is None

def test_get_checkpoint_path_invalid_input(config_handler):
    path = config_handler.get_checkpoint_path("", "default")
    assert path is None
    mock_logger.error.assert_called_with("Invalid container_id or namespace: id=, namespace=default")

def test_get_checkpoint_path_read_error(config_handler):
    with patch('os.path.exists', return_value=True), \
         patch('builtins.open', mock_open(read_data="invalid json")):
        path = config_handler.get_checkpoint_path("container1", "default")
        assert path is None 