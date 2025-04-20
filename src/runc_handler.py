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
from src.container_handler.filesystem_handler import ContainerFilesystemHandler
from src.container_handler.runtime_state import ContainerRuntimeState
from src.checkpoint_handler import CheckpointHandler
from src.container_handler.flag_manager import ContainerFlagManager

class RuncHandler:
    def __init__(self):
        self.parser = RuncCommandParser()
        self.original_runc_cmd = self._get_real_runc_cmd()
        self.config_handler = ContainerConfigHandler()
        self.filesystem_handler = ContainerFilesystemHandler()
        self.checkpoint_handler = CheckpointHandler()
        self.runtime_state = ContainerRuntimeState(self.original_runc_cmd)
        self.flag_manager = ContainerFlagManager()
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

    def _build_restore_command(self, container_id: str, global_options: Dict[str, str], 
                             subcmd_options: Dict[str, str], checkpoint_path: str) -> List[str]:
        """Build restore command with checkpoint path."""
        cmd = [self.original_runc_cmd]
        
        # Add global options
        for opt, value in global_options.items():
            cmd.extend([opt, value])
        
        # Add restore command and options
        cmd.append("restore")
        for opt, value in subcmd_options.items():
            cmd.extend([opt, value])
        
        # Ensure --detached option is present
        if "--detach" not in subcmd_options:
            cmd.append("--detach")
        
        # Add checkpoint path and container ID
        cmd.extend(["--image-path", checkpoint_path, container_id])
        
        logger.info("Built restore command: %s", " ".join(cmd))
        return cmd

    def _perform_restore_process(self, container_id: str, global_options: Dict[str, str], 
                        subcmd_options: Dict[str, str], checkpoint_path: str) -> bool:
        """Perform restore operation for container.
        
        Returns:
            bool: True if restore was successful, False otherwise
        """
        try:
            # Build and execute restore command
            restore_cmd = self._build_restore_command(
                container_id=container_id,
                global_options=global_options,
                subcmd_options=subcmd_options,
                checkpoint_path=checkpoint_path
            )
            
            logger.info("Executing restore command for container %s", container_id)
            result = subprocess.run(restore_cmd, check=False)
            
            if result.returncode == 0:
                logger.info("Successfully restored container %s", container_id)
                return True
                
            logger.warning("Restore command failed for container %s with code %d", container_id, result.returncode)
            return False
                
        except Exception as e:
            logger.warning("Error during restore for container %s: %s", container_id, str(e))
            return False

    def _handle_create_command(self, container_id: str, namespace: str, global_options: Dict[str, str], 
                             subcommand_options: Dict[str, str], arg: List[str]) -> int:
        """Handle create command processing."""
        logger.info("Processing create command for container %s in namespace %s", container_id, namespace)
        logger.info("Original command: %s", arg)

        # Get checkpoint path and upperdir
        checkpoint_path, upperdir = self._get_container_paths(container_id, namespace)
        if not checkpoint_path or not upperdir:
            logger.info("No checkpoint found for container %s, proceeding with create", container_id)
            return self._execute_command(arg)

        # Add bind mount if ARCH_SHAREDFS_HOST_PATH is set
        if not self.config_handler.add_bind_mount(container_id, namespace):
            logger.warning("Failed to add bind mount for container %s, falling back to create", container_id)
            return self._execute_command(arg)
        
        # Validate checkpoint
        if not self.checkpoint_handler.validate_checkpoint(checkpoint_path):
            logger.warning("Invalid checkpoint for container %s, falling back to create", container_id)
            return self._execute_command(arg)
        
        # Restore from checkpoint
        try:
            logger.info("Restoring container %s from checkpoint at %s", container_id, checkpoint_path)
            
            # Restore files from checkpoint
            if not self.checkpoint_handler.restore_checkpoint_file(checkpoint_path, upperdir):
                logger.warning("Failed to restore container files for %s, falling back to create", container_id)
                self.checkpoint_handler.rollback_restore_file(upperdir)
                return self._execute_command(arg)
            
            # Perform restore operation
            if self._perform_restore_process(container_id, global_options, subcommand_options, checkpoint_path):
                self.flag_manager.set_skip_start(namespace, container_id, True)
                return 0
                
        except Exception as e:
            logger.warning("Error during restore for container %s: %s, falling back to create", container_id, str(e))
            self.checkpoint_handler.rollback_restore_file(upperdir)
            
        # On any failure, cleanup and create
        logger.info("Falling back to create command for container %s", container_id)
        return self._execute_command(arg)

    def _handle_start_command(self, container_id: str, namespace: str, global_options: Dict[str, str], 
                            subcommand_options: Dict[str, str], args: List[str]) -> int:
        """Handle start command processing."""
        logger.info("Processing start command for container %s in namespace %s", container_id, namespace)
        
        # Check skip_start flag
        if self.flag_manager.get_skip_start(namespace, container_id):
            logger.info("Skip start flag set for container %s, resetting flag and exiting", container_id)
            self.flag_manager.set_skip_start(namespace, container_id, False)
            return 0
        
        # Pass through original command
        logger.info("No skip start flag for container %s, passing through", container_id)
        return self._execute_command(args)

    def _handle_resume_command(self, container_id: str, namespace: str, global_options: Dict[str, str], 
                             subcommand_options: Dict[str, str], args: List[str]) -> int:
        """Handle resume command processing."""
        logger.info("Processing resume command for container %s in namespace %s", container_id, namespace)
        
        # Check skip_resume flag
        if self.flag_manager.get_skip_resume(namespace, container_id):
            logger.info("Skip resume flag set for container %s, resetting flag and exiting", container_id)
            self.flag_manager.set_skip_resume(namespace, container_id, False)
            return 0
        
        # Pass through original command
        logger.info("No skip resume flag for container %s, passing through", container_id)
        return self._execute_command(args)

    def _get_container_paths(self, container_id: str, namespace: str) -> Tuple[Optional[str], Optional[str]]:
        """Get checkpoint path and upperdir for container."""
        checkpoint_path = self.config_handler.get_checkpoint_path(container_id, namespace)
        if not checkpoint_path:
            logger.warning("Could not determine checkpoint path for container %s", container_id)
            return None, None
            
        upperdir = self.filesystem_handler.get_upperdir(container_id, namespace)
        if not upperdir:
            logger.warning("Could not determine container upperdir for container %s", container_id)
            return None, None
            
        return checkpoint_path, upperdir


    def _cleanup_container_resources(self, container_id: str, namespace: str) -> None:
        """Clean up checkpoint and work directory for container."""
        # Get checkpoint path
        checkpoint_path = self.config_handler.get_checkpoint_path(container_id, namespace)
        
        # Clean up checkpoint if path exists
        if checkpoint_path:
            if not self.checkpoint_handler.cleanup_checkpoint(checkpoint_path):
                logger.warning("Failed to clean up checkpoint for container %s", container_id)
        
        # Clean up work directory
        if not self.config_handler.delete_work_directory(container_id, namespace):
            logger.warning("Failed to clean up work directory for container %s", container_id)

    def _handle_delete_command(self, container_id: str, namespace: str, global_options: Dict[str, str], 
                             subcommand_options: Dict[str, str], args: List[str]) -> int:
        """Handle delete command processing."""
        logger.info("Processing delete command for container %s in namespace %s", container_id, namespace)
        
        # Check if flag file exists
        if self.flag_manager.has_flag(namespace, container_id):
            logger.info("Flag file found for container %s in namespace %s", container_id, namespace)
            # Check if keep_resources is false
            if not self.flag_manager.get_keep_resources(namespace, container_id):
                logger.info("Keep resources flag is false for container %s, cleaning up resources", container_id)
                # Clean up resources
                self._cleanup_container_resources(container_id, namespace)
            # Clear flag
            self.flag_manager.clear_flag(namespace, container_id)
        
        # Execute the real runc delete command
        logger.info("Executing delete command for container %s", container_id)
        return self._execute_command(args)

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

    def intercept_command(self, args: List[str]) -> int:
        """Intercept and process Runc commands."""
        try:
            # Log the raw command for debugging
            logger.info("Raw command received: %s", " ".join(args))
            
            # Parse the command
            try:
                subcommand, global_options, subcommand_options, container_id, namespace = self.parser.parse_command(args)
                logger.info("Intercepted %s command for container %s in namespace %s", subcommand, container_id, namespace)
            except Exception as e:
                logger.warning("Failed to parse command: %s, proceeding with original command", str(e))
                return self._execute_command(args[1:])
            
            # Check if command should be intercepted
            if subcommand not in INTERCEPTABLE_COMMANDS:
                logger.info("Command %s not intercepted, passing through", subcommand)
                return self._execute_command(args[1:])
            
            # Check if container is ARCH-enabled
            if not self.config_handler.is_arch_enabled(container_id, namespace):
                logger.info("Container %s not ARCH-enabled, passing through", container_id)
                return self._execute_command(args[1:])

            # Check if state exists, if not create it
            if not self.flag_manager.has_flag(namespace, container_id):
                logger.info("Creating flag for container %s in namespace %s", container_id, namespace)
                self.flag_manager.create_flag(namespace, container_id)
            
            # Handle specific commands
            if subcommand == "create":
                return self._handle_create_command(container_id, namespace, global_options, subcommand_options, args[1:])
            elif subcommand == "start":
                return self._handle_start_command(container_id, namespace, global_options, subcommand_options, args[1:])
            elif subcommand == "delete":
                return self._handle_delete_command(container_id, namespace, global_options, subcommand_options, args[1:])
            elif subcommand == "checkpoint":
                return self._handle_checkpoint_command(container_id, namespace, global_options, subcommand_options, args[1:])
            elif subcommand == "resume":
                return self._handle_resume_command(container_id, namespace, global_options, subcommand_options, args[1:])
            else:
                logger.info("Unhandled command %s, passing through", subcommand)
                return self._execute_command(args[1:])
        except Exception as e:
            logger.warning("Error in command processing: %s, proceeding with original command", str(e))
            return self._execute_command(args[1:])

    def _handle_checkpoint_command(self, container_id: str, namespace: str, global_options: Dict[str, str], 
                                 subcommand_options: Dict[str, str], args: List[str]) -> int:
        """Handle checkpoint command processing."""
        logger.info("Processing checkpoint command for container %s in namespace %s", container_id, namespace)
        
        # Get checkpoint path and upperdir
        checkpoint_path, upperdir = self._get_container_paths(container_id, namespace)
        if not checkpoint_path or not upperdir:
            logger.warning("Could not determine container paths for container %s in namespace %s", container_id, namespace)
            return self._execute_command(args)
        
        try:
            # Save container files first
            logger.info("Saving container files to checkpoint at %s", checkpoint_path)
            if not self.checkpoint_handler.save_checkpoint_file(upperdir, checkpoint_path):
                logger.warning("Failed to save container files for container %s in namespace %s", container_id, namespace)
                return self._execute_command(args)
            
            # Set skip_resume flag
            logger.info("Setting skip_resume and keep_resources flags for container %s", container_id)
            self.flag_manager.set_skip_resume(namespace, container_id, True)
            self.flag_manager.set_keep_resources(namespace, container_id, True)
            
            # Build and execute checkpoint command
            checkpoint_cmd = self._build_checkpoint_command(
                container_id=container_id,
                namespace=namespace,
                global_options=global_options,
                subcmd_options=subcommand_options,
                checkpoint_path=checkpoint_path
            )
            
            logger.info("Executing checkpoint command for container %s", container_id)
            return self._execute_command(checkpoint_cmd)
                
        except Exception as e:
            logger.warning("Checkpoint failed: %s for container %s in namespace %s", str(e), container_id, namespace)
            return self._execute_command(args)

    def _build_checkpoint_command(self, container_id: str, namespace: str, global_options: Dict[str, str], 
                                subcmd_options: Dict[str, str], checkpoint_path: str) -> List[str]:
        """Build checkpoint command with checkpoint path."""
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
                elif value == "":  # Boolean flag
                    cmd.append(opt)
                else:
                    cmd.extend([opt, value])
        
        # Add container ID
        cmd.append(container_id)
        
        logger.info("Built checkpoint command: %s", " ".join(cmd))
        return cmd
