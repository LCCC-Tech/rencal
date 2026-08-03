import logging
import sys


def get_logger(name: str | None = None, level: int = logging.DEBUG) -> logging.Logger:
    """
    Get a configured logger with consistent formatting across the project.

    Args:
        name: Logger name (defaults to calling module name)
        level: Logging level (defaults to DEBUG, but respects QUIET_MODE/VERBOSE_MODE)

    Returns:
        Configured logger instance
    """
    # Import here to avoid circular imports
    try:
        from rencal.utils.constants import QUIET_MODE, VERBOSE_MODE
    except ImportError:
        QUIET_MODE = False
        VERBOSE_MODE = False

    # Use the calling module name if no name provided
    if name is None:
        import inspect

        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get("__name__", "rencal")
        else:
            name = "rencal"

    # Create logger
    logger = logging.getLogger(name)

    # Avoid adding multiple handlers if logger already exists
    if logger.handlers:
        return logger

    # Determine logging level based on modes
    if QUIET_MODE:
        level = logging.WARNING  # Only warnings and errors
    elif VERBOSE_MODE:
        level = logging.DEBUG  # All messages
    else:
        level = logging.INFO  # Default: INFO and above

    # Set level
    logger.setLevel(level)

    # Create formatter with your specified format
    formatter = logging.Formatter(
        fmt="[%(levelname)s] - %(message)s - [%(module)s] - %(asctime)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(console_handler)

    # Prevent propagation to root logger to avoid duplicate messages
    logger.propagate = False

    return logger


# For convenience, create a default logger for the rencal package
default_logger = get_logger("rencal")
