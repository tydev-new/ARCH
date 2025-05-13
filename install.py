#!/usr/bin/env python3
import os
import sys
import shutil
import subprocess
import json
from src.utils.logging import logger
from src.utils.constants import USER_CONFIG_PATH, CONFIG_PATH, ENV_REAL_RUNC_CMD

def check_root():
    """Check if running as root"""
    if os.geteuid() != 0:
        logger.error("This script must be run as root")
        sys.exit(1)

def check_dependencies():
    """Check if required system packages and Python version are compatible."""
    # Check Python version
    if sys.version_info < (3, 6):
        logger.error("Python 3.6 or higher is required")
        sys.exit(1)
        
    # Check system packages
    required = {'criu', 'containerd', 'runc'}
    missing = set()
    
    for pkg in required:
        try:
            subprocess.run(['which', pkg], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            missing.add(pkg)
    
    if missing:
        logger.error("Missing required system packages: %s", missing)
        logger.error("Please install them using your system package manager:")
        logger.error("  apt: sudo apt-get install %s", " ".join(missing))
        logger.error("  yum: sudo yum install %s", " ".join(missing))
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
    """Check if ARCH is already installed by checking environment variable and backup file"""
    # Check if environment variable exists
    real_runc = os.environ.get(ENV_REAL_RUNC_CMD)
    if not real_runc:
        return False
        
    # Check if backup file exists and is a file
    if not os.path.exists(real_runc) or not os.path.isfile(real_runc):
        return False
        
    # Check if current runc is our wrapper
    try:
        runc_path = find_runc_path()
        if not os.path.isfile(runc_path):
            return False
    except FileNotFoundError:
        return False
        
    return True

def install_wrapper():
    """Install the wrapper script"""
    try:
        # Check if already installed
        if is_already_installed():
            logger.info("ARCH is already installed")
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
        
        # Create config directory with proper permissions
        os.makedirs(USER_CONFIG_PATH, mode=0o777, exist_ok=True)
        
        # Save configuration with proper permissions
        with open(CONFIG_PATH, 'w') as f:
            f.write(f"{ENV_REAL_RUNC_CMD}={backup_path}\n")
        os.chmod(CONFIG_PATH, 0o666)  # rw-rw-rw-
        logger.info(f"Saved configuration to {CONFIG_PATH}")
        
        # Get wrapper script path and validate
        wrapper_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "main.py")
        if not os.path.exists(wrapper_script):
            logger.error(f"Wrapper script not found at {wrapper_script}")
            return False
        
        # Install wrapper script
        wrapper_content = f"""#!/bin/sh
# ARCH wrapper for runc
ARCH_RUNC_WRAPPER="{wrapper_script}"
REAL_RUNC="{backup_path}"

if [ -f "$ARCH_RUNC_WRAPPER" ]; then
    cd "$(dirname "$(dirname "$ARCH_RUNC_WRAPPER")")"
    exec python3 -m src.main "$@"
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
            logger.info("ARCH is not installed, nothing to clean up")
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
    """Uninstall ARCH"""
    try:
        # Clean up runc wrapper
        if not cleanup_runc_wrapper():
            logger.error("Failed to clean up Runc wrapper")
            return False
            
        # Remove config directory if empty
        if os.path.exists(USER_CONFIG_PATH) and not os.listdir(USER_CONFIG_PATH):
            os.rmdir(USER_CONFIG_PATH)
            logger.info(f"Removed empty directory {USER_CONFIG_PATH}")
            
        logger.info("ARCH uninstallation complete")
        return True
        
    except Exception as e:
        logger.error(f"Failed to uninstall ARCH: {str(e)}")
        return False

def check_runc_dependency():
    """Check if runc is available, exit if not found"""
    try:
        find_runc_path()
    except FileNotFoundError as e:
        logger.error("Critical dependency 'runc' not found. ARCH requires runc to be installed.")
        logger.error("Please install runc first: https://github.com/opencontainers/runc")
        sys.exit(1)

def main():
    """Main entry point"""
    check_root()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--uninstall":
        if uninstall():
            sys.exit(0)
        else:
            sys.exit(1)

    check_dependencies()
    check_runc_dependency()    
    if install_wrapper():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main() 