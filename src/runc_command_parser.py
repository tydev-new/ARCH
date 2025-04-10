import os
import sys
import subprocess
from typing import List, Dict, Optional, Tuple
from src.utils.logging import logger
from src.utils.constants import INTERCEPTABLE_COMMANDS

class RuncCommandParser:
    """
    Parser for Runc commands intercepted from Containerd.
    
    This parser handles the following command formats:
    - runc [global_options] subcommand [subcommand_options] container_id
    
    Global options are in the format: --option value
    Subcommand options follow the same format.
    """
    
    def __init__(self):
        """Initialize the parser with the list of interceptable commands."""
        self.interceptable_commands = INTERCEPTABLE_COMMANDS
    
    def parse_command(self, args: List[str]) -> Tuple[str, Dict, List[str], str, str]:
        """
        Parse Runc command arguments.
        
        Args:
            args: List of command arguments, including the command name
            
        Returns:
            Tuple containing:
            - subcommand: The main command (create, start, etc.)
            - global_options: Dictionary of global options
            - subcommand_options: List of subcommand options
            - container_id: The container identifier
            - namespace: The namespace extracted from root path
            
        Raises:
            ValueError: If the command is empty or missing required components
        """
        if not args:
            raise ValueError("Empty command")
            
        if len(args) < 2:
            raise ValueError("Command must include at least a subcommand and container ID")

        # Skip wrapper/runc path
        args = args[1:]
        
        # Last argument is container_id
        container_id = args[-1]
        args = args[:-1]
        
        # Find subcommand (first non-option argument after all global options)
        subcommand_idx = 0
        while subcommand_idx < len(args):
            if args[subcommand_idx].startswith('-'):
                # Skip this option and its value if present
                subcommand_idx += 1
                if subcommand_idx < len(args) and not args[subcommand_idx].startswith('-'):
                    subcommand_idx += 1
            else:
                # Found subcommand
                break
                
        if subcommand_idx >= len(args):
            raise ValueError("No subcommand found")
            
        subcommand = args[subcommand_idx]
        
        # Everything before subcommand is global options
        global_options = {}
        i = 0
        while i < subcommand_idx:
            if not args[i].startswith('--'):
                raise ValueError(f"Invalid option format: {args[i]}")
                
            key = args[i][2:]  # Remove -- prefix
            if i + 1 < subcommand_idx and not args[i + 1].startswith('-'):
                global_options[key] = args[i + 1]
                i += 1
            else:
                global_options[key] = True
            i += 1
        
        # Everything between subcommand and container_id is subcommand options
        subcommand_options = args[subcommand_idx + 1:]
        
        # Extract namespace from root path
        namespace = 'default'
        if 'root' in global_options:
            root_path = global_options['root']
            if root_path and not root_path.endswith('/'):
                parts = root_path.split('/')
                if parts:  # If there's at least one part
                    namespace = parts[-1]
        
        logger.debug(f"Parsed command: subcommand={subcommand}, "
                    f"global_options={global_options}, "
                    f"subcommand_options={subcommand_options}, "
                    f"container_id={container_id}, "
                    f"namespace={namespace}")
                    
        return subcommand, global_options, subcommand_options, container_id, namespace
    
    def should_intercept(self, subcommand: str, global_options: Dict) -> bool:
        """
        Determine if the command should be intercepted.
        
        Args:
            subcommand: The command to check
            global_options: Dictionary of global options
            
        Returns:
            True if the command should be intercepted, False otherwise
        """
        return subcommand in self.interceptable_commands
