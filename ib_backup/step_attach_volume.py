#!/usr/bin/env python3

from typing import Dict

import lib.steps
import lib.job
import lib.aws_ec2

import boto3

# Constants
DEV_IB_BACKUP_NAME = 'ib02.dev.code418.net'
DEV_IB_BACKUP_ATTACH_DEV_NAME = '/dev/sdh'


class AttachVolumeJob(lib.job.Job):
    """ Performs the attach volume step
    """

    def handle(self, event: Dict[str, object], ctx) -> lib.job.NextAction:
        # Get volume id from event
        if 'volume_id' not in event:
            raise KeyError("\"volume_id\" must be present in event")

        volume_id = event['volume_id']

        # AWS EC2 client
        ec2 = boto3.client('ec2')

        # Find dev backup infobright instance
        instance = lib.aws_ec2.find_instance_by_name(ec2, DEV_IB_BACKUP_NAME)
        instance_id = instance['InstanceId']

        self.logger.debug("Found dev Infobright backup instance, instance_id={}".format(instance_id))

        # Attach volume
        ec2.attach_volume(
            Device=DEV_IB_BACKUP_ATTACH_DEV_NAME,
            InstanceId=instance_id,
            VolumeId=volume_id
        )

        # Invoke next lambda
        self.next_lambda_event = {
            'volume_id': volume_id,
            'instance_id': instance_id
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
