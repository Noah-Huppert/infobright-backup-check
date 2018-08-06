#!/usr/bin/env python3

from typing import Dict

import lib.steps
import lib.job

import boto3


class WaitVolumeCreatedJob(lib.job.Job):
    """ Performs the wait volume created step
    """

    def handle(self, event: Dict[str, object], ctx) -> lib.job.NextAction:
        # Get dev ib backup instance id
        if 'dev_ib_backup_instance_id' not in event:
            raise KeyError("event must contain \"dev_ib_backup_instance_id\" field")

        dev_ib_backup_instance_id = event['dev_ib_backup_instance_id']

        # Get volume id from event
        if 'volume_id' not in event:
            raise KeyError("event must contain \"volume_id\" field")

        volume_id = event['volume_id']

        # AWS clients
        ec2 = boto3.client('ec2')

        # Get status of volume
        vol_resp = ec2.describe_volumes(VolumeIds=[volume_id])

        volumes = vol_resp['Volumes']
        if len(volumes) != 1:
            raise ValueError("AWS get volume api request did not return exactly 1 volume, resp: {}".format(vol_resp))

        volume = volumes[0]

        # Check if completed
        if volume['State'] == 'available':
            self.logger.debug("volume is created")

            # Invoke next lambda
            self.next_lambda_event = {
                'dev_ib_backup_instance_id': dev_ib_backup_instance_id,
                'volume_id': volume_id
            }

            return lib.job.NextAction.NEXT
        else:  # If not completed
            self.logger.debug("volume still creating")

            return lib.job.NextAction.REPEAT


def main(event, ctx):
    """ Entrypoint
    Args:
        - event: AWS event which triggered lambda
        - ctx: Additional information provided when lambda was invoked

    Raises: Any exception
    """
    step_job = WaitVolumeCreatedJob(lambda_name=lib.steps.STEP_WAIT_VOLUME_CREATED)
    step_job.run(event, ctx)
