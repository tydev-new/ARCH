import pytest
from unittest.mock import Mock, patch
from src.container_handler.config_handler import ContainerConfigHandler
import os

@pytest.fixture
def config_handler():
    with patch('src.container_handler.config_handler.os.path.exists', return_value=True), \
         patch('src.container_handler.config_handler.os.access', return_value=True):
        return ContainerConfigHandler()

def test_get_checkpoint_base_path(config_handler):
    with patch('src.container_handler.config_handler.CONFIG_PATH', '/path/to/config'):
        path = config_handler.get_checkpoint_base_path()
        assert path == '/path/to/config/checkpoints'

def test_is_tardis_enabled_true(config_handler):
    with patch('src.container_handler.config_handler.CONFIG_PATH', '/path/to/config'), \
         patch('src.container_handler.config_handler.os.path.exists', return_value=True):
        assert config_handler.is_tardis_enabled() is True

def test_is_tardis_enabled_false(config_handler):
    with patch('src.container_handler.config_handler.CONFIG_PATH', '/path/to/config'), \
         patch('src.container_handler.config_handler.os.path.exists', return_value=False):
        assert config_handler.is_tardis_enabled() is False

def test_get_container_config(config_handler):
    mock_config = {'container_id': 'test-container', 'bundle_path': '/path/to/bundle'}
    with patch('src.container_handler.config_handler.json.load', return_value=mock_config), \
         patch('src.container_handler.config_handler.open', Mock()):
        config = config_handler.get_container_config('test-container')
        assert config == mock_config

def test_get_container_config_not_found(config_handler):
    with patch('src.container_handler.config_handler.os.path.exists', return_value=False):
        config = config_handler.get_container_config('test-container')
        assert config is None

def test_save_container_config(config_handler):
    mock_config = {'container_id': 'test-container', 'bundle_path': '/path/to/bundle'}
    with patch('src.container_handler.config_handler.json.dump') as mock_dump, \
         patch('src.container_handler.config_handler.open', Mock()), \
         patch('src.container_handler.config_handler.os.makedirs'):
        config_handler.save_container_config('test-container', mock_config)
        mock_dump.assert_called_once()

def test_delete_container_config(config_handler):
    with patch('src.container_handler.config_handler.os.remove') as mock_remove:
        config_handler.delete_container_config('test-container')
        mock_remove.assert_called_once() 