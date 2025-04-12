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
        logger.info("Launching ctr events process")
        
        # Use the exact command that works in the alternative implementation
        process = subprocess.Popen(
            ["sudo", "ctr", "events"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line buffering
        )
        
        # Write PID to file
        logger.info("Writing PID to file: %s", EVENT_LISTENER_PID_FILE)
        try:
            with open(EVENT_LISTENER_PID_FILE, 'w') as f:
                f.write(str(process.pid))
            logger.info("Successfully wrote PID %d to file", process.pid)
        except Exception as e:
            logger.error("Failed to write PID to file: %s", e)
            return
            
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
                
            if os.path.exists(EVENT_LISTENER_PID_FILE):
                try:
                    os.remove(EVENT_LISTENER_PID_FILE)
                    logger.info("Removed PID file")
                except Exception as e:
                    logger.warning("Failed to remove PID file: %s", e)
    
    def _process_event(self, event_line):
        """Process a single event line."""
        try:
            # Log raw event line for debugging
            logger.info("Raw event line: %s", event_line.strip())
            
            # Try to parse as JSON first
            json_start = event_line.find('{')
            if json_start != -1:
                try:
                    # Extract parts before JSON
                    parts_before_json = event_line[:json_start].strip().split()
                    if len(parts_before_json) >= 4:
                        # Extract namespace and topic (last two items before JSON)
                        namespace = parts_before_json[-2]
                        topic = parts_before_json[-1]
                        
                        # Extract JSON data
                        event_data = event_line[json_start:]
                        
                        logger.info("Parsed event - Namespace: %s, Topic: %s", namespace, topic)
                        
                        # Only process exit events
                        if topic == "/tasks/exit":
                            event = json.loads(event_data)
                            container_id = event.get("container_id")
                            exit_code = event.get("exit_status", 0)  # default to 0 if not present
                            
                            if container_id:
                                # Check if we have state for this container
                                if self.state_manager.has_state(namespace, container_id):
                                    logger.info("Container %s in namespace %s exited with code %d", 
                                               container_id, namespace, exit_code)
                                    self.state_manager.set_exit_code(namespace, container_id, exit_code)
                                    return
                except json.JSONDecodeError as e:
                    logger.error("Failed to parse event JSON: %s", e)
                    logger.error("Failed event data: %s", event_data)
                    # Fall back to text parsing
            
            # Fall back to text parsing if JSON parsing failed
            # Parse the event line
            # Format: 2024-02-14T12:34:56.789012345Z namespace=default type=container id=abc123 event=exit
            parts = event_line.strip().split()
            if len(parts) < 5:
                logger.warning("Invalid event format: %s", event_line.strip())
                return
                
            # Extract namespace and container ID
            namespace = None
            container_id = None
            for part in parts[1:]:  # Skip timestamp
                if '=' in part:
                    key, value = part.split('=', 1)
                    if key == 'namespace':
                        namespace = value
                    elif key == 'id':
                        container_id = value
                        
            if not namespace or not container_id:
                logger.warning("Missing namespace or container ID in event: %s", event_line.strip())
                return
                
            # Check if this is an exit event
            if 'event=exit' not in event_line:
                return
                
            # Check if we have state for this container
            if not self.state_manager.has_state(namespace, container_id):
                logger.info("No state file found for container %s in namespace %s, skipping event", 
                           container_id, namespace)
                return
                
            # Extract exit code from the event
            exit_code = None
            for part in parts:
                if part.startswith('exit-code='):
                    try:
                        exit_code = int(part.split('=', 1)[1])
                    except (ValueError, IndexError):
                        pass
                        
            # If no exit code is found, treat it as 0 (successful exit)
            if exit_code is None:
                exit_code = 0
                logger.info("Container %s in namespace %s exited with no explicit code, treating as 0", 
                           container_id, namespace)
            
            logger.info("Container %s in namespace %s exited with code %d", 
                       container_id, namespace, exit_code)
            self.state_manager.set_exit_code(namespace, container_id, exit_code)
                
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
            except Exception as e:
                logger.warning("Failed to remove PID file: %s", e)

if __name__ == "__main__":
    main() 