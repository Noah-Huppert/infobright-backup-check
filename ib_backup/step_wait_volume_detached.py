#!/usr/bin/env python3
from typing import Dict

import lib.steps
import lib.job

import boto3


class WaitVolumeDetachedStep(lib.job.Job):
    """ Performs the wait volume detached step
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

        # Setup next lambda event
        self.next_lambda_event = {
            'volume_id': volume_id,
            'dev_ib_backup_instance_id': dev_ib_backup_instance_id
        }

        # If no attachments, successfully detached
        if len(attachments) == 0:
            return lib.job.NextAction.REPEAT

        # If attachments, get status of attachment b/c it could be detached
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
        if instance_attachment['State'] == 'detached':
            self.logger.debug("volume detached")

            return lib.job.NextAction.NEXT
        else:  # Still detaching
            self.logger.debug("volume still detaching")

            return lib.job.NextAction.REPEAT


def main(event, ctx):
    """ Lambda function handler
    Args:
        - event: AWS event which triggered Lambda function
        - ctx: Invocation information

    Raises: Any exception
    """
    step_job = WaitVolumeDetachedStep(lambda_name=lib.steps.STEP_WAIT_VOLUME_DETACHED, repeat_delay=60,
                                      max_iteration_count=3)
    step_job.run(event, ctx)
