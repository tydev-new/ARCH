import subprocess
import re
from src.utils.logging import logger

class ContainerFilesystemHandler:
    def get_upperdir(self, container_id: str, namespace: str) -> str:
        """
        Runs 'mount' and filters for an overlay mount containing the container id.
        Returns the value of upperdir if found, else None.
        """
        try:
            output = subprocess.check_output(["mount"], text=True)
        except subprocess.CalledProcessError as e:
            logger.error("Failed to run mount: %s", e)
            return None
            
        pattern = re.compile(r"upperdir=([^,\\)]+)")
        for line in output.splitlines():
            if "overlay" in line and container_id in line:
                match = pattern.search(line)
                if match:
                    upperdir = match.group(1)
                    logger.info("Found upperdir for container '%s': %s", container_id, upperdir)
                    return upperdir
                    
        logger.warning("Could not determine upperdir for container '%s'", container_id)
        return None 