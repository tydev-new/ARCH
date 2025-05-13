"""Constants used across the ARCH codebase."""

import os

# Configuration paths
USER_CONFIG_PATH = "/var/tmp/arch"
CONFIG_PATH = os.path.join(USER_CONFIG_PATH, "arch.env")
STATE_PATH = os.path.join(USER_CONFIG_PATH, "state")
DEFAULT_CHECKPOINT_PATH = os.path.join(USER_CONFIG_PATH, "checkpoint")

# Environment variables
ENV_REAL_RUNC_CMD = "ARCH_REAL_RUNC_CMD"

# Runc command related
INTERCEPTABLE_COMMANDS = {'create', 'start', 'delete', 'checkpoint', 'resume'}

# List of boolean flags for runc subcommands that don't take values
RUNC_SUBCMD_BOOLEAN_FLAGS = [
    # From runc-checkpoint
    "--leave-running", "--tcp-established", "--ext-unix-sk", 
    "--shell-job", "--lazy-pages", "--file-locks", 
    "--pre-dump", "--auto-dedup",
    # From runc-create
    "--no-pivot", "--no-new-keyring",
    # From runc-delete
    "--force",
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

# Container config paths
CONTAINER_CONFIG_PATHS = [
    "/run/containerd/io.containerd.runtime.v2.task/{namespace}/{container_id}/config.json",
    "/run/containerd/runc/{namespace}/{container_id}/config.json",
    "/run/runc/{namespace}/{container_id}/config.json"
] 

CONTAINER_ROOTFS_PATHS = [
    "/run/containerd/io.containerd.runtime.v2.task/{namespace}/{container_id}/rootfs",
    "/run/containerd/runc/{namespace}/{container_id}/rootfs",
    "/run/runc/{namespace}/{container_id}/rootfs"
] 

# Logging
LOG_FILE = "logs/arch.log"
DEFAULT_LOG_LEVEL = "WARNING"
