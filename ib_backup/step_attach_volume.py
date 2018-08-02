#!/usr/bin/env python3

import sys

import lib.steps
import lib.log

logger = lib.log.get_logger(lib.steps.STEP_ATTACH_VOLUME)


def main(event, ctx) -> int:
    """ Entrypoint
    Args:
        - event: AWS event which triggered lambda
        - ctx: Additional information provided when lambda was invoked

    Returns: Exit code
    """
    logger.debug("hello world, event={}, ctx={}".format(event, ctx))

    return 0


if __name__ == '__main__':
    sys.exit(main(None, None))
