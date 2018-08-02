#!/usr/bin/env python3

import lib.steps
import lib.job

from typing import Dict


class AttachVolumeJob(lib.job.Job):
    """ Performs the attach volume step
    """

    def handle(self, event: Dict[str, object], ctx: Dict[str, object]) -> lib.job.NextAction:
        self.logger.debug("hello attach volume step")

        return lib.job.NextAction.TERMINATE


def main(event, ctx) -> int:
    """ Entrypoint
    Args:
        - event: AWS event which triggered lambda
        - ctx: Additional information provided when lambda was invoked
    """
    step_job = AttachVolumeJob(lambda_name=lib.steps.STEP_ATTACH_VOLUME)
    step_job.run(event, ctx)


if __name__ == '__main__':
    main(None, None)
