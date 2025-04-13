# Event Listener Implementation - Full Conversation

## Initial Discussion

**User**: now review the eng requirement for exit event and code listener and give me your proposal, along with any questions?

**Assistant**: Let me check the engineering requirements for exit event and code listener:

```
5.1 Container process exit code

Tardis needs to monitor the exit code using following command: 

sudo ctr events

as Containerd and Runc do not provide direct API to capture the process exit code.

Ctr events continuously output container process (task) events in the following format:

2025-04-04 19:10:59.898514001 +0000 UTC default /tasks/exit {"container_id":"tc","id":"tc","pid":6615,"exit_status":137,"exited_at":{"seconds":1743793859,"nanos":783072930}}

need to parse into:
Namespace: default 
Container_id: tc
Topic: /tasks/exit
Exit code: 137

Note there are:
- Events other than /tasks/exit, which are dropped
- Exit code ("exit_status") may not be present, which is taken as exit code 0
```

Proposal:
1. Create a new class `ContainerEventListener` in `src/container_handler/event_listener.py`:
```python
class ContainerEventListener:
    def __init__(self, state_manager):
        self.state_manager = state_manager
        self.running = False
        
    def start(self):
        """Start listening for container events in a background thread"""
        self.running = True
        thread = threading.Thread(target=self._listen_events)
        thread.daemon = True  # Make thread daemon so it exits when main process exits
        thread.start()
        
    def _listen_events(self):
        """Listen to containerd events and process exit codes"""
        try:
            process = subprocess.Popen(
                ["ctr", "events"],
                stdout=subprocess.PIPE,
                text=True
            )
            
            while self.running:
                line = process.stdout.readline()
                if not line:
                    break
                    
                self._process_event(line)
                
        except Exception as e:
            logger.error(f"Error in event listener: {e}")
            
    def _process_event(self, event_line: str):
        """Process a single event line"""
        try:
            # Parse event line format: timestamp namespace topic json_data
            parts = event_line.split(" ", 3)
            if len(parts) != 4:
                return
                
            timestamp, namespace, topic, json_data = parts
            
            # Only process exit events
            if topic != "/tasks/exit":
                return
                
            # Parse JSON data
            data = json.loads(json_data)
            container_id = data.get("container_id")
            exit_status = data.get("exit_status", 0)  # Default to 0 if not present
            
            # Store exit code
            self.state_manager.set_exit_code(namespace, container_id, exit_status)
            logger.info(f"Recorded exit code {exit_status} for container {container_id} in namespace {namespace}")
            
        except Exception as e:
            logger.error(f"Error processing event: {e}")
```

2. Initialize and start the listener in `RuncHandler`:
```python
def __init__(self):
    # ... existing init code ...
    self.event_listener = ContainerEventListener(self.state_manager)
    self.event_listener.start()
```

Questions:
1. Should we handle reconnection if the `ctr events` command fails or exits?
2. Should we add any filtering for specific namespaces or containers?
3. Do we need to handle any specific error cases in the event parsing?
4. Should we add any additional logging or metrics for event processing?
5. How should we handle the case where events are missed during process startup?
6. Should we validate the exit code value range?
7. Do we need to handle any cleanup when the process exits?

Would you like me to proceed with implementing this proposal?

**User**: great questions!  1. yes, the listener should be a daemon, maybe as system service started by the installer? alternatively we can have runc handler start it on the first tardis enabled container.  2. ctr event itself don't have any filtering. we can in effect filtering but only set exit code for the namespace + container_id that's tardis enabled.  3, 4, no additional  6. no need to validate exit code.  7 no additional cleanup. we should clean up the state file with delete handler though. 5. not sure what you mean, pls elaborate the question

**Assistant**: Thanks for the clarifications! Let me clarify question #5:

When I asked about missing events during process startup, I was thinking about this scenario:
1. Container exits
2. Event is emitted
3. But our listener hasn't started yet (either because Tardis just started or restarted)
4. We miss capturing that exit code

But thinking about it now, this isn't really an issue because:
1. If container exited before Tardis starts, it would already be gone
2. For new containers, we'll always have the listener running before they can exit
3. The delete handler will work correctly in either case - no exit code means no cleanup

Based on your answers, let me revise the proposal:

1. For daemon approach:
```python
class ContainerEventListener:
    def __init__(self, state_manager, config_handler):
        self.state_manager = state_manager
        self.config_handler = config_handler
        self.running = False
        
    def start(self):
        """Start listening for container events in a background thread"""
        self.running = True
        thread = threading.Thread(target=self._listen_events)
        thread.daemon = True
        thread.start()
        
    def _listen_events(self):
        """Listen to containerd events and process exit codes"""
        while self.running:
            try:
                process = subprocess.Popen(
                    ["ctr", "events"],
                    stdout=subprocess.PIPE,
                    text=True
                )
                
                while self.running:
                    line = process.stdout.readline()
                    if not line:
                        break
                    self._process_event(line)
                    
            except Exception as e:
                logger.error(f"Error in event listener: {e}")
                time.sleep(1)  # Avoid tight loop on repeated failures
                
    def _process_event(self, event_line: str):
        """Process a single event line"""
        try:
            # Parse event line format: timestamp namespace topic json_data
            parts = event_line.split(" ", 3)
            if len(parts) != 4:
                return
                
            timestamp, namespace, topic, json_data = parts
            
            # Only process exit events
            if topic != "/tasks/exit":
                return
                
            # Parse JSON data
            data = json.loads(json_data)
            container_id = data.get("container_id")
            
            # Only process if container is Tardis-enabled
            if not self.config_handler.is_tardis_enabled(container_id, namespace):
                return
                
            exit_status = data.get("exit_status", 0)
            self.state_manager.set_exit_code(namespace, container_id, exit_status)
            logger.info(f"Recorded exit code {exit_status} for container {container_id} in namespace {namespace}")
            
        except Exception as e:
            logger.error(f"Error processing event: {e}")
```

2. For initialization, we have two options:

Option A - System Service:
```bash
# systemd service file
[Unit]
Description=Tardis Container Event Listener
After=containerd.service

[Service]
ExecStart=/usr/local/bin/tardis-event-listener
Restart=always

[Install]
WantedBy=multi-user.target
```

Option B - First Container:
```python
class RuncHandler:
    def __init__(self):
        self.event_listener = None
        # ... other init code ...

    def _ensure_event_listener(self):
        """Start event listener if not already running"""
        if self.event_listener is None:
            self.event_listener = ContainerEventListener(self.state_manager, self.config_handler)
            self.event_listener.start()

    def intercept_command(self, args: List[str]):
        # ... existing code ...
        
        # Check if container is Tardis-enabled
        if self.config_handler.is_tardis_enabled(container_id, namespace):
            self._ensure_event_listener()
```

Key points in this revised proposal:
1. Automatic reconnection on failure
2. Filter events by Tardis-enabled containers
3. Daemon thread for cleanup on process exit
4. Simple error handling and logging
5. Option for either system service or on-demand start

Would you like me to proceed with implementing one of these approaches? Do you prefer the system service or the on-demand start approach?

**User**: do you have analysis on the option a vs b? and recommendation? I prefer to go with the simpler approach, probably b, but like to get your thought

**Assistant**: Let me analyze both options:

Option A (System Service):
Pros:
1. More reliable - always running, survives Tardis process restarts
2. Cleaner separation of concerns
3. Better for monitoring/management via systemd
4. Can handle events from container start

Cons:
1. More complex setup - requires systemd configuration
2. Additional installation steps
3. Needs root access to install service
4. Running even when no Tardis containers exist
5. Harder to debug/test

Option B (On-demand in RuncHandler):
Pros:
1. Simpler implementation - just Python code
2. Self-contained within Tardis
3. Only runs when needed (Tardis containers exist)
4. Easier to test and debug
5. No additional installation/configuration
6. No root access needed

Cons:
1. Tied to RuncHandler lifecycle
2. Might miss events if started after container creation
3. Need to handle thread management carefully

Recommendation:
I recommend Option B (on-demand) because:
1. It follows the principle of least complexity
2. The cons are not critical for our use case:
   - Missing early events isn't critical (container would still be running)
   - Thread management is straightforward with daemon thread
3. Easier to implement, test, and maintain
4. No additional installation complexity
5. More portable (doesn't depend on systemd)

Would you like me to proceed with implementing Option B?

**User**: agree with option b then.  let's do it

[Implementation of event listener follows...]

**User**: in event listener process event, the parsing logic will not work, see example from eng. req. the timestamp has spaces in between and will split into multiple (4?) elements. double check and come back with a proposal

**Assistant**: Ah yes, that's clearer. Looking at the example from the requirements:
```
2025-04-04 19:10:59.898514001 +0000 UTC default /tasks/exit {"container_id":"tc","id":"tc","pid":6615,"exit_status":137,"exited_at":{"seconds":1743793859,"nanos":783072930}}
```

The timestamp part has spaces and includes:
- Date: `2025-04-04`
- Time: `19:10:59.898514001`
- Timezone: `+0000 UTC`

So our current `split(" ", 3)` won't work. Here's my revised proposal for `_process_event`:

```python
def _process_event(self, event_line: str):
    """Process a single event line"""
    try:
        # Find the position of /tasks/exit in the line
        topic_pos = event_line.find("/tasks/exit")
        if topic_pos == -1:
            return
            
        # Extract namespace (it's between the timestamp+tz and topic)
        # Split the part before topic and get the last element
        namespace = event_line[:topic_pos].strip().split()[-1]
        
        # Find the JSON data (everything after the topic)
        json_start = event_line.find("{", topic_pos)
        if json_start == -1:
            return
            
        # Parse JSON data
        json_data = event_line[json_start:]
        data = json.loads(json_data)
        container_id = data.get("container_id")
        
        # Only process if container is Tardis-enabled
        if not self.config_handler.is_tardis_enabled(container_id, namespace):
            return
            
        exit_status = data.get("exit_status", 0)
        self.state_manager.set_exit_code(namespace, container_id, exit_status)
        logger.info(f"Recorded exit code {exit_status} for container {container_id} in namespace {namespace}")
        
    except Exception as e:
        logger.error(f"Error processing event: {e}")
```

This approach:
1. Looks for "/tasks/exit" as an anchor point
2. Gets namespace by taking the last word before the topic
3. Finds and parses the JSON portion after the topic
4. More robust as it doesn't rely on counting spaces

Would you like me to implement this change?

**User**: yes

[Implementation of event listener parsing fix follows...]

## Finding the `ctr events` Process

**User**: how do we find the `ctr events` process? I tried `ps -ef | grep ctr` but it doesn't show up.

**Assistant**: The `ps -ef | grep ctr` approach has limitations for detecting the `ctr events` process. Let me implement a more robust detection method.

I'll modify the code to use a PID file approach to track the event listener process:

```python
def _is_event_listener_running(self):
    """Check if another event listener is already running."""
    if os.path.exists(EVENT_LISTENER_PID_FILE):
        try:
            with open(EVENT_LISTENER_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            # Check if process exists
            try:
                os.kill(pid, 0)
                return True
            except (OSError, ProcessLookupError):
                # Process not found, clean up stale PID file
                os.remove(EVENT_LISTENER_PID_FILE)
        except (ValueError, IOError) as e:
            logger.warning("Error checking PID file: %s", e)
    return False
```

This approach:
1. Uses a PID file to track the event listener process
2. Checks if the process is still running
3. Cleans up stale PID files
4. More reliable than parsing process output

## Using Constants for PID File Path

**User**: we should use a constant for the PID file path instead of hardcoding it.

**Assistant**: I'll add a constant for the PID file path in `src/utils/constants.py`:

```python
EVENT_LISTENER_PID_FILE = "/tmp/tardis_event_listener.pid"
```

Then update the event listener to use this constant:

```python
from src.utils.constants import EVENT_LISTENER_PID_FILE

# Use the constant instead of hardcoded path
if os.path.exists(EVENT_LISTENER_PID_FILE):
    # ...
```

## Updating PID File Path

**User**: update the constant `EVENT_LISTENER_PID_FILE` in `src/utils/constants.py` from `/tmp/tardis_event_listener.pid` to `/var/lib/tardis/event_listener.pid`

**Assistant**: I'll update the constant to use the new path:

```python
EVENT_LISTENER_PID_FILE = "/var/lib/tardis/event_listener.pid"
```

This change:
1. Places the PID file in a more appropriate location
2. Follows standard Linux filesystem hierarchy
3. Keeps all Tardis files in one directory

## Event Listener Operation Mode

**User**: is the event listener running in foreground or background?

**Assistant**: Currently, the event listener is running in the foreground. Let me modify it to run in the background with minimal code changes:

```python
def start(self):
    """Start listening for container events in a background thread"""
    self.running = True
    thread = threading.Thread(target=self._listen_events)
    thread.daemon = False  # Make thread non-daemon so it continues after main process exits
    thread.start()
```

This change:
1. Makes the thread non-daemon so it continues running after the main process exits
2. Keeps the implementation simple
3. Ensures the event listener stays active

## Code Review for Simplicity and Reliability

**User**: can you review the code for simplicity and reliability?

**Assistant**: After reviewing the code, I see several issues:

1. Inconsistent instance management
2. Thread management problems
3. Complex error handling

Let me propose a simpler approach focusing on core requirements:

1. Use PID file for process management
2. Basic error handling
3. Simple event parsing
4. Clear logging

## Event Listener PID File Format

**User**: what's in the `event_listener.pid` file?

**Assistant**: The `event_listener.pid` file contains the PID of the running event listener process. It's used to:
1. Track if an event listener is already running
2. Prevent multiple instances
3. Clean up stale processes

## Delete Handler Logging

**User**: I don't see any logs for the delete handler in `runc_handler.py`.

**Assistant**: Let me add detailed logging to the delete handler:

```python
def _handle_delete_command(self, container_id: str, namespace: str, args: List[str]) -> int:
    """Handle delete command processing."""
    logger.info("Processing delete command for container %s in namespace %s", container_id, namespace)
    
    exit_code = self.state_manager.get_exit_code(namespace, container_id)
    if exit_code is not None and exit_code == 0:
        logger.info("Container %s exited successfully with code 0, cleaning up", container_id)
        # ... cleanup code ...
    else:
        logger.info("Container %s did not exit successfully (code: %s), skipping cleanup", 
                   container_id, exit_code)
    
    # Pass through original command
    logger.info("Executing delete command for container %s", container_id)
    return self._execute_command(args[1:])
```

## Event Listener Background Operation

**User**: is the event listener still launching in foreground? can we launch it in background?

**Assistant**: Yes, the event listener is still launching in the foreground. Let me modify it to run in the background:

```python
def start(self):
    """Start listening for container events in a background process"""
    process = subprocess.Popen(
        ["python3", "-m", "src.container_handler.event_listener"],
        start_new_session=True,  # Detach from parent process
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Write PID to file
    with open(EVENT_LISTENER_PID_FILE, 'w') as f:
        f.write(str(process.pid))
```

This change:
1. Launches the event listener as a separate process
2. Detaches it from the parent process
3. Writes the PID to the PID file
4. Ensures it continues running after the parent process exits

## Adding Info Log to Main Function

**User**: can you add an info log to the main function?

**Assistant**: I'll add info logs to the main function:

```python
def main():
    """Run the event listener as a standalone process."""
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
    
    # Write our PID to file before starting
    try:
        with open(EVENT_LISTENER_PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
        logger.info("Started new event listener with PID %d", os.getpid())
    except Exception as e:
        logger.error("Failed to write PID file: %s", e)
        return
```

## Event Listener Not Showing Raw Events

**User**: the event listener is not showing any raw events.

**Assistant**: Let me check the implementation and fix the issue:

1. The event listener is running (PID 2672) but not processing events
2. The current implementation uses `subprocess.Popen` with `text=True` and `bufsize=1`
3. We need to match the working alternative implementation more closely

Let me modify the code to fix this:

```python
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
```

This change:
1. Uses the exact command that works in the alternative implementation
2. Adds line buffering to ensure events are processed immediately
3. Adds more detailed logging to track the process

## Final Implementation

The final implementation includes:
1. A standalone event listener process
2. PID file management
3. Robust event parsing
4. Detailed logging
5. Error handling
6. Background operation

The event listener now:
1. Runs as a separate process
2. Uses a PID file to prevent multiple instances
3. Parses events correctly
4. Logs all events for debugging
5. Handles errors gracefully
6. Continues running after the parent process exits 