import json
from typing import Dict

import boto3

def invoke_lambda(function_name: str, data: Dict[str, object]):
    """ Invokes a Lambda function
    Args:
        - function_name: Name of Lambda function to invoke
        - data: Any to provide to invoked function, must be JSON seralizable
    """
    lambda_client = boto3.client('lambda')

    resp = lambda_client.invoke(FunctionName=function_name, InvocationType='Event', Payload=json.dumps(data))
