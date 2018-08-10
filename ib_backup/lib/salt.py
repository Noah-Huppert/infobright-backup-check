import urllib.parse
from typing import List
import urllib.parse
from typing import Dict, List

import requests
import yaml


def get_auth_token(host: str, username: str, password: str) -> str:
    """ Retrieves a Salt API authentication token.
    Args:
        - host: Salt API host, includes uri scheme
        - username: Salt API username
        - password: Salt API password

    Returns:
        - Authentication token

    Raises:
        - ValueError: If Salt API response is not valid
    """
    # Make auth request
    req_headers = {
        'Accept': 'application/json'
    }
    req_url = urllib.parse.urljoin(host, '/login')
    req_body = {
        'username': username,
        'password': password,
        'eauth': 'pam'
    }

    resp = requests.post(req_url, headers=req_headers, data=req_body)

    # Parse response
    resp_body = resp.json()

    if 'return' not in resp_body or len(resp_body['return']) != 1:
        raise ValueError("Malformed Salt auth API response, expected 'return' key containing an array with 1 entry" +
                         ", was: {}".format(resp_body))

    return resp_body['return'][0]['token']


def exec(host: str, auth_token: str, minion: str, cmd: str, args: List[str] = [], salt_client: str = 'local',
         tgt_type: str = None):
    """ Executes a Salt command
    Args:
        - host: Salt API host, includes uri scheme
        - auth_token: Salt API auth token
        - minion: Minion target string
        - cmd: Salt command to run
        - args: Salt command positional arguments
        - salt_client: Salt runner client to use when executing the provided command. Defaults to 'local' which is the
                       same as running the salt command locally.
                       'local_async' can be used to run a command asynchronously. This client will return the ID of the
                       job which was started. Or 0 if the job failed to start. Provide the returned ID to get_job to
                       retrieve the result.
        - tgt_type: Type of target statement for minion

    Raises:
        - ValueError: If Salt API response is not valid
    """
    # Make request
    req_headers = {
        'Accept': 'application/x-yaml',
        'x-auth-token': auth_token
    }
    req_data = {
        'client': salt_client,
        'tgt': minion,
        'fun': cmd,
        'arg': args
    }

    if tgt_type is not None:
        req_data['tgt_type'] = tgt_type

    resp = requests.post(host, headers=req_headers, json=req_data)

    # Parse response
    resp_body = yaml.load(resp.content)

    if 'return' not in resp_body:
        raise ValueError("Malformed Salt state run API response, expected 'return' key holding an array, was: {}"
                         .format(resp_body))

    return resp_body['return']


def get_job(host: str, auth_token: str, job_id: str) -> Dict[str, object]:
    """ Retrieves the status of a Salt job
    Args:
        - host: Salt API host, includes uri scheme
        - auth_token: Salt API auth token
        - job_id: ID of Salt job to retrieve

    Raises:
        - ValueError: If job_id is 0, this signals that the job failed to start in the first place
        - ValueError: If the Salt API response is invalid

    Returns: Job status
    """
    # Check job_id
    if job_id == 0:
        raise ValueError("job_id == 0 signals that the job never successfully started")

    # Make request
    req_headers = {
        'Accept': 'application/x-yaml',
        'x-auth-token': auth_token
    }
    url = urllib.parse.urljoin(host, "jobs/{}".format(job_id))

    resp = requests.get(url, headers=req_headers)

    # Parse response
    resp_body = yaml.load(resp.content)

    if 'return' not in resp_body:
        raise ValueError("Malformed Salt API response, expected 'return' key")

    if len(resp_body['return']) == 0:
        raise ValueError("Expected at least 1 return result from Salt API, was: {}".format(resp_body))

    return resp_body['return']


def check_job_result(job_results: List[object]):
    """ Checks a Salt job result to ensure it completed successfully
    Args:
        - job_result: Salt API job result. Should be an array of objects.
                          - Each of these objects will have a top level key which is the name of the minion the result
                            is for.
                          - Inside these minion result objects there is a key for each command that was run
                          - Inside each of these command result objects the following keys will exist:
                                - __run_num__: Order command was run in
                                - comment: Note about command execution
                                - result: True if command succeeded, false if failed
                                - changes: Only shows if command got to run, object that contains the following
                                           sub fields:
                                      - pid: Process id
                                      - retcode: Return code, 0 if success
                                      - stderr: Error output
                                      - stdout: Regular output

    Raises:
        - ValueError: If a command failed to run successfully
    """
    # Check that at least 1 minion ran job
    if len(job_results) == 0:
        raise ValueError("No minions ran job, job_results={}".format(job_results))

    # Check each minion exited successfully
    for minion_job_results_top_obj in job_results:
        # Check object contains exactly 1 minion name
        if len(list(minion_job_results_top_obj)) != 1:
            raise ValueError("Minion job result object did not contain exactly 1 top level key representing the " +
                             "minion's name, minion_job_results_top_obj={}, job_results={}"
                             .format(minion_job_results_top_obj, job_results))

        # Get minion key name
        minion_name = list(minion_job_results_top_obj)[0]
        minion_job_results = minion_job_results_top_obj[minion_name]

        # Get names of commands minion ran
        cmd_names = list(minion_job_results)

        # Check at least 1 command ran
        if len(cmd_names) == 0:
            raise ValueError("Minion job results object did not contain at least 1 command status sub object" +
                             ", minion_job_results_top_obj={}, job_results={}"
                             .format(minion_job_results_top_obj, job_results))

        # Check each command minion ran succeeded
        for cmd_name in cmd_names:
            cmd_result = minion_job_results[cmd_name]

            if not cmd_result['result']:
                raise ValueError("Minion \"{}\" failed to run command={}, minion_job_results_top_obj={},"
                                 .format(minion_name, cmd_result, minion_job_results_top_obj) +
                                 "job_results={}".format(job_results))
