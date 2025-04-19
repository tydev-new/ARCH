import pytest
from unittest.mock import Mock, patch, mock_open
from src.checkpoint_handler import CheckpointHandler
import os
import tarfile
import shutil

@pytest.fixture
def checkpoint_handler():
    """Create a CheckpointHandler instance."""
    return CheckpointHandler()

@pytest.fixture
def temp_checkpoint_dir(tmp_path):
    """Create a temporary checkpoint directory."""
    checkpoint_dir = tmp_path / "checkpoint"
    checkpoint_dir.mkdir()
    return checkpoint_dir

@pytest.fixture
def temp_upperdir(tmp_path):
    """Create a temporary upperdir with some test files."""
    upperdir = tmp_path / "upperdir"
    upperdir.mkdir()
    (upperdir / "fs").mkdir()
    (upperdir / "fs" / "test.txt").write_text("test content")
    return upperdir

def test_validate_checkpoint_success(checkpoint_handler, temp_checkpoint_dir):
    """Test successful checkpoint validation with valid dump.log."""
    dump_log = temp_checkpoint_dir / "dump.log"
    dump_log.write_text("Some log\nDumping finished successfully")
    assert checkpoint_handler.validate_checkpoint(str(temp_checkpoint_dir)) is True

def test_validate_checkpoint_no_dump_log(checkpoint_handler, temp_checkpoint_dir):
    """Test checkpoint validation when dump.log doesn't exist."""
    assert checkpoint_handler.validate_checkpoint(str(temp_checkpoint_dir)) is False

def test_validate_checkpoint_invalid_content(checkpoint_handler, temp_checkpoint_dir):
    """Test checkpoint validation with invalid dump.log content."""
    dump_log = temp_checkpoint_dir / "dump.log"
    dump_log.write_text("Some log\nFailed to dump")
    assert checkpoint_handler.validate_checkpoint(str(temp_checkpoint_dir)) is False

def test_save_checkpoint_file_success(checkpoint_handler, temp_upperdir, temp_checkpoint_dir):
    """Test successful checkpoint save operation."""
    assert checkpoint_handler.save_checkpoint_file(str(temp_upperdir), str(temp_checkpoint_dir)) is True
    tar_path = temp_checkpoint_dir / "container_files.tar"
    assert tar_path.exists()
    
    # Verify tar contents
    with tarfile.open(tar_path, "r:gz") as tar:
        members = tar.getmembers()
        assert len(members) > 0
        assert any(m.name.endswith("test.txt") for m in members)

def test_save_checkpoint_file_no_upperdir(checkpoint_handler, temp_checkpoint_dir):
    """Test checkpoint save when upperdir doesn't exist."""
    assert checkpoint_handler.save_checkpoint_file("/nonexistent/path", str(temp_checkpoint_dir)) is False

def test_restore_checkpoint_file_success(checkpoint_handler, temp_checkpoint_dir, temp_upperdir):
    """Test successful checkpoint restore operation."""
    # First save a checkpoint
    assert checkpoint_handler.save_checkpoint_file(str(temp_upperdir), str(temp_checkpoint_dir)) is True
    
    # Create new upperdir for restore
    new_upperdir = temp_upperdir.parent / "new_upperdir"
    new_upperdir.mkdir()
    
    # Restore checkpoint
    assert checkpoint_handler.restore_checkpoint_file(str(temp_checkpoint_dir), str(new_upperdir)) is True
    assert (new_upperdir / "fs" / "test.txt").exists()
    assert (new_upperdir / "fs" / "test.txt").read_text() == "test content"

def test_restore_checkpoint_file_no_checkpoint(checkpoint_handler, temp_upperdir):
    """Test restore when checkpoint doesn't exist."""
    assert checkpoint_handler.restore_checkpoint_file("/nonexistent/checkpoint", str(temp_upperdir)) is False

def test_restore_checkpoint_file_with_backup(checkpoint_handler, temp_checkpoint_dir, temp_upperdir):
    """Test restore with existing fs directory backup."""
    # First save a checkpoint
    assert checkpoint_handler.save_checkpoint_file(str(temp_upperdir), str(temp_checkpoint_dir)) is True
    
    # Create backup directory
    backup_dir = temp_upperdir / "fs.bak"
    backup_dir.mkdir()
    (backup_dir / "backup.txt").write_text("backup content")
    
    # Restore checkpoint
    assert checkpoint_handler.restore_checkpoint_file(str(temp_checkpoint_dir), str(temp_upperdir)) is True
    assert not backup_dir.exists()  # Backup should be removed
    assert (temp_upperdir / "fs" / "test.txt").exists()  # Original file should be restored

def test_rollback_restore_file_success(checkpoint_handler, temp_upperdir):
    """Test successful rollback after failed restore."""
    checkpoint_handler.rollback_restore_file(str(temp_upperdir))
    assert not temp_upperdir.exists()

def test_cleanup_checkpoint_success(checkpoint_handler, temp_checkpoint_dir):
    """Test successful checkpoint cleanup."""
    assert checkpoint_handler.cleanup_checkpoint(str(temp_checkpoint_dir)) is True
    assert not temp_checkpoint_dir.exists()

def test_cleanup_checkpoint_no_path(checkpoint_handler):
    """Test cleanup when checkpoint path doesn't exist."""
    assert checkpoint_handler.cleanup_checkpoint("/nonexistent/path") is False 