#!/usr/bin/env python3
import os
import sys
import shutil
import subprocess
import json
from src.utils.logging import logger
from src.utils.constants import CONFIG_DIR, CONFIG_PATH, ENV_REAL_RUNC_CMD

def check_root():
    """Check if running as root"""
    if os.geteuid() != 0:
        logger.error("This script must be run as root")
        sys.exit(1)

def check_dependencies():
    """Check and install required dependencies."""
    try:
        import pkg_resources
        required = {'criu', 'containerd', 'runc'}
        installed = {pkg.key for pkg in pkg_resources.working_set}
        missing = required - installed

        if missing:
            logger.info(f"Installing missing dependencies: {missing}")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', *missing])

    except Exception as e:
        logger.error(f"Failed to check/install dependencies: {str(e)}")
        sys.exit(1)

def find_runc_path() -> str:
    """Find the real runc binary path using which command"""
    try:
        result = subprocess.run(["which", "runc"], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            path = result.stdout.strip()
            if os.path.exists(path) and os.access(path, os.X_OK):
                return path
    except Exception as e:
        logger.error(f"Error running which command: {str(e)}")
        
    raise FileNotFoundError("Could not find runc binary using which command")

def is_already_installed() -> bool:
    """Check if Tardis is already installed"""
    try:
        # Check environment variable
        backup_path = os.environ.get(ENV_REAL_RUNC_CMD)
        if not backup_path:
            logger.info("Environment variable not set")
            return False
            
        # Check if backup exists
        if not os.path.exists(backup_path):
            logger.info("Backup file not found")
            return False
            
        # Find the real runc binary
        real_runc_path = find_runc_path()
        
        # Check if current runc is our wrapper script
        if not os.path.exists(real_runc_path):
            logger.info("runc not found")
            return False
            
        if not os.path.isfile(real_runc_path):
            logger.info("runc is not a file")
            return False
            
        logger.info("Installation found")
        return True
    except Exception as e:
        logger.info(f"Error checking installation: {str(e)}")
        return False

def install_wrapper():
    """Install the wrapper script"""
    try:
        # Check if already installed
        if is_already_installed():
            logger.info("Tardis is already installed")
            return True
            
        # Find real runc path
        real_runc_path = find_runc_path()
        if not real_runc_path:
            logger.error("Could not find runc binary")
            return False
            
        # Create backup of original runc
        backup_path = f"{real_runc_path}.real"
        if not os.path.exists(backup_path):
            shutil.copy2(real_runc_path, backup_path)
            logger.info(f"Created backup at {backup_path}")
        
        # Create config directory if it doesn't exist
        os.makedirs(CONFIG_DIR, exist_ok=True)
        
        # Save configuration
        with open(CONFIG_PATH, 'w') as f:
            f.write(f"{ENV_REAL_RUNC_CMD}={backup_path}\n")
        logger.info(f"Saved configuration to {CONFIG_PATH}")
        
        # Install wrapper script
        wrapper_content = f"""#!/bin/sh
# Tardis wrapper for runc
MAIN_SCRIPT="{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}/src/main.py"
REAL_RUNC="{backup_path}"

if [ -f "$MAIN_SCRIPT" ]; then
    cd "$(dirname "$(dirname "$MAIN_SCRIPT")")"
    exec python3 -m "$MAIN_SCRIPT" "$@"
else
    exec "$REAL_RUNC" "$@"
fi
"""
        with open(real_runc_path, 'w') as f:
            f.write(wrapper_content)
        os.chmod(real_runc_path, 0o755)
        logger.info(f"Installed wrapper at {real_runc_path}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to install wrapper: {e}")
        return False

def cleanup_runc_wrapper():
    """Clean up the Runc wrapper"""
    try:
        # Check if already installed
        if not is_already_installed():
            logger.info("Tardis is not installed, nothing to clean up")
            return True
            
        # Find the real runc binary
        real_runc_path = find_runc_path()
        backup_path = f"{real_runc_path}.real"
        
        # Restore original runc
        if os.path.exists(backup_path):
            if os.path.exists(real_runc_path):
                os.remove(real_runc_path)
            shutil.copy2(backup_path, real_runc_path)
            logger.info(f"Restored original runc to {real_runc_path}")
            
            # Remove backup
            os.remove(backup_path)
            logger.info(f"Removed backup at {backup_path}")
            
        # Remove config file
        if os.path.exists(CONFIG_PATH):
            os.remove(CONFIG_PATH)
            logger.info(f"Removed {CONFIG_PATH}")
            
        logger.info("Runc wrapper cleanup complete")
        return True
        
    except Exception as e:
        logger.error(f"Failed to clean up Runc wrapper: {str(e)}")
        return False

def uninstall():
    """Uninstall Tardis"""
    try:
        # Clean up runc wrapper
        if not cleanup_runc_wrapper():
            logger.error("Failed to clean up Runc wrapper")
            return False
            
        # Remove config directory if empty
        if os.path.exists(CONFIG_DIR) and not os.listdir(CONFIG_DIR):
            os.rmdir(CONFIG_DIR)
            logger.info(f"Removed empty directory {CONFIG_DIR}")
            
        logger.info("Tardis uninstallation complete")
        return True
        
    except Exception as e:
        logger.error(f"Failed to uninstall Tardis: {str(e)}")
        return False

def check_runc_dependency():
    """Check if runc is available, exit if not found"""
    try:
        find_runc_path()
    except FileNotFoundError as e:
        logger.error("Critical dependency 'runc' not found. Tardis requires runc to be installed.")
        logger.error("Please install runc first: https://github.com/opencontainers/runc")
        sys.exit(1)

def main():
    """Main entry point"""
    check_root()
    check_runc_dependency()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--uninstall":
        if uninstall():
            sys.exit(0)
        else:
            sys.exit(1)
    
    if install_wrapper():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main() 