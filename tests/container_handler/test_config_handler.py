import os
import json
import pytest
from src.container_handler.config_handler import ContainerConfigHandler

@pytest.fixture
def handler():
    return ContainerConfigHandler()

@pytest.fixture
def sample_config():
    return {
        "process": {
            "env": [
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "TARDIS_ENABLE=1",
                "TARDIS_CHECKPOINT_HOST_PATH=/var/lib/tardis/checkpoint"
            ]
        }
    }

@pytest.fixture
def temp_config_file(tmp_path, sample_config):
    # Create a temporary config file
    config_dir = tmp_path / "run" / "containerd" / "runc" / "default" / "test-container"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.json"
    
    with open(config_file, 'w') as f:
        json.dump(sample_config, f)
        
    return str(config_file)

def test_find_config_path(handler, temp_config_file):
    path = handler.find_config_path("default", "test-container")
    assert path == temp_config_file

def test_find_config_path_not_found(handler):
    path = handler.find_config_path("nonexistent", "test-container")
    assert path is None

def test_read_config(handler, temp_config_file, sample_config):
    config = handler.read_config(temp_config_file)
    assert config == sample_config

def test_read_config_invalid_json(handler, tmp_path):
    # Create an invalid JSON file
    invalid_file = tmp_path / "invalid.json"
    with open(invalid_file, 'w') as f:
        f.write("invalid json")
        
    config = handler.read_config(str(invalid_file))
    assert config is None

def test_is_tardis_enabled(handler, sample_config):
    assert handler.is_tardis_enabled(sample_config) is True

def test_is_tardis_enabled_not_set(handler):
    config = {
        "process": {
            "env": ["PATH=/usr/local/bin"]
        }
    }
    assert handler.is_tardis_enabled(config) is False

def test_is_tardis_enabled_invalid_config(handler):
    config = {"invalid": "config"}
    assert handler.is_tardis_enabled(config) is False

def test_get_checkpoint_path(handler, sample_config):
    path = handler.get_checkpoint_path(sample_config)
    assert path == "/var/lib/tardis/checkpoint"

def test_get_checkpoint_path_not_set(handler):
    config = {
        "process": {
            "env": ["PATH=/usr/local/bin"]
        }
    }
    assert handler.get_checkpoint_path(config) is None

def test_get_checkpoint_path_invalid_config(handler):
    config = {"invalid": "config"}
    assert handler.get_checkpoint_path(config) is None 