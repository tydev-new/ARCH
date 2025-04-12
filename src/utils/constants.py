"""Constants used across the Tardis codebase."""

import os

# Installation paths and configuration
CONFIG_DIR = "/etc/tardis"
CONFIG_PATH = os.path.join(CONFIG_DIR, "tardis.env")
STATE_DIR = "/var/lib/tardis/state"
DEFAULT_CHECKPOINT_PATH = "/var/lib/tardis/checkpoint"

# Environment variables
ENV_REAL_RUNC_CMD = "TARDIS_REAL_RUNC_CMD"
# TODO: Used for container config validation to determine if container is Tardis-enabled
ENV_TARDIS_ENABLE = "TARDIS_ENABLE"

# Runc command related
INTERCEPTABLE_COMMANDS = {'create', 'start', 'checkpoint', 'resume', 'delete'}

# Add this constant for the event listener PID file
EVENT_LISTENER_PID_FILE = "/var/lib/tardis/event_listener.pid"

# List of boolean flags for runc subcommands that don't take values
RUNC_SUBCMD_BOOLEAN_FLAGS = [
    # From runc-checkpoint
    "--leave-running", "--tcp-established", "--ext-unix-sk", 
    "--shell-job", "--lazy-pages", "--file-locks", 
    "--pre-dump", "--auto-dedup",
    # From runc-create
    "--no-pivot", "--no-new-keyring",
    # Global options
    "--debug", "--systemd-cgroup", "--help", "-h", "--version", "-v",
    # Other common flags
    "--detach",
    # Additional global options
    "--rootless",
    # Additional checkpoint options
    "--manage-cgroups-mode", "--empty-ns", "--status-fd", "--page-server"
]

# No need for SHORT_OPTION_MAP since we don't use bundle value for special handling 