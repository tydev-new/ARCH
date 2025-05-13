#!/usr/bin/env python3

import os
import shutil
import subprocess
import time
import logging
import pytest
from pathlib import Path
from datetime import datetime

class TestCase:
    def __init__(self, test_name):
        # Test directories
        self.base_dir = Path("/tmp/arch_test")
        self.sharedfs_dir = self.base_dir / "sharedfs"
        self.log_dir = self.base_dir / "logs" / test_name
        
        # Test resources
        self.resource_dir = Path("/home/ec2-user/ARCH/tests/resource")
        self.test_dir = Path("/home/ec2-user/ARCH/tests/system-auto")
        
        # Container settings
        self.container_id = f"test_{test_name}"
        self.image_name = f"{test_name}_img"
        
        # Setup logging
        self._setup_logging()

    def _setup_logging(self):
        """Setup test-specific logging for both system test and ARCH"""
        # Create test log directory
        self.log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = self.log_dir / f"test_{timestamp}.log"
        
        # Setup system test logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ],
            force=True  # Override any existing logging configuration
        )
        
        # Setup ARCH logging with timestamp
        try:
            subprocess.run([
                "sudo", "./arch-cli", "log",
                "--level", "INFO",
                "--file", str(self.log_dir / f"arch_{timestamp}.log")
            ], check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to setup ARCH logging: {e}")
            raise

    def setup(self):
        """Setup test environment"""
        logging.info("Setting up test environment")
        
        # Create test directories
        self.sharedfs_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy and prepare test files
        self._prepare_test_files()
        
        # Build container image
        self._build_image()
        
        # Verify containerd status
        self._verify_containerd()

    def _prepare_test_files(self):
        """Copy and prepare test files from templates"""
        logging.info("Preparing test files")
        # Map test names to Dockerfile names
        dockerfile_map = {
            "python": "py",
            "c": "c",
            "shell": "sh"
        }
        # Copy Dockerfile template
        shutil.copy2(
            self.resource_dir / f"Dockerfile.{dockerfile_map[self.container_id.split('_')[1]]}_counter.bak",
            self.test_dir / "Dockerfile"
        )
        # Copy counter script
        script_map = {
            "python": ("py", "py"),
            "c": ("c", "exe"),
            "shell": ("sh", "sh")
        }
        prefix, ext = script_map[self.container_id.split('_')[1]]
        shutil.copy2(
            self.resource_dir / f"{prefix}_counter.{ext}",
            self.test_dir / f"{prefix}_counter.{ext}"
        )

    def _build_image(self):
        """Build and import container image"""
        logging.info("Building container image")
        try:
            subprocess.run(
                ["sudo", "docker", "build", "-t", self.image_name, "."],
                cwd=self.test_dir,
                check=True
            )
            subprocess.run(
                ["sudo", "docker", "save", self.image_name, "-o", f"{self.image_name}.tar"],
                cwd=self.test_dir,
                check=True
            )
            subprocess.run(
                ["sudo", "ctr", "image", "import", f"{self.image_name}.tar"],
                cwd=self.test_dir,
                check=True
            )
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to build image: {e}")
            raise

    def _verify_containerd(self):
        """Verify containerd is running"""
        logging.info("Verifying containerd status")
        try:
            subprocess.run(["sudo", "ctr", "version"], check=True)
        except subprocess.CalledProcessError as e:
            logging.error("Containerd is not running")
            raise

    def run_container(self):
        """Start container with ARCH enabled"""
        logging.info("Starting container")
        try:
            subprocess.run([
                "sudo", "ctr", "run", "--detach",
                "--env", "ARCH_ENABLE=1",
                f"--env", f"ARCH_SHAREDFS_HOST_PATH={self.sharedfs_dir}",
                "--env", "ARCH_WORKDIR_CONTAINER_PATH=/work",
                f"docker.io/library/{self.image_name}:latest",
                self.container_id
            ], check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to start container: {e}")
            raise

    def checkpoint(self):
        """Checkpoint container using arch-cli"""
        logging.info("Waiting 10 seconds before checkpoint")
        time.sleep(10)  # Wait for 10 seconds
        
        logging.info("Checkpointing container")
        try:
            result = subprocess.run([
                "sudo", "./arch-cli", "container", "finalize"
            ], capture_output=True, text=True, check=False)
            
            # Check if the error is just about content already existing
            if result.returncode != 0 and "content sha256: already exists" in result.stderr:
                logging.info("Checkpoint completed (content already exists)")
            elif result.returncode != 0:
                logging.error(f"Failed to checkpoint container: {result.stderr}")
                raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
            else:
                logging.info("Checkpoint completed successfully")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to checkpoint container: {e}")
            raise

    def cleanup_container(self):
        """Cleanup only container and its task, preserving checkpoint and work directory"""
        logging.info("Cleaning up container")
        try:
            # Get task status
            result = subprocess.run(
                ["sudo", "ctr", "t", "ls"],
                capture_output=True,
                text=True,
                check=False
            )
            
            # If task exists and is running, try to kill it
            if self.container_id in result.stdout and "RUNNING" in result.stdout:
                # Try KILL signal first
                subprocess.run([
                    "sudo", "ctr", "t", "kill", "--signal", "KILL", self.container_id
                ], check=False)
                
                # If still running, find PID and kill -9
                time.sleep(1)  # Give it a moment to stop
                result = subprocess.run(
                    ["sudo", "ctr", "t", "ls"],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if self.container_id in result.stdout and "RUNNING" in result.stdout:
                    # Extract PID from task list
                    for line in result.stdout.splitlines():
                        if self.container_id in line:
                            pid = line.split()[1]
                            subprocess.run(["sudo", "kill", "-9", pid], check=False)
            
            # Remove container task
            subprocess.run([
                "sudo", "ctr", "t", "rm", self.container_id
            ], check=False)
            
            # Remove container
            subprocess.run([
                "sudo", "ctr", "c", "rm", self.container_id
            ], check=False)
        except Exception as e:
            logging.error(f"Container cleanup failed: {e}")

    def cleanup_all(self):
        """Full cleanup including checkpoint images and work directory"""
        logging.info("Performing full cleanup")
        try:
            # Cleanup container first
            self.cleanup_container()
            
            # Remove snapshot if exists
            subprocess.run([
                "sudo", "ctr", "snapshots", "rm", self.container_id
            ], check=False)
            
            # Cleanup test files
            test_dir = self.test_dir
            for file in ["Dockerfile", f"{self.container_id.split('_')[1]}_counter.{self.container_id.split('_')[1]}", f"{self.image_name}.tar"]:
                if (test_dir / file).exists():
                    (test_dir / file).unlink()
            
            # Remove checkpoint and work directories
            if self.sharedfs_dir.exists():
                shutil.rmtree(self.sharedfs_dir)
        except Exception as e:
            logging.error(f"Full cleanup failed: {e}")

    def _verify_container_running(self):
        """Verify container is running"""
        logging.info("Verifying container is running")
        try:
            result = subprocess.run(
                ["sudo", "ctr", "t", "ls"],
                capture_output=True,
                text=True,
                check=True
            )
            if self.container_id not in result.stdout or "RUNNING" not in result.stdout:
                raise AssertionError(f"Container {self.container_id} is not running")
            logging.info("Container is running")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to verify container status: {e}")
            raise

    def _verify_checkpoint_image(self):
        """Verify checkpoint directory exists and has content"""
        logging.info("Verifying checkpoint directory")
        try:
            # Check if checkpoint directory exists under shared filesystem
            # Structure: sharedfs_dir/checkpoint/default/<container_id>
            checkpoint_dir = self.sharedfs_dir / "checkpoint" / "default" / self.container_id
            if not checkpoint_dir.exists():
                raise AssertionError(f"Checkpoint directory not found for container {self.container_id}")
            # Check if directory has content
            if not any(checkpoint_dir.iterdir()):
                raise AssertionError(f"Checkpoint directory is empty for container {self.container_id}")
            logging.info(f"Checkpoint directory found with contents: {list(checkpoint_dir.iterdir())}")
        except Exception as e:
            logging.error(f"Failed to verify checkpoint directory: {e}")
            raise

    def _check_arch_logs(self):
        """Check ARCH logs for any error messages"""
        logging.info("Checking ARCH logs for errors")
        try:
            # Get the most recent arch log file
            arch_logs = list(self.log_dir.glob("arch_*.log"))
            if not arch_logs:
                raise FileNotFoundError("No ARCH log files found")
            
            latest_log = max(arch_logs, key=lambda x: x.stat().st_mtime)
            
            # Only fail on lines with 'ERROR' (case-sensitive)
            with open(latest_log, 'r') as f:
                for line in f:
                    if "ERROR" in line:
                        raise AssertionError(f"Error found in ARCH logs: {line.strip()}")
            
            logging.info("No errors found in ARCH logs")
        except Exception as e:
            logging.error(f"Failed to check ARCH logs: {e}")
            raise

@pytest.fixture
def test_case(request):
    """Fixture to create and cleanup test case"""
    test = TestCase(request.param)
    try:
        test.setup()
        yield test
    finally:
        test.cleanup_all()

@pytest.mark.parametrize("test_case", ["python", "c", "shell"], indirect=True)
def test_counter_checkpoint(test_case):
    """Test counter with checkpoint and restore
    
    Test Steps:
    1. Setup test environment
    2. Run container with ARCH enabled
    3. Checkpoint container after 10 seconds
    4. Cleanup container only (preserving checkpoint and work directory)
    5. Run container again (verify restore)
    
    Success Criteria:
    1. Container starts successfully
    2. Checkpoint completes without errors
    3. Checkpoint image is created in shared filesystem
    4. Container restores successfully
    5. Log files show no errors
    """
    # Cleanup any existing resources before test
    test_case.cleanup_all()
    
    # First run
    test_case.run_container()
    test_case._verify_container_running()  # Verify container started
    test_case.checkpoint()
    test_case._verify_checkpoint_image()  # Verify checkpoint image
    test_case._check_arch_logs()  # Check logs after checkpoint
    
    # Cleanup container only, preserving checkpoint and work directory
    test_case.cleanup_container()
    
    # Run again to verify restore
    test_case.run_container()
    test_case._verify_container_running()  # Verify container restored
    test_case._check_arch_logs()  # Check logs after restore 