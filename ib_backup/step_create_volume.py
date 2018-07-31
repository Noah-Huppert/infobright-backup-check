#!/usr/bin/env python3

import sys
import datetime

import lib.log

import boto3

# Constants
PROD_IB_BACKUP_NAME = 'ib-backup.us-east-1.code418.net'
PROD_IB_BACKUP_DATA_VOLUME_NAME = '/dev/sdg'

# Setup logger
logger = lib.log.get_logger("step_create_volume")


def main(event=None, ctx=None) -> int:
    """ Lambda function handler
    Args:
        - event: AWS event which triggered Lambda function
        - ctx: Invocation information

    Returns:
        - Exit code
    """
    ec2 = boto3.client('ec2')

    # Find production Infobright backup instance
    instances_resp = ec2.describe_instances(Filters=[{
        'Name': 'tag:Name',
        'Values': [ PROD_IB_BACKUP_NAME ]
    }])

    instances_rs = instances_resp['Reservations']

    if len(instances_rs) == 0:
           logger.error("Could not find production Infobright backup instance")
           return 1

    instance = instances_rs[0]['Instances'][0]

    logger.debug("Found production backup Infobright instance, InstanceId={}".format(instance['InstanceId']))

    # Get id of Infobright data volume
    instance_dev_mappings = instance['BlockDeviceMappings']

    volume_id = None

    for dev_mapping in instance_dev_mappings:
        if dev_mapping['DeviceName'] == PROD_IB_BACKUP_DATA_VOLUME_NAME:
            volume_id = dev_mapping['Ebs']['VolumeId']

    if volume_id is None:
        logger.error("Could not find data volume \"{}\" attached to production Infobright backup instance".format(
                     PROD_IB_BACKUP_DATA_VOLUME_NAME))
        return 1

    logger.debug("Found production backup Infobright instance data volume, VolumeId={}".format(volume_id))

    # Get latest snapshot for volume
    snapshot_pager = ec2.get_paginator('describe_snapshots')
    snapshot_resps = snapshot_pager.paginate(Filters=[{
        'Name': 'volume-id',
        'Values': [ volume_id ]
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
        logger.error("No snapshot for volume \"{}\" found".format(volume_id))
        return 1

    snapshot_size = newest_snapshot['VolumeSize']
    snapshot_id = newest_snapshot['SnapshotId']

    logger.debug("Found latest production backup Infobright data volume snapshot, SnapshotId={}".format(snapshot_id))

    # Create test volume from snapshot
    test_volume_name = "test-ib-snapshot-{}".format(snapshot_id)
    create_volume_resp = ec2.create_volume(AvailabilityZone='us-east-1a', SnapshotId=snapshot_id, Size=snapshot_size,
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

    logger.debug("Created test volume from production backup Infobright volume snapshot, " +
                 "VolumeId={}".format(created_volume_id))

    # Invoke next lambda
    logger.debug("This is where I would invoke the next lambda")

    return 0


if __name__ == '__main__':
    sys.exit(main())
