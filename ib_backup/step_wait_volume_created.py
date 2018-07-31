#!/usr/bin/env python3

import os
import sys

import lib.log

logger = lib.log.get_logger("step_wait_volume_created")


def main(event, ctx) -> int:
    """ Entrypoint
    Args:
        - event: AWS event which triggered lambda
        - ctx: Additional information provided when lambda was invoked

    Returns: Exit code
    """
    logger.debug("event={}, ctx={}".format(event, ctx))
    return 0


if __name__ != '__main__':
    sys.exit(main(None, None))
