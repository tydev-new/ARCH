import os
import sys
import subprocess
import json
from typing import List, Optional, Dict
from src.utils.logging import logger
from src.runc_command_parser import RuncCommandParser
from src.utils.constants import CONFIG_PATH, ENV_REAL_RUNC_CMD, INTERCEPTABLE_COMMANDS
from src.container_handler.config_handler import ContainerConfigHandler
from src.container_handler.state_manager import ContainerStateManager

class RuncHandler:
    def __init__(self):
        self.parser = RuncCommandParser()
        self.original_runc_cmd = self._get_real_runc_cmd()
        self.config_handler = ContainerConfigHandler()
        self.state_manager = ContainerStateManager()

    def _get_real_runc_cmd(self) -> str:
        """Get the path to the real Runc binary from environment variable or env file"""
        # Try environment variable first
        env_cmd = os.environ.get(ENV_REAL_RUNC_CMD)
        if env_cmd and os.path.exists(env_cmd) and os.access(env_cmd, os.X_OK):
            return env_cmd
            
        # Try reading from tardis.env file
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r') as f:
                    for line in f:
                        if line.startswith(f'{ENV_REAL_RUNC_CMD}='):
                            path = line.split('=', 1)[1].strip()
                            if os.path.exists(path) and os.access(path, os.X_OK):
                                return path
            except Exception as e:
                logger.error(f"Error reading {CONFIG_PATH}: {str(e)}")
                
        logger.error("Could not find runc binary")
        sys.exit(1)

    def intercept_command(self, args: List[str]) -> int:
        """
        Parse and log Runc command details.
        Returns the exit code of the original command.
        """
        try:
            # Log raw command
            logger.info(f"Raw Runc command: {' '.join(args)}")
            
            # Parse command details
            subcommand, global_options, subcommand_options, container_id, namespace = self.parser.parse_command(args)
            
            # Log parsed command details
            logger.info(f"Intercepted Runc command: subcommand={subcommand}, "
                       f"global_options={global_options}, "
                       f"subcommand_options={subcommand_options}, "
                       f"container_id={container_id}, "
                       f"namespace={namespace}")

            # Skip processing if not create/delete or no container info
            if not (container_id and namespace and subcommand in INTERCEPTABLE_COMMANDS):
                logger.info(f"Skipping command {subcommand} for container {container_id} in namespace {namespace}")
                return self._execute_original_command(args)

            # Check if container is Tardis-enabled
            is_enabled = self.config_handler.is_tardis_enabled(container_id, namespace)
            if not is_enabled:
                logger.info(f"Container {container_id} in namespace {namespace} is not Tardis-enabled")
                return self._execute_original_command(args)
            
            # Log state check result
            has_state = self.state_manager.has_state(namespace, container_id)
            logger.info(f"Container {container_id} in namespace {namespace} has state: {has_state}")
            
            # Handle Tardis-enabled container state
            if subcommand == "create" and not has_state:
                self.state_manager.create_state(namespace, container_id)
                logger.info(f"Created state for container {container_id} in namespace {namespace}")
            elif subcommand == "delete" and has_state:
                self.state_manager.clear_state(namespace, container_id)
                logger.info(f"Cleared state for container {container_id} in namespace {namespace}")

            # Get checkpoint path if container is enabled
            checkpoint_path = self.config_handler.get_checkpoint_path(container_id, namespace)
            if checkpoint_path:
                logger.info(f"Container {container_id} checkpoint path: {checkpoint_path}")

            # Execute original command
            return self._execute_original_command(args)

        except Exception as e:
            logger.error(f"Error intercepting command: {str(e)}")
            return 1

    def _execute_original_command(self, args: List[str]) -> int:
        """Execute the original Runc command"""
        try:
            final_cmd = [self.original_runc_cmd] + args[1:]
            logger.info(f"Would execute command: {' '.join(final_cmd)}")
            
            os.execvp(self.original_runc_cmd, final_cmd)
            
        except Exception as e:
            logger.error(f"Error executing original command: {str(e)}")
            return 1
