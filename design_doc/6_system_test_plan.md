# ARCH System Test Plan

## 1. Introduction

This doc outlines the system-level test plan for ARCH (Automated Restore for Container Handler). The goal is to validate the functionality, performance, reliability, and interoperability of ARCH according to the design specifications.

The test plan covers the entire ARCH system, including:
- Checkpointing
- Restoring
- Migrating different container workloads
- CLI interfaces
- Integration with containerd and runc
- Interoperability with container orchestrators

### References
- Product Requirements Document (PRD)
- Engineering Requirements Document (ERD)
- Software Design Documents
- GitHub Repository: [GitHub - tydev-new/ARCH](https://github.com/tydev-new/ARCH)

## 2. Test Items

- RUNCShim (wrapper for runc OCI runtime, called by containerd)
- ARCH CLI
- Installer

## 3. Features to be Tested

### Tested Features
- Container Checkpoint Creation: Including both process and file state
- Container Restoration: Validate restoration from checkpoint images
- Enable checkpoint and shared filesystem: Using container environment variables
- Migration Across Nodes: Test moving containers between nodes using stored checkpoint data

### Not Tested
- The kernel-level CRIU (Checkpoint/Restore In Userspace) functionalities, which are indirectly tested through runc
- Performance benchmarking beyond basic functional validation
- Load testing
- User management or access control (not in initial scope)

## 4. Test Environment and Workload

### Hardware Requirements
- AWS t3.medium instance as reference
- Minimum 4GB RAM
- 20GB disk space for test images and checkpoints

### Software Requirements
- Amazon Linux 2023 (primary)
- CRIU v3.17 or above
- ARCH, runc, containerd properly installed
- Docker for container image creation

### Future Test Environments (TODO)
- RockyLinux
- Ubuntu

### Test Workload
- Simple counter app that shows timestamp and counter on stdout and write to file
- Multiple implementations (shell script, Python, C/C++)
- Various container base images (Ubuntu, RockyLinux, etc)

## 5. Test Cases

### General Steps
1. Create docker container image with test counter app
2. Load container image using containerd cli - `ctr image import`
3. Start container using containerd cli - `ctr run`
4. Checkpoint container using containerd cli - `ctr container checkpoint`
5. Cleanup container using containerd cli - `ctr task rm` and `ctr container rm`
6. Re-start container again using containerd cli - `ctr run`

### Expected Result
For container started with environment variable `ARCH_ENABLED = yes`, the counter app output file should show continued count, with a gap in the timestamp that matches checkpoint and restart.

The output file is located in container rootfs. While the container is running, it can be accessed from the host under `/usr/lib/containerd/io.xxxxx/[namespace]/[container_id]` using sudo. 

For container started with environment variable `ARCH_SHAREDFS_HOST_PATH = [path]`, the output file is directly accessible from host under host path.

### Test with Different Workloads
- Create and run with docker container image with test counter app written in Python
- Create and run with docker container image with test counter app written in C
- Create and run with docker container image with test counter app written in shell script

### Test with Different Environment Variable Settings
- `ARCH_ENABLED = yes / no`
- `ARCH_CHECKPOINT_HOST_PATH`
- `ARCH_SHAREDFS_HOST_PATH`

## 6. Future Test Cases (TODO)

### Error Scenarios
- Failed checkpoints due to insufficient disk space
- Network interruptions during checkpoint/restore
- Invalid checkpoint image handling
- Container crash during checkpoint

### Concurrent Operations
- Multiple containers checkpoint/restore simultaneously
- Resource contention scenarios
- Network bandwidth sharing

### Container Resource Limits
- CPU limits
- Memory limits
- Disk I/O limits

### Environment Variables
- Invalid/edge case values
- Variable interactions
- Missing required variables

## 7. Test Data Collection and Reporting

### Test Execution Logs
- Container start/stop times
- Checkpoint/restore durations
- Error messages and stack traces
- System resource usage during operations

### Test Results
- Pass/fail status for each test case
- Detailed error descriptions
- System configuration details
- Test environment information

### Reporting Format
- Test case ID
- Test description
- Expected result
- Actual result
- Error details (if any)
- System logs reference
- Test environment details