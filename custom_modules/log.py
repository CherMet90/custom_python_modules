import logging
import sys
import os
from logging.handlers import RotatingFileHandler

def setup_logger(log_level='INFO', log_dir='logs', log_file='app.log'):
    """
    Setup logger with configurable parameters

    Args:
        log_level: Logging level as string ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        log_dir: Directory for log files
        log_file: Log file name

    Returns:
        Logger instance
    """
    # Convert string log level to logging constant
    if isinstance(log_level, str):
        log_level = log_level.upper()
        numeric_level = getattr(logging, log_level, logging.INFO)
    else:
        # Support for direct logging constants (backward compatibility)
        numeric_level = log_level

    # Initialize logger with the name 'app'
    logger = logging.getLogger('app')

    # Clear existing handlers to avoid duplication
    logger.handlers.clear()

    logger.setLevel(numeric_level)

    # Configure Console Handler
    c_format = '[%(asctime)s.%(msecs)03d %(module)s - %(funcName)23s() ] %(message)s'
    c_handler = logging.StreamHandler(sys.stdout)
    c_handler.setFormatter(logging.Formatter(
        c_format, datefmt='%d.%m.%Y %H:%M:%S'))
    logger.addHandler(c_handler)

    # Configure File Handler
    # Ensure logs directory exists
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    f_format = "[%(asctime)s.%(msecs)03d - %(funcName)23s() ] %(message)s"
    log_path = os.path.join(log_dir, log_file)
    f_handler = RotatingFileHandler(
        log_path, maxBytes=10_000_000, backupCount=5, encoding='utf-8')
    f_handler.setFormatter(logging.Formatter(
        f_format, datefmt='%d.%m.%Y %H:%M:%S'))
    logger.addHandler(f_handler)

    return logger

# for backward compatibility
logger = setup_logger()