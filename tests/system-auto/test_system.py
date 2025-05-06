#!/usr/bin/env python3

import os
import shutil
import subprocess
import time
import logging
import pytest
from pathlib import Path
from datetime import datetime

# Setup logging
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

class ContainerManager:
    def __init__(self, container_id="test_py_counter"):
        self.container_id = container_id
        self.base_path = Path("/home/ec2-user/ARCH")
        self.host_path = self.base_path / "data"
        self.host_path.mkdir(exist_ok=True)

    def setup_test_files(self):
        """Copy necessary files for Python counter test"""
        test_dir = Path(__file__).parent
        resource_dir = self.base_path / "tests" / "resource"
        
        # Copy Dockerfile
        shutil.copy2(
            resource_dir / "Dockerfile.py_counter.bak",
            test_dir / "Dockerfile"
        )
        # Copy Python counter script
        shutil.copy2(
            resource_dir / "py_counter.py",
            test_dir / "py_counter.py"
        )

    def build_image(self):
        """Build Docker image for Python counter"""
        test_dir = Path(__file__).parent
        try:
            subprocess.run(
                ["sudo", "docker", "build", "-t", "py_counter_img", "."],
                cwd=test_dir,
                check=True
            )
            subprocess.run(
                ["sudo", "docker", "save", "py_counter_img", "-o", "py_counter_img.tar"],
                cwd=test_dir,
                check=True
            )
            subprocess.run(
                ["sudo", "ctr", "image", "import", "py_counter_img.tar"],
                cwd=test_dir,
                check=True
            )
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to build image: {e}")
            raise

    def start_container(self):
        """Start container with ARCH enabled"""
        try:
            subprocess.run([
                "sudo", "ctr", "run", "--detach",
                "--env", "ARCH_ENABLED=1",
                "--env", f"ARCH_SHAREDFS_HOST_PATH={self.host_path}",
                "docker.io/library/py_counter_img:latest",
                self.container_id
            ], check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to start container: {e}")
            raise

    def checkpoint_container(self):
        """Checkpoint the container"""
        try:
            subprocess.run([
                "sudo", "ctr", "c", "checkpoint",
                "--rw", "--task", "--image",
                self.container_id, f"checkpoint/{self.container_id}"
            ], check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to checkpoint container: {e}")
            raise

    def cleanup(self):
        """Cleanup container and test files"""
        try:
            # Remove container task if running
            subprocess.run([
                "sudo", "ctr", "t", "rm", self.container_id
            ], check=False)
            
            # Remove container
            subprocess.run([
                "sudo", "ctr", "c", "rm", self.container_id
            ], check=False)
            
            # Cleanup test files
            test_dir = Path(__file__).parent
            if (test_dir / "Dockerfile").exists():
                (test_dir / "Dockerfile").unlink()
            if (test_dir / "py_counter.py").exists():
                (test_dir / "py_counter.py").unlink()
            if (test_dir / "py_counter_img.tar").exists():
                (test_dir / "py_counter_img.tar").unlink()
        except Exception as e:
            logging.error(f"Cleanup failed: {e}")

@pytest.fixture
def container_manager():
    manager = ContainerManager()
    yield manager
    manager.cleanup()

def test_python_counter(container_manager):
    """Test Python counter with checkpoint/restore"""
    # Setup test environment
    container_manager.setup_test_files()
    container_manager.build_image()
    
    # Start container and let it run for a bit
    container_manager.start_container()
    time.sleep(10)  # Let counter run for 10 seconds
    
    # Checkpoint container
    container_manager.checkpoint_container()
    
    # TODO: Add restore and validation steps 