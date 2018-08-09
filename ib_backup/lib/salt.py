import urllib.parse
from typing import List
import urllib.parse
from typing import Dict

import requests


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


def exec(host: str, auth_token: str, minion: str, cmd: str, args: List[str] = [], salt_client: str = 'local'):
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

    Raises:
        - ValueError: If Salt API response is not valid
    """
    # Make request
    req_headers = {
        'Accept': 'application/json',
        'x-auth-token': auth_token
    }
    req_data = {
        'client': salt_client,
        'tgt': minion,
        'fun': cmd,
        'arg': args
    }
    url = urllib.parse.urljoin(host, "run")

    resp = requests.post(url, headers=req_headers, json=req_data)

    # Parse response
    resp_body = resp.json()

    if 'return' not in resp_body:
        raise ValueError("Malformed Salt state run API response, expected 'return' key holding an array, was: {}"
                         .format(resp_body))

    print("salt.exec, args={}, resp={}".format(args, resp_body))
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
        'Accept': 'application/json',
        'x-auth-token': auth_token
    }
    url = urllib.parse.urljoin(host, "jobs/{}".format(job_id))

    resp = requests.post(url, headers=req_headers)

    # Parse response
    resp_body = resp.json()

    if 'return' not in resp_body:
        raise ValueError("Malformed Salt API response, expected 'return' key")

    resp_return = resp['return']
    if job_id not in resp_return:
        raise ValueError("Job Id \"{}\" not returned by Salt API".format(job_id))

    return resp_return[job_id]
