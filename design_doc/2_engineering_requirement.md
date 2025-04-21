# ARCH Engineering Requirements

## Overview

This document outlines the requirements for ARCH to checkpoint and restore containers automatically and seamlessly. ARCH acts as a wrapper between Containerd and Runc, intercepting Runc commands from Containerd, processing them, and calling the real Runc with modified commands when necessary.

## System Components

1. Runc Command Processing
2. Container Configuration Management
3. Container Filesystem Operations
4. Checkpoint Handler
5. Internal State Management
6. Logging and Error Handling

## 1. Runc Command Processing

ARCH parses the Runc commands that our wrapper captures as input, processes them, and then builds a modified command to call the real Runc.

### 1.1 Command Parsing

All Runc commands follow this general structure:

```
runc [global_options] subcommand [subcommand_options] container_id
```

ARCH needs to extract the subcommand, namespace, container_id, global_options, and subcommand_options from the input args.

#### General Parsing Steps:

- Get global options, extract namespace as last subdirectory in root directory
- Identify subcommand, note subcmd follows global options
- Get subcommand-specific options
- Container ID is extracted from the end of the command

#### Example 1:
Runc command:
```
runc --root /run/containerd/runc/default --log /run/containerd/io.containerd.runtime.v2.task/default/tc/log.json --log-format json create --bundle /run/containerd/io.containerd.runtime.v2.task/default/tc --pid-file /run/containerd/io.containerd.runtime.v2.task/default/tc/init.pid tc
```

Extracted data:
- subcommand: create
- namespace: default
- container_id: tc
- global options: --root /run/containerd/runc/default --log /run/containerd/io.containerd.runtime.v2.task/default/tc/log.json --log-format json
- subcmd options: --bundle /run/containerd/io.containerd.runtime.v2.task/default/tc --pid-file /run/containerd/io.containerd.runtime.v2.task/default/tc/init.pid

#### Example 2:
Runc command:
```
runc --root /run/containerd/runc/default start tc
```

Extracted data:
- subcommand: start
- namespace: default
- container_id: tc
- global options: --root /run/containerd/runc/default
- subcmd options: None

### 1.2 Verify Container Configuration

ARCH checks whether the container is ARCH-enabled by looking into the container's config json and checking if the environment variable ARCH_ENABLE is present. See section 2.1.

If not enabled, ARCH calls real Runc with the unmodified args.

### 1.3 Subcommand Processing

ARCH only processes the following subcommands:
- "create"
- "start"
- "checkpoint"
- "resume"
- "delete"

For all other subcommands, ARCH calls real Runc with the unmodified args.

ARCH uses the parser extracted info for subcommand processing. For each subcmd, use namespace and container_id to uniquely identify the container.

### 1.4 Create Subcommand Processing

Expand the existing Containerd and Runc behavior to create container, by adding option to restore from a checkpoint image. Restore operation has two parts - copy the container upperdir files and restore the process using Runc.

#### Process Flow:

1. Check if container requires a new bind mount, do so if needed, see Section 2.3.
2. Verify whether a checkpoint image exists, use config.json image path info as input, see Section 2.2.
3. Validate the checkpoint image by looking into its log file, see Section 4.2.
4. If verify or validate fails, then ARCH calls real Runc with the unmodified args.
5. If both verify and validate pass, do the following to restore the container from image:
   - Restore container upperdir files by copying from image path, see section 3.
   - Modify Runc subcommand from create to restore, along with new --image-path and --detach subcmd options.

#### Command Modification Example:

From:
```
create --bundle <bundle_path> --pid-file <pid_file_path> <container_id>
```

To:
```
restore --detach --image-path <image_path> --bundle <bundle_path> --pid-file <pid_file_path> <container_id>
```

#### Specific Example:

From:
```
create --bundle /run/containerd/io.containerd.runtime.v2.task/default/tc --pid-file /run/containerd/io.containerd.runtime.v2.task/default/tc/init.pid tc
```

To:
```
restore --detach --image-path /var/lib/arch/checkpoint/default/tc --bundle /run/containerd/io.containerd.runtime.v2.task/default/tc --pid-file /run/containerd/io.containerd.runtime.v2.task/default/tc/init.pid tc
```

Call the real Runc with complete command including the intercepted global options, modified subcmd, subcmd options, and container_id.

If restore successful, set the internal state for the container with a skip_start flag. See Section 5. Containerd calls Runc with start subcmd after create. Since restore subcmd already starts the container by default, skip calling Runc with start subcmd to avoid conflict.

If the restore fails, do the following:
1. Roll back changes to the container by cleaning up the upperdir files
2. Call real Runc with the unmodified args, i.e., original create subcmd and options

### 1.5 Start Subcommand Processing

1. Check the skip_start flag, if set, reset the flag, then immediately exit with return code 0.
2. If skip_start not set, call real Runc with unmodified args.

### 1.6 Checkpoint Subcommand Processing

Expand the existing Containerd and Runc behavior to checkpoint container process, by adding operation to copy the container upperdir files into the checkpoint image.

#### Process Flow:

1. Retrieve checkpoint image path from container's config.json
2. Retrieve container upperdir path
3. Copy files from container upperdir to checkpoint image, using tar to compress
4. If there are any failures, call real Runc with the unmodified args. Otherwise:
   - Modify the Runc command:
     - Remove the --work-path, --leave replace subcommand options
     - Replace --image-path value by the retrieved image path

#### Command Modification Example:

From:
```
checkpoint --image-path <xxx> --work-path <yyy> --file-locks --leave-running <container_id>
```

To:
```
checkpoint --image-path <image_path> --file-locks <container_id>
```

Call real Runc with the modified subcmd options.

If Runc command successful, set the internal state for the container with a skip_resume flag.

### 1.7 Resume Subcommand Processing

1. Check the skip_resume flag, if set, reset the flag, then immediately exit with return code 0.
2. If skip_resume not set, call real Runc with unmodified args.

### 1.8 Delete Subcommand Processing

Clean up the checkpoint image when the container process exits successfully.

#### Process Flow:

1. Check the container flag for exit, see Section 5
2. If exit flag exists and exit code is 0:
   - Delete the checkpoint image path
   - If bind mount was used, based on container config.json, clean up the bind mount, see Section 2
   - Remove exit flag
3. Call the real Runc with unmodified args.

## 2. Container Configuration

Takes namespace and container_id as inputs.

### 2.1 Find Container Config.json

First uniquely identify the container using namespace and container_id.

Use the following to find the config.json file location:

```python
possible_paths = [
    "/run/containerd/io.containerd.runtime.v2.task/<namespace>/<container_id>/config.json",
    "/run/containerd/runc/<namespace>/<container_id>/config.json",
    "/run/runc/<namespace>/<container_id>/config.json"
]
```

Should return and log error if config.json not found.

### 2.2 Environment Variables

ARCH needs to read the following environment variables from the config.json file:

- `ARCH_ENABLE = 1`
- `ARCH_CHECKPOINT_HOST_PATH = /your/path/for/checkpoint/images`
- `ARCH_NETWORKFS_HOST_PATH = /your/path/for/network_fs/mount/on/host`
- `ARCH_WORKDIR_CONTAINER_PATH = /your/path/for/work_dir/inside/container`
- `ARCH_ENABLE_MANAGED_EBS = 1`
- `ARCH_MANAGED_EBS_SIZE_GB = "your volume size in GB"`

#### Default Values:

- Reading `ARCH_ENABLE` and `ARCH_ENABLE_MANAGED_EBS` returns 0 if the variable is missing or does not have a value.
- `XXX_PATH` variables by default return None.

**Note**: If config.json has no 'process' key, it is considered a valid case and the container is not ARCH-enabled.

### 2.3 Modify Settings

ARCH needs to modify the following settings and write out the config.json file:

1. Add bind mount given input of source and destination path
   - If source path (path inside container) is already bind mounted to another destination/host path, give error message and do not change config.json file
2. Add current working directory given input path
   - If current working directory already set, give warning message and update config.json file

## 3. Container Files

Containerd uses overlay file system where the writeable files are stored in upperdir, while read-only files are stored in lowerdir.

ARCH needs to copy the upperdir files to checkpoint image during checkpoint, and the reverse during restore.

### Process Flow:

1. First uniquely identify the container using namespace and container_id as input
2. Find the container upperdir path
3. Copy all files from upperdir path to checkpoint image path, using tar compression
4. Copy all files from checkpoint image path to upperdir path, and expand the tar file
5. Roll back copy to upperdir path, in case restore failed, and ARCH need to create a new container

### 3.1 Upperdir Path

The upperdir path is dynamic, use the following logic:

```python
def get_upperdir(self, container_id):
    """
    Runs 'mount' and filters for an overlay mount containing the container id.
    Returns the value of upperdir if found, else None.
    """
    try:
        output = subprocess.check_output(["mount"], text=True)
    except subprocess.CalledProcessError as e:
        self.logger.error("Failed to run mount: %s", e)
        return None
    pattern = re.compile(r"upperdir=([^,\\)]+)")
    for line in output.splitlines():
        if "overlay" in line and container_id in line:
            match = pattern.search(line)
            if match:
                upperdir = match.group(1)
                self.logger.info("Found upperdir for container '%s': %s", container_id, upperdir)
                return upperdir
    self.logger.warning("Could not determine upperdir for container '%s'", container_id)
    return None
```

Double check how namespace also impacts the upperdir path.

### 3.2 Copy to Container Roll Back

Roll back only deletes the files copied from checkpoint image to upperdir, not blindly delete all files in the upperdir path.

## 4. Checkpoint Handler

ARCH needs to manage metadata for each container checkpoint, including:

- Checkpoint image path
- Validate checkpoint image

### 4.1 Checkpoint Image Path

Build the checkpoint image path, based on namespace, container_id, env variables from the container config.json, and following priority:

1. If `ARCH_NETWORKFS_HOST_PATH`, then image path = `$ARCH_NETWORKFS_HOST_PATH/checkpoint/namespace/container_id`
2. Else if `ARCH_CHECKPOINT_HOST_PATH`, then image path = `$ARCH_CHECKPOINT_HOST_PATH/namespace/container_id`
3. Else image path = `$BASE_CHECKPOINT_PATH/namespace/container_id`

### 4.2 Validate Checkpoint Image

Need to validate the checkpoint image, based on image path as input.

Find dump.log in the image path, and verify its last line includes "Dumping finished successfully".

If both conditions pass, return true. If either fails, return false.

## 5. Internal State

Need to track the containers states relevant to checkpoint and restore.

Since ARCH is called by multiple processes, each state read & write operation needs to be atomic and persistent to file.

The tracked states include:

- skip_start flag - During Containerd's call to Runc create, if the container is actually restored from checkpoint, ARCH needs to skip the next Containerd call to Runc start, as the restored container starts automatically.
- skip_resume flag - Similar reason for Containerd's call to Runc Checkpoint, we need to skip the next Runc resume call, as ARCH kills the container process after checkpoint to maintain consistent states.
- Container process exit code

### 5.1 Container Process Exit Code

ARCH needs to monitor the exit code using the following command:

```
sudo ctr events
```

as Containerd and Runc do not provide direct API to capture the process exit code.

Ctr events continuously output container process (task) events in the following format:

```
2025-04-04 19:10:59.898514001 +0000 UTC default /tasks/exit {"container_id":"tc","id":"tc","pid":6615,"exit_status":137,"exited_at":{"seconds":1743793859,"nanos":783072930}}
```

Need to parse into:

- Namespace: default
- Container_id: tc
- Topic: /tasks/exit
- Exit code: 137

Note there are:

- Events other than /tasks/exit, which are dropped
- Exit code ("exit_status") may not be present, which is taken as exit code 0

ARCH needs to set a flag for exit code for the enabled containers after parsing a matching exit event, based on namespace and container_id.

## 6. Error Handling and Logging

The execution code should be covered with try…catch blocks as much as possible.

In case of error, retry is not needed, instead, follow design behavior and/or fail gracefully, and log the error.

Logs should be:

- Consolidated into a single log file
- Have multiple levels - INFO, ERROR
- For Runc command, log both the intercepted command as well as modified command, as INFO

