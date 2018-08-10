import os
from typing import Dict

import lib.job
import lib.steps

import boto3


class CleanupJob(lib.job.Job):
    """ Performs the cleanup step
    """
    def handle(self, event: Dict[str, object], ctx) -> lib.job.NextAction:
        # Get volume id from event
        if 'volume_id' not in event:
            raise KeyError("event must contain \"volume_id\" field")

        volume_id = event['volume_id']

        # Get instance id from event
        if 'dev_ib_backup_instance_id' not in event:
            raise KeyError("event must contain \"dev_ib_backup_instance_id\" field")

        dev_ib_backup_instance_id = event['dev_ib_backup_instance_id']

        # AWS clients
        ec2 = boto3.client('ec2')

        # Delete test volume
        ec2.delete_volume(VolumeId=volume_id)

        self.logger.debug("Deleted test volume, volume_id={}".format(volume_id))

        return lib.job.NextAction.TERMINATE


def main(event, ctx):
    """ Lambda function handler
    Args:
        - event: AWS event which triggered Lambda function
        - ctx: Invocation information

    Raises: Any exception
    """
    step_job = CleanupJob(lambda_name=lib.steps.STEP_CLEANUP)
    step_job.run(event, ctx)
