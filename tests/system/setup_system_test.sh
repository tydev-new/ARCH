#!/bin/sh
# Exit immediately if any command exits with a non-zero status.
set -e

# Error handler function that prints the error line and exits.
error_exit() {
  echo "Error on line $1. Exiting."
  exit 1
}

# Trap any error and call error_exit with the line number.
trap 'error_exit $LINENO' ERR

# Parse command line arguments
BUILD_IMAGE=0
while getopts "b" opt; do
  case $opt in
    b)
      BUILD_IMAGE=1
      ;;
    \?)
      echo "Invalid option: -$OPTARG" >&2
      exit 1
      ;;
  esac
done

echo "Running setup script..."

#echo "Starting container exit monitor..."
#python3 ../src/container_exit_monitor.py &

#IMAGE_ID="sh_counter_img"
#IMAGE_ID="py_counter_img"
IMAGE_ID="cmd_counter_img"
CONTAINER_ID="tc"
BASE_PATH="/home/ec2-user/new-tardis/data"
MYEBS_MOUNT_PATH="$BASE_PATH/data/myEBSMount"

cd /home/ec2-user/new-tardis/tests/system

# Generate docker image if -b option is provided
if [ $BUILD_IMAGE -eq 1 ]; then
    echo "Generate docker image ..."
    echo "sudo docker build -t $IMAGE_ID ."
    if ! sudo docker build -t "$IMAGE_ID" .; then
        error_exit $LINENO
    fi

    echo "sudo docker save $IMAGE_ID -o $IMAGE_ID.tar"
    if ! sudo docker save "$IMAGE_ID" -o "$IMAGE_ID.tar"; then
        error_exit $LINENO
    fi

    # Load image to containerd
    echo "Load image to containerd..."
    echo "sudo ctr image import $IMAGE_ID.tar"
    if ! sudo ctr image import "$IMAGE_ID.tar"; then
        error_exit $LINENO
    fi
else
    echo "Skipping image build steps..."
fi

# Start container task
echo "Start container task ..."
#echo "sudo ctr run --detach --mount type=bind,src=$MYEBS_MOUNT_PATH,dst=/tmp,options=rbind --cwd /tmp docker.io/library/$IMAGE_ID:latest $CONTAINER_ID"
#if ! sudo ctr run --detach --mount type=bind,src=$MYEBS_MOUNT_PATH,dst=/tmp,options=rbind --cwd /tmp docker.io/library/"$IMAGE_ID":latest "$CONTAINER_ID"; then
#if ! sudo ctr run --detach --env TARDIS_ENABLE=1 --env TARDIS_CHECKPOINT_HOST_PATH=$BASE_PATH/data/checkpoints --env TARDIS_ENABLE_MANAGED_EBS=1 --env TARDIS_MANAGED_EBS_SIZE_GB=2 --env TARDIS_MANAGED_EBS_MOUNT_PATH=/tmp docker.io/library/"$IMAGE_ID":latest "$CONTAINER_ID"; then
#if ! sudo ctr run --detach --env TARDIS_ENABLE=1 --env TARDIS_CHECKPOINT_HOST_PATH=$BASE_PATH docker.io/library/"$IMAGE_ID":latest "$CONTAINER_ID"; then
if ! sudo ctr run --detach --env TARDIS_ENABLE=1 --env TARDIS_NETWORKFS_HOST_PATH=$BASE_PATH docker.io/library/"$IMAGE_ID":latest "$CONTAINER_ID"; then
  error_exit $LINENO
fi

echo "Setup script complete."
