import os
import json
from enum import Enum
from typing import Dict
import datetime
import time

import lib.log

import boto3


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


class Job:
    """ Provides common functionality for a lambda which is part of a series of lambdas which complete a process
    A lambda can be used in combination with multiple other lambdas to create a pipeline:

        lambda a --invokes--> lambda b --invokes--> lambda c

    A lambda can also invoke itself in order to loop and wait for a specific condition to be met:

        lambda a --invokes--> lambda a --invokes--> lambda a

    These 2 behaviors can be combined to create more complex behavior.

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
        - max_iteration_count (int): Required if `handle` returns NextAction.REPEAT, maximum number of times a lambda
            can repeat before being considered repeating infinitely, set to -1 for infinite
        - repeat_delay (int): Required if `handle` returns NextAction.REPEAT, Number of seconds a job will wait before
            invoking itself again, default to 15 seconds
        - logger (logging.Logger): Logger for lambda
    """
    def __init__(self, lambda_name: str, next_lambda_name: str = None, wait_queue_url: str = None,
                 max_iteration_count: int = 3, repeat_delay: int = 15):
        """ Creates a Job instance and runs the `handle` method
        Args:
            - See class fields
            - If next_lambda_name is not specified will attempt to load a value from the NEXT_LAMBDA_NAME environment
                variable
            - If wait_queue_url is not specified will attempt to load a value from the WAIT_QUEUE_URL environment
                variable

        Raises:
            - ValueError: If lambda_name is none or empty
        """
        # Initialize fields
        self.lambda_name = lambda_name

        if not self.lambda_name:
            raise ValueError("lambda_name field was not provided")

        self.next_lambda_name = next_lambda_name

        if not self.next_lambda_name:
            self.next_lambda_name = os.environ.get("NEXT_LAMBDA_NAME", None)

        self.next_lambda_event = None

        self.max_iteration_count = max_iteration_count
        self.repeat_delay = repeat_delay

        self.logger = lib.log.get_logger("{}-{}".format(self.lambda_name, datetime.datetime.now()))

    def run(self, event: Dict[str, object], ctx):
        """ Invokes the custom `handle` method and performs an action based on the returned NextAction value
        See the NextAction documentation for more details on what actions will be performed for each value.

        Args:
            - event: AWS event which caused lambda to be run
            - ctx: AWS lambda invocation context

        Raises: Any exception on any failure
        """
        # Get iteration count, or set if it doesn't exist
        iteration_count = 0
        if 'iteration_count' in event:
            iteration_count = event['iteration_count']

        # Check iteration count is not over max
        if self.max_iteration_count != -1 and iteration_count > self.max_iteration_count:
            raise ValueError("Lambda invoked too many times in a row, iteration_count={}, max_iteration_count={}"
                             .format(iteration_count, self.max_iteration_count))

        # Invoke handle method
        self.logger.debug("Invoking handle, event={}".format(event))

        next_action = self.handle(event, ctx)

        # Handle return value
        if next_action == NextAction.TERMINATE:  # Do nothing after lambda is finished
            self.logger.debug("Handle finished, next action=TERMINATE")
            return
        elif next_action == NextAction.NEXT:  # Invoke the lambda specified by the `next_lambda_name` class field
            # Check `next_lambda_name` provided
            if not self.next_lambda_name:
                raise ValueError("Job.handle returned NextAction.NEXT but the Job.next_lambda_name field was not set")

            # Check `next_lambda_event` provided
            if not self.next_lambda_event:
                raise ValueError("Job.handle returned NextAction.NEXT but the job.next_lambda_event field was not set")

            self.logger.debug("Handle finished, next action=NEXT, next_lambda_name={}, next_lambda_event={}"
                              .format(self.next_lambda_name, self.next_lambda_event))

            # Invoke
            self.__invoke_lambda__(self.next_lambda_event, self.next_lambda_name)
        elif next_action == NextAction.REPEAT:  # Invoke this lambda again
            self.logger.debug("Handle finished, next action=REPEAT, event={}".format(event))

            self.logger.debug("Waiting {} seconds, then invoking self again".format(self.repeat_delay))

            time.sleep(self.repeat_delay)

            event['iteration_count'] = iteration_count + 1

            self.logger.debug("Done waiting, invoking self again")
            self.__invoke_lambda__(event, ctx.function_name)
        else:
            raise ValueError("Unknown Job.handle return value: {}".format(next_action))

    def __invoke_lambda__(self, event: Dict[str, object], invoke_lambda_name: str):
        """ Invokes an AWS Lambda function
        Args:
            - event: Event to send to lambda
            - invoke_lambda_name: Name of lambda to invoke
        """
        # Invoke
        lambda_client = boto3.client('lambda')

        invoke_res = lambda_client.invoke(FunctionName=invoke_lambda_name,
                                          InvocationType='Event',
                                          Payload=json.dumps(event))

        self.logger.debug("Invoked lambda, name={}, event={}, result={}".format(invoke_lambda_name, event, invoke_res))

    def handle(self, event: Dict[str, object], ctx) -> NextAction:
        """ The code to run when the lambda is invoked.
        Args:
            - event: AWS event which caused lambda to be run
            - ctx: AWS lambda invocation context

        Raises: Any exception on any failure

        Returns: NextAction to determine what should happen after handle finishes
        """
        raise NotImplementedError()
