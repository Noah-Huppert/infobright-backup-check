#!/usr/bin/env python3

from typing import Dict

import lib.steps
import lib.job
import lib.aws_ec2

import boto3

# Constants
DEV_IB_BACKUP_NAME = 'ib02.dev.code418.net'
PROD_IB_BACKUP_NAME = 'ib-backup.us-east-1.code418.net'
PROD_IB_BACKUP_DATA_VOLUME_NAME = '/dev/sdg'


class CreateVolumeJob(lib.job.Job):
    """ Performs the create volume step
    """

    def handle(self, event: Dict[str, object], ctx) -> lib.job.NextAction:
        # AWS clients
        ec2 = boto3.client('ec2')

        # Find dev backup infobright instance
        dev_ib_backup_instance = lib.aws_ec2.find_instance_by_name(ec2, DEV_IB_BACKUP_NAME)
        dev_ib_backup_instance_id = dev_ib_backup_instance['InstanceId']

        self.logger.debug("Found dev Infobright backup instance, dev_ib_backup_instance_id={}"
                          .format(dev_ib_backup_instance_id))

        # Get availability zone of dev ib backup instance
        volume_az = dev_ib_backup_instance['Placement']['AvailabilityZone']

        # Find production Infobright backup instance
        prod_ib_backup_instance = lib.aws_ec2.find_instance_by_name(ec2, PROD_IB_BACKUP_NAME)

        self.logger.debug("Found production backup Infobright instance, prod_ib_backup_instance_id={}"
                          .format(prod_ib_backup_instance['InstanceId']))

        # Get id of Infobright data volume
        prod_ib_backup_instance_device_mappings = prod_ib_backup_instance['BlockDeviceMappings']

        prod_ib_backup_data_volume_id = None

        for dev_mapping in prod_ib_backup_instance_device_mappings:
            if dev_mapping['DeviceName'] == PROD_IB_BACKUP_DATA_VOLUME_NAME:
                prod_ib_backup_data_volume_id = dev_mapping['Ebs']['VolumeId']

        if prod_ib_backup_data_volume_id is None:
            raise ValueError("Could not find data volume \"{}\" attached to production Infobright backup instance"
                             .format(PROD_IB_BACKUP_DATA_VOLUME_NAME))

        self.logger.debug("Found production backup Infobright instance data volume, prod_ib_backup_data_volume_id={}"
                          .format(prod_ib_backup_data_volume_id))

        # Get latest snapshot for volume
        snapshot_pager = ec2.get_paginator('describe_snapshots')
        snapshot_resps = snapshot_pager.paginate(Filters=[{
            'Name': 'volume-id',
            'Values': [prod_ib_backup_data_volume_id]
        }])

        newest_date = None
        newest_snapshot = None

        for snapshot_resp in snapshot_resps:
            snapshots = snapshot_resp['Snapshots']

            for snapshot in snapshots:
                start_date = snapshot['StartTime']

                if newest_date is None or start_date > newest_date:
                    newest_date = start_date
                    newest_snapshot = snapshot

        if newest_snapshot is None:
            raise ValueError("No snapshot for volume \"{}\" found".format(volume_id))

        snapshot_size = newest_snapshot['VolumeSize']
        snapshot_id = newest_snapshot['SnapshotId']

        self.logger.debug("Found latest production backup Infobright data volume snapshot, snapshot_id={}"
                          .format(snapshot_id))

        # Create test volume from snapshot
        test_volume_name = "test-ib-snapshot-{}".format(snapshot_id)
        create_volume_resp = ec2.create_volume(AvailabilityZone=volume_az,
                                               SnapshotId=snapshot_id, Size=snapshot_size,
                                               VolumeType='gp2',
                                               TagSpecifications=[{
                                                   'ResourceType': 'volume',
                                                   'Tags': [{
                                                       'Key': 'Name',
                                                       'Value': test_volume_name
                                                   }, {
                                                       'Key': 'IBBackupTest',
                                                       'Value': 'True'
                                                   }]
                                               }])

        created_volume_id = create_volume_resp['VolumeId']

        self.logger.debug("Created test volume from production backup Infobright volume snapshot, " +
                          "volume_id={}".format(created_volume_id))

        # Invoke next lambda
        self.next_lambda_event = {
            'dev_ib_backup_instance_id': dev_ib_backup_instance_id,
            'volume_id': created_volume_id
        }

        return lib.job.NextAction.NEXT


def main(event, ctx):
    """ Lambda function handler
    Args:
        - event: AWS event which triggered Lambda function
        - ctx: Invocation information

    Raises: Any exception
    """
    step_job = CreateVolumeJob(lambda_name=lib.steps.STEP_CREATE_VOLUME)
    step_job.run(event, ctx)
