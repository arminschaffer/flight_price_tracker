import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def logger_setup(logger_file_name: str, logger_dir: str = "logs/", logger_name: str = "logger") -> logging.Logger:
    logger = logging.getLogger(logger_name)

    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.INFO)

    logger.propagate = False

    # Rotate logs at 5MB, keep 3 backup files
    file_handler = RotatingFileHandler(
        Path(logger_dir).joinpath(logger_file_name), maxBytes=2 * 1024 * 1024, backupCount=3, delay=False
    )
    stream_handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger
