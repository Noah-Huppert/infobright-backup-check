#!/usr/bin/env python3

from typing import Dict

import lib.steps
import lib.job
import lib.aws_ec2

import boto3

# Constants
DEV_IB_BACKUP_ATTACH_DEV_NAME = '/dev/sdg'


class AttachVolumeJob(lib.job.Job):
    """ Performs the attach volume step
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

        # AWS EC2 client
        ec2 = boto3.client('ec2')

        # Attach volume
        ec2.attach_volume(
            Device=DEV_IB_BACKUP_ATTACH_DEV_NAME,
            InstanceId=dev_ib_backup_instance_id,
            VolumeId=volume_id
        )

        self.logger.debug("Attached volume to dev Infobright backup instance, volume_id={}, instance_id={}"
                          .format(volume_id, instance_id))

        # Invoke next lambda
        self.next_lambda_event = {
            'volume_id': volume_id,
            'dev_ib_backup_instance_id': dev_ib_backup_instance_id,
            'mount_point': DEV_IB_BACKUP_ATTACH_DEV_NAME
        }

        return lib.job.NextAction.NEXT


def main(event, ctx) -> int:
    """ Entrypoint
    Args:
        - event: AWS event which triggered lambda
        - ctx: Additional information provided when lambda was invoked
    """
    step_job = AttachVolumeJob(lambda_name=lib.steps.STEP_ATTACH_VOLUME)
    step_job.run(event, ctx)
