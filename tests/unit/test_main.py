import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Mock logger at module level
mock_logger = MagicMock()
patch('src.utils.logging.logger', mock_logger).start()

from src.main import main

def test_main_success():
    with patch('src.main.RuncHandler') as mock_handler:
        mock_instance = mock_handler.return_value
        mock_instance.intercept_command.return_value = 0
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        mock_instance.intercept_command.assert_called_once_with(sys.argv)

def test_main_error():
    with patch('src.main.RuncHandler') as mock_handler:
        mock_instance = mock_handler.return_value
        mock_instance.intercept_command.return_value = 1
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

def test_main_exception():
    mock_logger.reset_mock()
    with patch('src.main.RuncHandler') as mock_handler:
        mock_handler.side_effect = Exception("Test error")
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        mock_logger.error.assert_called_once_with("Fatal error: Test error") 