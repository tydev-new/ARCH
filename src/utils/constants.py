"""Constants used across the Tardis codebase."""

import os

# Installation paths and configuration
CONFIG_DIR = "/etc/tardis"
CONFIG_PATH = os.path.join(CONFIG_DIR, "tardis.env")
STATE_DIR = "/var/lib/tardis/state"

# Environment variables
ENV_REAL_RUNC_CMD = "TARDIS_REAL_RUNC_CMD"
# TODO: Used for container config validation to determine if container is Tardis-enabled
ENV_TARDIS_ENABLE = "TARDIS_ENABLE"

# Runc command related
INTERCEPTABLE_COMMANDS = {'create', 'start', 'checkpoint', 'restore', 'delete'} 