import pytest
from unittest.mock import patch
from src.container_handler.filesystem_handler import ContainerFilesystemHandler
import subprocess

@pytest.fixture
def filesystem_handler():
    return ContainerFilesystemHandler()

def test_get_upperdir_success(filesystem_handler):
    """Test successful extraction of upperdir path."""
    mount_output = """
overlay on /run/containerd/io.containerd.runtime.v2.task/default/container1/rootfs type overlay (rw,relatime,lowerdir=/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/1/fs,upperdir=/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/2/fs,workdir=/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/2/work)
    """
    with patch('subprocess.check_output', return_value=mount_output):
        upperdir = filesystem_handler.get_upperdir('container1', 'default')
        assert upperdir == '/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/2/fs'

def test_get_upperdir_mount_command_fails(filesystem_handler):
    """Test handling of mount command failure."""
    with patch('subprocess.check_output', side_effect=subprocess.CalledProcessError(1, 'mount')):
        upperdir = filesystem_handler.get_upperdir('container1', 'default')
        assert upperdir is None

def test_get_upperdir_no_matching_mount(filesystem_handler):
    """Test when no matching container mount is found."""
    mount_output = """
overlay on /run/containerd/io.containerd.runtime.v2.task/default/other-container/rootfs type overlay (rw,relatime,upperdir=/path/to/upper)
    """
    with patch('subprocess.check_output', return_value=mount_output):
        upperdir = filesystem_handler.get_upperdir('container1', 'default')
        assert upperdir is None

def test_get_upperdir_no_upperdir_option(filesystem_handler):
    """Test when mount is found but has no upperdir option."""
    mount_output = """
overlay on /run/containerd/io.containerd.runtime.v2.task/default/container1/rootfs type overlay (rw,relatime,lowerdir=/path/to/lower,workdir=/path/to/work)
    """
    with patch('subprocess.check_output', return_value=mount_output):
        upperdir = filesystem_handler.get_upperdir('container1', 'default')
        assert upperdir is None

def test_get_upperdir_invalid_mount_output(filesystem_handler):
    """Test handling of invalid mount output format."""
    mount_output = "invalid mount output format"
    with patch('subprocess.check_output', return_value=mount_output):
        upperdir = filesystem_handler.get_upperdir('container1', 'default')
        assert upperdir is None

def test_get_upperdir_multiple_mounts(filesystem_handler):
    """Test with multiple overlay mounts, should find correct one."""
    mount_output = """
overlay on /path/to/other type overlay (rw,upperdir=/wrong/path)
overlay on /run/containerd/io.containerd.runtime.v2.task/default/container1/rootfs type overlay (rw,upperdir=/correct/path)
overlay on /path/to/another type overlay (rw,upperdir=/another/wrong/path)
    """
    with patch('subprocess.check_output', return_value=mount_output):
        upperdir = filesystem_handler.get_upperdir('container1', 'default')
        assert upperdir == '/correct/path' 