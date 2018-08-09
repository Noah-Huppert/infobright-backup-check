import os
from typing import Dict

import lib.job
import lib.steps
import lib.salt

import boto3


class WaitTestCompletedJob(lib.job.Job):
    """ Performs the wait test completed step
    """
    def handle(self, event: Dict[str, object], ctx) -> lib.job.NextAction:
        # Get Salt API configuration
        missing_env_vars = []

        salt_api_url = os.environ.get('SALT_API_URL', None)
        if not salt_api_url:
            missing_env_vars.append('SALT_API_URL')

        salt_api_user = os.environ.get('SALT_API_USER', None)
        if not salt_api_user:
            missing_env_vars.append('SALT_API_USER')

        salt_api_password = os.environ.get('SALT_API_PASSWORD', None)
        if not salt_api_password:
            missing_env_vars.append('SALT_API_PASSWORD')

        if len(missing_env_vars) > 0:
            raise KeyError("Missing environment variables: {}".format(missing_env_vars))

        # Get volume id from event
        if 'volume_id' not in event:
            raise KeyError("event must contain \"volume_id\" field")

        volume_id = event['volume_id']

        # Get instance id from event
        if 'dev_ib_backup_instance_id' not in event:
            raise KeyError("event must contain \"dev_ib_backup_instance_id\" field")

        dev_ib_backup_instance_id = event['dev_ib_backup_instance_id']

        # Get mount point from event
        if 'mount_point' not in event:
            raise KeyError("\"mount_point\" expected to be in event")

        mount_point = event['mount_point']

        # Get test cmd salt job id from event
        if 'test_cmd_salt_job_id' not in event:
            raise KeyError("event must contain \"test_cmd_salt_job_id\" field")

        test_cmd_salt_job_id = event['test_cmd_salt_job_id']

        # AWS clients
        ec2 = boto3.client('ec2')

        # Authenticate with Salt API
        salt_api_token = lib.salt.get_auth_token(host=salt_api_url, username=salt_api_user, password=salt_api_password)

        self.logger.debug("Authenticated with Salt API")

        # Get status of test backup Salt job
        test_cmd_salt_job_status = lib.salt.get_job(host=salt_api_url, auth_token=salt_api_token,
                                                    job_id=test_cmd_salt_job_id)
        raise ValueError(test_cmd_salt_job_status)

        # Tear down ib02.dev for snapshot test
        ib_backup_salt_target = "G@ec2:instance_id:{}".format(dev_ib_backup_instance_id)

        lib.salt.exec(host=salt_api_url, auth_token=salt_api_token, minion=ib_backup_salt_target, cmd='state.apply',
                      args=['infobright-backup-check.teardown-ib-restore-test'])
        self.logger.debug("Teared down Infobright development instance for test")

        # Detach volume
        ec2.detach_volume(Device=mount_point, InstanceId=dev_ib_backup_instance_id, VolumeId=volume_id)

        self.logger.debug("Detached volume from dev Infobright instance, volume_id={}, dev_ib_backup_instance_id={}"
                          .format(volume_id, dev_ib_backup_instance_id))

        return lib.job.NextAction.TERMINATE


def main(event, ctx):
    """ Lambda function handler
    Args:
        - event: AWS event which triggered Lambda function
        - ctx: Invocation information

    Raises: Any exception
    """
    step_job = WaitTestCompletedJob(lambda_name=lib.steps.STEP_TEST_BACKUP)
    step_job.run(event, ctx)
