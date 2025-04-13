import os
import sys
import subprocess
import json
import shutil
from typing import List, Optional, Dict, Tuple
from src.utils.logging import logger
from src.runc_command_parser import RuncCommandParser
from src.utils.constants import CONFIG_PATH, ENV_REAL_RUNC_CMD, INTERCEPTABLE_COMMANDS
from src.container_handler.config_handler import ContainerConfigHandler
from src.container_handler.state_manager import ContainerStateManager
from src.container_handler.filesystem_handler import ContainerFilesystemHandler
from src.checkpoint_handler import CheckpointHandler
from src.container_handler.event_listener import ContainerEventListener

class RuncHandler:
    def __init__(self):
        self.parser = RuncCommandParser()
        self.original_runc_cmd = self._get_real_runc_cmd()
        self.config_handler = ContainerConfigHandler()
        self.state_manager = ContainerStateManager()
        self.filesystem_handler = ContainerFilesystemHandler()
        self.checkpoint_handler = CheckpointHandler()
        self.event_listener = None
        logger.info("RuncHandler initialized with real runc at: %s", self.original_runc_cmd)

    def _get_real_runc_cmd(self) -> str:
        """Get the path to the real Runc binary from environment variable or env file"""
        # Try environment variable first
        env_cmd = os.environ.get(ENV_REAL_RUNC_CMD)
        if env_cmd and os.path.exists(env_cmd) and os.access(env_cmd, os.X_OK):
            logger.info("Using real runc from environment variable: %s", env_cmd)
            return env_cmd
            
        # Try reading from tardis.env file
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r') as f:
                    for line in f:
                        if line.startswith(f'{ENV_REAL_RUNC_CMD}='):
                            path = line.split('=', 1)[1].strip()
                            if os.path.exists(path) and os.access(path, os.X_OK):
                                logger.info("Using real runc from config file: %s", path)
                                return path
            except Exception as e:
                logger.error("Error reading %s: %s", CONFIG_PATH, str(e))
                
        logger.error("Could not find runc binary")
        sys.exit(1)

    def _handle_error(self, error_msg: str, container_id: str, namespace: str) -> int:
        """Common error handling for command processing."""
        logger.error("%s for container %s in namespace %s", error_msg, container_id, namespace)
        return 1

    def _modify_restore_command(self, container_id: str, namespace: str, global_options: Dict[str, str], subcmd_options: Dict[str, str], checkpoint_path: str) -> List[str]:
        """Modify the restore command to use our checkpoint path."""
        # Start with the real runc command
        cmd = [self.original_runc_cmd]
        
        # Add global options
        for opt, value in global_options.items():
            cmd.extend([opt, value])
        
        # Add subcommand
        cmd.append("restore")
        
        # Add subcommand options
        for opt, value in subcmd_options.items():
            cmd.extend([opt, value])
        
        # Add our checkpoint path
        cmd.extend(["--image-path", checkpoint_path])
        
        # Ensure --detached option is present
        if "--detach" not in subcmd_options:
            cmd.append("--detach")
        
        # Add container ID
        cmd.append(container_id)
        
        logger.info("Modified restore command: %s", " ".join(cmd))
        return cmd

    def _handle_create_command(self, container_id: str, namespace: str, global_options: Dict[str, str], subcommand_options: Dict[str, str], arg: List[str]) -> int:
        """Handle create command processing."""
        logger.info("Processing create command for container %s in namespace %s", container_id, namespace)
        logger.info("Original command: %s", arg)

        # Create state file for Tardis-enabled container
        self.state_manager.create_state(namespace, container_id)
        logger.info("Created state file for container %s in namespace %s", container_id, namespace)

        # Add bind mount if TARDIS_NETWORKFS_HOST_PATH is set
        if not self.config_handler.add_bind_mount(container_id, namespace):
            logger.warning("Failed to add bind mount for container %s", container_id)
            # Continue with create/restore even if bind mount fails

        # Then check for checkpoint image
        checkpoint_path = self.config_handler.get_checkpoint_path(container_id, namespace)
        if not checkpoint_path:
            logger.info("No checkpoint found for container %s, proceeding with create", container_id)
            return self._execute_command(arg)

        # Validate checkpoint
        if not self.checkpoint_handler.validate_checkpoint(checkpoint_path):
            logger.warning("Invalid checkpoint for container %s", container_id)
            return self._execute_command(arg)
        
        # Get container upperdir
        upperdir = self.filesystem_handler.get_upperdir(container_id, namespace)
        if not upperdir:
            logger.warning("Could not determine container upperdir %s, %s", container_id, namespace)
            return self._execute_command(arg)
        
        # Restore from checkpoint
        try:
            logger.info("Restoring container %s from checkpoint at %s", container_id, checkpoint_path)
            # Restore files from checkpoint
            if not self.checkpoint_handler.restore_checkpoint(checkpoint_path, upperdir):
                logger.warning("Failed to restore container files %s, %s", container_id, namespace)
                return self._execute_command(arg)
            
            # Build restore command using _modify_restore_command
            restore_cmd = self._modify_restore_command(
                container_id=container_id,
                namespace=namespace,
                global_options=global_options,
                subcmd_options=subcommand_options,
                checkpoint_path=checkpoint_path
            )
            
            # Execute restore command using subprocess.run
            logger.info("Executing restore command for container %s", container_id)
            result = subprocess.run(restore_cmd, check=False)
            
            if result.returncode == 0:
                logger.info("Successfully restored container %s", container_id)
                self.state_manager.set_skip_start(namespace, container_id, True)
                return 0
                
        except Exception:
            pass
            
        # On any failure, cleanup and create
        logger.info("Falling back to create command for container %s", container_id)
        self.checkpoint_handler.rollback_restore(upperdir)
        return self._execute_command(arg)

    def _handle_checkpoint_command(self, container_id: str, namespace: str, global_options: Dict[str, str], subcommand_options: Dict[str, str]) -> int:
        """Handle checkpoint command processing."""
        logger.info("Processing checkpoint command for container %s in namespace %s", container_id, namespace)
        
        # Get checkpoint path
        checkpoint_path = self.config_handler.get_checkpoint_path(container_id, namespace)
        if not checkpoint_path:
            return self._handle_error("Could not determine checkpoint path", container_id, namespace)
        
        # Get container upperdir
        upperdir = self.filesystem_handler.get_upperdir(container_id, namespace)
        if not upperdir:
            return self._handle_error("Could not determine container upperdir", container_id, namespace)
        
        try:
            # Save container files first
            logger.info("Saving container files to checkpoint at %s", checkpoint_path)
            if not self.checkpoint_handler.save_checkpoint(upperdir, checkpoint_path):
                return self._handle_error("Failed to save container files", container_id, namespace)
            
            # Set skip_resume flag
            logger.info("Setting skip_resume flag for container %s", container_id)
            self.state_manager.set_skip_resume(namespace, container_id, True)
            
            logger.info("Before modify command")
            # Modify and execute command last (since execvp will replace current process)
            modified_cmd = self._modify_checkpoint_command(
                container_id=container_id,
                namespace=namespace,
                global_options=global_options,
                subcmd_options=subcommand_options,
                checkpoint_path=checkpoint_path
            )
            logger.info("Modified command: %s", " ".join(modified_cmd))
            return self._execute_command(modified_cmd)
            
        except Exception as e:
            return self._handle_error(f"Checkpoint failed: {str(e)}", container_id, namespace)

    def _execute_command(self, args: List[str]) -> int:
        """Execute the command with the real Runc binary."""
        try:
            logger.info("Executing command: %s", " ".join([self.original_runc_cmd] + args))
            # Replace current process with the real runc command
            os.execvp(self.original_runc_cmd, [self.original_runc_cmd] + args)
            # This line will never be reached if execvp succeeds
            return 0
        except Exception as e:
            logger.error("Error executing command: %s", str(e))
            return 1

    def _modify_checkpoint_command(self, container_id: str, namespace: str, global_options: Dict[str, str], subcmd_options: Dict[str, str], checkpoint_path: str) -> List[str]:
        """Modify the checkpoint command to use our checkpoint path."""
        # Start with empty command list
        cmd = []
        
        # Add global options
        for opt, value in global_options.items():
            cmd.extend([opt, value])
        
        # Add subcommand
        cmd.append("checkpoint")
        
        # Add subcommand options, excluding work-path and leave-running
        for opt, value in subcmd_options.items():
            # Skip work-path and leave-running options
            if opt in ["--work-path", "--leave-running"]:
                continue
                
            if opt == "--image-path":
                cmd.extend([opt, checkpoint_path])  # Use our checkpoint path
            elif value == "":  # Handle options with empty values
                cmd.append(opt)
            else:
                cmd.extend([opt, value])
        
        # Add container ID
        cmd.append(container_id)
        
        logger.info("Modified checkpoint command: %s", " ".join(cmd))
        return cmd

    def _handle_start_command(self, container_id: str, namespace: str, args: List[str]) -> int:
        """Handle start command processing."""
        logger.info("Processing start command for container %s in namespace %s", container_id, namespace)
        
        # Check skip_start flag
        if self.state_manager.get_skip_start(namespace, container_id):
            logger.info("Skip start flag set for container %s, resetting flag and exiting", container_id)
            self.state_manager.set_skip_start(namespace, container_id, False)
            return 0
        
        # Pass through original command
        logger.info("No skip start flag for container %s, passing through", container_id)
        return self._execute_command(args[1:])

    def _handle_resume_command(self, container_id: str, namespace: str, args: List[str]) -> int:
        """Handle resume command processing."""
        logger.info("Processing resume command for container %s in namespace %s", container_id, namespace)
        
        # Check skip_resume flag
        if self.state_manager.get_skip_resume(namespace, container_id):
            logger.info("Skip resume flag set for container %s, resetting flag and exiting", container_id)
            self.state_manager.set_skip_resume(namespace, container_id, False)
            return 0
        
        # Pass through original command
        logger.info("No skip resume flag for container %s, passing through", container_id)
        return self._execute_command(args[1:])

    def _handle_delete_command(self, container_id: str, namespace: str, args: List[str]) -> int:
        """Handle delete command processing."""
        logger.info("Starting delete command processing for container %s in namespace %s", container_id, namespace)
        
        # Check exit code
        logger.info("Checking exit code for container %s", container_id)
        exit_code = self.state_manager.get_exit_code(namespace, container_id)
        logger.info("Exit code for container %s: %s", container_id, exit_code)
        
        if exit_code is not None and exit_code == 0:  # Only cleanup if exit code is 0
            logger.info("Container %s exited successfully with code 0, proceeding with cleanup", container_id)
            
            # Get checkpoint path
            logger.info("Getting checkpoint path for container %s", container_id)
            checkpoint_path = self.config_handler.get_checkpoint_path(container_id, namespace)
            logger.info("Checkpoint path for container %s: %s", container_id, checkpoint_path)
            
            # Clean up checkpoint
            if checkpoint_path:
                logger.info("Cleaning up checkpoint for container %s at %s", container_id, checkpoint_path)
                if self.checkpoint_handler.cleanup_checkpoint(checkpoint_path):
                    logger.info("Successfully cleaned up checkpoint for container %s", container_id)
                else:
                    logger.warning("Failed to clean up checkpoint for container %s", container_id)
            else:
                logger.info("No checkpoint path found for container %s, skipping cleanup", container_id)
                
            # Delete work directory
            logger.info("Deleting work directory for container %s", container_id)
            if self.config_handler.delete_work_directory(container_id, namespace):
                logger.info("Successfully deleted work directory for container %s", container_id)
            else:
                logger.warning("Failed to delete work directory for container %s", container_id)
        
        # Always clear state regardless of exit code
        self.state_manager.clear_state(namespace, container_id)
        logger.info("Cleared state for container %s", container_id)
        
        # Pass through original command
        logger.info("Executing original delete command for container %s", container_id)
        return self._execute_command(args[1:])

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

    def intercept_command(self, args: List[str]) -> int:
        """Intercept and process Runc commands."""
        try:
            # Log the raw command for debugging
            logger.info("Raw command received: %s", " ".join(args))
            
            # Parse the command
            subcommand, global_options, subcommand_options, container_id, namespace = self.parser.parse_command(args)
            logger.info("Intercepted %s command for container %s in namespace %s", subcommand, container_id, namespace)
            
            # Check if command should be intercepted
            if subcommand not in INTERCEPTABLE_COMMANDS:
                logger.info("Command %s not intercepted, passing through", subcommand)
                return self._execute_command(args[1:])
            
            # Check if container is Tardis-enabled
            if not self.config_handler.is_tardis_enabled(container_id, namespace):
                logger.info("Container %s not Tardis-enabled, passing through", container_id)
                return self._execute_command(args[1:])
                
            # Start event listener for Tardis-enabled containers
            self._ensure_event_listener()
            
            # Handle specific commands
            if subcommand == "create":
                return self._handle_create_command(container_id, namespace, global_options, subcommand_options, args[1:])
            elif subcommand == "checkpoint":
                return self._handle_checkpoint_command(container_id, namespace, global_options, subcommand_options)
            elif subcommand == "start":
                return self._handle_start_command(container_id, namespace, args)
            elif subcommand == "resume":
                return self._handle_resume_command(container_id, namespace, args)
            elif subcommand == "delete":
                return self._handle_delete_command(container_id, namespace, args)
            else:
                logger.info("Unhandled command %s, passing through", subcommand)
                return self._execute_command(args[1:])
        except Exception as e:
            logger.error("Error intercepting command: %s", str(e))
            return 1
