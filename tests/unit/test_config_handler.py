import os
import sys
import json
import shutil
import tempfile
import pytest
import logging
from unittest.mock import patch, mock_open, MagicMock
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.container_handler.config_handler import ContainerConfigHandler
from src.utils.constants import CONTAINER_CONFIG_PATHS, LOG_FILE
from src.utils.logging import setup_logger

@pytest.fixture(autouse=True)
def setup_and_cleanup_logging():
    """Setup logging and cleanup log file after each test"""
    # Ensure logs directory exists
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    # Setup logger with DEBUG level
    logger = setup_logger('arch', level=logging.DEBUG)
    yield logger
    # Cleanup log file after test
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)

def assert_log_contains(expected_message: str):
    """Helper function to check if a message exists in the log file"""
    if not os.path.exists(LOG_FILE):
        pytest.fail(f"Log file {LOG_FILE} does not exist")
    with open(LOG_FILE, 'r') as f:
        log_content = f.read()
        assert expected_message in log_content, f"Expected message '{expected_message}' not found in log"

# Load actual config file
CONFIG_PATH = "tests/resource/sample_container_run_directory/config.json"
with open(CONFIG_PATH, 'r') as f:
    SAMPLE_CONFIG = json.load(f)

@pytest.fixture
def temp_test_dir():
    """Create a temporary directory with a copy of sample config for each test"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create container directory structure
        container_dir = os.path.join(temp_dir, "container1")
        os.makedirs(container_dir)
        
        # Copy and modify config.json with test env vars
        with open("tests/resource/sample_container_run_directory/config.json", 'r') as f:
            config = json.load(f)
        
        # Add/update environment variables
        env_vars = config.get('process', {}).get('env', [])
        new_env_vars = []
        for var in env_vars:
            if not var.startswith(("ARCH_SHAREDFS_HOST_PATH=", "ARCH_WORKDIR_CONTAINER_PATH=")):
                new_env_vars.append(var)
        
        new_env_vars.extend([
            f"ARCH_SHAREDFS_HOST_PATH={temp_dir}",
            "ARCH_WORKDIR_CONTAINER_PATH=/tmp",
            "ARCH_ENABLE=1"
        ])
        config['process']['env'] = new_env_vars
        
        # Write modified config
        with open(os.path.join(container_dir, "config.json"), 'w') as f:
            json.dump(config, f)
        
        # Create rootfs directory with minimal structure
        rootfs_dir = os.path.join(container_dir, "rootfs")
        os.makedirs(rootfs_dir)
        os.makedirs(os.path.join(rootfs_dir, "tmp"))
        
        yield temp_dir

@pytest.fixture
def config_handler():
    return ContainerConfigHandler()

@pytest.fixture
def sample_config_path():
    return "/run/containerd/io.containerd.runtime.v2.task/default/container1/config.json"

def test_find_config_path_success(config_handler, temp_test_dir):
    # Create directory structure following the pattern from CONTAINER_CONFIG_PATHS
    config_dir = os.path.join(temp_test_dir, "default", "container1")
    os.makedirs(config_dir, exist_ok=True)
    
    # Copy sample config to the expected location
    config_path = os.path.join(config_dir, "config.json")
    shutil.copy(CONFIG_PATH, config_path)
    
    # Create test config path pattern and update handler's paths
    test_config_path = os.path.join(temp_test_dir, "{namespace}", "{container_id}", "config.json")
    config_handler.possible_config_paths = [test_config_path]
    
    # Test finding the config
    path = config_handler._find_config_path("default", "container1")
    assert path == config_path
    assert_log_contains("Found config.json at: " + config_path)

def test_find_config_path_not_found(config_handler, temp_test_dir):
    # Create test config path pattern and update handler's paths
    test_config_path = os.path.join(temp_test_dir, "{namespace}", "{container_id}", "config.json")
    config_handler.possible_config_paths = [test_config_path]
    
    # Test finding non-existent config
    path = config_handler._find_config_path("default", "container1")
    assert path is None
    assert_log_contains("Could not find config.json for container container1 in namespace default")

def test_read_config_success(config_handler, temp_test_dir):
    config_path = os.path.join(temp_test_dir, "container1", "config.json")
    config = config_handler._read_config(config_path)
    assert config is not None
    assert 'process' in config
    assert 'env' in config['process']
    assert_log_contains(f"Successfully read config.json from {config_path}")

def test_read_config_json_error(config_handler, temp_test_dir):
    config_path = os.path.join(temp_test_dir, "container1", "config.json")
    with open(config_path, 'w') as f:
        f.write("invalid json")
    config = config_handler._read_config(config_path)
    assert config is None
    assert_log_contains(
        f"Failed to read config.json from {config_path}: Expecting value: line 1 column 1 (char 0)"
    )

def test_read_config_io_error(config_handler):
    config = config_handler._read_config("/nonexistent/path")
    assert config is None
    assert_log_contains("Failed to read config.json from /nonexistent/path: [Errno 2] No such file or directory: '/nonexistent/path'")

def test_is_arch_enabled_success(config_handler, temp_test_dir):
    # Create config with ARCH_ENABLE=1
    config = {
        "process": {
            "env": [
                "ARCH_SHAREDFS_HOST_PATH=/tmp",
                "ARCH_WORKDIR_CONTAINER_PATH=/tmp",
                "ARCH_ENABLE=1"
            ]
        }
    }
    
    # Write config file
    config_path = os.path.join(temp_test_dir, "container1", "config.json")
    with open(config_path, 'w') as f:
        json.dump(config, f)
        
    # Mock _find_config_path to return our test config
    with patch.object(config_handler, '_find_config_path', return_value=config_path):
        is_enabled = config_handler.is_arch_enabled("container1", "default")
        assert is_enabled is True

def test_is_arch_enabled_not_found(config_handler, temp_test_dir):
    # Create config without ARCH_ENABLE
    config = {
        "process": {
            "env": []
        }
    }
    # Mock config paths to use nonexistent path
    with patch('src.container_handler.config_handler.CONTAINER_CONFIG_PATHS', 
              ["/nonexistent/{namespace}/{container_id}/config.json"]):
        is_enabled = config_handler.is_arch_enabled("container1", "default")
        assert is_enabled is False

def test_is_arch_enabled_invalid_input(config_handler):
    is_enabled = config_handler.is_arch_enabled("", "default")
    assert not is_enabled
    assert_log_contains("Invalid container_id or namespace: id=, namespace=default")

def test_get_checkpoint_path_success(config_handler, config_template, temp_container_env):
    """Test get_checkpoint_path with networkfs path"""
    env_vars = [
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        f"ARCH_SHAREDFS_HOST_PATH={temp_container_env}"
    ]
    create_test_config(config_template, env_vars, temp_container_env)
    
    config_handler.possible_config_paths = [
        os.path.join(temp_container_env, "{namespace}", "{container_id}", "config.json")
    ]
    
    expected_path = os.path.join(temp_container_env, "checkpoint", "default", "container1")
    assert config_handler.get_checkpoint_path("container1", "default") == expected_path

def test_get_checkpoint_path_not_found(config_handler):
    with patch('os.path.exists', return_value=False):
        path = config_handler.get_checkpoint_path("container1", "default")
        assert path == "/var/lib/arch/checkpoint/default/container1"

def test_get_checkpoint_path_invalid_input(config_handler):
    path = config_handler.get_checkpoint_path("", "default")
    assert path == "/var/lib/arch/checkpoint/default/"

def test_get_checkpoint_path_read_error(config_handler):
    with patch('os.path.exists', return_value=True), \
         patch('builtins.open', mock_open(read_data="invalid json")):
        path = config_handler.get_checkpoint_path("container1", "default")
        assert path == "/var/lib/arch/checkpoint/default/container1"

def test_ensure_directory_success(config_handler):
    with patch('os.makedirs') as mock_makedirs:
        result = config_handler._ensure_directory("/path/to/dir")
        assert result is True
        mock_makedirs.assert_called_once_with("/path/to/dir", exist_ok=True)

def test_ensure_directory_error(config_handler):
    with patch('os.makedirs', side_effect=OSError("Permission denied")):
        result = config_handler._ensure_directory("/path/to/dir")
        assert result is False

def test_add_bind_mount_success(config_handler, config_template, temp_container_env):
    """Test add_bind_mount with valid configuration"""
    env_vars = [
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        f"ARCH_SHAREDFS_HOST_PATH={temp_container_env}",
        "ARCH_WORKDIR_CONTAINER_PATH=/tmp"
    ]
    config_path = create_test_config(config_template, env_vars, temp_container_env)
    
    config_handler.possible_config_paths = [
        os.path.join(temp_container_env, "{namespace}", "{container_id}", "config.json")
    ]
    
    # Create work directory
    work_dir = os.path.join(temp_container_env, "work", "default", "container1")
    os.makedirs(work_dir)
    
    assert config_handler.add_bind_mount("container1", "default") is True
    
    # Verify config was updated correctly
    with open(config_path, 'r') as f:
        updated_config = json.load(f)
    
    assert validate_oci_mount_and_cwd(
        updated_config,
        work_dir,
        "/tmp",
        "/tmp"
    )

def test_add_bind_mount_no_networkfs(config_handler, config_template, temp_container_env):
    """Test add_bind_mount when networkfs path is not set"""
    env_vars = ["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"]
    create_test_config(config_template, env_vars, temp_container_env)
    
    config_handler.possible_config_paths = [
        os.path.join(temp_container_env, "{namespace}", "{container_id}", "config.json")
    ]
    
    assert config_handler.add_bind_mount("container1", "default") is True

def test_add_bind_mount_rootfs_not_found(config_handler, config_template, temp_container_env):
    """Test add_bind_mount when rootfs directory is missing"""
    env_vars = [
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        f"ARCH_SHAREDFS_HOST_PATH={temp_container_env}",
        "ARCH_WORKDIR_CONTAINER_PATH=/tmp"
    ]
    create_test_config(config_template, env_vars, temp_container_env)
    
    # Remove rootfs directory
    rootfs_dir = os.path.join(temp_container_env, "default", "container1", "rootfs")
    shutil.rmtree(rootfs_dir)
    
    config_handler.possible_config_paths = [
        os.path.join(temp_container_env, "{namespace}", "{container_id}", "config.json")
    ]
    
    assert config_handler.add_bind_mount("container1", "default") is False

def test_add_bind_mount_destination_not_found(config_handler, config_template, temp_container_env):
    """Test add_bind_mount when destination directory is missing"""
    env_vars = [
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        f"ARCH_SHAREDFS_HOST_PATH={temp_container_env}",
        "ARCH_WORKDIR_CONTAINER_PATH=/nonexistent"
    ]
    create_test_config(config_template, env_vars, temp_container_env)
    
    config_handler.possible_config_paths = [
        os.path.join(temp_container_env, "{namespace}", "{container_id}", "config.json")
    ]
    
    assert config_handler.add_bind_mount("container1", "default") is False

def test_delete_work_directory_success(config_handler, config_template, temp_container_env):
    """Test delete_work_directory with existing directory"""
    env_vars = [
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        f"ARCH_SHAREDFS_HOST_PATH={temp_container_env}"
    ]
    create_test_config(config_template, env_vars, temp_container_env)
    
    # Create work directory
    work_dir = os.path.join(temp_container_env, "work", "default", "container1")
    os.makedirs(work_dir)
    
    config_handler.possible_config_paths = [
        os.path.join(temp_container_env, "{namespace}", "{container_id}", "config.json")
    ]
    
    assert config_handler.delete_work_directory("container1", "default") is True
    assert not os.path.exists(work_dir)

def test_delete_work_directory_no_networkfs(config_handler, config_template, temp_container_env):
    """Test delete_work_directory when networkfs path is not set"""
    env_vars = ["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"]
    create_test_config(config_template, env_vars, temp_container_env)
    
    config_handler.possible_config_paths = [
        os.path.join(temp_container_env, "{namespace}", "{container_id}", "config.json")
    ]
    
    assert config_handler.delete_work_directory("container1", "default") is True

def test_delete_work_directory_not_found(config_handler, config_template, temp_container_env):
    """Test delete_work_directory when directory doesn't exist"""
    env_vars = [
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        f"ARCH_SHAREDFS_HOST_PATH={temp_container_env}"
    ]
    create_test_config(config_template, env_vars, temp_container_env)
    
    config_handler.possible_config_paths = [
        os.path.join(temp_container_env, "{namespace}", "{container_id}", "config.json")
    ]
    
    assert config_handler.delete_work_directory("container1", "default") is True

def validate_oci_mount_and_cwd(config: dict, expected_source: str, expected_dest: str, expected_cwd: str) -> bool:
    """
    Validate OCI config mount and cwd sections.
    
    Args:
        config: OCI config dictionary
        expected_source: Expected mount source path
        expected_dest: Expected mount destination path
        expected_cwd: Expected working directory
        
    Returns:
        bool: True if validation passes, False otherwise
    """
    # Validate mount
    mount_found = False
    for mount in config.get('mounts', []):
        if (mount.get('type') == 'bind' and 
            mount.get('source') == expected_source and 
            mount.get('destination') == expected_dest and
            mount.get('options') == ['rbind', 'rw']):
            mount_found = True
            break
            
    # Validate cwd
    cwd_valid = config.get('process', {}).get('cwd') == expected_cwd
    
    return mount_found and cwd_valid

@pytest.fixture
def config_template():
    """Load the OCI config template"""
    template_path = Path(__file__).parent.parent / "resource" / "config.json.template"
    with open(template_path, 'r') as f:
        return json.load(f)

@pytest.fixture
def temp_container_env():
    """Create temporary container environment"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create container directory structure
        container_dir = os.path.join(temp_dir, "default", "container1")
        os.makedirs(container_dir)
        
        # Create rootfs with tmp directory
        rootfs_dir = os.path.join(container_dir, "rootfs")
        os.makedirs(rootfs_dir)
        os.makedirs(os.path.join(rootfs_dir, "tmp"))
        
        yield temp_dir

def create_test_config(base_config: dict, env_vars: list, temp_dir: str) -> str:
    """
    Create a test config file with given environment variables.
    
    Args:
        base_config: Base OCI config
        env_vars: List of environment variables to add
        temp_dir: Temporary directory path
        
    Returns:
        str: Path to created config file
    """
    config = base_config.copy()
    config['process']['env'] = env_vars
    
    config_path = os.path.join(temp_dir, "default", "container1", "config.json")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    
    with open(config_path, 'w') as f:
        json.dump(config, f)
        
    return config_path

def test_is_arch_enabled_true(config_handler, config_template, temp_container_env):
    """Test is_arch_enabled when ARCH is enabled"""
    env_vars = [
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "ARCH_ENABLE=1"
    ]
    create_test_config(config_template, env_vars, temp_container_env)
    
    # Update config paths to use temp directory
    config_handler.possible_config_paths = [
        os.path.join(temp_container_env, "{namespace}", "{container_id}", "config.json")
    ]
    
    assert config_handler.is_arch_enabled("container1", "default") is True

def test_is_arch_enabled_false(config_handler, config_template, temp_container_env):
    """Test is_arch_enabled when ARCH is disabled"""
    env_vars = [
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "ARCH_ENABLE=0"
    ]
    create_test_config(config_template, env_vars, temp_container_env)
    
    config_handler.possible_config_paths = [
        os.path.join(temp_container_env, "{namespace}", "{container_id}", "config.json")
    ]
    
    assert config_handler.is_arch_enabled("container1", "default") is False

def test_is_arch_enabled_not_found(config_handler, temp_container_env):
    """Test is_arch_enabled when config not found"""
    config_handler.possible_config_paths = [
        os.path.join(temp_container_env, "{namespace}", "{container_id}", "config.json")
    ]
    
    assert config_handler.is_arch_enabled("container1", "default") is False

def test_get_checkpoint_path_networkfs(config_handler, config_template, temp_container_env):
    """Test get_checkpoint_path with networkfs path"""
    env_vars = [
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        f"ARCH_SHAREDFS_HOST_PATH={temp_container_env}"
    ]
    create_test_config(config_template, env_vars, temp_container_env)
    
    config_handler.possible_config_paths = [
        os.path.join(temp_container_env, "{namespace}", "{container_id}", "config.json")
    ]
    
    expected_path = os.path.join(temp_container_env, "checkpoint", "default", "container1")
    assert config_handler.get_checkpoint_path("container1", "default") == expected_path

def test_get_checkpoint_path_host(config_handler, config_template, temp_container_env):
    """Test get_checkpoint_path with checkpoint host path"""
    env_vars = [
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        f"ARCH_CHECKPOINT_HOST_PATH={temp_container_env}"
    ]
    create_test_config(config_template, env_vars, temp_container_env)
    
    config_handler.possible_config_paths = [
        os.path.join(temp_container_env, "{namespace}", "{container_id}", "config.json")
    ]
    
    expected_path = os.path.join(temp_container_env, "default", "container1")
    assert config_handler.get_checkpoint_path("container1", "default") == expected_path

def test_get_checkpoint_path_default(config_handler, config_template, temp_container_env):
    """Test get_checkpoint_path with default path"""
    env_vars = ["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"]
    create_test_config(config_template, env_vars, temp_container_env)
    
    config_handler.possible_config_paths = [
        os.path.join(temp_container_env, "{namespace}", "{container_id}", "config.json")
    ]
    
    expected_path = os.path.join("/var/lib/arch/checkpoint", "default", "container1")
    assert config_handler.get_checkpoint_path("container1", "default") == expected_path 