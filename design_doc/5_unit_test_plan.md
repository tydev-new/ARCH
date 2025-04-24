# ARCH Unit Test Plan

## 1. Test Coverage Requirements

### 1.1 Code Coverage
- Minimum 80% line coverage
- 100% coverage of public methods
- Critical path coverage

### 1.2 Test Categories
- Happy path tests
- Error handling tests
- Edge cases
- Resource cleanup

## 2. Test Environment and Execution

### 2.1 Prerequisites
- Python 3.8+
- pytest
- mock
- Test directories created

### 2.2 Test Data
- Sample container config
- Test files and directories
- Checkpoint images
- Log files

### 2.3 Test Execution
```bash
python3 -m pytest tests/unit/ -v
```

## 3. Unit Tests

### 3.1 RuncHandler Tests
- **Command Interception**
  - Test non-interceptable commands
    - Input: `["runc", "list"]`
    - Mock Returns:
      - is_arch_enabled: `False`
      - os.execvp: raises Exception
    - Expected Output: `1` (exec failed)
    - Assertions:
      - execvp called with original runc command
      - flag file not created

  - Test non-ARCH enabled containers
    - Input: `["runc", "create", "container1"]`
    - Mock Returns:
      - is_arch_enabled: `False`
      - os.execvp: raises Exception
    - Expected Output: `1` (exec failed)
    - Assertions:
      - execvp called with original runc command
      - flag file not created

  - Test create command with checkpoint
    - Input: `["runc", "create", "--bundle", "/path/to/bundle", "container1"]`
    - Mock Returns:
      - is_arch_enabled: `True`
      - get_checkpoint_path: `"/path/to/checkpoint"`
      - validate_checkpoint: `True`
      - get_upperdir: `"/path/to/upperdir"`
      - restore_checkpoint_file: `True`
      - os.execvp: raises Exception
    - Expected Output: `0` (success)
    - Assertions:
      - execvp called with modified command:
        - subcommand changed from `create` to `restore`
        - `--detach` option added
        - `--image-path` set to `/path/to/checkpoint`
        - other options preserved
      - skip_start flag set to True
      - flag file created

  - Test create command without checkpoint
    - Input: `["runc", "create", "--bundle", "/path/to/bundle", "container1"]`
    - Mock Returns:
      - is_arch_enabled: `True`
      - get_checkpoint_path: `None`
      - os.execvp: raises Exception
    - Expected Output: `1` (exec failed)
    - Assertions:
      - execvp called with original create command
      - flag file created

  - Test checkpoint command with options
    - Input: `["runc", "checkpoint", "--work-path", "/tmp/work", "--leave-running", "--image-path", "/old/path", "container1"]`
    - Mock Returns:
      - is_arch_enabled: `True`
      - get_checkpoint_path: `"/path/to/checkpoint"`
      - get_upperdir: `"/path/to/upperdir"`
      - save_checkpoint_file: `True`
      - os.execvp: raises Exception
    - Expected Output: `1` (exec failed)
    - Assertions:
      - execvp called with modified command:
        - `--work-path` and `--leave-running` removed
        - `--image-path` value replaced with `/path/to/checkpoint`
      - skip_resume flag set to True
      - keep_resources flag set to True

  - Test start command with skip flag
    - Input: `["runc", "start", "container1"]`
    - Mock Returns:
      - is_arch_enabled: `True`
      - get_skip_start: `True`
      - os.execvp: raises Exception
    - Expected Output: `0` (success)
    - Assertions:
      - skip_start flag cleared
      - execvp not called

  - Test resume command with skip flag
    - Input: `["runc", "resume", "container1"]`
    - Mock Returns:
      - is_arch_enabled: `True`
      - get_skip_resume: `True`
      - os.execvp: raises Exception
    - Expected Output: `0` (success)
    - Assertions:
      - skip_resume flag cleared
      - execvp not called

  - Test delete command with successful exit
    - Input: `["runc", "delete", "container1"]`
    - Mock Returns:
      - is_arch_enabled: `True`
      - get_exit_code: `0`
      - get_keep_resources: `False`
      - os.execvp: raises Exception
    - Expected Output: `1` (exec failed)
    - Assertions:
      - cleanup_checkpoint called with checkpoint path
      - flag cleared via flag_manager
      - execvp called with original runc command

  - Test delete command with failed exit
    - Input: `["runc", "delete", "container1"]`
    - Mock Returns:
      - is_arch_enabled: `True`
      - get_exit_code: `1`
      - os.execvp: raises Exception
    - Expected Output: `1` (exec failed)
    - Assertions:
      - cleanup_checkpoint not called
      - flag not cleared
      - execvp called with original runc command

  - Test delete command with no exit code
    - Input: `["runc", "delete", "container1"]`
    - Mock Returns:
      - is_arch_enabled: `True`
      - get_exit_code: `None`
      - os.execvp: raises Exception
    - Expected Output: `1` (exec failed)
    - Assertions:
      - cleanup_checkpoint not called
      - flag not cleared
      - execvp called with original runc command

  - Test delete command with keep_resources flag
    - Input: `["runc", "delete", "container1"]`
    - Mock Returns:
      - is_arch_enabled: `True`
      - get_exit_code: `0`
      - get_keep_resources: `True`
      - os.execvp: raises Exception
    - Expected Output: `1` (exec failed)
    - Assertions:
      - cleanup_checkpoint not called
      - flag cleared via flag_manager
      - execvp called with original runc command

  - Test error handling
    - Input: `["runc", "invalid", "command"]`
    - Expected Output: `1` (error)
    - Assertions:
      - error logged with message
      - execvp not called
      - flag file not created

  - Test command options
    - Test create with bundle path
      - Input: `["runc", "--root", "/var/run/runc", "create", "--bundle", "/path/to/bundle", "container1"]`
      - Mock Returns:
        - is_arch_enabled: `True`
        - get_checkpoint_path: `None`
        - os.execvp: raises Exception
      - Expected Output: `1` (exec failed)
      - Assertions:
        - execvp called with bundle option
        - state created

    - Test checkpoint with work path
      - Input: `["runc", "checkpoint", "--work-path", "/tmp/work", "container1"]`
      - Mock Returns:
        - is_arch_enabled: `True`
        - get_checkpoint_path: `"/path/to/checkpoint"`
        - os.execvp: raises Exception
      - Expected Output: `1` (exec failed)
      - Assertions:
        - execvp called with modified command:
          - `--work-path` removed
          - `--image-path` value replaced with `/path/to/checkpoint`

    - Test start with detach
      - Input: `["runc", "start", "--detach", "container1"]`
      - Mock Returns:
        - is_arch_enabled: `True`
        - get_skip_start: `True`
        - os.execvp: raises Exception
      - Expected Output: `0` (success)
      - Assertions:
        - skip_start flag cleared
        - execvp not called

  - Test flag management
    - Test create flag
      - Input: `["runc", "create", "--arch-create", "container1"]`
      - Mock Returns:
        - is_arch_enabled: `True`
        - os.execvp: raises Exception
      - Expected Output: `1` (exec failed)
      - Assertions:
        - execvp called with create command
        - state created

    - Test delete flag
      - Input: `["runc", "delete", "--arch-delete", "container1"]`
      - Mock Returns:
        - is_arch_enabled: `True`
        - os.execvp: raises Exception
      - Expected Output: `1` (exec failed)
      - Assertions:
        - execvp called with delete command
        - cleanup performed

### 3.2 ConfigHandler Tests
- **Container Configuration**
  - Test ARCH_ENABLE flag detection
    - Input: config.json with ARCH_ENABLE=1
    - Expected Output: `True`
    - Assertions:
      - is_arch_enabled returns True
      - flag file created

  - Test ARCH_ENABLE flag not present
    - Input: config.json without ARCH_ENABLE
    - Expected Output: `False`
    - Assertions:
      - is_arch_enabled returns False
      - flag file not created

  - Test invalid config
    - Input: invalid JSON in config.json
    - Expected Output: `False`
    - Assertions:
      - is_arch_enabled returns False
      - error logged

  - Test checkpoint path resolution
    - Test networkfs path
      - Input: config.json with ARCH_NETWORKFS_HOST_PATH=/path/to/networkfs
      - Expected Output: `/path/to/networkfs/checkpoint/namespace/container_id`
      - Assertions:
        - get_checkpoint_path returns correct path

    - Test host path
      - Input: config.json with ARCH_CHECKPOINT_HOST_PATH=/path/to/checkpoint
      - Expected Output: `/path/to/checkpoint/namespace/container_id`
      - Assertions:
        - get_checkpoint_path returns correct path

    - Test default path
      - Input: config.json without path variables
      - Expected Output: `/var/lib/arch/checkpoint/namespace/container_id`
      - Assertions:
        - get_checkpoint_path returns default path

  - Test shared filesystem path resolution
    - Test with valid path
      - Input: config.json with ARCH_NETWORKFS_HOST_PATH=/path/to/networkfs
      - Expected Output: `/path/to/networkfs`
      - Assertions:
        - get_networkfs_path returns correct path

    - Test with invalid path
      - Input: config.json with ARCH_NETWORKFS_HOST_PATH=/nonexistent/path
      - Expected Output: `None`
      - Assertions:
        - get_networkfs_path returns None
        - error logged

  - Test environment variable parsing
    - Test required variables
      - Input: config.json with all required variables
      - Expected Output: All variables parsed correctly
      - Assertions:
        - get_env_vars returns all variables

    - Test optional variables
      - Input: config.json with only required variables
      - Expected Output: Required variables parsed, optional variables defaulted
      - Assertions:
        - get_env_vars returns required variables
        - optional variables have default values

  - Test config file validation
    - Test valid config
      - Input: valid config.json
      - Expected Output: Config loaded successfully
      - Assertions:
        - load_config returns config object

    - Test invalid JSON
      - Input: invalid JSON in config.json
      - Expected Output: `None`
      - Assertions:
        - load_config returns None
        - error logged

    - Test missing fields
      - Input: config.json with missing required fields
      - Expected Output: Config loaded with defaults
      - Assertions:
        - load_config returns config with defaults

  - Test bind mount operations
    - Test successful mount
      - Input: source_path and destination_path
      - Expected Output: `True`
      - Assertions:
        - add_bind_mount returns True
        - config.json updated with mount

    - Test no networkfs path
      - Input: source_path and destination_path, no networkfs path
      - Expected Output: `False`
      - Assertions:
        - add_bind_mount returns False
        - error logged

    - Test rootfs not found
      - Input: source_path and destination_path, rootfs not found
      - Expected Output: `False`
      - Assertions:
        - add_bind_mount returns False
        - error logged

    - Test destination not found
      - Input: source_path and destination_path, destination not found
      - Expected Output: `False`
      - Assertions:
        - add_bind_mount returns False
        - error logged

  - Test work directory management
    - Test successful deletion
      - Input: work_dir_path
      - Expected Output: `True`
      - Assertions:
        - delete_work_dir returns True
        - directory deleted

    - Test no networkfs path
      - Input: work_dir_path, no networkfs path
      - Expected Output: `False`
      - Assertions:
        - delete_work_dir returns False
        - error logged

    - Test directory not found
      - Input: nonexistent work_dir_path
      - Expected Output: `False`
      - Assertions:
        - delete_work_dir returns False
        - error logged

### 3.3 CheckpointHandler Tests
- **Checkpoint Operations**
  - Test checkpoint image creation
    - Test successful creation
      - Input: container_id, namespace, checkpoint_path
      - Expected Output: `True`
      - Assertions:
        - create_checkpoint_image returns True
        - image created at checkpoint_path

    - Test creation failure
      - Input: container_id, namespace, invalid checkpoint_path
      - Expected Output: `False`
      - Assertions:
        - create_checkpoint_image returns False
        - error logged

  - Test checkpoint validation
    - Test valid checkpoint
      - Input: checkpoint_path with valid dump.log
      - Expected Output: `True`
      - Assertions:
        - validate_checkpoint returns True

    - Test invalid checkpoint
      - Input: checkpoint_path with invalid dump.log
      - Expected Output: `False`
      - Assertions:
        - validate_checkpoint returns False
        - error logged

  - Test file copying
    - Test successful copy
      - Input: source_path, destination_path
      - Expected Output: `True`
      - Assertions:
        - copy_files returns True
        - files copied correctly

    - Test copy failure
      - Input: source_path, invalid destination_path
      - Expected Output: `False`
      - Assertions:
        - copy_files returns False
        - error logged

  - Test restore from checkpoint
    - Test successful restore
      - Input: container_id, namespace, checkpoint_path
      - Expected Output: `True`
      - Assertions:
        - restore_checkpoint_file returns True
        - files restored correctly

    - Test restore failure
      - Input: container_id, namespace, invalid checkpoint_path
      - Expected Output: `False`
      - Assertions:
        - restore_checkpoint_file returns False
        - error logged

  - Test cleanup on failure
    - Test cleanup success
      - Input: container_id, namespace, checkpoint_path
      - Expected Output: `True`
      - Assertions:
        - cleanup_checkpoint returns True
        - checkpoint files cleaned up

    - Test cleanup failure
      - Input: container_id, namespace, invalid checkpoint_path
      - Expected Output: `False`
      - Assertions:
        - cleanup_checkpoint returns False
        - error logged

### 3.4 FilesystemHandler Tests
- **File Operations**
  - Test upperdir management
    - Test successful get
      - Input: container_id, namespace
      - Expected Output: upperdir path
      - Assertions:
        - get_upperdir returns correct path

    - Test not found
      - Input: nonexistent container_id, namespace
      - Expected Output: `None`
      - Assertions:
        - get_upperdir returns None
        - error logged

  - Test bind mount operations
    - Test successful mount
      - Input: source_path, destination_path
      - Expected Output: `True`
      - Assertions:
        - add_bind_mount returns True
        - mount created correctly

    - Test mount failure
      - Input: source_path, invalid destination_path
      - Expected Output: `False`
      - Assertions:
        - add_bind_mount returns False
        - error logged

  - Test work directory management
    - Test successful creation
      - Input: work_dir_path
      - Expected Output: `True`
      - Assertions:
        - create_work_dir returns True
        - directory created correctly

    - Test creation failure
      - Input: invalid work_dir_path
      - Expected Output: `False`
      - Assertions:
        - create_work_dir returns False
        - error logged

  - Test cleanup operations
    - Test successful cleanup
      - Input: path to clean up
      - Expected Output: `True`
      - Assertions:
        - cleanup_path returns True
        - path cleaned up correctly

    - Test cleanup failure
      - Input: invalid path
      - Expected Output: `False`
      - Assertions:
        - cleanup_path returns False
        - error logged

### 3.5 Command Parser Tests
- **Command Parsing**
  - Test global options parsing
    - Test with options
      - Input: `["runc", "--root", "/var/run/runc", "create", "container1"]`
      - Expected Output: 
        - subcommand: `"create"`
        - global_options: `{"--root": "/var/run/runc"}`
        - subcommand_options: `{}`
        - container_id: `"container1"`
        - namespace: `"default"`
      - Assertions:
        - parse_command returns correct tuple format
        - global options parsed correctly
        - namespace extracted from root path

    - Test without options
      - Input: `["runc", "create", "container1"]`
      - Expected Output:
        - subcommand: `"create"`
        - global_options: `{}`
        - subcommand_options: `{}`
        - container_id: `"container1"`
        - namespace: `"default"`
      - Assertions:
        - parse_command returns correct tuple format
        - empty global options dict returned
        - default namespace used
        
    - Test with single global option
      - Input: `["runc", "--help"]`
      - Expected Output: Raises ValueError("No subcommand found")
      - Assertions:
        - parse_command raises ValueError
        - error message indicates missing subcommand

  - Test subcommand parsing
    - Test valid subcommands
      - Input: `["runc", "create", "container1"]`
      - Expected Output:
        - subcommand: `"create"`
        - global_options: `{}`
        - subcommand_options: `{}`
        - container_id: `"container1"`
        - namespace: `"default"`
      - Assertions:
        - parse_command returns correct tuple format
        - subcommand extracted correctly

    - Test invalid subcommands
      - Input: `["runc", "invalid", "container1"]`
      - Expected Output:
        - subcommand: `"invalid"`
        - global_options: `{}`
        - subcommand_options: `{}`
        - container_id: `"container1"`
        - namespace: `"default"`
      - Assertions:
        - parse_command returns correct tuple format
        - invalid subcommand still parsed

  - Test container ID extraction
    - Test with ID
      - Input: `["runc", "create", "container1"]`
      - Expected Output:
        - subcommand: `"create"`
        - global_options: `{}`
        - subcommand_options: `{}`
        - container_id: `"container1"`
        - namespace: `"default"`
      - Assertions:
        - parse_command returns correct tuple format
        - container ID extracted correctly

    - Test without ID
      - Input: `["runc", "list"]`
      - Expected Output:
        - subcommand: `"list"`
        - global_options: `{}`
        - subcommand_options: `{}`
        - container_id: `""`
        - namespace: `"default"`
      - Assertions:
        - parse_command returns correct tuple format
        - empty container ID returned

  - Test namespace handling
    - Test with namespace
      - Input: `["runc", "--root", "/var/run/runc/k8s", "create", "container1"]`
      - Expected Output:
        - subcommand: `"create"`
        - global_options: `{"--root": "/var/run/runc/k8s"}`
        - subcommand_options: `{}`
        - container_id: `"container1"`
        - namespace: `"k8s"`
      - Assertions:
        - parse_command returns correct tuple format
        - namespace extracted from root path

    - Test without namespace
      - Input: `["runc", "--root", "/var/run/runc", "create", "container1"]`
      - Expected Output:
        - subcommand: `"create"`
        - global_options: `{"--root": "/var/run/runc"}`
        - subcommand_options: `{}`
        - container_id: `"container1"`
        - namespace: `"default"`
      - Assertions:
        - parse_command returns correct tuple format
        - default namespace used

  - Test error cases
    - Test invalid format
      - Input: `["runc"]`
      - Expected Output: Raises ValueError("Empty command")
      - Assertions:
        - parse_command raises ValueError
        - error message indicates empty command

    - Test missing required fields
      - Input: `["runc", "create"]`
      - Expected Output:
        - subcommand: `"create"`
        - global_options: `{}`
        - subcommand_options: `{}`
        - container_id: `""`
        - namespace: `"default"`
      - Assertions:
        - parse_command returns correct tuple format
        - empty container ID returned

## 4. Test Documentation

### 4.1 Test Cases
- Test case ID
- Description
- Prerequisites
- Steps
- Expected results
- Actual results

### 4.2 Test Results
- Test execution logs
- Coverage reports
- Error logs
- Performance metrics 