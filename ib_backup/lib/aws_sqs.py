import os
import json
from typing import Dict

import boto3

# Max number of times a lambda should be invoked in a row before it stops invoking, used to prevent infinite loops
MAX_LAMBDA_INVOKES = 3

def send_wait_queue_msg(sqs, target_lambda: str, iteration_count: int = 0):
    """ Sends a message to the SQS wait queue
    Args:
        - sqs: AWS SQS API client
        - target_lambda: Name of lambda to target with message
        - iteration_count: Number of times this lambda has been invoked before, used to prevent infinite loops

    Raises:
        - KeyError: If the SQS wait queue url is not provided by the WAIT_QUEUE_URL environment variable
    """
    # Get wait queue arn
    wait_queue_url = os.environ.get("WAIT_QUEUE_URL", None)
    if wait_queue_url is None:
        raise KeyError("The SQS wait queue's url must be provided by the \"WAIT_QUEUE_URL\" environment variable")

    # Send message
    queue_event = {
        'target_lambda': target_lambda,
        'iteration_count': iteration_count
    }
    queue_event_str = json.dumps(queue_event)

    sqs.send_message(
        QueueUrl=wait_queue_url,
        MessageBody=queue_event_str
    )

def check_if_should_run_from_wait_queue(lambda_name: str, event: Dict[str, object],
                                        max_lambda_invokes: int = MAX_LAMBDA_INVOKES) -> bool:
    """ Determines if a lambda is being invoked by the SQS wait queue, and if it should continue running
    Looks at the `target_lambda` field in the event to see if it matches the lambda_name field.
    Looks at the `iteration_count` field in the event to see if the lambda has looped too many times and should be
    killed.

    Args:
        - lambda_name: Name of the lambda to check for
        - event: AWS Lambda invocation event
        - max_lambda_invokes: Max number of times a lambda should be invoked in a row before it stops invoking, used to
            prevent infinite loops

    Raises:
        - ValueError: If the `iteration_count` in the event is greater than the provided max_lambda_invokes

    Returns: If the lambda should execute
    """
    # Check if not invoked by SQS queue
    if 'target_lambda' not in event:
        # If not invoked by SQS queue then this function can't help determine if the lambda should keep executing
        return True

    # Check this specific lambda was invoked
    if event['target_lambda'] != lambda_name:
        return False

    # Check that max iteration count has not been reached
    if event['iteration_count'] >= max_lambda_invokes:  # Great than or equal to b/c iteration_count starts at 0
        raise ValueError("Lambda invoked too many times in a row, could be an infinite loop, exiting," +
                         "count: {}".format(event['iteration_count']))

    # If all checks pass, can execute
    return True
