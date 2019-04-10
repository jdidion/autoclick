import logging
from pathlib import Path
import sys
from typing import Optional

from autoclick.composites import composite_factory


@composite_factory(hidden=["log_name"])
def log(
    log_name: str = "DEFAULT", log_level: str = "WARN", log_file: Optional[Path] = None
) -> logging.Logger:
    """

    Args:
        log_name:
        log_level:
        log_file:

    Returns:

    """
    logger = logging.getLogger(log_name)
    logger.setLevel(log_level)
    if log_file:
        logger.addHandler(logging.FileHandler(log_file))
    else:
        logger.addHandler(logging.StreamHandler(sys.stderr))
    return logger
