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

class RuncHandler:
    def __init__(self):
        self.parser = RuncCommandParser()
        self.original_runc_cmd = self._get_real_runc_cmd()
        self.config_handler = ContainerConfigHandler()
        self.state_manager = ContainerStateManager()
        self.filesystem_handler = ContainerFilesystemHandler()
        self.checkpoint_handler = CheckpointHandler()
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
        if "--detached" not in subcmd_options:
            cmd.append("--detached")
        
        # Add container ID
        cmd.append(container_id)
        
        logger.info("Modified restore command: %s", " ".join(cmd))
        return cmd

    def _handle_create_command(self, container_id: str, namespace: str, global_options: Dict[str, str], subcommand_options: Dict[str, str], arg: List[str]) -> int:
        """Handle create command processing."""
        logger.info("Processing create command for container %s in namespace %s", container_id, namespace)
        logger.info("Original command: %s", arg)
        # First verify bind mount
        # TODO: Implement bind mount verification
        # if not self.config_handler.verify_bind_mount(container_id, namespace):
        #     return self._handle_error("Failed to verify bind mount", container_id, namespace)

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
            return self._handle_error("Could not determine container upperdir", container_id, namespace)
        
        # Restore from checkpoint
        try:
            logger.info("Restoring container %s from checkpoint at %s", container_id, checkpoint_path)
            # Restore files from checkpoint
            if not self.checkpoint_handler.restore_checkpoint(checkpoint_path, upperdir):
                return self._handle_error("Failed to restore container files", container_id, namespace)
            
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
            if opt not in ["--work-path", "--leave-running"]:  # Skip work-path and leave-running options
                if opt == "--image-path":
                    cmd.extend([opt, checkpoint_path])  # Use our checkpoint path
                else:
                    cmd.extend([opt, value])
        
        # Add container ID
        cmd.append(container_id)
        
        logger.info("Modified checkpoint command: %s", " ".join(cmd))
        return cmd

    def intercept_command(self, args: List[str]) -> int:
        """Intercept and process Runc commands."""
        try:
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
            
            # Handle specific commands
            if subcommand == "create":
                return self._handle_create_command(container_id, namespace, global_options, subcommand_options, args[1:])
            elif subcommand == "checkpoint":
                return self._handle_checkpoint_command(container_id, namespace, global_options, subcommand_options)
            else:
                logger.info("Unhandled command %s, passing through", subcommand)
                return self._execute_command(args[1:])
        except Exception as e:
            logger.error("Error intercepting command: %s", str(e))
            return 1
