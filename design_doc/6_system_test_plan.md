# ARCH System Test Plan

## 1. System Tests

### 1.1 Basic Mode Tests
- **Local Checkpoint**
  - Test container creation
    - Input: `runc create --bundle /path/to/bundle container1`
    - Expected Output: `0` (success)
    - Assertions:
      - Container created successfully
      - Flag file created
      - Container state initialized

  - Test checkpoint creation
    - Input: `runc checkpoint container1`
    - Expected Output: `0` (success)
    - Assertions:
      - Checkpoint image created
      - Container files saved
      - Skip resume flag set

  - Test container restore
    - Input: `runc create --bundle /path/to/bundle container1`
    - Expected Output: `0` (success)
    - Assertions:
      - Container restored from checkpoint
      - Files restored correctly
      - Skip start flag set

  - Test cleanup on delete
    - Input: `runc delete container1`
    - Expected Output: `0` (success)
    - Assertions:
      - Checkpoint files cleaned up
      - Flag file deleted
      - Container resources released

  - Test error handling
    - Test invalid checkpoint
      - Input: `runc create --bundle /path/to/bundle container1`
      - Expected Output: `1` (error)
      - Assertions:
        - Error logged
        - Fallback to create
        - Flag file created

    - Test restore failure
      - Input: `runc create --bundle /path/to/bundle container1`
      - Expected Output: `1` (error)
      - Assertions:
        - Error logged
        - Fallback to create
        - Flag file created

### 1.2 Network FS Mode Tests
- **Shared Filesystem**
  - Test container creation with shared FS
    - Input: `runc create --bundle /path/to/bundle container1`
    - Expected Output: `0` (success)
    - Assertions:
      - Container created successfully
      - Bind mount added
      - Flag file created

  - Test work directory mounting
    - Input: `runc checkpoint container1`
    - Expected Output: `0` (success)
    - Assertions:
      - Work directory mounted
      - Checkpoint created in shared FS
      - Skip resume flag set

  - Test checkpoint in shared FS
    - Input: `runc checkpoint container1`
    - Expected Output: `0` (success)
    - Assertions:
      - Checkpoint created in shared FS
      - Files saved correctly
      - Skip resume flag set

  - Test restore from shared FS
    - Input: `runc create --bundle /path/to/bundle container1`
    - Expected Output: `0` (success)
    - Assertions:
      - Container restored from shared FS
      - Files restored correctly
      - Skip start flag set

  - Test cleanup
    - Input: `runc delete container1`
    - Expected Output: `0` (success)
    - Assertions:
      - Checkpoint files cleaned up
      - Work directory unmounted
      - Flag file deleted

### 1.3 Integration Tests
- **Container Lifecycle**
  - Test complete container lifecycle
    - Steps:
      1. Create container
      2. Start container
      3. Checkpoint container
      4. Delete container
      5. Create container from checkpoint
      6. Start container
      7. Delete container
    - Expected Output: `0` (success)
    - Assertions:
      - All operations successful
      - State maintained correctly
      - Resources cleaned up

  - Test multiple containers
    - Steps:
      1. Create multiple containers
      2. Checkpoint containers
      3. Delete containers
      4. Restore containers
    - Expected Output: `0` (success)
    - Assertions:
      - All containers managed correctly
      - No resource conflicts
      - Clean state transitions

  - Test error recovery
    - Steps:
      1. Create container
      2. Simulate failure during checkpoint
      3. Delete container
      4. Create new container
    - Expected Output: `0` (success)
    - Assertions:
      - System recovers from failure
      - Resources cleaned up
      - New container created successfully

  - Test resource cleanup
    - Steps:
      1. Create multiple containers
      2. Delete containers with various states
      3. Verify cleanup
    - Expected Output: `0` (success)
    - Assertions:
      - All resources cleaned up
      - No leftover files
      - System in clean state

## 2. Container Process Exit Monitoring
- **Exit Event Monitoring**
  - Test successful exit monitoring
    - Input: Container with exit code 0
    - Expected Output: Exit event detected with code 0
    - Assertions:
      - Exit event parsed correctly
      - Exit code 0 recorded
      - Flag file updated

  - Test failed exit monitoring
    - Input: Container with exit code 137
    - Expected Output: Exit event detected with code 137
    - Assertions:
      - Exit event parsed correctly
      - Exit code 137 recorded
      - Flag file updated

  - Test no exit code monitoring
    - Input: Container with no exit code
    - Expected Output: Exit event detected with default code 0
    - Assertions:
      - Exit event parsed correctly
      - Default exit code 0 recorded
      - Flag file updated

  - Test multiple container monitoring
    - Input: Multiple containers with different exit codes
    - Expected Output: Exit events detected for each container
    - Assertions:
      - Exit events parsed correctly for each container
      - Exit codes recorded correctly
      - Flag files updated correctly

  - Test non-exit events
    - Input: Container with non-exit events
    - Expected Output: Non-exit events ignored
    - Assertions:
      - Only exit events processed
      - Non-exit events ignored
      - Flag files not updated for non-exit events

## 3. Test Environment Setup

### 3.1 Prerequisites
- Docker installed
- Containerd configured
- Test container image built
- Test directories created

### 3.2 Test Data
- Sample container config
- Test files and directories
- Checkpoint images
- Log files

## 4. Test Execution

### 4.1 System Test Execution
```bash
# Setup
./tests/system/setup_system_test.sh

# Run tests
python3 -m pytest tests/system/ -v

# Cleanup
./tests/system/cleanup_system_test.sh
```

## 5. Test Coverage Requirements

### 5.1 Test Categories
- Happy path tests
- Error handling tests
- Edge cases
- Resource cleanup

### 5.2 Performance Metrics
- Container creation time
- Checkpoint creation time
- Restore time
- Resource usage

## 6. Test Documentation

### 6.1 Test Cases
- Test case ID
- Description
- Prerequisites
- Steps
- Expected results
- Actual results

### 6.2 Test Results
- Test execution logs
- Error logs
- Performance metrics
- Resource usage reports 