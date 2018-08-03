from typing import Dict

import lib.job
import lib.steps


class TestBackupJob(lib.job.Job):
    """ Performs the test backup step
    """

    def handle(self, event: Dict[str, object], ctx) -> lib.job.NextAction:
        self.logger.debug("hello test backup")
        return lib.job.NextAction.TERMINATE


def main(event, ctx):
    """ Lambda function handler
    Args:
        - event: AWS event which triggered Lambda function
        - ctx: Invocation information

    Raises: Any exception
    """
    step_job = TestBackupJob(lambda_name=lib.steps.STEP_TEST_BACKUP)
    step_job.run(event, ctx)
