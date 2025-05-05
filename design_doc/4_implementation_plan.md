# ARCH Implementation Plan

## Overview

This document outlines the implementation plan for ARCH, including detailed task breakdown, milestones, testing strategy, and documentation requirements. The plan is divided into phases based on the implementation priorities identified in the requirements review.

## Project Setup

- Project root folder: `/home/ec2-user/new-arch`
- Logging will be implemented from the beginning as it's essential for debugging

## Engineering Task Breakdown

### 1. ARCH Shim Implementation

#### Command Interception
- Create a mechanism to intercept Runc commands from Containerd
- Implement binary replacement or path manipulation approach
- Ensure proper error handling for interception failures

#### Command Parsing
- Implement parsing of Runc command structure
- Extract subcommand, namespace, container_id, global options, and subcommand options
- Handle different command formats and variations

#### Container Configuration Validation
- Implement logic to check if a container is ARCH-enabled
- Parse container config.json to check for ARCH_ENABLE environment variable
- Handle different config.json locations and formats

#### Command Routing
- Implement logic to route commands to appropriate handlers
- Process specific subcommands: create, start, checkpoint, resume, delete
- Pass through other subcommands to the real Runc

#### Command Modification
- Implement logic to modify Runc commands when necessary
- Convert create commands to restore commands for ARCH-enabled containers
- Modify checkpoint commands to include appropriate options

### 2. Checkpoint Handler Implementation

#### Checkpoint Image Path Determination
- Implement logic to determine checkpoint image path based on environment variables
- Handle different implementation modes (Basic, Network FS)
- Create subfolders with namespace and container_id

#### Checkpoint Image Validation
- Implement validation of checkpoint images
- Check for dump.log and verify successful completion
- Handle validation failures gracefully

#### File Copying
- Implement copying of container files to checkpoint images
- Use tar for compression
- Handle large files and directories efficiently

#### Checkpoint Metadata Management
- Implement tracking of checkpoint metadata
- Store information about checkpoint timing and status
- Handle metadata updates and cleanup

### 3. Container Handler Implementation

#### Container Configuration Reading
- Implement reading of container configuration from config.json
- Extract environment variables and settings
- Handle different config.json formats and locations

#### Container State Tracking
- Implement tracking of container state
- Monitor container lifecycle events
- Track exit codes using ctr events

#### Container File Management
- Implement management of container files
- Handle upperdir files for overlay filesystem
- Manage file copying and cleanup

#### Container Lifecycle Event Handling
- Implement handling of container lifecycle events
- Process create, start, checkpoint, resume, and delete events
- Update container state based on events

### 4. Basic Monitoring

#### Logging
- Implement comprehensive logging from the beginning
- Log intercepted and modified commands
- Log errors and important events

#### Error Handling
- Implement graceful error handling
- Log errors with appropriate context
- Allow Containerd to proceed when possible

#### Basic Metrics Collection
- Implement collection of basic metrics
- Track number of checkpoints and restores
- Monitor success and failure rates

## Implementation Timeline

### Phase 1: Basic Functionality (Days 1-3)

#### Day 1: ARCH Wrapper Implementation and Logging
- Implement logging framework
- Implement command interception
- Implement command parsing
- Implement container configuration validation

#### Day 2: Checkpoint Handler Implementation
- Implement checkpoint image path determination
- Implement checkpoint image validation
- Implement file copying

#### Day 3: Container Handler and Basic Monitoring
- Implement container state tracking
- Implement container file management
- Implement error handling and basic metrics collection

### Phase 2: Enhanced Features (Days 4-7)

#### Day 4: AWS Integration
- Implement ECS integration
- Implement AWS Batch integration

#### Day 5-6: Performance Improvements
- Optimize file copying
- Optimize checkpoint image validation
- Optimize container state tracking

#### Day 7: Extended Monitoring
- Implement CloudWatch logging integration
- Implement advanced metrics collection

### Documentation (Days 1-7)

- Create user guide with installation instructions and environment variable configuration
- Create API documentation for command-line interface and environment variables
- Create deployment guides for ECS, AWS Batch, and on-premises
- Create example configurations for simple counter app container

## Milestones

1. **Logging and Command Parsing Complete** (Day 1)
   - Logging framework is implemented
   - Runc commands are correctly parsed
   - Container configuration is correctly validated
   - Commands are correctly routed

2. **Checkpoint/Restore Complete** (Day 2-3)
   - Checkpoint images are correctly created
   - Checkpoint images are correctly validated
   - Containers are correctly restored from checkpoint images

3. **Basic Monitoring Complete** (Day 3)
   - Error handling is implemented
   - Basic metrics are collected

4. **AWS Integration Complete** (Day 4)
   - ECS integration is implemented
   - AWS Batch integration is implemented
   - CloudWatch logging integration is implemented

5. **Performance Improvements Complete** (Day 5-6)
   - File copying is optimized
   - Checkpoint image validation is optimized
   - Container state tracking is optimized

6. **Extended Monitoring Complete** (Day 7)
   - DynamoDB metrics storage is implemented
   - AWS-managed Grafana integration is implemented
   - Advanced metrics collection is implemented

## Testing Strategy

### Unit Testing
- Test each component in isolation
- Mock dependencies for controlled testing
- Focus on edge cases and error conditions

### Integration Testing
- Test interactions between components
- Test with simple containers
- Verify checkpoint and restore functionality

### System Testing
- Test with multiple concurrent containers
- Test on different container runtimes and Linux distributions
- Verify performance and scalability

## Risk Management

### Compatibility Risks
- Test on all supported container runtimes and Linux distributions
- Implement fallback mechanisms for unsupported configurations

### Performance Risks
- Monitor performance impact during development
- Implement optimizations for performance-critical components

### Integration Risks
- Test integration with AWS services thoroughly
- Implement graceful degradation for integration failures

### Documentation Risks
- Review documentation with users
- Provide additional support for complex configurations

## Technical Dependencies

### External Dependencies
- Containerd
- Runc
- Python 3.6+
- tar
- subprocess
- json
- re
- os
- sys
- logging

### Internal Dependencies
- RuncHandler depends on RuncCommandParser
- CheckpointHandler depends on ContainerHandler
- ContainerHandler depends on ContainerConfigHandler and ContainerStateManager

## Code Structure

```
/home/ec2-user/new-arch/
├── __init__.py
├── main.py                  # Entry point
├── runc_handler.py          # Main Runc command handler
├── runc_command_parser.py   # Runc command parsing
├── checkpoint_handler.py    # Checkpoint and restore operations
├── container_handler.py     # Container configuration and state
│   ├── config_handler.py    # Container configuration
│   ├── state_manager.py     # Container state tracking
│   └── file_handler.py      # Container file management
├── utils/
│   ├── logging.py           # Logging utilities
│   ├── file_utils.py        # File operation utilities
│   └── command_utils.py     # Command execution utilities
└── tests/
    ├── unit/                # Unit tests
    ├── integration/         # Integration tests
    └── system/              # System tests
```

## Conclusion

This implementation plan provides a comprehensive roadmap for developing ARCH, with detailed task breakdown, clear milestones, and testing strategy. By following this plan, we can ensure that ARCH meets the requirements and delivers value to users. 
