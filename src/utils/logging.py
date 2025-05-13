import logging
import os
import sys
from typing import Optional
from src.utils.constants import LOG_FILE, DEFAULT_LOG_LEVEL, CONFIG_PATH, USER_CONFIG_PATH

def debug_log(msg: str):
    """Write debug message to debug.log file."""
    with open('debug.log', 'a') as f:
        f.write(f"{msg}\n")

def read_config():
    """Read logging configuration from config file."""
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            for line in f:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    config[key] = value
    return config

def setup_logger(name: str, level: Optional[int] = None, log_file: str = LOG_FILE) -> logging.Logger:
    """
    Set up a logger with consistent formatting and configuration.
    
    Args:
        name: Name of the logger
        level: Optional logging level. Defaults to INFO if not specified.
        log_file: Optional path to log file. If not specified, logs only to console.
    
    Returns:
        logging.Logger: Configured logger instance
    """
    # Get config values
    config = {}
    debug_log(f"Reading config from: {CONFIG_PATH}")
    
    # Ensure config directory exists with proper permissions
    os.makedirs(USER_CONFIG_PATH, mode=0o777, exist_ok=True)
    
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            for line in f:
                line = line.strip()
                if line and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    debug_log(f"Read config: {config}")
    
    # Use config file path if available, otherwise use provided path
    config_log_file = config.get('ARCH_LOG_FILE')
    if config_log_file:
        log_file = config_log_file
    
    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, mode=0o777, exist_ok=True)  # rwxrwxrwx
    
    logger = logging.getLogger(name)
    
    # Set default level to INFO if not specified
    if level is None:
        # Try config file first
        config_level = config.get('ARCH_LOG_LEVEL')
        debug_log(f"Config level from file: {config_level}")
        if config_level:
            level = getattr(logging, config_level.upper())
            debug_log(f"Set level to: {level}")
        else:
            # Fall back to environment variable
            env_level = os.environ.get('ARCH_LOG_LEVEL', DEFAULT_LOG_LEVEL).upper()
            debug_log(f"Env level: {env_level}")
            try:
                level = getattr(logging, env_level)
                debug_log(f"Set level to: {level}")
            except AttributeError:
                level = logging.INFO
                debug_log("Failed to set level from env, defaulting to INFO")
    
    logger.setLevel(level)
    
    # Clear existing handlers
    logger.handlers = []
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s - (%(filename)s)',
        datefmt='%H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler if log_file is specified
    if log_file:
        # Create empty log file if it doesn't exist and set permissions
        if not os.path.exists(log_file):
            with open(log_file, 'a') as f:
                pass
            os.chmod(log_file, 0o666)  # rw-rw-rw-
            
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

# Create default logger for the application
logger = setup_logger('arch')


