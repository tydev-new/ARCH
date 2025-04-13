import pytest
from unittest.mock import Mock, patch
import os
import sys
import tempfile
import shutil
from src.container_handler.event_listener import ContainerEventListener
from src.container_handler.state_manager import ContainerStateManager
from src.utils.constants import EVENT_LISTENER_PID_FILE

def test_task_exit_event_processing():
    """Test processing of container task/exit events using exact sample from engineering requirements."""
    # Mock state manager
    state_manager = Mock(spec=ContainerStateManager)
    state_manager.has_state.return_value = True
    
    # Create event listener
    event_listener = ContainerEventListener(state_manager)
    
    # Exact sample from engineering requirements
    raw_event = (
        "2025-04-04 19:10:59.898514001 +0000 UTC default /tasks/exit "
        '{"container_id":"tc","id":"tc","pid":6615,"exit_status":137,"exited_at":{"seconds":1743793859,"nanos":783072930}}'
    )
    
    # Process the event
    event_listener._process_event(raw_event)
    
    # Verify state manager was called correctly
    state_manager.has_state.assert_called_once_with("default", "tc")
    state_manager.set_exit_code.assert_called_once_with("default", "tc", 137)

def test_task_exit_event_no_exit_code():
    """Test processing of container task/exit events without explicit exit_status (should default to 0)."""
    state_manager = Mock(spec=ContainerStateManager)
    state_manager.has_state.return_value = True
    
    event_listener = ContainerEventListener(state_manager)
    
    # Same format but without exit_status field
    raw_event = (
        "2025-04-04 19:10:59.898514001 +0000 UTC default /tasks/exit "
        '{"container_id":"tc","id":"tc","pid":6615,"exited_at":{"seconds":1743793859,"nanos":783072930}}'
    )
    
    # Process the event
    event_listener._process_event(raw_event)
    
    # Verify state manager was called with default exit code 0
    state_manager.has_state.assert_called_once_with("default", "tc")
    state_manager.set_exit_code.assert_called_once_with("default", "tc", 0)

def test_task_exit_event_no_state():
    """Test processing of container task/exit events for unknown container."""
    state_manager = Mock(spec=ContainerStateManager)
    state_manager.has_state.return_value = False
    
    event_listener = ContainerEventListener(state_manager)
    
    # Same format as engineering requirements sample
    raw_event = (
        "2025-04-04 19:10:59.898514001 +0000 UTC default /tasks/exit "
        '{"container_id":"tc","id":"tc","pid":6615,"exit_status":137,"exited_at":{"seconds":1743793859,"nanos":783072930}}'
    )
    
    # Process the event
    event_listener._process_event(raw_event)
    
    # Verify state manager was called but set_exit_code was not
    state_manager.has_state.assert_called_once_with("default", "tc")
    state_manager.set_exit_code.assert_not_called()

@pytest.fixture
def temp_pid_dir():
    """Create a temporary directory for PID files."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Note: cleanup is handled by the event listener itself

def test_pid_file_creation(temp_pid_dir):
    """Test PID file creation when starting event listener."""
    pid_file = os.path.join(temp_pid_dir, 'event_listener.pid')
    print(f"\nTesting PID file creation at: {pid_file}")
    
    with patch('src.container_handler.event_listener.EVENT_LISTENER_PID_FILE', pid_file), \
         patch('os.geteuid') as mock_geteuid, \
         patch('subprocess.Popen') as mock_popen, \
         patch('src.container_handler.state_manager.ContainerStateManager') as mock_state_manager_class, \
         patch('src.container_handler.event_listener.ContainerEventListener') as mock_event_listener_class, \
         patch('os.remove') as mock_remove:  # Add mock for os.remove
        
        # Setup mocks
        mock_geteuid.return_value = 0  # Root user
        
        # Mock state manager and event listener
        mock_state_manager = Mock()
        mock_state_manager_class.return_value = mock_state_manager
        mock_event_listener = Mock()
        mock_event_listener_class.return_value = mock_event_listener
        
        # Mock listen_for_events to prevent cleanup
        def mock_listen():
            raise KeyboardInterrupt()  # Stop without cleanup
        mock_event_listener.listen_for_events.side_effect = mock_listen
        
        # Mock ctr events process
        mock_process = Mock()
        mock_process.stdout.readline.side_effect = [""]  # EOF immediately
        mock_process.stderr = Mock()
        mock_process.stderr.__iter__ = Mock(return_value=iter([]))
        mock_popen.return_value = mock_process
        
        # Import and run main
        from src.container_handler.event_listener import main
        try:
            print("Starting main()")
            main()
            print("main() completed")
        except KeyboardInterrupt:
            print("Caught KeyboardInterrupt")
        except Exception as e:
            print(f"Caught exception: {type(e).__name__}: {str(e)}")
        
        # Verify PID file exists and contains a valid PID
        print(f"Checking if PID file exists: {os.path.exists(pid_file)}")
        assert os.path.exists(pid_file), "PID file should exist"
        with open(pid_file, 'r') as f:
            pid = f.read().strip()
            print(f"Read PID from file: {pid}")
            assert pid.isdigit(), "PID should be a number"
            
        # Verify os.remove was called with the correct PID file path
        mock_remove.assert_called_with(pid_file)

def test_pid_file_cleanup():
    """Test PID file cleanup when event listener exits."""
    with patch('os.path.exists') as mock_exists, \
         patch('os.remove') as mock_remove, \
         patch('builtins.open', create=True) as mock_open, \
         patch('os.getpid') as mock_getpid, \
         patch('os.geteuid') as mock_geteuid, \
         patch('src.container_handler.event_listener.ContainerEventListener.listen_for_events') as mock_listen:
        
        # Setup mocks for system operations only
        mock_exists.return_value = True  # PID file exists
        mock_getpid.return_value = 12345
        mock_geteuid.return_value = 0  # Root user
        mock_listen.side_effect = KeyboardInterrupt()  # Stop after first iteration
        
        # Import and run main
        from src.container_handler.event_listener import main
        main()
        
        # Verify PID file was cleaned up
        mock_remove.assert_called_with(EVENT_LISTENER_PID_FILE)

def test_duplicate_process_handling(temp_pid_dir):
    """Test handling of duplicate event listener processes."""
    pid_file = os.path.join(temp_pid_dir, 'event_listener.pid')
    
    with patch('src.container_handler.event_listener.EVENT_LISTENER_PID_FILE', pid_file), \
         patch('os.geteuid') as mock_geteuid, \
         patch('src.container_handler.event_listener.ContainerEventListener.listen_for_events') as mock_listen:
        
        mock_geteuid.return_value = 0  # Root user
        mock_listen.side_effect = KeyboardInterrupt()  # Stop after first iteration
        
        # Create PID file with current process ID
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
        
        # Import and run main
        from src.container_handler.event_listener import main
        main()
        
        # Verify PID file still exists with same content
        assert os.path.exists(pid_file)
        with open(pid_file, 'r') as f:
            assert f.read().strip() == str(os.getpid())

def test_process_output():
    """Test processing of ctr events output."""
    state_manager = Mock(spec=ContainerStateManager)
    event_listener = ContainerEventListener(state_manager)
    
    with patch('subprocess.Popen') as mock_popen:
        # Mock ctr events output
        mock_process = Mock()
        mock_process.pid = 12345  # Add mock PID
        mock_process.stdout.readline.side_effect = [
            "2025-04-04 19:10:59.898514001 +0000 UTC default /tasks/exit {\"container_id\":\"tc1\",\"exit_status\":0}\n",
            "2025-04-04 19:11:00.000000000 +0000 UTC default /tasks/exit {\"container_id\":\"tc2\",\"exit_status\":1}\n",
            ""  # EOF
        ]
        mock_process.stderr = Mock()
        mock_process.stderr.__iter__ = Mock(return_value=iter(["Some warning\n"]))
        mock_popen.return_value = mock_process
        
        # Process events
        event_listener.listen_for_events()
        
        # Verify events were processed
        assert state_manager.set_exit_code.call_count == 2
        state_manager.set_exit_code.assert_any_call("default", "tc1", 0)
        state_manager.set_exit_code.assert_any_call("default", "tc2", 1)

def test_process_output_error():
    """Test error handling in process output."""
    state_manager = Mock(spec=ContainerStateManager)
    event_listener = ContainerEventListener(state_manager)
    
    with patch('subprocess.Popen') as mock_popen:
        # Mock subprocess.Popen with error
        mock_process = Mock()
        mock_process.pid = 12345  # Add mock PID
        mock_process.stdout.readline.side_effect = Exception("Mock error")
        mock_process.stderr = Mock()
        mock_process.stderr.__iter__ = Mock(return_value=iter([]))
        mock_popen.return_value = mock_process
        
        # Process should handle error gracefully
        event_listener.listen_for_events()
        
        # Verify process was terminated
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once()

def test_event_processing_error():
    """Test handling of malformed events."""
    state_manager = Mock(spec=ContainerStateManager)
    event_listener = ContainerEventListener(state_manager)
    
    with patch('subprocess.Popen') as mock_popen:
        # Mock subprocess.Popen
        mock_process = Mock()
        mock_process.pid = 12345  # Add mock PID
        mock_process.stdout.readline.side_effect = [
            # Invalid JSON in event
            "2025-04-04 19:10:59.898514001 +0000 UTC default /tasks/exit {\"container_id\":\"tc\",\"invalid json\n",
            ""  # EOF
        ]
        mock_process.stderr = Mock()
        mock_process.stderr.__iter__ = Mock(return_value=iter([]))
        mock_popen.return_value = mock_process
        
        # Process should not raise exception
        event_listener.listen_for_events()
        
        # Verify state manager was not called
        state_manager.set_exit_code.assert_not_called()

def test_event_processing_non_exit():
    """Test handling of non-exit events."""
    state_manager = Mock(spec=ContainerStateManager)
    event_listener = ContainerEventListener(state_manager)
    
    with patch('subprocess.Popen') as mock_popen:
        # Mock subprocess.Popen
        mock_process = Mock()
        mock_process.pid = 12345  # Add mock PID
        mock_process.stdout.readline.side_effect = [
            # Non-exit event
            "2025-04-04 19:10:59.898514001 +0000 UTC default /tasks/start {\"container_id\":\"tc\",\"pid\":1234}\n",
            ""  # EOF
        ]
        mock_process.stderr = Mock()
        mock_process.stderr.__iter__ = Mock(return_value=iter([]))
        mock_popen.return_value = mock_process
        
        # Process should ignore non-exit events
        event_listener.listen_for_events()
        
        # Verify state manager was not called
        state_manager.set_exit_code.assert_not_called()

def test_sudo_handling():
    """Test handling of non-root execution."""
    with patch('os.path.exists') as mock_exists, \
         patch('os.geteuid') as mock_geteuid, \
         patch('os.execvp') as mock_execvp:
        
        # Setup mocks
        mock_exists.return_value = False
        mock_geteuid.return_value = 1000  # Non-root user
        
        # Import and run main
        from src.container_handler.event_listener import main
        main()
        
        # Verify sudo restart was attempted
        mock_execvp.assert_called_once_with("sudo", ["sudo", sys.argv[0]])

def test_sudo_restart_error():
    """Test error handling when sudo restart fails."""
    with patch('os.path.exists') as mock_exists, \
         patch('os.geteuid') as mock_geteuid, \
         patch('os.execvp') as mock_execvp:
        
        # Setup mocks
        mock_exists.return_value = False
        mock_geteuid.return_value = 1000  # Non-root user
        mock_execvp.side_effect = Exception("Mock sudo error")
        
        # Import and run main
        from src.container_handler.event_listener import main
        main()
        
        # Verify sudo restart was attempted
        mock_execvp.assert_called_once_with("sudo", ["sudo", sys.argv[0]])

def test_stale_pid_file(temp_pid_dir):
    """Test cleanup of stale PID file."""
    pid_file = os.path.join(temp_pid_dir, 'event_listener.pid')
    
    with patch('src.container_handler.event_listener.EVENT_LISTENER_PID_FILE', pid_file), \
         patch('os.geteuid') as mock_geteuid, \
         patch('subprocess.Popen') as mock_popen, \
         patch('os.remove') as mock_remove:  # Add mock for os.remove
        
        mock_geteuid.return_value = 0  # Root user
        
        # Mock ctr events output
        mock_process = Mock()
        mock_process.pid = 12345  # Add mock PID
        mock_process.stdout.readline.side_effect = [""]  # EOF immediately
        mock_process.stderr = Mock()
        mock_process.stderr.__iter__ = Mock(return_value=iter([]))
        mock_popen.return_value = mock_process
        
        # Create PID file with non-existent process ID
        with open(pid_file, 'w') as f:
            f.write('99999')  # Non-existent PID
        
        # Import and run main
        from src.container_handler.event_listener import main
        try:
            main()
        except KeyboardInterrupt:
            pass
        
        # Verify PID file was updated with current process ID
        assert os.path.exists(pid_file), "PID file should exist"
        with open(pid_file, 'r') as f:
            assert f.read().strip() == str(os.getpid()), "PID should be updated to current process" 