#!/bin/sh

echo "Running cleanup script..."

# Remove old checkpoint dir if it exists from a failed run
#echo "Removing old checkpoint directory..."
#sudo rm -rf ./checkpoint

CONTAINER_ID="tc"
# Find and kill running 'tc' task if it exists
echo "Finding running 'tc' task..."
container_info=$(sudo ctr t ls | grep $CONTAINER_ID)

# If the 'tc' container is found
if [[ ! -z "$container_info" ]]; then
  echo "'tc' task found. Killing process and removing task..."
  # Extract the PID
  pid=$(echo "$container_info" | awk '{print $2}')

  # Kill the process
  sudo kill -9 "$pid"
  echo "Process killed."

  # Remove the task
  sudo ctr t rm tc
  echo "Task removed."
else
  echo "'tc' task not found."
fi

# Check if the container exists and delete it
echo "Checking if container exists and deleting it..."
if sudo ctr c ls | grep -q $CONTAINER_ID; then
   sudo ctr c rm $CONTAINER_ID
   echo "Container removed."
else
   echo "Container not found."
fi

echo "Looking for container exit monitor processes..."
MONITOR_PIDS=$(ps -ef | grep "container_exit_monitor" | grep -v grep | grep -v "cleanup_exit_monitor" | awk '{print $2}')

if [ -z "$MONITOR_PIDS" ]; then
    echo "No container exit monitor processes found."
    exit 0
fi

echo "Found container exit monitor processes: $MONITOR_PIDS"
echo "Killing processes..."

for PID in $MONITOR_PIDS; do
    echo "Killing process $PID..."
    kill $PID 2>/dev/null || sudo kill $PID 2>/dev/null
    
    # Verify process was killed
    if ps -p $PID > /dev/null; then
        echo "Process $PID still running, attempting force kill..."
        kill -9 $PID 2>/dev/null || sudo kill -9 $PID 2>/dev/null
        
        if ps -p $PID > /dev/null; then
            echo "WARNING: Failed to kill process $PID"
        else
            echo "Process $PID forcefully terminated."
        fi
    else
        echo "Process $PID terminated."
    fi
done

echo "Cleanup script complete."
