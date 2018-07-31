import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """ Assembles a logger with the provided name to print to stdout.
    Args:
        - name: Log prefix

    Returns:
        - Logger
    """
    logger = logging.getLogger(name)

    logger.setLevel(logging.DEBUG)

    hndlr = logging.StreamHandler(sys.stdout)
    hndlr.setFormatter(logging.Formatter("[%(levelname)-8s] %(name)s: " +
                                         "%(message)s"))

    logger.addHandler(hndlr)

    return logger
