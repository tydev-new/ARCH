import os
import sys
import pytest
from unittest.mock import patch, mock_open, MagicMock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from install import (
    check_root,
    check_dependencies,
    find_runc_path,
    install_wrapper,
    cleanup_runc_wrapper,
    is_already_installed
)

def test_check_root_not_root():
    with patch('os.geteuid', return_value=1000):
        with pytest.raises(SystemExit):
            check_root()

def test_check_root_is_root():
    with patch('os.geteuid', return_value=0):
        check_root()  # Should not raise

def test_check_dependencies_python_version_ok():
    with patch('sys.version_info', (3, 8)):
        check_dependencies()  # Should not raise

def test_check_dependencies_python_version_old():
    with patch('sys.version_info', (3, 5)):
        with pytest.raises(SystemExit):
            check_dependencies()

def test_find_runc_path_common_location():
    with patch('subprocess.run') as mock_run, \
         patch('os.path.exists', return_value=True), \
         patch('os.access', return_value=True):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="/usr/bin/runc\n",
            stderr=""
        )
        path = find_runc_path()
        assert path == "/usr/bin/runc"

def test_find_runc_path_which_command():
    def mock_exists(path):
        return path == "/custom/path/runc"
        
    with patch('os.path.exists', side_effect=mock_exists), \
         patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="/custom/path/runc\n",
            stderr=""
        )
        with patch('os.access', return_value=True):
            path = find_runc_path()
            assert path == "/custom/path/runc"

def test_find_runc_path_not_found():
    with patch('os.path.exists', return_value=False), \
         patch('subprocess.run') as mock_run:
        mock_run.return_value.returncode = 1
        with pytest.raises(FileNotFoundError):
            find_runc_path()

def test_is_already_installed_true():
    with patch('os.environ.get', return_value="/usr/bin/runc.real"), \
         patch('os.path.exists', return_value=True), \
         patch('os.path.isfile', return_value=True), \
         patch('install.find_runc_path', return_value="/usr/bin/runc"):
        assert is_already_installed() is True

def test_is_already_installed_false_no_env():
    with patch('os.environ.get', return_value=None):
        assert is_already_installed() is False

def test_is_already_installed_false_no_backup():
    with patch('os.environ.get', return_value="/usr/bin/runc.real"), \
         patch('os.path.exists', return_value=False):
        assert is_already_installed() is False

def test_is_already_installed_false_not_script():
    with patch('os.environ.get', return_value="/usr/bin/runc.real"), \
         patch('os.path.exists', return_value=True), \
         patch('os.path.isfile', return_value=False):
        assert is_already_installed() is False

def test_install_wrapper_already_installed():
    with patch('install.is_already_installed', return_value=True):
        assert install_wrapper() is True

def test_install_wrapper_success():
    with patch('install.is_already_installed', return_value=False), \
         patch('install.find_runc_path', return_value="/usr/bin/runc"), \
         patch('os.path.exists', side_effect=lambda path: path == "/path/to/src/main.py"), \
         patch('os.makedirs'), \
         patch('shutil.copy2'), \
         patch('os.remove'), \
         patch('builtins.open', mock_open()), \
         patch('os.chmod'), \
         patch('os.path.abspath', return_value="/path/to/main.py"), \
         patch('os.path.dirname', return_value="/path/to"), \
         patch('os.path.join', side_effect=lambda *args: "/".join(args)):
        assert install_wrapper() is True

def test_cleanup_runc_wrapper_not_installed():
    with patch('install.is_already_installed', return_value=False):
        assert cleanup_runc_wrapper() is True

def test_cleanup_runc_wrapper_success():
    with patch('install.is_already_installed', return_value=True), \
         patch('install.find_runc_path', return_value="/usr/bin/runc"), \
         patch('os.path.exists', return_value=True), \
         patch('os.remove'), \
         patch('shutil.copy2'), \
         patch('builtins.open', mock_open()):
        assert cleanup_runc_wrapper() is True

def test_cleanup_runc_wrapper_no_backup():
    with patch('install.is_already_installed', return_value=True), \
         patch('os.environ.get', return_value="/usr/bin/runc.real"), \
         patch('os.path.exists', return_value=False):
        assert cleanup_runc_wrapper() is False 