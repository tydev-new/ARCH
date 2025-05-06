import os
import sys
import shutil
import tarfile
from typing import Tuple
from src.utils.logging import logger

class CheckpointHandler:
    """Handles checkpoint and restore operations for containers."""
    
    def __init__(self):
        """Initialize the checkpoint handler."""
        pass

    def validate_checkpoint(self, checkpoint_path: str) -> bool:
        """Validate checkpoint by checking dump.log."""
        logger.info(f"Validating checkpoint at {checkpoint_path}")
        dump_log = os.path.join(checkpoint_path, "dump.log")
        if not os.path.exists(dump_log):
            logger.warning("dump.log not found in checkpoint")
            return False
            
        try:
            with open(dump_log, 'r') as f:
                last_line = f.readlines()[-1].strip()
                if "Dumping finished successfully" not in last_line:
                    logger.error("Checkpoint not completed successfully")
                    return False
            logger.info("Checkpoint validation successful")
            return True
        except Exception as e:
            logger.error(f"Error validating checkpoint: {e}")
            return False

    def save_checkpoint_file(self, upperdir: str, checkpoint_path: str) -> bool:
        """Save container files to checkpoint using tar compression."""
        try:
            logger.info(f"Starting checkpoint save from {upperdir} to {checkpoint_path}")
            if not os.path.exists(upperdir):
                logger.error(f"Upperdir does not exist: {upperdir}")
                return False
                
            # Create checkpoint directory
            logger.info(f"Creating checkpoint directory at {checkpoint_path}")
            os.makedirs(checkpoint_path, exist_ok=True)
            
            # Create tar archive
            tar_path = os.path.join(checkpoint_path, "container_files.tar")
            logger.info(f"Creating tar archive at {tar_path}")
            with tarfile.open(tar_path, "w:gz") as tar:
                tar.add(upperdir, arcname=os.path.basename(upperdir))
            
            logger.info(f"Successfully saved checkpoint to {tar_path}")
            return True
                
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            return False

    def restore_checkpoint_file(self, checkpoint_path: str, upperdir: str) -> bool:
        """Restore container files from checkpoint."""
        try:
            logger.info(f"Starting checkpoint restore from {checkpoint_path} to {upperdir}")
            if not os.path.exists(checkpoint_path):
                logger.error(f"Checkpoint path does not exist: {checkpoint_path}")
                return False
            
            if not os.path.exists(upperdir):
                logger.error(f"Upperdir does not exist: {upperdir}")
                return False
            
            # Extract tar archive
            tar_path = os.path.join(checkpoint_path, "container_files.tar")
            logger.info(f"Looking for tar archive at {tar_path}")
            if not os.path.exists(tar_path):
                logger.error(f"Checkpoint tar file not found: {tar_path}")
                return False
                
            # Backup existing fs folder if it exists
            fs_path = os.path.join(upperdir, "fs")
            backup_path = None
            if os.path.exists(fs_path):
                backup_path = f"{fs_path}.bak"
                if os.path.exists(backup_path):
                    shutil.rmtree(backup_path)
                shutil.move(fs_path, backup_path)
                
            logger.info(f"Extracting tar archive to {upperdir}")
            with tarfile.open(tar_path, "r:gz") as tar:
                root_dir = tar.getmembers()[0].name.split('/')[0]
                for member in tar.getmembers():
                    if member.name == root_dir:
                        continue
                    member.name = member.name[len(root_dir)+1:]
                    tar.extract(member, path=upperdir)
            
            # Clean up backup after successful restore
            if backup_path and os.path.exists(backup_path):
                logger.info(f"Cleaning up backup at {backup_path}")
                shutil.rmtree(backup_path)
            
            logger.info(f"Successfully restored checkpoint to {upperdir}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore checkpoint: {e}")
            return False

    def rollback_restore_file(self, upperdir: str) -> None:
        """Clean up upperdir after failed restore."""
        logger.info(f"Starting rollback for upperdir {upperdir}")
        if os.path.exists(upperdir):
            logger.warning("Cleaning up upperdir %s after restore failure", upperdir)
            shutil.rmtree(upperdir)
            logger.info("Rollback completed successfully")
        else:
            logger.info("Upperdir does not exist, no cleanup needed")

    def cleanup_checkpoint(self, checkpoint_path: str) -> bool:
        """Clean up checkpoint files."""
        if not checkpoint_path:
            logger.info("No checkpoint path provided, skipping cleanup")
            return False
            
        if not os.path.exists(checkpoint_path):
            logger.info(f"Checkpoint path {checkpoint_path} does not exist, skipping cleanup")
            return False
            
        try:
            logger.info(f"Removing checkpoint at {checkpoint_path}")
            shutil.rmtree(checkpoint_path)
            return True
        except Exception as e:
            logger.error(f"Failed to remove checkpoint: {e}")
            return False
