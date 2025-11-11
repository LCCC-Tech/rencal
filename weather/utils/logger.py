import logging
import sys


def get_logger(name: str | None = None, level: int = logging.DEBUG) -> logging.Logger:
    """
    Get a configured logger with consistent formatting across the project.

    Args:
        name: Logger name (defaults to calling module name)
        level: Logging level (defaults to DEBUG)

    Returns:
        Configured logger instance
    """
    # Use the calling module name if no name provided
    if name is None:
        import inspect

        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get("__name__", "weather")
        else:
            name = "weather"

    # Create logger
    logger = logging.getLogger(name)

    # Avoid adding multiple handlers if logger already exists
    if logger.handlers:
        return logger

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


# For convenience, create a default logger for the weather package
default_logger = get_logger("weather")
