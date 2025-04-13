#!/usr/bin/env python3
import sys
from src.runc_handler import RuncHandler
from src.utils.logging import logger

def main():
    """
    Main entry point for Tardis Runc wrapper.
    Intercepts and handles Runc commands.
    """
    try:
        logger.info("Tardis starting, intercepting command: %s", " ".join(sys.argv))
        handler = RuncHandler()
        logger.info("RuncHandler initialized, processing command")
        exit_code = handler.intercept_command(sys.argv)
        logger.info("Command processing completed with exit code: %d", exit_code)
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
