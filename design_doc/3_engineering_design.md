# ARCH Technical Design

## Architecture Overview

ARCH acts as a shim between Containerd and Runc, intercepting Runc commands, processing them, and calling the real Runc with modified commands when necessary. The architecture consists of the following components:

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Containerd │────▶│ ARCH shim    │────▶│    Runc     │
└─────────────┘     └──────────────┘     └─────────────┘
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

### 1. ARCH shim

The main component that intercepts Runc commands from Containerd.

**Responsibilities**:
- Parse and validate Runc commands
- Determine if a container is ARCH-enabled
- Route commands to appropriate handlers
- Call the real Runc with modified commands when necessary
- Preserve container ID and namespace information in checkpoint paths

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
- Manage file system checkpointing using tar format

**Key Classes**:
- `CheckpointHandler`: Manages checkpoint and restore operations
- `CheckpointValidator`: Validates checkpoint images

**Checkpoint Image Format**:
- Process state: CRIU native format
- Filesystem: Standard tar format
- Metadata: JSON format for container configuration

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
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Containerd │────▶│ ARCH shim    │────▶│ Checkpoint  │
│             │     │             │     │   Handler   │
└─────────────┘     └──────────────┘     └─────────────┘
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

6. Checkpoint Handler copies container files to the checkpoint image using tar
7. Checkpoint Handler calls Runc with modified checkpoint command
8. Runc (integrated CRIU) performs the checkpoint operation
9. Checkpoint Handler updates container state

### Restore Flow

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
4. Failed checkpoint images are automatically cleaned up from the filesystem
5. Cleanup includes removing partial checkpoint data and temporary files

### Restore Failures

1. If restore fails, ARCH rolls back changes to the container
2. ARCH calls Runc with the original create command
3. The container is created from scratch
4. Failed restore attempts are logged with detailed error information
5. No cleanup required as container is not yet running

### Data Consistency

1. Runc guarantees process consistency during checkpoint
2. Processes are paused during checkpoint, ensuring file consistency
3. Checkpoint images are validated before restore
4. Container ID and namespace information is preserved in checkpoint path structure
5. Path structure: `/checkpoint/{namespace}/{container_id}/`

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

## Technical Considerations

### CRIU Integration

1. ARCH leverages CRIU through Runc's interface
2. CRIU configuration and parameters are managed through Runc's checkpoint/restore options
3. ARCH modifies these options as needed for specific use cases
4. All CRIU limitations apply to ARCH:
   - Memory limits and constraints
   - Network socket handling
   - Process state preservation
5. Applications should implement network connection retry mechanisms

### Checkpoint Image Format

1. Single directory-based image format
2. Path structure: `/checkpoint/{namespace}/{container_id}/`
3. Contains:
   - CRIU process state files
   - Filesystem tar archives
   - Container configuration metadata

### Error Handling

1. CRIU errors are exposed through Runc's return codes and exceptions
2. ARCH logs all CRIU-related errors with appropriate context
3. Error handling follows the general recovery patterns:
   - Failed checkpoints: Clean up partial data, continue container operation
   - Failed restores: Roll back changes, attempt fresh container creation
4. Detailed error logging includes:
   - CRIU operation type (checkpoint/restore)
   - Container context
   - Runc error codes
   - CRIU-specific error messages
