# Event Listener Logging Fix - Full Conversation

## Initial Issue
User: I'm seeing persistent error messages in logs about missing state file for a container. Did we miss changing some error to warning in some cases?

Assistant: Let me check the state manager code to see if we missed any error messages that should be warnings.

## Evolution of the Issue
User: I'm confused about why event listener logs are not appearing in the tardis.log file, despite the event listener being active.

Assistant: Let me check the event listener and RuncHandler to ensure proper logging and process management. I'll verify if the event listener is running and check the PID file.

## Investigation Findings
1. Event listener process was running but not writing logs
2. PID file management was causing issues:
   - The event listener was writing the `ctr events` process PID to the PID file
   - The Python process was exiting early because it thought another instance was running
   - The `ctr events` process was running but not processing events

## Solution Implementation
1. Moved PID file management from `listen_for_events()` to `main()`
2. Removed PID file management from `listen_for_events()`
3. Ensured proper cleanup in `main()`

## Verification
- Event listener now properly writes its Python process PID to the PID file
- Python process stays running to handle events
- Events are properly logged to tardis.log
- PID file is cleaned up when the process exits

## Conclusion
The issue was resolved by fixing the PID file management in the event listener. No changes were needed to the RuncHandler as it was already correctly implemented.

## Code Changes
1. Main function changes:
```python
def main():
    # Write our PID to file before starting
    try:
        with open(EVENT_LISTENER_PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
        logger.info("Started new event listener with PID %d", os.getpid())
    except Exception as e:
        logger.error("Failed to write PID file: %s", e)
        return
```

2. Event listener changes:
```python
def listen_for_events(self):
    """Listen for container events."""
    logger.info("TEST EVENT LISTENER STARTED - This should appear in tardis.log")
    logger.info("Launching ctr events process")
    
    process = subprocess.Popen(
        ["sudo", "ctr", "events"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    
    logger.info("Event listener process started with PID %d", process.pid)
    
    # Process events
    self._process_output(process)
```

3. Cleanup changes:
```python
finally:
    if os.path.exists(EVENT_LISTENER_PID_FILE):
        try:
            os.remove(EVENT_LISTENER_PID_FILE)
            logger.info("Cleaned up PID file")
        except Exception as e:
            logger.warning("Failed to remove PID file: %s", e)
```

## Final Note
The RuncHandler was already correctly implemented and didn't require any changes:
```python
def _ensure_event_listener(self):
    """Ensure the event listener is running."""
    # Get the project root directory (where install.py is located)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Launch event_listener.py as a separate process
    subprocess.Popen(
        ["python3", "-m", "src.container_handler.event_listener"],
        cwd=project_root,
        env=os.environ.copy()  # Inherit environment for log file path
    )
    logger.info("Started event listener process")
``` 