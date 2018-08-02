#!/usr/bin/env python3

import os

import lib.steps
import lib.log
import lib.aws_sqs
import lib.aws_lambda

import boto3

logger = lib.log.get_logger(lib.steps.STEP_WAIT_VOLUME_CREATED)


def main(event, ctx):
    """ Entrypoint
    Args:
        - event: AWS event which triggered lambda
        - ctx: Additional information provided when lambda was invoked

    Raises: Any exception
    """

    logger.debug("event={}".format(event))

    # Get name of the lambda we will invoke at the end of this one
    next_lambda_name = os.environ.get("NEXT_LAMBDA_NAME", None)
    if next_lambda_name is None:
        raise KeyError("NEXT_LAMBDA_NAME environment variable must be set")

    # Check if invoked by wait queue
    if not lib.aws_sqs.check_if_should_run_from_wait_queue(lib.steps.STEP_WAIT_VOLUME_CREATED, event):
        logger.debug("lambda not targeted")
        return

    # Get iteration count from event
    iteration_count = 0
    if 'iteration_count' in event:
        iteration_count = event['iteration_count']

    # Get volume id from event
    if 'volume_id' not in event:
        raise KeyError("event must contain \"volume_id\" field")

    volume_id = event['volume_id']

    # AWS clients
    ec2 = boto3.client('ec2')
    sqs = boto3.client('sqs')

    # Get status of volume
    vol_resp = ec2.describe_volumes(
        Filters=[{
            'Name': 'volume-id',
            'Values': [ volume_id ]
        }]
    )

    volumes = vol_resp['Volumes']
    if len(volumes) != 1:
        raise ValueError("AWS get volume api request did not return exactly 1 volume, resp: {}".format(vol_resp))

    volume = volumes[0]

    # Check if completed
    if volume['State'] == 'available':
        logger.debug("volume is created, invoking next step, volume_id={}, next_lambda_name={}"
                     .format(volume_id, next_lambda_name))

        lib.aws_lambda.invoke_lambda(next_lambda_name, { 'volume_id': volume_id })
    else:  # If not completed
        logger.debug("volume still creating, will check again in 1 minute, volume_id={}, iteration_count={}"
                     .format(volume_id, iteration_count))

        lib.aws_sqs.send_wait_queue_msg(sqs, lib.steps.STEP_WAIT_VOLUME_CREATED, iteration_count + 1)


if __name__ == '__main__':
    main(None, None)
