import logging
import os
import sys
from typing import Optional

def setup_logger(name: str, level: Optional[int] = None, log_file: Optional[str] = None) -> logging.Logger:
    """
    Set up a logger with consistent formatting and configuration.
    
    Args:
        name: Name of the logger
        level: Optional logging level. Defaults to INFO if not specified.
        log_file: Optional path to log file. If not specified, logs only to console.
    
    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger(name)
    
    if level is None:
        level = os.environ.get('TARDIS_LOG_LEVEL', 'INFO').upper()
        level = getattr(logging, level, logging.INFO)
    
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
        # Create log directory if it doesn't exist
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
            os.chmod(log_dir, 0o666)  # rw-rw-rw-
            
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
logger = setup_logger('tardis', log_file='logs/tardis.log')

# Remove duplicate logger creation
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
# )
# logger = logging.getLogger('tardis')
