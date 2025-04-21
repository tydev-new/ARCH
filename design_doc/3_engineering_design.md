# ARCH Technical Design

## Architecture Overview

ARCH acts as a wrapper between Containerd and Runc, intercepting Runc commands, processing them, and calling the real Runc with modified commands when necessary. The architecture consists of the following components:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Containerd │────▶│    ARCH     │────▶│    Runc     │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │ Checkpoint  │
                    │   Handler   │
                    └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Container  │
                    │   Handler   │
                    └─────────────┘
```

## Component Breakdown

### 1. ARCH Wrapper

The main component that intercepts Runc commands from Containerd.

**Responsibilities**:
- Parse and validate Runc commands
- Determine if a container is ARCH-enabled
- Route commands to appropriate handlers
- Call the real Runc with modified commands when necessary

**Key Classes**:
- `RuncHandler`: Main entry point for command processing
- `RuncCommandParser`: Parses Runc commands into structured data

### 2. Checkpoint Handler

Manages checkpoint and restore operations.

**Responsibilities**:
- Determine checkpoint image path
- Validate checkpoint images
- Copy container files to/from checkpoint images
- Manage checkpoint metadata

**Key Classes**:
- `CheckpointHandler`: Manages checkpoint and restore operations
- `CheckpointValidator`: Validates checkpoint images

### 3. Container Handler

Manages container configuration and state.

**Responsibilities**:
- Read and modify container configuration
- Track container state
- Manage container files
- Handle container lifecycle events

**Key Classes**:
- `ContainerConfigHandler`: Reads and validates container configuration, manages bind mounts
- `ContainerRuntimeState`: Tracks container state and manages runc binary interactions
- `FlagManager`: Handles container flags and settings
- `FilesystemHandler`: Manages container filesystem operations

## Data Flows

### Checkpoint Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Containerd │────▶│    ARCH     │────▶│ Checkpoint  │
│             │     │             │     │   Handler   │
└─────────────┘     └─────────────┘     └─────────────┘
                           │                    │
                           │                    │
                           ▼                    ▼
                    ┌─────────────┐     ┌─────────────┐
                    │  Container  │     │    Runc     │
                    │   Handler   │────▶│             │
                    └─────────────┘     └─────────────┘
```

1. Containerd sends a checkpoint command to ARCH
2. ARCH parses the command and determines if the container is ARCH-enabled
3. If enabled, ARCH calls the Checkpoint Handler
4. Checkpoint Handler determines the checkpoint image path
5. Checkpoint Handler copies container files to the checkpoint image
6. Checkpoint Handler calls Runc with modified checkpoint command
7. Runc performs the checkpoint operation
8. Checkpoint Handler updates container state

### Restore Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Containerd │────▶│    ARCH     │────▶│ Checkpoint  │
│             │     │             │     │   Handler   │
└─────────────┘     └─────────────┘     └─────────────┘
                           │                    │
                           │                    │
                           ▼                    ▼
                    ┌─────────────┐     ┌─────────────┐
                    │  Container  │     │    Runc     │
                    │   Handler   │◀────│             │
                    └─────────────┘     └─────────────┘
```

1. Containerd sends a create command to ARCH
2. ARCH parses the command and determines if the container is ARCH-enabled
3. If enabled, ARCH checks if a checkpoint image exists
4. If a checkpoint image exists, ARCH calls the Checkpoint Handler
5. Checkpoint Handler validates the checkpoint image
6. Checkpoint Handler copies files from the checkpoint image to the container
7. Checkpoint Handler calls Runc with a restore command instead of create
8. Runc performs the restore operation
9. Checkpoint Handler updates container state

## Error Handling and Recovery

### Checkpoint Failures

1. If checkpoint fails, ARCH logs the error and allows Containerd to proceed with the next command
2. No automatic retry is implemented
3. The container continues running as normal

### Restore Failures

1. If restore fails, ARCH rolls back changes to the container
2. ARCH calls Runc with the original create command
3. The container is created from scratch

### Data Consistency

1. Runc guarantees process consistency during checkpoint
2. Processes are paused during checkpoint, ensuring file consistency
3. Checkpoint images are validated before restore

## Security Considerations

1. ARCH assumes it runs within a secure private network or VPN
2. No additional security measures are implemented in the initial release
3. Access control and encryption will be addressed in future releases

## Performance Considerations

1. No specific performance requirements for the initial release
2. Designed to support up to 200 concurrent containers per host
3. Performance optimizations will be addressed in future releases

## Integration with AWS Services

### ECS Integration

1. ARCH is installed via userdata or AMI
2. Environment variables are configured in task definitions
3. No additional parameters beyond environment variables

### AWS Batch Integration

1. ARCH is installed via userdata or AMI
2. Environment variables are configured in job definitions
3. No additional parameters beyond environment variables

## Limitations

1. No support for container dependencies in the initial release
2. Only one checkpoint per container before termination
3. No support for GPU workloads
4. No support for EBS volumes in the initial release 