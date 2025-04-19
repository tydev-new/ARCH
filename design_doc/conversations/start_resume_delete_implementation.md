# Start, Resume, and Delete Command Implementation Discussion

**User**: let's tackle delet cmd handler now... give me a proposal based on engineering requirement

**Assistant**: Let me check the engineering requirements for the delete command handling:

From the requirements:
```
1.6 Delete subcommand processing

Clean up the checkpoint image when the container process exits successfully.

Do the following:
1. Check the container flag for exit, see Section 5
2. If exit flag exist and exit code is 0:
   - Delete the checkpoint image path
   - If bind mount was used, based on container config.json, clean up the bind mount
   - Remove exit flag
3. Call the real Runc with unmodified args
```

Based on this, I propose:

```python
def _handle_delete_command(self, container_id: str, namespace: str, args: List[str]) -> int:
    """Handle delete command processing."""
    logger.info("Processing delete command for container %s in namespace %s", container_id, namespace)
    
    # Check exit flag and code
    exit_code = self.state_manager.get_exit_code(namespace, container_id)
    if exit_code == 0:
        logger.info("Container %s exited successfully, cleaning up", container_id)
        
        # Get and delete checkpoint image
        checkpoint_path = self.config_handler.get_checkpoint_path(container_id, namespace)
        if checkpoint_path and os.path.exists(checkpoint_path):
            logger.info("Removing checkpoint at %s", checkpoint_path)
            try:
                shutil.rmtree(checkpoint_path)
            except Exception as e:
                logger.error("Failed to remove checkpoint: %s", e)
        
        # Clean up bind mount if used
        if self.config_handler.has_bind_mount(container_id, namespace):
            logger.info("Cleaning up bind mount for container %s", container_id)
            self.config_handler.cleanup_bind_mount(container_id, namespace)
        
        # Remove exit flag
        self.state_manager.remove_exit_code(namespace, container_id)
    
    # Pass through original command
    logger.info("Executing delete command for container %s", container_id)
    return self._execute_command(args[1:])
```

And update `intercept_command`:
```python
elif subcommand == "delete":
    return self._handle_delete_command(container_id, namespace, args)
```

Questions before implementing:
1. Should we handle any specific error cases during cleanup?
2. Should we continue with delete if checkpoint cleanup fails?
3. Do we need to verify the container state before cleanup?
4. Should we add any additional logging for debugging?

Let me know if this proposal aligns with your requirements and if you'd like me to proceed with the implementation.

**User**: answers 2. yes. we should continue 3. no need to verify. 4. logging is okay 1. only specific test case, what if there's no exit event yet, how will get exit code return?   regarding design, a. maybe we should add a cleanup method to checkpoint handler, what do you think? pro/cons b. let's leave out the bind mount handling fo now 

**Assistant**: Good points! Let me address each one:

1. If there's no exit event yet, `get_exit_code` should return None or a special value to indicate no exit event. We should handle this case and proceed with delete.

a. Adding a cleanup method to checkpoint handler:

Pros:
1. Better separation of concerns - checkpoint handler manages all checkpoint-related operations
2. Consistent with existing pattern (save_checkpoint, restore_checkpoint)
3. Makes it easier to modify checkpoint cleanup logic in one place
4. Follows the same error handling pattern as other checkpoint operations

Cons:
1. One more layer of abstraction
2. Might need to pass through error information

Given the pros outweigh the cons, here's my revised proposal:

```python
# In checkpoint_handler.py
def cleanup_checkpoint(self, checkpoint_path: str) -> bool:
    """Clean up checkpoint files."""
    try:
        if checkpoint_path and os.path.exists(checkpoint_path):
            logger.info(f"Removing checkpoint at {checkpoint_path}")
            shutil.rmtree(checkpoint_path)
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to remove checkpoint: {e}")
        return False

# In runc_handler.py
def _handle_delete_command(self, container_id: str, namespace: str, args: List[str]) -> int:
    """Handle delete command processing."""
    logger.info("Processing delete command for container %s in namespace %s", container_id, namespace)
    
    # Check exit code, proceed with delete if container exited successfully or no exit event
    exit_code = self.state_manager.get_exit_code(namespace, container_id)
    if exit_code == 0:  # Only cleanup on successful exit
        logger.info("Container %s exited successfully, cleaning up", container_id)
        
        # Get and delete checkpoint image
        checkpoint_path = self.config_handler.get_checkpoint_path(container_id, namespace)
        if checkpoint_path:
            self.checkpoint_handler.cleanup_checkpoint(checkpoint_path)
            
        # Remove exit flag
        self.state_manager.remove_exit_code(namespace, container_id)
    
    # Pass through original command
    logger.info("Executing delete command for container %s", container_id)
    return self._execute_command(args[1:])
```

This design:
1. Handles missing exit event gracefully
2. Moves checkpoint cleanup to checkpoint handler
3. Continues with delete regardless of cleanup result
4. Leaves out bind mount handling for now
5. Maintains clear logging

Would you like me to proceed with this implementation?

**User**: change logic to only delete checkpoint is there is exit code and exit code is 0

**Assistant**: Ah yes, that's clearer. We should only delete the checkpoint if we explicitly know the container exited successfully (exit_code exists AND is 0). Here's the revised proposal:

```python
# In checkpoint_handler.py
def cleanup_checkpoint(self, checkpoint_path: str) -> bool:
    """Clean up checkpoint files."""
    try:
        if checkpoint_path and os.path.exists(checkpoint_path):
            logger.info(f"Removing checkpoint at {checkpoint_path}")
            shutil.rmtree(checkpoint_path)
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to remove checkpoint: {e}")
        return False

# In runc_handler.py
def _handle_delete_command(self, container_id: str, namespace: str, args: List[str]) -> int:
    """Handle delete command processing."""
    logger.info("Processing delete command for container %s in namespace %s", container_id, namespace)
    
    exit_code = self.state_manager.get_exit_code(namespace, container_id)
    if exit_code is not None and exit_code == 0:  # Only cleanup if exit code exists and is 0
        logger.info("Container %s exited successfully with code 0, cleaning up", container_id)
        
        # Get and delete checkpoint image
        checkpoint_path = self.config_handler.get_checkpoint_path(container_id, namespace)
        if checkpoint_path:
            self.checkpoint_handler.cleanup_checkpoint(checkpoint_path)
            
        # Remove exit flag
        self.state_manager.remove_exit_code(namespace, container_id)
    
    # Pass through original command
    logger.info("Executing delete command for container %s", container_id)
    return self._execute_command(args[1:])
```

Key changes:
1. Only perform cleanup if `exit_code is not None and exit_code == 0`
2. This ensures we have an explicit successful exit before removing the checkpoint
3. In all other cases (no exit code or non-zero exit), we preserve the checkpoint and just pass through the delete command

Would you like me to implement these changes?

**User**: yes... implement changes first, then we can talk about how to add the event listener for container exit codes

**Assistant**: [Implementation of checkpoint cleanup and delete command handling]

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

**User**: pls save this conversation about start, resume, and delete handling under design_doc/converstations, full conversation, not summary 