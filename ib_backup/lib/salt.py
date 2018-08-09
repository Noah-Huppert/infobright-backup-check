import urllib.parse
from typing import List

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
    print(resp.content)
    resp_body = resp.json()
    print(resp_body)

    if 'return' not in resp_body or len(resp_body['return']) != 1:
        raise ValueError("Malformed Salt auth API response, expected 'return' key containing an array with 1 entry" +
                         ", was: {}".format(resp_body))

    return resp_body['return'][0]['token']


def exec(host: str, auth_token: str, minion: str, cmd: str, args: List[str] = []):
    """ Executes a Salt command
    Args:
        - host: Salt API host, includes uri scheme
        - auth_token: Salt API auth token
        - minion: Minion target string
        - cmd: Salt command to run
        - args: Salt command positional arguments

    Raises:
        - ValueError: If Salt API response is not valid
    """
    # Make request
    req_headers = {
        'Accept': 'application/x-yaml',
        'x-auth-token': auth_token
    }
    req_data = {
        'client': 'local',
        'tgt': minion,
        'fun': cmd,
        'arg': args
    }

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

    return resp['return']
