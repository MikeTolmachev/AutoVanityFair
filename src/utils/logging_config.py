import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(log_dir: str = "logs", level: int = logging.INFO) -> logging.Logger:
    """Configure rotating file + console logging."""
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger("openlinkedin")
    logger.setLevel(level)

    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(fmt)
    logger.addHandler(console)

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "openlinkedin.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger
