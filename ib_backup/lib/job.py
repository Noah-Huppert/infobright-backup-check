import os
from enum import Enum
from typing import Dict

import boto3


class Job:
    """ Provides common functionality for a lambda which is part of a series of lambdas which complete a process
    A lambda can be used in combination with multiple other lambdas to create a pipeline:

        lambda a --invokes--> lambda b --invokes--> lambda c

    A lambda can also invoke itself in order to loop and wait for a specific condition to be met:

        lambda a --invokes--> lambda a --invokes--> lambda a

    If a lambda knows that the condition it is waiting for may take some time to happen it can send messages to an SQS
    queue who's delivery is delayed by a specific amount of time. And then be triggered whenever a message is delivered
    to that SQS queue at a later time

        lambda a --adds msg to queue--> sqs queue --msg triggers lambda--> lambda a --adds msg to queue-->
        sqs queue --msg triggers lambda--> repeat...

    These 3 behaviors can be combined to create more complex behavior.

    Override the `handle` method with custom lambda code. The return value of this method determines what will happen
    when the `handle` method is finished. See method documentation for more information.

    Call the `run` method to invoke your custom handler. This will look at the output of your `handle` method and
    perform an action based on what is returned.

    Fields:
        - lambda_name (str): Required, Name of lambda step
        - next_lambda_name (str): Required if `handle` returns NextAction.NEXT, Name of the lambda to trigger after
            this one completes, None if no lambdas should be triggered after
        - next_lambda_event (Dict[str, object]): Required if `handle` returns NextAction.NEXT, The event to provide to
            the lambda specified by next_lambda_name, None if no lambda should be triggered after
        - wait_queue_url (str): Required if `handle` returns NextAction.REPEAT, URL of the SQS wait queue to send wait
            messages to, None if job does not require use of the wait queue
        - max_iteration_count (int): Required if `handle` returns NextAction.REPEAT, maximum number of times a lambda
            can repeat before being considered repeating infinitely
        - logger (logging.Logger): Logger for lambda
    """

    class NextAction(Enum):
        """ Indicates what should happen after the `handle` method completes
        Fields:
            - TERMINATE (int): Do nothing
            - NEXT (int): Invoke the lambda specified by the `next_lambda_name` field
            - REPEAT (int): Send a message to the wait SQS queue specified by the `wait_queue_url` to re-invoke this
                same lambda
        """
        TERMINATE = 1
        NEXT = 2
        REPEAT = 3

    def __init__(self, lambda_name: str, next_lambda_name: str = None, wait_queue_url: str = None,
                 max_iteration_count: int = 3):
        """ Creates a Job instance and runs the `handle` method
        Args:
            - See class fields
            - If wait_queue_url is not specified will attempt to load a value from the WAIT_QUEUE_URL environment
                variable

        Raises:
            - ValueError: If lambda_name is none or empty
        """
        # Initialize fields
        self.lambda_name = lambda_name

        self.next_lambda_name = next_lambda_name
        self.next_lambda_event = None

        self.wait_queue_url = wait_queue_url
        self.max_iteration_count = max_iteration_count

        if self.wait_queue_url is None:
            self.wait_queue_url = os.environ.get("WAIT_QUEUE_URL", None)

        if self.lambda_name is None or len(self.lambda_name) == 0:
            raise ValueError("lambda_name field was not provided")


    def run(self, event: Dict[str, object], ctx: Dict[str, object]):
        """ Invokes the custom `handle` method and performs an action based on the returned NextAction value
        See the NextAction documentation for more details on what actions will be performed for each value.

        Args:
            - event: AWS event which caused lambda to be run
            - ctx: AWS lambda invocation context

        Raises: Any exception on any failure
        """
        # If invoked by sqs wait queue
        if 'target_lambda' in event:
            target_lambda = event['target_lambda']

            # Check target lambda in event is for this job
            if target_lambda != self.lambda_name:
                # If not targeted, don't execute
                return

            # Check if max_iteration_count has been reached
            if 'iteration_count' not in event:
                raise KeyError("Lambda invoked by sqs queue message but \"iteration_count\" key not provided")

            iteration_count = event['iteration_count']
            if iteration_count >= self.max_iteration_count:
                raise ValueError("Lambda max iteration count reached: {}".format(iteration_count))

        # Invoke handle method
        next_action = self.handle(event, ctx)

        # Handle return value
        if next_action == NextAction.TERMINATE:  # Do nothing after lambda is finished
            return
        elif next_action == NextAction.NEXT:  # Invoke the lambda specified by the `next_lambda_name` class field
            # Check `next_lambda_name` provided
            if self.next_lambda_name is None or len(next_lambda_name) == 0:
                raise ValueError("Job.handle returned NextAction.NEXT but the Job.next_lambda_name field was not set")

            # Invoke
            lambda_client = boto3.client('lambda')

            lambda_client.invoke(FunctionName=self.next_lambda_name,
                                 InvocationType='Event',
                                 Payload=json.dumps(self.next_lambda_event))
        elif next_action == NextAction.REPEAT:  # Invoke this lambda again
            # Check `wait_queue_url` is provided
            if self.wait_queue_url is None or len(self.wait_queue_url) == 0:
                raise ValueError("Job.handle returned NextAction.REPEAT but the Job.wait_queue_url field was not set")

            # Add msg to wait queue to invoke lambda again in the future
            queue_event = {
                'target_lambda': target_lambda,
                'iteration_count': iteration_count
            }
            queue_event_str = json.dumps(queue_event)

            sqs.send_message(
                QueueUrl=wait_queue_url,
                MessageBody=queue_event_str
            )
        else:
            raise ValueError("Unknown Job.handle return value: {}".format(next_action))


    def handle(self, event: Dict[str, object], ctx: Dict[str, object]) -> NextAction:
        """ The code to run when the lambda is invoked.
        Args:
            - event: AWS event which caused lambda to be run
            - ctx: AWS lambda invocation context

        Raises: Any exception on any failure

        Returns: NextAction to determine what should happen after handle finishes
        """
        raise NotImplementedError()

