import os
import sys
import subprocess
from typing import List, Dict, Optional, Tuple
from src.utils.logging import logger
from src.utils.constants import INTERCEPTABLE_COMMANDS, RUNC_SUBCMD_BOOLEAN_FLAGS

class RuncCommandParser:
    """
    Parser for Runc commands intercepted from Containerd.
    
    This parser handles the following command formats:
    - runc [global_options] subcommand [subcommand_options] container_id
    
    Global options are in the format: --option value or -o value
    Subcommand options follow the same format.
    """
    
    def __init__(self):
        """Initialize the parser with the list of interceptable commands."""
        self.interceptable_commands = INTERCEPTABLE_COMMANDS
    
    def _normalize_option(self, opt: str) -> str:
        """Return the option as is since we don't need to map short options."""
        return opt
    
    def parse_command(self, args: List[str]) -> Tuple[str, Dict[str, str], Dict[str, str], str, str]:
        """Parse runc command into components.
        
        Returns:
            Tuple containing:
            - subcommand (str): The subcommand
            - global_options (Dict[str, str]): Global options and their values
            - subcommand_options (Dict[str, str]): Subcommand options and their values
            - container_id (str): The container ID
            - namespace (str): The namespace extracted from root path
        """
        if not args:
            raise ValueError("Empty command")
            
        logger.info(f"Parsing command: {args}")
            
        # Get the command
        command = args[0]
        i = 1
        
        # Parse global options
        global_options = {}
        while i < len(args) and (args[i].startswith("--") or args[i].startswith("-")):
            opt = args[i]
            normalized_opt = self._normalize_option(opt)
            
            # Check if this is a boolean flag
            if normalized_opt in RUNC_SUBCMD_BOOLEAN_FLAGS:
                global_options[normalized_opt] = ""
                i += 1
            # Check if there's a value for this option
            elif i + 1 < len(args) and not (args[i + 1].startswith("--") or args[i + 1].startswith("-")):
                global_options[normalized_opt] = args[i + 1]
                i += 2
            else:
                # No value provided, treat as boolean flag
                global_options[normalized_opt] = ""
                i += 1
                
        # Check for special global-only commands
        if i >= len(args):
            # This is a global-only command like --version or --help
            logger.info("Detected global-only command")
            return "", global_options, {}, "", "default"
            
        # Parse subcommand
        subcommand = args[i]
        logger.info(f"Identified subcommand: {subcommand}")
        i += 1
        
        # Parse subcommand options (everything between subcommand and container ID)
        subcommand_options = {}
        while i < len(args):
            if args[i].startswith("--") or args[i].startswith("-"):
                opt = args[i]
                normalized_opt = self._normalize_option(opt)
                
                # Check if this is a boolean flag
                if normalized_opt in RUNC_SUBCMD_BOOLEAN_FLAGS:
                    subcommand_options[normalized_opt] = ""
                    i += 1
                # Check if there's a value for this option
                elif i + 1 < len(args) and not (args[i + 1].startswith("--") or args[i + 1].startswith("-")):
                    subcommand_options[normalized_opt] = args[i + 1]
                    i += 2
                else:
                    # No value provided, treat as boolean flag
                    subcommand_options[normalized_opt] = ""
                    i += 1
            else:
                i += 1  # Skip non-option arguments
        
        # Get container ID (last argument if it exists and isn't an option)
        container_id = ""
        if args and not (args[-1].startswith("--") or args[-1].startswith("-")):
            container_id = args[-1]
        
        # Extract namespace from root path
        namespace = 'default'
        if '--root' in global_options:
            root_path = global_options['--root']
            if root_path and not root_path.endswith('/'):
                parts = root_path.split('/')
                if parts:  # If there's at least one part
                    namespace = parts[-1]
        
        logger.info(f"Parsed command: subcommand={subcommand}, "
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
