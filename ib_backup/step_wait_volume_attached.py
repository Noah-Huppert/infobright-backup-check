#!/usr/bin/env python3
from typing import Dict

import lib.steps
import lib.job

import boto3


class WaitVolumeAttachedStep(lib.job.Job):
    """ Performs the wait volume attached step
    """

    def handle(self, event: Dict[str, object], ctx) -> lib.job.NextAction:
        # Get volume id from event
        if 'volume_id' not in event:
            raise KeyError("event must contain \"volume_id\" field")

        volume_id = event['volume_id']

        # Get dev ib backup instance id
        if 'dev_ib_backup_instance_id' not in event:
            raise KeyError("event must contain \"dev_ib_backup_instance_id\" field")

        dev_ib_backup_instance_id = event['dev_ib_backup_instance_id']

        # Get mount point from event
        if 'mount_point' not in event:
            raise KeyError("\"mount_point\" expected to be in event")

        mount_point = event['mount_point']

        # AWS client
        ec2 = boto3.client('ec2')

        # Get volume
        volumes_resp = ec2.describe_volumes(VolumeIds=[volume_id])

        volumes = volumes_resp['Volumes']
        if len(volumes) == 0:
            raise ValueError("Could not find any volumes with provided id")

        if len(volumes) != 1:
            raise ValueError("Found more than 1 volume with id, volumes_resp={}".format(volumes_resp))

        volume = volumes[0]

        # Get attachment object
        attachments = volume['Attachments']

        if len(attachments) == 0:
            raise ValueError("Test volume as no attachments, volume={}".format(volume))

        instance_attachment = None

        for attachment in attachments:
            if attachment['InstanceId'] == dev_ib_backup_instance_id:
                instance_attachment = attachment
                break

        if instance_attachment is None:
            raise ValueError("Could not find volume attachment for instance, dev ib backup instance id={}, volume={}"
                             .format(dev_ib_backup_instance_id, volume))

        self.logger.debug("Found volume attachment status")

        # Check status
        if instance_attachment['State'] == 'attached':
            self.logger.debug("volume attached")

            # Invoke next lambda
            self.next_lambda_event = {
                'volume_id': volume_id,
                'dev_ib_backup_instance_id': dev_ib_backup_instance_id,
                'mount_point': mount_point
            }

            return lib.job.NextAction.NEXT
        else:  # Still attaching
            self.logger.debug("volume still attaching")

            return lib.job.NextAction.REPEAT


def main(event, ctx):
    """ Lambda function handler
    Args:
        - event: AWS event which triggered Lambda function
        - ctx: Invocation information

    Raises: Any exception
    """
    step_job = WaitVolumeAttachedStep(lambda_name=lib.steps.STEP_WAIT_VOLUME_ATTACHED)
    step_job.run(event, ctx)
