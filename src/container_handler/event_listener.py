import subprocess
import logging
import os
import json
import signal
import sys
from src.utils.constants import EVENT_LISTENER_PID_FILE
from src.utils.logging import logger

# Use the main logger instead of creating a new one
# logger = logging.getLogger(__name__)

class ContainerEventListener:
    def __init__(self, state_manager):
        self.state_manager = state_manager
    
    def listen_for_events(self):
        """Listen for container events."""
        logger.info("TEST EVENT LISTENER STARTED - This should appear in tardis.log")
        logger.info("Launching ctr events process")
        
        # Use the exact command that works in the alternative implementation
        process = subprocess.Popen(
            ["sudo", "ctr", "events"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line buffering
        )
        
        logger.info("Event listener process started with PID %d", process.pid)
        
        # Process events
        self._process_output(process)
    
    def _process_output(self, process):
        """Process the output from the ctr events command."""
        try:
            logger.info("Event listener process started, waiting for events")
            
            # Process stdout - use the exact approach from the alternative implementation
            while True:
                line = process.stdout.readline()
                if not line:
                    logger.info("No more output from ctr events, breaking loop")
                    break
                    
                logger.info("Raw event received: %s", line.strip())
                self._process_event(line)
                
            # Check for stderr output
            for line in process.stderr:
                logger.warning("Event listener stderr: %s", line.strip())
                
        except Exception as e:
            logger.error("Error processing event output: %s", e)
        finally:
            logger.info("Event listener output processing ended")
            # Ensure process is terminated
            if process:
                process.terminate()
                process.wait()
    
    def _process_event(self, event_line):
        """Process a single event line."""
        try:
            # Log raw event line for debugging
            logger.info("Raw event line: %s", event_line.strip())
            
            # Parse the event line
            json_start = event_line.find('{')
            if json_start == -1:
                logger.info("Skipping non-JSON event: %s", event_line.strip())
                return  # Not a JSON event, skip
                
            # Extract parts before JSON
            parts_before_json = event_line[:json_start].strip().split()
            if len(parts_before_json) < 4:
                logger.info("Skipping event with invalid format: %s", event_line.strip())
                return  # Invalid format, skip
                
            # Extract namespace and topic (last two items before JSON)
            namespace = parts_before_json[-2]
            topic = parts_before_json[-1]
            
            logger.info("Processing event - Namespace: %s, Topic: %s", namespace, topic)
            
            # Only process exit events
            if topic != "/tasks/exit":
                logger.info("Skipping non-exit event: %s", topic)
                return
                
            # Extract and parse JSON data
            event_data = event_line[json_start:]
            try:
                event = json.loads(event_data)
                container_id = event.get("container_id")
                exit_code = event.get("exit_status", 0)  # default to 0 if not present
                
                logger.info("Parsed exit event - Container: %s, Exit Code: %d", container_id, exit_code)
                
                if container_id and self.state_manager.has_state(namespace, container_id):
                    logger.info("Container %s in namespace %s exited with code %d", 
                               container_id, namespace, exit_code)
                    self.state_manager.set_exit_code(namespace, container_id, exit_code)
                else:
                    logger.info("No state found for container %s in namespace %s", container_id, namespace)
            except json.JSONDecodeError as e:
                logger.error("Failed to parse event JSON: %s", e)
                logger.error("Failed event data: %s", event_data)
                
        except Exception as e:
            logger.error("Error processing event: %s", e)
            logger.error("Failed event line: %s", event_line.strip())

def main():
    """Run the event listener as a standalone process."""
    from src.container_handler.state_manager import ContainerStateManager
    
    logger.info("Starting event listener as standalone process")
    
    # Check if another instance is running
    if os.path.exists(EVENT_LISTENER_PID_FILE):
        try:
            with open(EVENT_LISTENER_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            # Check if process exists
            try:
                os.kill(pid, 0)
                logger.info("Event listener already running with PID %d", pid)
                return
            except (OSError, ProcessLookupError):
                # Process not found, clean up stale PID file
                os.remove(EVENT_LISTENER_PID_FILE)
        except (ValueError, IOError) as e:
            logger.warning("Error checking PID file: %s", e)
    
    # Check if running with sudo
    if os.geteuid() != 0:
        logger.warning("Event listener should be run with sudo privileges")
        logger.info("Attempting to restart with sudo")
        try:
            os.execvp("sudo", ["sudo", sys.argv[0]])
        except Exception as e:
            logger.error("Failed to restart with sudo: %s", e)
            return
    
    # Write our PID to file before starting
    try:
        with open(EVENT_LISTENER_PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
        logger.info("Started new event listener with PID %d", os.getpid())
    except Exception as e:
        logger.error("Failed to write PID file: %s", e)
        return
    
    state_manager = ContainerStateManager()
    event_listener = ContainerEventListener(state_manager)
    
    try:
        event_listener.listen_for_events()
    except KeyboardInterrupt:
        logger.info("Event listener stopped by user")
    except Exception as e:
        logger.error("Error in event listener: %s", e)
    finally:
        if os.path.exists(EVENT_LISTENER_PID_FILE):
            try:
                os.remove(EVENT_LISTENER_PID_FILE)
                logger.info("Cleaned up PID file")
            except Exception as e:
                logger.warning("Failed to remove PID file: %s", e)

if __name__ == "__main__":
    main() 