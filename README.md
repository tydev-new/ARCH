# 🚀 ARCH - Automated Restore for Container Handler

ARCH enables automated container checkpoint-and-restore. With ARCH, containers can seamlessly migrate across nodes and time. It allows containers to survive spot instance reclaims, pause during peak hours, and restore without losing progress. 

In practical terms, 
- For cloud users, they can safely run containerized batch workload on spot instances, with cost savings up to 90% on cloud compute resources *
- For on-prem users, they can significantly improve resource utilization and scheduled completion time for long-running batch workload

Furthermore, ARCH requires no modifications to existing applications and workflow.

*Note: To build a complete system, additional components customized for each cloud provider (AWS, GCP, Azure) are required.

## 🧠 Why ARCH?

### The Problem
Container checkpoint-and-restore is a powerful capability, but existing solutions have significant limitations:

1. **Incomplete State Preservation**
   - CRIU checkpoints application processes and memory state
   - However, it doesn't handle file system state synchronization
   - This creates inconsistencies when restoring containers

2. **Manual Operations Required**
   - Runc CLI requires manual checkpoint/restore commands
   - Containerd CLI lacks automated checkpoint image management
   - No built-in support for automated migration

3. **Production Readiness Gaps**
   - No integrated solution for file system state management
   - Limited automation for container lifecycle events
   - Complex configuration for production deployments

### The ARCH Solution
ARCH bridges these gaps by providing a complete solution for container checkpoint-and-restore:

1. **Complete State Management**
   - Automated container checkpoint and restore
   - Synchronized process and file system state preservation
   - Multiple storage backend support (local and shared filesystems)

2. **Production-Ready Features**
   - Minimal configuration required
   - No modifications needed to applications, container images, or orchestrators
   - Seamless integration with existing container ecosystems

3. **Enterprise-Grade Reliability**
   - Automated container lifecycle management
   - Robust error handling and recovery
   - Comprehensive logging and monitoring

In addition, ARCH serves as an exploration of how AI can enhance infrastructure software development - more details to follow.

## 🧪 Usage 

ARCH is written in Python, and currently supports container run times. Containerd and Runc, by providing a shim layer between the two. Any higher level container orchestrators are also supported, such as Docker, Kubernetes, and AWS ECS.

Support for Apptainer / Singularity is planned.

## 🛠️ Installation

ARCH requires the following dependencies:
- Python ([python/cpython](https://github.com/python/cpython)) - Python 3.8 or later
- Container runtime: Containerd ([containerd/containerd](https://github.com/containerd/containerd)) 
- OCI container runtime: Runc ([opencontainers/runc](https://github.com/opencontainers/runc)) 
- Process checkpoint/restore: CRIU ([checkpoint-restore/criu](https://github.com/checkpoint-restore/criu))
- CPU Architecture: x86_64, ARM64
- Operating System: Linux (kernel 4.15 or later)

### Full Installation
1. Clone the repository (recommended for full access to all features):
```bash
git clone https://github.com/tydev-new/ARCH.git
cd ARCH
# Run installer
sudo python3 install.py
```

### Minimal Installation
For users who only need the core functionality:

```bash
# Download and extract via CLI 
curl -L -o ARCH.zip https://github.com/tydev-new/ARCH/archive/refs/heads/main.zip
# Extract only the src folder and install.py
unzip ARCH.zip "ARCH-main/src/*" "ARCH-main/install.py"
mv ARCH-main/src ARCH-main/install.py ./
rm -rf ARCH-main ARCH.zip

# Run installer
sudo python3 install.py
```

## 🛠️ Operations
ARCH has two entrypoints:
- `main.py`: The shim layer between Containerd and Runc, it automatically restores containers from checkpoint images. It's configured by the installer - no additional action required.
- `arch-cli`: Command to checkpoint all ARCH-enabled containers on the node. This should be invoked upon receiving spot instance reclaim warnings. Example usage:
  ```bash
  # When spot reclaim warning is received
  cd ARCH
  ./arch-cli container finalize
  ```

  Logging can be configured using:
  ```bash
  # Set log level (default: WARNING)
  ./arch-cli log --level DEBUG
  
  # Set log file path
  ./arch-cli log --file /path/to/log
  
  # Both at once
  ./arch-cli log --level INFO --file /path/to/log
  ```

  Logging configuration is stored in `/var/tmp/arch/arch.env` and will be picked up by both `arch-cli` and `main.py`.

ARCH has two modes of operations, controlled by setting the containerized workload's environment variables.

### 1. Local Filesystem Mode
This mode is useful for small workloads and testing purposes. ARCH checkpoints the container workload and saves the image into a user-specified path. The checkpoint includes the process and all writable files in the container.

The user is responsible for managing the checkpoint image lifecycle, such as moving it to the new instance before restore.

To use this mode, add the following environment variables to your container:
```bash
ARCH_ENABLE=1
ARCH_CHECKPOINT_HOST_PATH=/your/path/for/checkpoint/images
```

The checkpoint image is stored under `ARCH_CHECKPOINT_HOST_PATH/namespace/container_id`.

### 2. Shared Filesystem Mode
This mode is useful for medium workloads, where migrating files has high overhead. In addition to checkpointing process and files, ARCH also mounts a user-specified container path (destination) to a shared filesystem path on the host (source), and sets it as the current working directory.

The shared filesystem must be accessible from multiple nodes. Supported options include:
- Network filesystems (e.g., AWS EFS)
- FUSE-backed filesystems using cloud object storage:
  - JuiceFS (recommended for AWS)
  - S3FS
  - Other S3-compatible object storage solutions

The user is responsible for managing the lifecycle of the shared filesystem.

To use this mode, add the following environment variables to your container:
```bash
ARCH_ENABLE=1
ARCH_SHAREDFS_HOST_PATH=/your/path/for/shared_fs/mount/on/host
ARCH_WORKDIR_CONTAINER_PATH=/your/path/for/work_dir/inside/container
```

If `ARCH_SHAREDFS_HOST_PATH` is specified, ARCH ignores the `ARCH_CHECKPOINT_HOST_PATH` setting. The checkpoint image is stored under `ARCH_SHAREDFS_HOST_PATH/checkpoint/namespace/container_id`, while application files are stored under 'ARCH_SHAREDFS_HOST_PATH/work/namespace/container_id`


## 📦 Project Structure

```
ARCH/
├── src/                      # Source code
│   ├── container_handler/    # Container management components
│   ├── utils/               # Helper utilities
│   ├── arch_cli.py          # Command-line interface
│   ├── main.py              # Main shim entry point
│   ├── checkpoint_handler.py # Checkpoint/restore logic
│   ├── runc_handler.py      # runC shim implementation
│   └── runc_command_parser.py # runC command parsing
├── tests/                    # Test suite
│   ├── unit/                # Unit tests
│   ├── system-auto/         # Automated system tests
│   ├── system-manual/       # Manual system tests
│   └── resource/            # Test resources
├── design_doc/              # Architecture and design documentation
├── install.py               # Installation script
└── arch-cli                 # CLI entry point
```

The detailed ARCH design can be found under `design_doc/`.

## 🔓 License & Status

- 📦 Project Stage: Alpha
- 🔐 License: Apache 2.0
- 🔗 GitHub: https://github.com/tydev-new/ARCH
- ✅ Status: All unit and system tests passing, ready for user testing

## 🌌 What's Next?

ARCH is part of a broader initiative to explore:
- Batch job orchestration
- AI-powered infrastructure tooling
- Serverless stateful computing
- Intelligent DevOps workflows

## 🤝 Contributing

We welcome contributions! Please:
1. Try it out
2. Report issues
3. Submit pull requests
4. Share feedback

## 📝 License

Copyright 2025 Yong Tian and ARCH Contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
