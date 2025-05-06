import pytest
import os
import tempfile
from unittest.mock import patch
from src.arch_cli import parse_args, configure_logging, get_arch_containers, finalize_container
from src.utils.constants import CONFIG_PATH

@pytest.fixture
def config_file():
    """Create a temporary config file for testing."""
    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as f:
        f.write("""ARCH_REAL_RUNC_CMD=/usr/sbin/runc.real
ARCH_LOG_LEVEL=INFO
ARCH_LOG_FILE=/var/log/arch.log""")
        f.flush()
        os.fsync(f.fileno())
        f.seek(0)
        yield f.name
    os.unlink(f.name)

@pytest.fixture
def mock_flag_manager():
    """Mock the flag manager for container operations."""
    with patch('src.arch_cli.ContainerFlagManager') as mock:
        mock.return_value.list_containers.return_value = [
            ('default', 'container1'),
            ('default', 'container2')
        ]
        yield mock

@pytest.fixture
def mock_runtime_state():
    """Mock the runtime state for container operations."""
    with patch('src.arch_cli.ContainerRuntimeState') as mock:
        instance = mock.return_value
        instance.get_container_state.return_value = ('running', None)
        yield mock

class TestArchCLI:
    def test_parse_args_container_finalize(self):
        """Test parsing container finalize command."""
        args = parse_args(['container', 'finalize'])
        assert args.command == 'container'
        assert args.container_command == 'finalize'

    def test_parse_args_log_level(self):
        """Test parsing log level command."""
        args = parse_args(['log', '--level', 'DEBUG'])
        assert args.command == 'log'
        assert args.level == 'DEBUG'

    def test_parse_args_log_file(self):
        """Test parsing log file command."""
        args = parse_args(['log', '--file', '/tmp/test.log'])
        assert args.command == 'log'
        assert args.file == '/tmp/test.log'

    def test_configure_logging_level(self, config_file):
        """Test configuring log level."""
        with patch('src.arch_cli.CONFIG_PATH', config_file):
            args = parse_args(['log', '--level', 'DEBUG'])
            configure_logging(args)
            with open(config_file, 'r') as f:
                content = f.read()
                assert 'ARCH_LOG_LEVEL=DEBUG' in content
                assert 'ARCH_REAL_RUNC_CMD=/usr/sbin/runc.real' in content  # Verify existing config preserved

    def test_configure_logging_file(self, config_file):
        """Test configuring log file."""
        with patch('src.arch_cli.CONFIG_PATH', config_file):
            args = parse_args(['log', '--file', '/tmp/test.log'])
            configure_logging(args)
            with open(config_file, 'r') as f:
                content = f.read()
                assert 'ARCH_LOG_FILE=/tmp/test.log' in content
                assert 'ARCH_REAL_RUNC_CMD=/usr/sbin/runc.real' in content  # Verify existing config preserved

    def test_get_arch_containers(self, mock_flag_manager):
        """Test getting arch containers."""
        containers = get_arch_containers()
        assert len(containers) == 2
        assert containers[0]['id'] == 'container1'
        assert containers[0]['namespace'] == 'default'

    def test_finalize_container_success(self, mock_runtime_state):
        """Test successful container finalization."""
        with patch('src.arch_cli.subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stderr = ''
            result = finalize_container('container1', 'default')
            assert result is True
            assert mock_run.call_count == 4  # checkpoint, kill, rm task, rm container

    def test_finalize_container_not_running(self, mock_runtime_state):
        """Test finalizing non-running container."""
        mock_runtime_state.return_value.get_container_state.return_value = ('stopped', None)
        with patch('src.arch_cli.subprocess.run') as mock_run:
            result = finalize_container('container1', 'default')
            assert result is False
            assert mock_run.call_count == 0

    def test_finalize_container_checkpoint_failure(self, mock_runtime_state):
        """Test container finalization with checkpoint failure."""
        with patch('src.arch_cli.subprocess.run') as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = 'checkpoint failed'
            result = finalize_container('container1', 'default')
            assert result is True  # Still returns True as we try to clean up
            assert mock_run.call_count == 4  # All cleanup steps still attempted 